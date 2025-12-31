#!/usr/bin/env python3
"""
Quick inventory script to analyze pseudopotential files and their metadata sources.
"""

import json
from pathlib import Path
from collections import defaultdict

def main():
    repo_root = Path(__file__).parent.parent
    index_path = repo_root / "PSEUDO_FILE_INDEX.json"
    manifest_path = repo_root / "MANIFEST_PSEUDO_SEED.json"
    
    with open(index_path) as f:
        index = json.load(f)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Build library mapping
    lib_map = {}
    for entry in manifest["files"]:
        if entry.get("category") == "sssp":
            lib_map[entry["relative_path"]] = "SSSP"
        elif entry.get("category") == "pseudo-dojo":
            lib_map[entry["relative_path"]] = "PseudoDojo"
        elif entry.get("category") == "gipaw":
            lib_map[entry["relative_path"]] = "GIPAW"
        elif entry.get("category") == "scan":
            lib_map[entry["relative_path"]] = "SCAN_TM"
    
    # Analyze occurrences
    inventory = []
    lib_stats = defaultdict(lambda: {"count": 0, "formats": set(), "basenames": []})
    
    for occ in index["occurrences"]:
        archive_name = occ["archive"]["name"]
        basename = Path(occ["path_in_archive"]).name
        lib_name = occ["library"]["library_name"] or "Unknown"
        
        # Find corresponding file
        sha256 = occ["sha256"]
        file_rec = next((f for f in index["files"] if f["sha256"] == sha256), None)
        
        if file_rec:
            inventory.append({
                "library": lib_name,
                "archive": archive_name,
                "basename": basename,
                "element": file_rec["element"],
                "upf_format": file_rec["upf_format"],
                "size_bytes": file_rec["size_bytes"]
            })
            
            lib_stats[lib_name]["count"] += 1
            lib_stats[lib_name]["formats"].add(file_rec["upf_format"])
            lib_stats[lib_name]["basenames"].append(basename)
    
    # Print summary
    print("=" * 80)
    print("PSEUDOPOTENTIAL INVENTORY")
    print("=" * 80)
    print(f"\nTotal files: {len(index['files'])}")
    print(f"Total occurrences: {len(index['occurrences'])}")
    
    print("\nLibrary Distribution:")
    for lib, stats in sorted(lib_stats.items()):
        print(f"  {lib:15s}: {stats['count']:4d} files, formats: {sorted(stats['formats'])}")
    
    print("\nSample filenames by library:")
    for lib, stats in sorted(lib_stats.items()):
        print(f"\n  {lib}:")
        for basename in sorted(set(stats["basenames"]))[:5]:
            print(f"    - {basename}")
        if len(set(stats["basenames"])) > 5:
            print(f"    ... and {len(set(stats['basenames'])) - 5} more")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

