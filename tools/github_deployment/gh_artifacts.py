#!/usr/bin/env python3
"""
GitHub Artifact Manager for snapcast_client

A command-line tool to manage GitHub Actions artifacts and deploy to Hawkbit server.

Usage:
    python gh_artifacts.py list [--token TOKEN] [--count N]
    python gh_artifacts.py download ARTIFACT_ID [--token TOKEN] [--output FILE]
    python gh_artifacts.py deploy ARTIFACT_ID [--token TOKEN] [--hawkbit-url URL] [--username USER] [--password PASS]
    python gh_artifacts.py status [--hawkbit-url URL] [--username USER] [--password PASS]

Environment Variables:
    GITHUB_TOKEN: Personal access token with 'actions:read' permission
    HAWKBIT_URL: Default Hawkbit server URL (e.g., http://192.168.2.44:8080)
    HAWKBIT_USERNAME: Default Hawkbit username
    HAWKBIT_PASSWORD: Default Hawkbit password
"""
import argparse
import json
import os
import sys
import time
import zipfile
import tempfile
from typing import Dict, List, Optional, Tuple
import requests
from pathlib import Path

# GitHub repository details
REPO_OWNER = "FosterCL1"
REPO_NAME = "snapcast_client"
GITHUB_API = "https://api.github.com"


def get_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Get headers with optional authentication."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_commit_message(commit_url: str, token: Optional[str] = None) -> str:
    """Get the commit message for a given commit URL."""
    headers = get_headers(token)
    try:
        response = requests.get(commit_url, headers=headers)
        response.raise_for_status()
        commit_data = response.json()
        return commit_data.get("commit", {}).get("message", "No commit message").split('\n')[0][:80]
    except Exception as e:
        print(f"  Warning: Could not get commit message: {e}", file=sys.stderr)
        return ""

def get_pr_info(pr_url: str, token: Optional[str] = None) -> str:
    """Get PR title for a given PR URL."""
    if not pr_url:
        return ""
    
    headers = get_headers(token)
    try:
        response = requests.get(pr_url, headers=headers)
        response.raise_for_status()
        pr_data = response.json()
        return f"PR #{pr_url.split('/')[-1]}: {pr_data.get('title', '')}"
    except Exception as e:
        print(f"  Warning: Could not get PR info: {e}", file=sys.stderr)
        return ""

def format_relative_time(timestamp_str: str) -> str:
    """Convert ISO timestamp to relative time (e.g., '2 hours ago')."""
    from datetime import datetime, timezone
    try:
        created = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - created
        
        seconds = delta.total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"
    except Exception:
        return "unknown"

