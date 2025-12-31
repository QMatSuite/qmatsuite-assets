#!/usr/bin/env python3
"""
Extract and examine sample UPF files to understand their structure for classification.
"""

import json
import tarfile
import zipfile
from pathlib import Path

def extract_sample(archive_path, extract_to, max_files=3):
    """Extract a few sample files from an archive."""
    extract_to.mkdir(parents=True, exist_ok=True)
    
    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            upf_files = [f for f in zf.namelist() if f.lower().endswith(('.upf', '.upf'))]
            for fname in upf_files[:max_files]:
                zf.extract(fname, extract_to)
                return [extract_to / fname for fname in upf_files[:max_files]]
    elif archive_path.suffix.lower() in [".tar", ".tgz"] or archive_path.name.endswith(".tar.gz"):
        mode = "r:gz" if archive_path.suffix.lower() in [".tgz", ".gz"] or archive_path.name.endswith(".tar.gz") else "r"
        with tarfile.open(archive_path, mode) as tf:
            upf_files = [m for m in tf.getmembers() if m.name.lower().endswith(('.upf', '.upf')) and m.isfile()]
            for member in upf_files[:max_files]:
                tf.extract(member, extract_to)
            return [extract_to / m.name for m in upf_files[:max_files]]
    return []

def examine_upf_header(filepath):
    """Examine UPF header for classification clues."""
    try:
        with open(filepath, "rb") as f:
            content = f.read(8192).decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": str(e)}
    
    info = {
        "filename": filepath.name,
        "has_pp_header": "<PP_HEADER" in content,
        "has_pp_info": "<PP_INFO" in content,
        "header_attributes": {},
        "info_text": ""
    }
    
    # Extract PP_HEADER attributes (UPF v2 style)
    import re
    header_match = re.search(r'<PP_HEADER[^>]*>', content, re.IGNORECASE)
    if header_match:
        header_line = header_match.group(0)
        # Extract key attributes
        for attr in ["is_ultrasoft", "is_paw", "pseudo_type", "relativistic", "has_so"]:
            match = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', header_line, re.IGNORECASE)
            if match:
                info["header_attributes"][attr] = match.group(1)
    
    # Extract PP_INFO block (first 500 chars)
    info_match = re.search(r'<PP_INFO>(.*?)</PP_INFO>', content, re.DOTALL | re.IGNORECASE)
    if info_match:
        info["info_text"] = info_match.group(1)[:500]
    
    return info

def main():
    repo_root = Path(__file__).parent.parent
    pseudo_seed = repo_root / "pseudo_seed"
    samples_dir = repo_root / "temp" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample archives from each library
    archives = [
        ("SSSP", "SSSP_1.3.0_PBE_efficiency.tar.gz"),
        ("PseudoDojo", "nc-sr-04_pbe_standard_upf.tgz"),
        ("GIPAW", "GIPAW_DavideCeresoli.zip"),
        ("SCAN_TM", "SCAN_TM_YiYao_2017.zip"),
    ]
    
    print("=" * 80)
    print("UPF FILE STRUCTURE EXAMINATION")
    print("=" * 80)
    
    for lib_name, archive_name in archives:
        archive_path = pseudo_seed / archive_name
        if not archive_path.exists():
            print(f"\nSkipping {archive_name} (not found)")
            continue
        
        print(f"\n{lib_name} ({archive_name}):")
        print("-" * 80)
        
        lib_samples_dir = samples_dir / lib_name.lower()
        files = extract_sample(archive_path, lib_samples_dir, max_files=2)
        
        for filepath in files:
            if filepath.exists():
                info = examine_upf_header(filepath)
                print(f"\n  File: {info['filename']}")
                print(f"    Has PP_HEADER: {info['has_pp_header']}")
                print(f"    Has PP_INFO: {info['has_pp_info']}")
                if info['header_attributes']:
                    print(f"    Header attributes: {info['header_attributes']}")
                if info['info_text']:
                    print(f"    PP_INFO snippet: {info['info_text'][:200]}...")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

