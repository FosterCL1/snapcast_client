#!/usr/bin/env python3
"""
GitHub Artifact Manager for snapcast_client

A command-line tool to list and download GitHub Actions artifacts from FosterCL1/snapcast_client.

Usage:
    python gh_artifacts.py list [--token TOKEN] [--count N]
    python gh_artifacts.py download ARTIFACT_ID [--token TOKEN] [--output FILE]

Environment Variables:
    GITHUB_TOKEN: Personal access token with 'actions:read' permission
"""
import argparse
import json
import os
import sys
from typing import Dict, List, Optional
import requests

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


if __name__ == "__main__":
    main()
