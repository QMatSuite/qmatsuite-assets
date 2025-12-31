#!/usr/bin/env python3
"""
Check PseudoDojo GitHub repository to find JSON metadata files and map them to archives.
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path

def list_github_folder(owner, repo, path):
    """List contents of a GitHub folder using the API."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    
    try:
        with urllib.request.urlopen(api_url, timeout=10) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
            else:
                print(f"API request failed: {response.status}")
                return None
    except Exception as e:
        print(f"Error accessing GitHub API: {e}")
        return None

def main():
    owner = "abinit"
    repo = "pseudo_dojo"
    folder_path = "website"
    
    print("=" * 80)
    print("PseudoDojo Website Folder Contents")
    print("=" * 80)
    print(f"\nQuerying: https://github.com/{owner}/{repo}/tree/master/{folder_path}\n")
    
    contents = list_github_folder(owner, repo, folder_path)
    
    if not contents:
        print("Could not retrieve folder contents.")
        return
    
    # Filter for JSON files
    json_files = [item for item in contents if item.get("type") == "file" and item.get("name", "").endswith(".json")]
    other_files = [item for item in contents if item.get("type") == "file" and not item.get("name", "").endswith(".json")]
    subdirs = [item for item in contents if item.get("type") == "dir"]
    
    print(f"Found {len(json_files)} JSON files:")
    print("-" * 80)
    for item in sorted(json_files, key=lambda x: x.get("name", "")):
        name = item.get("name", "")
        size = item.get("size", 0)
        print(f"  {name:50s} ({size:,} bytes)")
    
    if subdirs:
        print(f"\nFound {len(subdirs)} subdirectories:")
        for item in sorted(subdirs, key=lambda x: x.get("name", "")):
            print(f"  {item.get('name')}/")
    
    # Try to download and examine JSON files to understand structure
    print("\n" + "=" * 80)
    print("Examining JSON file contents:")
    print("=" * 80)
    
    for item in json_files[:5]:  # Limit to first 5
        name = item.get("name")
        download_url = item.get("download_url")
        
        if download_url:
            try:
                with urllib.request.urlopen(download_url, timeout=10) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        print(f"\n{name}:")
                        print(f"  Keys: {list(data.keys())[:10]}")
                        if isinstance(data, dict) and len(data) > 0:
                            # Show first entry structure
                            first_key = list(data.keys())[0]
                            first_val = data[first_key]
                            if isinstance(first_val, dict):
                                print(f"  Sample entry keys: {list(first_val.keys())[:10]}")
            except Exception as e:
                print(f"  Error reading {name}: {e}")
    
    # Map to local archives
    print("\n" + "=" * 80)
    print("Mapping to local PseudoDojo archives:")
    print("=" * 80)
    
    repo_root = Path(__file__).parent.parent
    pseudo_seed = repo_root / "pseudo_seed"
    
    local_archives = []
    for item in pseudo_seed.iterdir():
        if item.is_file() and (item.name.startswith("nc-") or item.name.startswith("paw-")):
            local_archives.append(item.name)
    
    print(f"\nLocal PseudoDojo archives ({len(local_archives)}):")
    for arch in sorted(local_archives):
        print(f"  {arch}")
    
    # Try to infer mapping
    print("\n" + "=" * 80)
    print("Inferred JSON-to-Archive Mapping:")
    print("=" * 80)
    
    for json_file in json_files:
        json_name = json_file.get("name", "")
        # Try to match based on naming patterns
        # e.g., nc-sr-04_pbe_standard.json -> nc-sr-04_pbe_standard_upf.tgz
        base_name = json_name.replace(".json", "")
        
        # Find matching archives
        matches = [arch for arch in local_archives if base_name in arch or arch.replace("_upf.tgz", "").replace("_upf.tar", "") == base_name]
        
        if matches:
            print(f"\n{json_name}:")
            for match in matches:
                print(f"  -> {match}")
        else:
            print(f"\n{json_name}: (no clear match found)")

if __name__ == "__main__":
    main()