def list_artifacts(token: Optional[str] = None, count: int = 5) -> List[Dict]:
    """List recent workflow artifacts with detailed information."""
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts"
    headers = get_headers(token)
    
    try:
        # First get the artifacts with workflow run information
        response = requests.get(
            url, 
            headers=headers, 
            params={
                "per_page": count,
                "sort": "created_at",
                "direction": "desc"
            }
        )
        response.raise_for_status()
        artifacts = response.json().get("artifacts", [])
        
        if not artifacts:
            print("No artifacts found.")
            return []
            
        print(f"\nLast {len(artifacts)} artifacts for {REPO_OWNER}/{REPO_NAME}:\n")
        
        # Print header
        print(f"{'ID':<12} {'Branch':<20} {'Commit':<10} {'Age':<12} {'Message'}")
        print("-" * 100)
        
        # Get details for each artifact
        for artifact in artifacts:
            workflow_run = artifact.get("workflow_run", {})
            
            # Get commit details
            head_branch = workflow_run.get("head_branch", "unknown")
            head_sha = workflow_run.get("head_sha", "")[:8]  # Short SHA
            
            # Get commit message (first line only, truncated)
            commit_url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/commits/{head_sha}" if head_sha else ""
            commit_msg = ""
            if commit_url:
                try:
                    commit_response = requests.get(
                        commit_url,
                        headers=get_headers(token)
                    )
                    if commit_response.status_code == 200:
                        commit_data = commit_response.json()
                        commit_msg = commit_data.get("commit", {}).get("message", "").split('\n')[0][:50]
                except Exception as e:
                    commit_msg = "[Error fetching commit]"
            
            # Format relative time
            created_raw = artifact.get("created_at", "")
            relative_time = format_relative_time(created_raw) if created_raw else "unknown"
            
            # Print the main line
            print(f"{artifact['id']:<12} "
                  f"{head_branch[:18]:<20} "
                  f"{head_sha:<10} "
                  f"{relative_time:<12} "
                  f"{commit_msg}")
            
            # Print any PR info if available
            prs = workflow_run.get("pull_requests", [])
            if prs:
                pr = prs[0]
                pr_number = pr.get("number")
                if pr_number:
                    pr_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/pull/{pr_number}"
                    print(f"{'':<12} {'PR #' + str(pr_number):<20} {'':<10} {'':<12} {pr_url}")
            
        return artifacts
    except requests.exceptions.RequestException as e:
        print(f"Error fetching artifacts: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        return []


def download_artifact(artifact_id: int, token: Optional[str] = None, output_path: Optional[str] = None) -> bool:
    """Download a specific artifact."""
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts/{artifact_id}/zip"
    headers = get_headers(token)
    
    if not output_path:
        output_path = f"snapcast_artifact_{artifact_id}.zip"
    
    try:
        with requests.get(url, headers=headers, stream=True) as response:
            response.raise_for_status()
            
            # Create parent directories if they don't exist
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Save the file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Downloaded artifact {artifact_id} to {output_path}")
            return True
            
    except requests.exceptions.RequestException as e:
        print(f"Error downloading artifact: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        return False


def extract_zip(zip_path: str, extract_to: str = None) -> str:
    """Extract a zip file and return the directory path."""
    if not extract_to:
        extract_to = tempfile.mkdtemp(prefix="artifact_")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
    return extract_to


def find_raucb_file(directory: str) -> str:
    """Find the rootfs.raucb file in the directory."""
    for root, _, files in os.walk(directory):
        if 'rootfs.raucb' in files:
            return os.path.join(root, 'rootfs.raucb')
    raise FileNotFoundError("rootfs.raucb not found in the artifact")


def get_all_targets(base_url: str, username: str, password: str, verbose: bool = False) -> List[Dict]:
    """Get all targets from Hawkbit server."""
    targets_url = f"{base_url}/rest/v1/targets"
    try:
        response = requests.get(
            targets_url,
            auth=(username, password),
            headers={"Accept": "application/json"},
            params={"limit": 1000}  # Adjust limit as needed
        )
        response.raise_for_status()
        return response.json().get("content", [])
    except requests.exceptions.RequestException as e:
        print(f"Error getting targets: {e}", file=sys.stderr)
        return []


def get_target_status(base_url: str, target_id: str, username: str, password: str, verbose: bool = False) -> Dict:
    """Get detailed status for a specific target including current and requested versions."""
    target_url = f"{base_url}/rest/v1/targets/{target_id}"
    try:
        response = requests.get(
            target_url,
            auth=(username, password),
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        target_data = response.json()
        
        # Debug: Print raw response if verbose
        if verbose:
            print(f"\nDebug - Raw API response for {target_id}:")
            print(json.dumps(target_data, indent=2))
        
        # Extract version information
        status = {
            "controllerId": target_data.get("controllerId", "unknown"),
            "name": target_data.get("name", "N/A"),
            "description": target_data.get("description", "N/A"),
            "updateStatus": target_data.get("updateStatus", "unknown"),
            "installedVersion": "N/A",
            "assignedVersion": "N/A",
            "installedDistribution": "N/A",
            "assignedDistribution": "N/A"
        }
        
        # Get installed (current) distribution by following the installedDS link
        links = target_data.get("_links", {})
        installed_ds_link = links.get("installedDS", {}).get("href")
        if installed_ds_link:
            try:
                installed_response = requests.get(
                    installed_ds_link,
                    auth=(username, password),
                    headers={"Accept": "application/json"}
                )
                if installed_response.status_code == 200:
                    installed_ds = installed_response.json()
                    if verbose:
                        print(f"\nDebug - Installed DS response:")
                        print(json.dumps(installed_ds, indent=2))
                    status["installedDistribution"] = installed_ds.get("name", "N/A")
                    status["installedVersion"] = installed_ds.get("version", "N/A")
            except requests.exceptions.RequestException as e:
                if verbose:
                    print(f"Warning: Could not get installed DS: {e}")
        
        # Get assigned (requested) distribution by following the assignedDS link
        assigned_ds_link = links.get("assignedDS", {}).get("href")
        if assigned_ds_link:
            try:
                assigned_response = requests.get(
                    assigned_ds_link,
                    auth=(username, password),
                    headers={"Accept": "application/json"}
                )
                if assigned_response.status_code == 200:
                    assigned_ds = assigned_response.json()
                    if verbose:
                        print(f"\nDebug - Assigned DS response:")
                        print(json.dumps(assigned_ds, indent=2))
                    status["assignedDistribution"] = assigned_ds.get("name", "N/A")
                    status["assignedVersion"] = assigned_ds.get("version", "N/A")
            except requests.exceptions.RequestException as e:
                if verbose:
                    print(f"Warning: Could not get assigned DS: {e}")
        
        return status
        
    except requests.exceptions.RequestException as e:
        print(f"Error getting status for target {target_id}: {e}", file=sys.stderr)
        return {
            "controllerId": target_id,
            "name": "Error",
            "description": str(e),
            "updateStatus": "error",
            "installedVersion": "N/A",
            "assignedVersion": "N/A",
            "installedDistribution": "N/A",
            "assignedDistribution": "N/A"
        }


def show_all_targets_status(base_url: str, username: str, password: str, verbose: bool = False) -> bool:
    """Display status of all Hawkbit targets including current and requested versions."""
    targets = get_all_targets(base_url, username, password, verbose=verbose)
    
    if not targets:
        print("No targets found or error occurred.", file=sys.stderr)
        return False
    
    print(f"\nFound {len(targets)} target(s):\n")
    
    # Print header
    print(f"{'Target ID':<25} {'Status':<15} {'Current Ver':<15} {'Requested Ver':<15} {'Distribution'}")
    print("-" * 110)
    
    # Get detailed status for each target
    for target in targets:
        target_id = target["controllerId"]
        status = get_target_status(base_url, target_id, username, password, verbose=verbose)
        
        # Determine if versions match
        version_match = ""
        if status["installedVersion"] != "N/A" and status["assignedVersion"] != "N/A":
            if status["installedVersion"] == status["assignedVersion"]:
                version_match = "✓"
            else:
                version_match = "↑"  # Update pending
        
        # Format the output
        update_status = status["updateStatus"]
        current_ver = status["installedVersion"]
        requested_ver = status["assignedVersion"]
        dist_name = status["installedDistribution"]
        
        # Truncate distribution name if too long
        if len(dist_name) > 30:
            dist_name = dist_name[:27] + "..."
        
        print(f"{target_id:<25} {update_status:<15} {current_ver:<15} {requested_ver:<15} {dist_name}")
        
        # Show additional details if verbose
        if verbose:
            print(f"  Name: {status['name']}")
            print(f"  Description: {status['description']}")
            if status["assignedDistribution"] != "N/A" and status["assignedDistribution"] != status["installedDistribution"]:
                print(f"  Assigned Distribution: {status['assignedDistribution']}")
    
    print()
    return True


def assign_distribution_to_targets(base_url: str, dist_id: int, username: str, password: str, verbose: bool = False) -> bool:
    """Assign a distribution set to all targets."""
    targets = get_all_targets(base_url, username, password, verbose=verbose)
    if not targets:
        print("No targets found to assign distribution to", file=sys.stderr)
        return False
    
    success_count = 0
    
    for target in targets:
        target_id = target["controllerId"]
        assign_url = f"{base_url}/rest/v1/targets/{target_id}/assignedDS"
        
        assign_data = {
            "id": dist_id
        }
        
        try:
            vprint(verbose, f"Assigning distribution {dist_id} to target {target_id}")
            response = requests.post(
                assign_url,
                auth=(username, password),
                json=assign_data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/hal+json"
                }
            )
            
            if response.status_code in (200, 201):
                success_count += 1
            else:
                print(f"Failed to assign to {target_id}: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error assigning to {target_id}: {e}")
    
    if success_count == 0:
        print("Failed to assign distribution to any targets", file=sys.stderr)
        return False
        
    if verbose or success_count == 0:
        print(f"Successfully assigned distribution to {success_count} out of {len(targets)} targets")
    return True


def find_existing_distribution(base_url: str, name: str, username: str, password: str, verbose: bool = False) -> tuple[Optional[int], str]:
    """
    Find an existing distribution by name and return its ID and the next available version number.
    Handles version conflicts by finding the next available version number.
    """
    try:
        # First, get all distributions with the same name
        all_ds = []
        page = 0
        page_size = 50
        
        while True:
            # First, get the list of distribution sets with the given name
            list_url = f"{base_url}/rest/v1/distributionsets"
            list_params = {
                "limit": page_size,
                "offset": page * page_size,
                "q": f"name=={name}"
            }
            
            list_response = requests.get(
                list_url,
                auth=(username, password),
                params=list_params,
                headers={"Accept": "application/json"}
            )
            list_response.raise_for_status()
            
            content = list_response.json()
            if not content.get("content"):
                break
                
            all_ds.extend(content["content"])
            
            # Check if there are more pages
            if (page + 1) * page_size >= content.get("totalElements", 0):
                break
            page += 1
        
        if not all_ds:
            return None, "1.0"
        
        # Extract and parse versions
        versions = []
        latest_ds = None
        latest_version = 0.0
        
        for ds in all_ds:
            try:
                version_str = ds.get("version", "0.0")
                # Handle both string and numeric versions
                version = float(version_str) if str(version_str).replace('.', '').isdigit() else 0.0
                versions.append(version)
                
                # Track the distribution with the highest version
                if version > latest_version:
                    latest_version = version
                    latest_ds = ds
            except (ValueError, AttributeError):
                continue
        
        if not versions:  # No valid versions found
            return None, "1.0"
        
        # Find the next available version
        versions_sorted = sorted(versions, reverse=True)
        next_version = versions_sorted[0] + 1.0
        
        # Check if the next version already exists (just in case)
        while next_version in versions:
            next_version += 1.0
        
        # Return the latest distribution ID (if any) and the next version
        return (latest_ds["id"], f"{next_version:.1f}") if latest_ds else (None, f"{next_version:.1f}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error searching for distributions: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            print(f"Response body: {e.response.text}", file=sys.stderr)
        return None, "1.0"
    except Exception as e:
        print(f"Unexpected error finding distributions: {e}", file=sys.stderr)
        return None, "1.0"


def create_or_update_distribution(base_url: str, name: str, module_id: int, username: str, password: str, assign_to_all: bool = True, verbose: bool = False) -> bool:
    """Create or update a distribution set in Hawkbit and assign the software module to it."""
    dist_url = f"{base_url}/rest/v1/distributionsets"
    
    # First try to find an existing distribution with the same name and get next version
    existing_dist_id, next_version = find_existing_distribution(base_url, name, username, password, verbose=verbose)
    
    if existing_dist_id:
        vprint(verbose, f"Found existing distribution with ID: {existing_dist_id}, checking modules...")
        
        # Get existing modules
        try:
            response = requests.get(
                f"{dist_url}/{existing_dist_id}/assignedModules",
                auth=(username, password),
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                # If the module is already assigned, we're done
                modules = response.json()
                if any(module.get("id") == module_id for module in modules):
                    vprint(verbose, f"Module {module_id} is already assigned to distribution {existing_dist_id}")
                    
                    # Assign to all targets if requested
                    if assign_to_all and not assign_distribution_to_targets(base_url, existing_dist_id, username, password, verbose=verbose):
                        print("Warning: Failed to assign distribution to all targets", file=sys.stderr)
                        return False
                    return True
            
            # If we get here, we need to create a new version with the updated module
            vprint(verbose, f"Creating new version {next_version} of distribution {name}")
            
        except requests.exceptions.RequestException as e:
            print(f"Error checking existing distribution modules: {e}", file=sys.stderr)
            # Continue with creating a new version
    
    # Create a new distribution with the next version number
    dist_data = [{
        "name": name,
        "version": next_version,
        "description": f"Snapcast Client Deployment - {name} (v{next_version})",
        "type": "os",
        "modules": [{"id": module_id}],
        "requiredMigrationStep": False
    }]
    
    try:
        vprint(verbose, f"Creating distribution set with data: {json.dumps(dist_data, indent=2)}")
        
        response = requests.post(
            dist_url,
            auth=(username, password),
            json=dist_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        # If we get a conflict, try with the next version number
        if response.status_code == 409:
            # Extract current version and increment
            current_version = float(dist_data[0]["version"])
            next_version = f"{current_version + 1:.1f}"
            dist_data[0]["version"] = next_version
            dist_data[0]["description"] = f"Snapcast Client Deployment - {name} (v{next_version})"
            vprint(verbose, f"Distribution conflict, retrying with version: {next_version}")
            
            response = requests.post(
                dist_url,
                auth=(username, password),
                json=dist_data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        
        vprint(verbose, f"Distribution creation response: {response.status_code}")
        vprint(verbose, f"Response body: {response.text}")
        
        response.raise_for_status()
        
        created_dists = response.json()
        if not isinstance(created_dists, list) or not created_dists:
            print("Error: Unexpected response format for distribution creation", file=sys.stderr)
            return False
            
        dist_id = created_dists[0].get("id")
        if not dist_id:
            print("Error: Could not get distribution ID from response", file=sys.stderr)
            return False
            
        vprint(verbose, f"Created distribution set with ID: {dist_id}")
        
        # Assign to all targets if requested
        if assign_to_all:
            if not assign_distribution_to_targets(base_url, dist_id, username, password, verbose=verbose):
                print("Warning: Failed to assign distribution to all targets", file=sys.stderr)
                return False
                
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating distribution: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            print(f"Response body: {e.response.text}", file=sys.stderr)
        return False


def upload_to_hawkbit(raucb_path: str, base_url: str, username: str, password: str, distribution_name: str, assign_to_all: bool = True, verbose: bool = False) -> bool:
    """Upload a file to Hawkbit server and create a distribution set."""
    # First, create a software module
    module_url = f"{base_url}/rest/v1/softwaremodules"
    
    # Create a unique name based on the current timestamp
    import time
    timestamp = int(time.time())
    module_name = f"snapcast_{timestamp}"
    
    # Set verbose flag for nested function calls
    global vprint_verbose
    vprint_verbose = verbose
    
    module_data = [{
        "name": module_name,
        "version": "1.0",
        "type": "os",
        "vendor": "snapcast"
    }]
    
    try:
        # Debug: Print the request we're about to make
        vprint(verbose, f"Creating software module with data: {json.dumps(module_data, indent=2)}")
        
        # Create software module
        response = requests.post(
            module_url,
            auth=(username, password),
            json=module_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        vprint(verbose, f"Response status: {response.status_code}")
        vprint(verbose, f"Response body: {response.text}")
        
        response.raise_for_status()
        
        # The response should be an array of created modules
        created_modules = response.json()
        if not isinstance(created_modules, list) or not created_modules:
            print("Error: Unexpected response format from server", file=sys.stderr)
            return False
            
        module_id = created_modules[0].get("id")
        if not module_id:
            print("Error: Could not get module ID from response", file=sys.stderr)
            return False
            
        vprint(verbose, f"Created software module with ID: {module_id}")
        
        # Upload artifact
        upload_url = f"{base_url}/rest/v1/softwaremodules/{module_id}/artifacts"
        vprint(verbose, f"Uploading {raucb_path} to {upload_url}")
        
        with open(raucb_path, 'rb') as f:
            files = {
                'file': (os.path.basename(raucb_path), f, 'application/octet-stream')
            }
            upload_response = requests.post(
                upload_url,
                auth=(username, password),
                files=files,
                headers={"Accept": "application/json"}
            )
            
            vprint(verbose, f"Upload response status: {upload_response.status_code}")
            vprint(verbose, f"Upload response body: {upload_response.text}")
            
            upload_response.raise_for_status()
        
        print(f"Successfully uploaded {raucb_path} to Hawkbit server")
        
        # Create or update a distribution set with the uploaded module and assign to all targets
        if not create_or_update_distribution(base_url, distribution_name, module_id, username, password, assign_to_all):
            print("Warning: Failed to create/update or assign distribution set, but software module was uploaded", file=sys.stderr)
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error in upload_to_hawkbit: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            print(f"Response headers: {e.response.headers}", file=sys.stderr)
            print(f"Response body: {e.response.text}", file=sys.stderr)
        return False


def vprint(verbose, *args, **kwargs):
    """Print only if verbose is True"""
    if verbose:
        print(*args, **kwargs)


def main():
    # Main parser with global arguments
    parser = argparse.ArgumentParser(description="Manage GitHub Actions artifacts for snapcast_client")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List recent artifacts")
    list_parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                           help="GitHub token (default: $GITHUB_TOKEN)")
    list_parser.add_argument("--count", type=int, default=5,
                           help="Number of artifacts to show (default: 5)")
    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download an artifact")
    download_parser.add_argument("artifact_id", type=int, help="ID of the artifact to download")
    download_parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                               help="GitHub token (default: $GITHUB_TOKEN)")
    download_parser.add_argument("--output", "-o", help="Output file path")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy an artifact to Hawkbit")
    deploy_parser.add_argument("artifact_id", type=int, help="ID of the artifact to deploy")
    deploy_parser.add_argument("distribution_name", nargs='?', default="test", 
                             help="Name for the Hawkbit distribution set (default: test)")
    deploy_parser.add_argument("--no-assign", action="store_false", dest="assign_to_all",
                             help="Don't assign the distribution to all targets automatically")
    deploy_parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"),
                             help="GitHub token (default: $GITHUB_TOKEN)")
    deploy_parser.add_argument("--hawkbit-url", default=os.getenv("HAWKBIT_URL", "http://192.168.2.44:8080"),
                             help="Hawkbit server URL (default: $HAWKBIT_URL or http://192.168.2.44:8080)")
    deploy_parser.add_argument("--username", default=os.getenv("HAWKBIT_USERNAME", "admin"),
                             help="Hawkbit username (default: $HAWKBIT_USERNAME or admin)")
    deploy_parser.add_argument("--password", default=os.getenv("HAWKBIT_PASSWORD", "admin"),
                             help="Hawkbit password (default: $HAWKBIT_PASSWORD or admin)")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show status of all Hawkbit targets")
    status_parser.add_argument("--hawkbit-url", default=os.getenv("HAWKBIT_URL", "http://192.168.2.44:8080"),
                             help="Hawkbit server URL (default: $HAWKBIT_URL or http://192.168.2.44:8080)")
    status_parser.add_argument("--username", default=os.getenv("HAWKBIT_USERNAME", "admin"),
                             help="Hawkbit username (default: $HAWKBIT_USERNAME or admin)")
    status_parser.add_argument("--password", default=os.getenv("HAWKBIT_PASSWORD", "admin"),
                             help="Hawkbit password (default: $HAWKBIT_PASSWORD or admin)")
    
    args = parser.parse_args()
    
    if args.command == "list":
        if not list_artifacts(token=args.token, count=args.count):
            print("No artifacts found or error occurred.")
            return
            
    elif args.command == "download":
        if not args.token:
            print("Error: GitHub token is required. Set GITHUB_TOKEN environment variable or use --token", file=sys.stderr)
            sys.exit(1)
            
        success = download_artifact(
            artifact_id=args.artifact_id,
            token=args.token,
            output_path=args.output
        )
        
        if not success:
            sys.exit(1)
    
    elif args.command == "deploy":
        if not args.token:
            print("Error: GitHub token is required. Set GITHUB_TOKEN environment variable or use --token", file=sys.stderr)
            sys.exit(1)
        
        # Create a temporary directory for the artifact
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download the artifact
            artifact_zip = os.path.join(temp_dir, f"artifact_{args.artifact_id}.zip")
            if not download_artifact(
                artifact_id=args.artifact_id,
                token=args.token,
                output_path=artifact_zip
            ):
                sys.exit(1)
            
            # Extract the artifact
            try:
                extract_dir = extract_zip(artifact_zip)
                raucb_file = find_raucb_file(extract_dir)
                vprint(args.verbose, f"Found RAUC bundle: {raucb_file}")
                
                # Upload to Hawkbit and create distribution
                if not upload_to_hawkbit(
                    raucb_path=raucb_file,
                    base_url=args.hawkbit_url.rstrip('/'),
                    username=args.username,
                    password=args.password,
                    distribution_name=args.distribution_name,
                    assign_to_all=args.assign_to_all,
                    verbose=args.verbose
                ):
                    sys.exit(1)
                    
            except Exception as e:
                print(f"Error during deployment: {e}", file=sys.stderr)
                sys.exit(1)
    
    elif args.command == "status":
        if not show_all_targets_status(
            base_url=args.hawkbit_url.rstrip('/'),
            username=args.username,
            password=args.password,
            verbose=args.verbose
        ):
            sys.exit(1)


if __name__ == "__main__":
    main()
