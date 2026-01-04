#!/usr/bin/env python3
"""
Sort PSL (PseudoDojo Standard Library) UPF files by version.

Extracts version numbers from filenames (pattern: psl.X.Y.Z.UPF) and organizes
files into version-specific folders (e.g., v1.0.0/, v0.1/, etc.).
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict


def extract_psl_version(filename):
    """
    Extract PSL version from filename.
    
    Pattern: psl.X.Y.Z.UPF or psl.X.Y.UPF
    Returns: version string (e.g., "1.0.0", "0.1", "0.2.1") or None
    """
    # Match pattern: psl.X.Y.Z.UPF or psl.X.Y.UPF
    # The version can be anywhere in the filename
    match = re.search(r'psl\.(\d+\.\d+(?:\.\d+)?)\.UPF', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def normalize_version(version_str):
    """
    Normalize version string for folder naming.
    
    Converts "1.0.0" -> "v1.0.0", "0.1" -> "v0.1"
    """
    return f"v{version_str}"


def sort_files_by_version(source_dir, dry_run=False):
    """
    Sort UPF files by PSL version into version-specific folders.
    
    Args:
        source_dir: Path to directory containing UPF files
        dry_run: If True, only print what would be done
    
    Returns:
        dict with statistics
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"ERROR: Source directory does not exist: {source_dir}")
        return None
    
    # Find all UPF files
    upf_files = list(source_path.glob("*.UPF"))
    if not upf_files:
        print(f"WARNING: No UPF files found in {source_dir}")
        return None
    
    print(f"Found {len(upf_files)} UPF files")
    
    # Group files by version
    version_groups = defaultdict(list)
    unversioned = []
    
    for filepath in upf_files:
        version = extract_psl_version(filepath.name)
        if version:
            version_groups[version].append(filepath)
        else:
            unversioned.append(filepath)
    
    print(f"\nVersion distribution:")
    for version in sorted(version_groups.keys()):
        print(f"  {version}: {len(version_groups[version])} files")
    
    if unversioned:
        print(f"  (unversioned): {len(unversioned)} files")
    
    if dry_run:
        print("\nDRY RUN: Would organize files as follows:")
        for version in sorted(version_groups.keys()):
            folder_name = normalize_version(version)
            print(f"  {folder_name}/: {len(version_groups[version])} files")
        if unversioned:
            print(f"  unversioned/: {len(unversioned)} files")
        return {
            'total_files': len(upf_files),
            'versioned': len(upf_files) - len(unversioned),
            'unversioned': len(unversioned),
            'versions': sorted(version_groups.keys())
        }
    
    # Create version folders and move files
    moved_count = 0
    skipped_count = 0
    
    for version in sorted(version_groups.keys()):
        folder_name = normalize_version(version)
        version_dir = source_path / folder_name
        version_dir.mkdir(exist_ok=True)
        
        for filepath in version_groups[version]:
            dest_path = version_dir / filepath.name
            
            if dest_path.exists():
                # Check if it's the same file (same size)
                if filepath.stat().st_size == dest_path.stat().st_size:
                    print(f"  SKIP: {filepath.name} already exists in {folder_name}/")
                    skipped_count += 1
                    filepath.unlink()  # Remove duplicate
                    continue
                else:
                    # Different file with same name - add suffix
                    base_name = filepath.stem
                    suffix = 1
                    while dest_path.exists():
                        dest_path = version_dir / f"{base_name}_{suffix}.UPF"
                        suffix += 1
            
            shutil.move(str(filepath), str(dest_path))
            moved_count += 1
    
    # Handle unversioned files
    if unversioned:
        unversioned_dir = source_path / "unversioned"
        unversioned_dir.mkdir(exist_ok=True)
        
        for filepath in unversioned:
            dest_path = unversioned_dir / filepath.name
            if dest_path.exists():
                if filepath.stat().st_size == dest_path.stat().st_size:
                    print(f"  SKIP: {filepath.name} already exists in unversioned/")
                    skipped_count += 1
                    filepath.unlink()
                    continue
                else:
                    base_name = filepath.stem
                    suffix = 1
                    while dest_path.exists():
                        dest_path = unversioned_dir / f"{base_name}_{suffix}.UPF"
                        suffix += 1
            
            shutil.move(str(filepath), str(dest_path))
            moved_count += 1
    
    print(f"\nMoved {moved_count} files")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} duplicates")
    
    return {
        'total_files': len(upf_files),
        'moved': moved_count,
        'skipped': skipped_count,
        'versioned': len(upf_files) - len(unversioned),
        'unversioned': len(unversioned),
        'versions': sorted(version_groups.keys())
    }


