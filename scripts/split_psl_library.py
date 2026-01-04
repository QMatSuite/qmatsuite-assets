#!/usr/bin/env python3
"""
Split ps-library into two folders:
1. ps-library-legacy: Contains v0.1 through v0.3.1 (with version subfolders)
2. ps-library-v1.0.0: Contains all v1.0.0 UPFs in flat layout

Also splits and updates manifests, then creates tar.gz archives.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from collections import defaultdict


def compute_sha256(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def split_psl_library(source_dir, dest_base, dry_run=False):
    """
    Split ps-library into legacy and v1.0.0 folders.
    
    Args:
        source_dir: Path to ps-library directory
        dest_base: Base directory for output
        dry_run: If True, only print what would be done
    """
    source_path = Path(source_dir)
    dest_base_path = Path(dest_base)
    
    if not source_path.exists():
        print(f"ERROR: Source directory does not exist: {source_dir}")
        return None
    
    # Load manifest
    manifest_path = source_path / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest.json not found in {source_dir}")
        return None
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    print(f"Loaded manifest with {len(manifest)} entries")
    
    # Split manifest entries
    legacy_entries = []
    v1_entries = []
    
    legacy_versions = ['v0.1', 'v0.2', 'v0.2.1', 'v0.2.2', 'v0.2.3', 'v0.3.0', 'v0.3.1']
    
    for entry in manifest:
        filename = entry['filename']
        if filename.startswith('v1.0.0/'):
            # For v1.0.0, remove the version folder prefix for flat layout
            flat_filename = filename.replace('v1.0.0/', '')
            new_entry = entry.copy()
            new_entry['filename'] = flat_filename
            v1_entries.append(new_entry)
        elif any(filename.startswith(f"{v}/") for v in legacy_versions):
            legacy_entries.append(entry)
        else:
            print(f"WARNING: Entry with unexpected path: {filename}")
    
    print(f"\nManifest split:")
    print(f"  Legacy entries: {len(legacy_entries)}")
    print(f"  v1.0.0 entries: {len(v1_entries)}")
    
    if dry_run:
        print("\nDRY RUN: Would create:")
        print(f"  {dest_base_path / 'ps-library-legacy'}/")
        print(f"  {dest_base_path / 'ps-library-v1.0.0'}/")
        return {
            'legacy_count': len(legacy_entries),
            'v1_count': len(v1_entries),
            'total': len(manifest)
        }
    
    # Create output directories
    legacy_dir = dest_base_path / "ps-library-legacy"
    v1_dir = dest_base_path / "ps-library-v1.0.0"
    
    legacy_dir.mkdir(parents=True, exist_ok=True)
    v1_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nCreating directories...")
    print(f"  {legacy_dir}")
    print(f"  {v1_dir}")
    
    # Copy legacy files (preserve version folder structure)
    print(f"\nCopying legacy files...")
    legacy_copied = 0
    for entry in legacy_entries:
        src_file = source_path / entry['filename']
        if src_file.exists():
            # Preserve version folder structure
            dest_file = legacy_dir / entry['filename']
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            legacy_copied += 1
        else:
            print(f"  WARNING: Source file not found: {src_file}")
    
    print(f"  Copied {legacy_copied} legacy files")
    
    # Copy v1.0.0 files (flat layout - no version folder)
    print(f"\nCopying v1.0.0 files (flat layout)...")
    v1_copied = 0
    for entry in v1_entries:
        # Source is in v1.0.0/ subfolder
        src_file = source_path / f"v1.0.0/{entry['filename']}"
        if src_file.exists():
            # Destination is flat (no subfolder)
            dest_file = v1_dir / entry['filename']
            shutil.copy2(src_file, dest_file)
            v1_copied += 1
        else:
            print(f"  WARNING: Source file not found: {src_file}")
    
    print(f"  Copied {v1_copied} v1.0.0 files")
    
    # Write manifests
    print(f"\nWriting manifests...")
    
    legacy_manifest_path = legacy_dir / "manifest.json"
    with open(legacy_manifest_path, 'w') as f:
        json.dump(legacy_entries, f, indent=2)
    print(f"  {legacy_manifest_path} ({len(legacy_entries)} entries)")
    
    v1_manifest_path = v1_dir / "manifest.json"
    with open(v1_manifest_path, 'w') as f:
        json.dump(v1_entries, f, indent=2)
    print(f"  {v1_manifest_path} ({len(v1_entries)} entries)")
    
    return {
        'legacy_dir': legacy_dir,
        'v1_dir': v1_dir,
        'legacy_count': legacy_copied,
        'v1_count': v1_copied,
        'total': legacy_copied + v1_copied,
        'legacy_manifest': legacy_manifest_path,
        'v1_manifest': v1_manifest_path
    }


def create_tar_gz(source_dir, output_path, compression_level=9):
    """
    Create a tar.gz archive with maximum compression.
    
    Args:
        source_dir: Directory to archive
        output_path: Output tar.gz file path
        compression_level: Compression level (1-9, default 9 for maximum)
    """
    source_path = Path(source_dir)
    output_file = Path(output_path)
    
    print(f"\nCreating archive: {output_file}")
    print(f"  Source: {source_path}")
    print(f"  Compression level: {compression_level}")
    
    # Count files first
    upf_files = list(source_path.rglob("*.UPF"))
    manifest_files = list(source_path.rglob("manifest.json"))
    total_files = len(upf_files) + len(manifest_files)
    
    print(f"  Files to archive: {total_files} ({len(upf_files)} UPF + {len(manifest_files)} manifest)")
    
    # Create tar.gz with maximum compression
    with tarfile.open(output_file, 'w:gz', compresslevel=compression_level) as tar:
        # Add all files, preserving directory structure relative to source_dir
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(source_path)
                tar.add(file_path, arcname=arcname)
    
    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"  Archive created: {size_mb:.2f} MB")
    
    return output_file


def verify_split(source_dir, legacy_dir, v1_dir, legacy_manifest, v1_manifest):
    """
    Verify the split was done correctly.
    
    Checks:
    - Total UPF count matches
    - Manifest SHA256 verification
    - File counts match
    """
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)
    
    source_path = Path(source_dir)
    legacy_path = Path(legacy_dir)
    v1_path = Path(v1_dir)
    
    # Count UPFs in source
    source_upf = list(source_path.rglob("*.UPF"))
    source_count = len(source_upf)
    print(f"\n1. Source directory:")
    print(f"   Total UPF files: {source_count}")
    
    # Count UPFs in split directories
    legacy_upf = list(legacy_path.rglob("*.UPF"))
    v1_upf = list(v1_path.glob("*.UPF"))  # Flat layout, no rglob needed
    legacy_count = len(legacy_upf)
    v1_count = len(v1_upf)
    total_split = legacy_count + v1_count
    
    print(f"\n2. Split directories:")
    print(f"   Legacy UPF files: {legacy_count}")
    print(f"   v1.0.0 UPF files: {v1_count}")
    print(f"   Total: {total_split}")
    
    if source_count == total_split:
        print(f"   ✓ Count matches!")
    else:
        print(f"   ✗ COUNT MISMATCH: {source_count} != {total_split}")
        return False
    
    # Verify manifests
    print(f"\n3. Manifest verification:")
    
    # Load original manifest
    original_manifest_path = source_path / "manifest.json"
    with open(original_manifest_path) as f:
        original_manifest = json.load(f)
    
    original_sha = compute_sha256(original_manifest_path)
    print(f"   Original manifest SHA256: {original_sha}")
    
    # Load split manifests
    with open(legacy_manifest) as f:
        legacy_manifest_data = json.load(f)
    with open(v1_manifest) as f:
        v1_manifest_data = json.load(f)
    
    legacy_sha = compute_sha256(legacy_manifest)
    v1_sha = compute_sha256(v1_manifest)
    
    print(f"   Legacy manifest SHA256: {legacy_sha}")
    print(f"   v1.0.0 manifest SHA256: {v1_sha}")
    
    # Verify manifest entry counts
    original_count = len(original_manifest)
    legacy_count_manifest = len(legacy_manifest_data)
    v1_count_manifest = len(v1_manifest_data)
    total_manifest = legacy_count_manifest + v1_count_manifest
    
    print(f"\n4. Manifest entry counts:")
    print(f"   Original: {original_count}")
    print(f"   Legacy: {legacy_count_manifest}")
    print(f"   v1.0.0: {v1_count_manifest}")
    print(f"   Total: {total_manifest}")
    
    if original_count == total_manifest:
        print(f"   ✓ Manifest entry counts match!")
    else:
        print(f"   ✗ MANIFEST COUNT MISMATCH: {original_count} != {total_manifest}")
        return False
    
    # Verify files exist at manifest paths
    print(f"\n5. File path verification:")
    
    legacy_missing = 0
    for entry in legacy_manifest_data[:100]:  # Check first 100
        filepath = legacy_path / entry['filename']
        if not filepath.exists():
            legacy_missing += 1
    
    v1_missing = 0
    for entry in v1_manifest_data[:100]:  # Check first 100
        filepath = v1_path / entry['filename']
        if not filepath.exists():
            v1_missing += 1
    
    if legacy_missing == 0 and v1_missing == 0:
        print(f"   ✓ All checked files exist at manifest paths")
    else:
        print(f"   ✗ Missing files: {legacy_missing} legacy, {v1_missing} v1.0.0")
        return False
    
    print("\n" + "="*80)
    print("VERIFICATION PASSED")
    print("="*80)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Split ps-library into legacy and v1.0.0 folders, create tar.gz archives'
    )
    parser.add_argument(
        '--source',
        default='temp/qe-legacy-upf/ps-library',
        help='Source ps-library directory (default: temp/qe-legacy-upf/ps-library)'
    )
    parser.add_argument(
        '--dest',
        default='temp/qe-legacy-upf',
        help='Destination base directory (default: temp/qe-legacy-upf)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without actually doing it'
    )
    parser.add_argument(
        '--no-archive',
        action='store_true',
        help='Skip creating tar.gz archives'
    )
    parser.add_argument(
        '--compression',
        type=int,
        default=9,
        choices=range(1, 10),
        help='Compression level 1-9 (default: 9 for maximum)'
    )
    
    args = parser.parse_args()
    
    # Step 1: Split the library
    result = split_psl_library(args.source, args.dest, dry_run=args.dry_run)
    
    if result is None:
        return 1
    
    if args.dry_run:
        print("\nDRY RUN complete. Run without --dry-run to perform the split.")
        return 0
    
    # Step 2: Create tar.gz archives
    if not args.no_archive:
        print("\n" + "="*80)
        print("CREATING ARCHIVES")
        print("="*80)
        
        legacy_archive = Path(args.dest) / "ps-library-legacy.tar.gz"
        v1_archive = Path(args.dest) / "ps-library-v1.0.0.tar.gz"
        
        create_tar_gz(result['legacy_dir'], legacy_archive, compression_level=args.compression)
        create_tar_gz(result['v1_dir'], v1_archive, compression_level=args.compression)
        
        # Compute archive SHA256
        print(f"\nArchive SHA256 hashes:")
        legacy_sha = compute_sha256(legacy_archive)
        v1_sha = compute_sha256(v1_archive)
        print(f"  {legacy_archive.name}: {legacy_sha}")
        print(f"  {v1_archive.name}: {v1_sha}")
    
    # Step 3: Verify
    if not args.no_archive:
        verify_split(
            args.source,
            result['legacy_dir'],
            result['v1_dir'],
            result['legacy_manifest'],
            result['v1_manifest']
        )
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Legacy files: {result['legacy_count']}")
    print(f"v1.0.0 files: {result['v1_count']}")
    print(f"Total: {result['total']}")
    
    if not args.no_archive:
        legacy_archive = Path(args.dest) / "ps-library-legacy.tar.gz"
        v1_archive = Path(args.dest) / "ps-library-v1.0.0.tar.gz"
        print(f"\nArchives created:")
        print(f"  {legacy_archive}")
        print(f"  {v1_archive}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

