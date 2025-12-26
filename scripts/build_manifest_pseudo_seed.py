#!/usr/bin/env python3
"""
Build manifest for pseudo_seed directory.

This script walks the pseudo_seed/ directory, computes SHA256 hashes,
and generates/updates MANIFEST_PSEUDO_SEED.json with metadata.
"""

import json
import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def parse_filename(filename: str) -> Dict:
    """
    Parse filename to extract metadata.
    Returns dict with category, library_name, library_version, and flavor fields.
    """
    result = {
        "category": "other",
        "library_name": None,
        "library_version": None,
        "relativistic": None,
        "xc": None,
        "quality": None,
        "type": None,
    }
    
    # SSSP files
    if filename.startswith("SSSP_"):
        result["category"] = "sssp"
        result["library_name"] = "SSSP"
        # Extract version: SSSP_1.3.0_PBE_efficiency.json -> "1.3.0"
        parts = filename.split("_")
        if len(parts) >= 2:
            result["library_version"] = parts[1]
        # Extract flavor from filename
        if "efficiency" in filename.lower():
            result["quality"] = "efficiency"
        elif "precision" in filename.lower():
            result["quality"] = "precision"
        if "pbe" in filename.lower():
            result["xc"] = "pbe"
        return result
    
    # GIPAW
    if filename.startswith("GIPAW_"):
        result["category"] = "gipaw"
        result["library_name"] = "GIPAW"
        # Version not clearly specified in filename
        return result
    
    # SCAN TM
    if filename.startswith("SCAN_TM_"):
        result["category"] = "scan"
        result["library_name"] = "SCAN_TM"
        # Extract year: SCAN_TM_YiYao_2017.zip -> "2017"
        # Remove extension first
        name_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
        parts = name_no_ext.split("_")
        for part in parts:
            if part.isdigit() and len(part) == 4:
                result["library_version"] = part
                break
        return result
    
    # PseudoDojo files
    # Pattern: nc-sr-04_pbe_standard_upf.tgz
    # Pattern: paw-sr-11_pbesol_stringent_upf.tgz
    if filename.startswith("nc-") or filename.startswith("paw-"):
        result["category"] = "pseudo-dojo"
        result["library_name"] = "PseudoDojo"
        
        # Extract type: nc-* or paw-*
        if filename.startswith("nc-"):
            result["type"] = "nc"
        elif filename.startswith("paw-"):
            result["type"] = "paw"
        
        # Extract relativistic: nc-sr-* or nc-fr-*
        if "-sr-" in filename:
            result["relativistic"] = "sr"
        elif "-fr-" in filename:
            result["relativistic"] = "fr"
        
        # Extract version: nc-sr-04_* -> "04", paw-sr-11_* -> "11"
        parts = filename.split("-")
        if len(parts) >= 3:
            version_part = parts[2].split("_")[0]
            if version_part.isdigit():
                result["library_version"] = version_part
        
        # Extract XC functional
        if "_pbe_" in filename or filename.endswith("_pbe_"):
            result["xc"] = "pbe"
        elif "_pbesol_" in filename:
            result["xc"] = "pbesol"
        elif "_lda_" in filename:
            result["xc"] = "lda"
        elif "_pw_" in filename:
            result["xc"] = "pw"
        
        # Extract quality
        if "_standard_" in filename:
            result["quality"] = "standard"
        elif "_stringent_" in filename:
            result["quality"] = "stringent"
        
        return result
    
    return result


def get_upstream_urls(category: str, library_name: str, filename: str) -> List[str]:
    """Get upstream URLs based on category and library."""
    urls = []
    
    if category == "sssp":
        urls.extend([
            "https://legacy.materialscloud.org/discover/sssp/table/efficiency",
            "https://legacy.materialscloud.org/discover/sssp/table/precision",
        ])
        # SSSP gets both QE URLs
        urls.extend([
            "https://www.quantum-espresso.org/other-resources/",
            "https://www.quantum-espresso.org/pseudopotentials/",
        ])
    elif category == "pseudo-dojo":
        urls.extend([
            "https://www.pseudo-dojo.org",
            "https://www.pseudo-dojo.org/faq.html",
        ])
        # Other categories only get other-resources
        urls.append("https://www.quantum-espresso.org/other-resources/")
    elif category == "gipaw":
        urls.append("https://sites.google.com/site/dceresoli/pseudopotentials")
        urls.append("https://www.quantum-espresso.org/other-resources/")
    elif category == "scan":
        urls.append("https://yaoyi92.github.io/scan-tm-pseudopotentials.html")
        urls.append("https://www.quantum-espresso.org/other-resources/")
    else:
        # Fallback for other categories
        urls.append("https://www.quantum-espresso.org/other-resources/")
    
    return urls


def build_manifest(pseudo_seed_dir: Path, output_file: Path) -> None:
    """Build manifest from pseudo_seed directory."""
    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "schema_version": "1.0",
        "files": [],
    }
    
    # Walk the directory
    for filepath in sorted(pseudo_seed_dir.iterdir()):
        if not filepath.is_file():
            continue
        
        # Skip hidden/system files
        if filepath.name.startswith("."):
            continue
        
        relative_path = filepath.relative_to(pseudo_seed_dir.parent)
        size_bytes = filepath.stat().st_size
        sha256 = compute_sha256(filepath)
        
        # Parse metadata
        metadata = parse_filename(filepath.name)
        upstream_urls = get_upstream_urls(
            metadata["category"],
            metadata["library_name"],
            filepath.name
        )
        
        file_entry = {
            "relative_path": str(relative_path),
            "size_bytes": size_bytes,
            "sha256": sha256,
            "category": metadata["category"],
            "library_name": metadata["library_name"],
            "library_version": metadata["library_version"],
            "relativistic": metadata["relativistic"],
            "xc": metadata["xc"],
            "quality": metadata["quality"],
            "type": metadata["type"],
            "upstream_urls": upstream_urls,
            "license_url": None,  # Will be filled manually if known
            "notes": None,
        }
        
        manifest["files"].append(file_entry)
    
    # Write manifest
    with open(output_file, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
    
    print(f"Manifest generated: {output_file}")
    print(f"Total files: {len(manifest['files'])}")


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    pseudo_seed_dir = repo_root / "pseudo_seed"
    output_file = repo_root / "MANIFEST_PSEUDO_SEED.json"
    
    if not pseudo_seed_dir.exists():
        print(f"Error: {pseudo_seed_dir} does not exist")
        exit(1)
    
    build_manifest(pseudo_seed_dir, output_file)