def update_manifest(source_dir):
    """
    Update manifest.json to reflect new file locations.
    
    Updates the 'filename' field to include the version folder path.
    """
    source_path = Path(source_dir)
    manifest_path = source_path / "manifest.json"
    
    if not manifest_path.exists():
        print("WARNING: manifest.json not found, skipping update")
        return
    
    print("\nUpdating manifest.json...")
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    updated_count = 0
    for entry in manifest:
        filename = entry['filename']
        version = extract_psl_version(filename)
        
        if version:
            folder_name = normalize_version(version)
            new_filename = f"{folder_name}/{filename}"
            entry['filename'] = new_filename
            updated_count += 1
        else:
            # Check if file exists in unversioned folder
            unversioned_path = source_path / "unversioned" / filename
            if unversioned_path.exists():
                entry['filename'] = f"unversioned/{filename}"
                updated_count += 1
    
    # Write updated manifest
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Updated {updated_count} entries in manifest.json")


def verify_organization(source_dir):
    """
    Verify that files are correctly organized.
    
    Checks:
    - All files are in version folders
    - File counts match
    - No orphaned files in root
    """
    source_path = Path(source_dir)
    
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)
    
    # Count files in version folders
    version_folders = [d for d in source_path.iterdir() if d.is_dir() and d.name.startswith('v')]
    unversioned_dir = source_path / "unversioned"
    
    total_in_folders = 0
    for version_dir in sorted(version_folders):
        upf_files = list(version_dir.glob("*.UPF"))
        total_in_folders += len(upf_files)
        print(f"  {version_dir.name}/: {len(upf_files)} files")
    
    if unversioned_dir.exists():
        upf_files = list(unversioned_dir.glob("*.UPF"))
        total_in_folders += len(upf_files)
        print(f"  unversioned/: {len(upf_files)} files")
    
    # Check for orphaned files in root
    root_upf_files = list(source_path.glob("*.UPF"))
    if root_upf_files:
        print(f"\n  WARNING: {len(root_upf_files)} UPF files still in root directory:")
        for f in root_upf_files[:5]:
            print(f"    - {f.name}")
        if len(root_upf_files) > 5:
            print(f"    ... and {len(root_upf_files) - 5} more")
    else:
        print(f"\n  ✓ All files organized into version folders")
        print(f"  ✓ Total files in folders: {total_in_folders}")
    
    # Verify manifest
    manifest_path = source_path / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        manifest_with_folders = sum(1 for e in manifest if '/' in e['filename'])
        print(f"\n  Manifest entries with folder paths: {manifest_with_folders}/{len(manifest)}")
        
        if manifest_with_folders == len(manifest):
            print(f"  ✓ All manifest entries updated")
        else:
            print(f"  WARNING: Some manifest entries may need updating")


def main():
    parser = argparse.ArgumentParser(
        description='Sort PSL UPF files by version into version-specific folders'
    )
    parser.add_argument(
        '--source',
        default='temp/qe-legacy-upf/ps-library',
        help='Source directory containing UPF files (default: temp/qe-legacy-upf/ps-library)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without actually moving files'
    )
    parser.add_argument(
        '--no-manifest-update',
        action='store_true',
        help='Skip updating manifest.json'
    )
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip verification step'
    )
    
    args = parser.parse_args()
    
    # Sort files
    result = sort_files_by_version(args.source, dry_run=args.dry_run)
    
    if result is None:
        return 1
    
    if args.dry_run:
        print("\nDRY RUN complete. Run without --dry-run to actually organize files.")
        return 0
    
    # Update manifest
    if not args.no_manifest_update:
        update_manifest(args.source)
    
    # Verify
    if not args.no_verify:
        verify_organization(args.source)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total files processed: {result['total_files']}")
    print(f"Versioned files: {result['versioned']}")
    print(f"Unversioned files: {result['unversioned']}")
    print(f"Versions found: {', '.join(result['versions'])}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

