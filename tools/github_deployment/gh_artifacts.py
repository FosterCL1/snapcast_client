#!/usr/bin/env python3
"""
GitHub Artifact Manager for snapcast_client

A command-line tool to manage GitHub Actions artifacts and deploy to Hawkbit server.

Usage:
    python gh_artifacts.py list [--token TOKEN] [--count N]
    python gh_artifacts.py download ARTIFACT_ID [--token TOKEN] [--output FILE]
    python gh_artifacts.py deploy ARTIFACT_ID [--token TOKEN] [--hawkbit-url URL] [--username USER] [--password PASS]

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


def list_artifacts(token: Optional[str] = None, count: int = 5) -> List[Dict]:
    """List recent workflow artifacts."""
    url = f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts"
    headers = get_headers(token)
    
    try:
        response = requests.get(url, headers=headers, params={"per_page": count})
        response.raise_for_status()
        data = response.json()
        return data.get("artifacts", [])
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


def get_all_targets(base_url: str, username: str, password: str) -> List[Dict]:
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


def assign_distribution_to_targets(base_url: str, dist_id: int, username: str, password: str) -> bool:
    """Assign a distribution set to all targets."""
    targets = get_all_targets(base_url, username, password)
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
            print(f"Assigning distribution {dist_id} to target {target_id}")
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
        
    print(f"Successfully assigned distribution to {success_count} out of {len(targets)} targets")
    return True


def create_distribution(base_url: str, name: str, module_id: int, username: str, password: str, assign_to_all: bool = True) -> bool:
    """Create a distribution set in Hawkbit and assign the software module to it."""
    dist_url = f"{base_url}/rest/v1/distributionsets"
    
    dist_data = [{
        "name": name,
        "version": "1.0",
        "description": f"Snapcast Client Deployment - {name}",
        "type": "os",
        "modules": [{"id": module_id}],
        "requiredMigrationStep": False
    }]
    
    try:
        print(f"Creating distribution set with data: {json.dumps(dist_data, indent=2)}")
        
        response = requests.post(
            dist_url,
            auth=(username, password),
            json=dist_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        print(f"Distribution creation response: {response.status_code}")
        print(f"Response body: {response.text}")
        
        response.raise_for_status()
        
        created_dists = response.json()
        if not isinstance(created_dists, list) or not created_dists:
            print("Error: Unexpected response format for distribution creation", file=sys.stderr)
            return False
            
        dist_id = created_dists[0].get("id")
        if not dist_id:
            print("Error: Could not get distribution ID from response", file=sys.stderr)
            return False
            
        print(f"Created distribution set with ID: {dist_id}")
        
        # Assign to all targets if requested
        if assign_to_all:
            if not assign_distribution_to_targets(base_url, dist_id, username, password):
                print("Warning: Failed to assign distribution to all targets", file=sys.stderr)
                return False
                
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating distribution: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            print(f"Response body: {e.response.text}", file=sys.stderr)
        return False


def upload_to_hawkbit(raucb_path: str, base_url: str, username: str, password: str, distribution_name: str, assign_to_all: bool = True) -> bool:
    """Upload a file to Hawkbit server and create a distribution set."""
    # First, create a software module
    module_url = f"{base_url}/rest/v1/softwaremodules"
    
    # Create a unique name based on the current timestamp
    import time
    timestamp = int(time.time())
    module_name = f"snapcast_{timestamp}"
    
    module_data = [{
        "name": module_name,
        "version": "1.0",
        "type": "os",
        "vendor": "snapcast"
    }]
    
    try:
        # Debug: Print the request we're about to make
        print(f"Creating software module with data: {json.dumps(module_data, indent=2)}")
        
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
        
        # Debug: Print the raw response
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
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
            
        print(f"Created software module with ID: {module_id}")
        
        # Upload artifact
        upload_url = f"{base_url}/rest/v1/softwaremodules/{module_id}/artifacts"
        print(f"Uploading {raucb_path} to {upload_url}")
        
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
            
            # Debug: Print upload response
            print(f"Upload response status: {upload_response.status_code}")
            print(f"Upload response body: {upload_response.text}")
            
            upload_response.raise_for_status()
        
        print(f"Successfully uploaded {raucb_path} to Hawkbit server")
        
        # Create a distribution set with the uploaded module and assign to all targets
        if not create_distribution(base_url, distribution_name, module_id, username, password, assign_to_all):
            print("Warning: Failed to create or assign distribution set, but software module was uploaded", file=sys.stderr)
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error in upload_to_hawkbit: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            print(f"Response headers: {e.response.headers}", file=sys.stderr)
            print(f"Response body: {e.response.text}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Manage GitHub Actions artifacts for snapcast_client")
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
    
    args = parser.parse_args()
    
    if args.command == "list":
        artifacts = list_artifacts(token=args.token, count=args.count)
        if not artifacts:
            print("No artifacts found or error occurred.")
            return
            
        print(f"\nLast {len(artifacts)} artifacts for {REPO_OWNER}/{REPO_NAME}:\n")
        print(f"{'ID':<10} {'Name':<30} {'Workflow':<30} {'Created At'}")
        print("-" * 80)
        
        for art in artifacts:
            workflow = art["workflow_run"]["head_sha"][:7] if art.get("workflow_run") else "N/A"
            print(f"{art['id']:<10} {art['name'][:28]:<30} {workflow:<30} {art['created_at'].split('T')[0]}")
    
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
                print(f"Found RAUC bundle: {raucb_file}")
                
                # Upload to Hawkbit and create distribution
                if not upload_to_hawkbit(
                    raucb_path=raucb_file,
                    base_url=args.hawkbit_url.rstrip('/'),
                    username=args.username,
                    password=args.password,
                    distribution_name=args.distribution_name,
                    assign_to_all=args.assign_to_all
                ):
                    sys.exit(1)
                    
            except Exception as e:
                print(f"Error during deployment: {e}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
