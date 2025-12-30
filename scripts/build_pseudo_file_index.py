#!/usr/bin/env python3
"""
Build normalized per-UPF file index for all pseudopotentials in pseudo_seed/.

This script:
1. Validates archive SHA256 against MANIFEST_PSEUDO_SEED.json
2. Extracts all archives
3. Indexes UPF files by sha256 (primary key)
4. Creates normalized PSEUDO_FILE_INDEX.json with files[] and occurrences[]

Schema v1.2.0: Uses sha_family (whitespace-stripped text hash) instead of sha_token.
Note: Downstream code in QMatSuite main repo will need to consume sha_family instead of sha_token.
"""

import json
import hashlib
import re
import tarfile
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict


# Valid element symbols (H through Og, 118 elements)
VALID_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og"
}


def sha256_file(filepath: Path) -> str:
    """Compute SHA256 hash of file bytes."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def compute_sha_family_from_text(text: str) -> str:
    """
    Compute sha_family by stripping all whitespace from text and hashing.
    
    Definition: sha_family = sha256(canonical_utf8_bytes) where canonical
    is the text with all whitespace characters (isspace()) removed.
    """
    # Strip all whitespace characters (using isspace() definition)
    canonical = ''.join(ch for ch in text if not ch.isspace())
    
    # Assert: canonical contains zero whitespace characters
    assert not any(ch.isspace() for ch in canonical), "Canonical string must contain no whitespace"
    
    # Compute sha256 of canonical UTF-8 bytes
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_archive(filepath: Path) -> bool:
    """Check if file is an archive."""
    suffixes = filepath.suffixes
    if not suffixes:
        return False
    ext = "".join(suffixes[-2:]) if len(suffixes) >= 2 else suffixes[-1]
    return ext.lower() in [".tar", ".tar.gz", ".tgz", ".zip"]


def is_upf_file(filepath: Path, content_bytes: Optional[bytes] = None) -> bool:
    """Check if file is a UPF file based on extension and content."""
    ext = filepath.suffix.lower()
    if ext in [".upf"]:
        # Check content if provided
        if content_bytes is not None:
            content_preview = content_bytes[:4096].decode("utf-8", errors="ignore")
            return "<UPF" in content_preview or "<PP_HEADER" in content_preview
        return True
    
    # No extension or other extension: check content
    if content_bytes is not None:
        content_preview = content_bytes[:4096].decode("utf-8", errors="ignore")
        return "<UPF" in content_preview or "<PP_HEADER" in content_preview
    
    return False


def parse_element_from_upf(content_bytes: bytes) -> Optional[str]:
    """
    Parse element symbol from UPF file content.
    Supports both UPF v1 and v2 formats.
    Returns normalized element symbol or None.
    """
    try:
        content = content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return None
    
    element_candidates = []
    
    # UPF v2: Look for element="Br" or element='Br' in PP_HEADER tag
    # Pattern: <PP_HEADER ... element="Br" ... /> or <PP_HEADER ... element='Br' ... />
    v2_pattern = r'<PP_HEADER[^>]*\belement=["\']\s*([A-Za-z]{1,2})\s*["\']'
    matches = re.findall(v2_pattern, content, re.IGNORECASE)
    if matches:
        element_candidates.extend(matches)
    
    # UPF v1: Look for "Element" keyword in PP_HEADER block
    # Pattern: "Al                   Element" (element symbol, whitespace, "Element")
    header_block_match = re.search(r'<PP_HEADER[^>]*>(.*?)</PP_HEADER>', content, re.DOTALL | re.IGNORECASE)
    if header_block_match:
        header_content = header_block_match.group(1)
        # Look for lines matching: ^\s*([A-Za-z]{1,2})\s+Element\s*$
        v1_pattern = r'^\s*([A-Za-z]{1,2})\s+Element\s*$'
        for line in header_content.split('\n'):
            match = re.match(v1_pattern, line, re.IGNORECASE)
            if match:
                element_candidates.append(match.group(1))
    
    # Fallback: Check PP_INPUTFILE section for "atsym" line
    if not element_candidates:
        inputfile_match = re.search(r'<PP_INPUTFILE>(.*?)</PP_INPUTFILE>', content, re.DOTALL | re.IGNORECASE)
        if inputfile_match:
            inputfile_content = inputfile_match.group(1)
            # Look for line starting with element symbol followed by number
            for line in inputfile_content.split('\n'):
                # Match lines like "B  5.00" or "B\t5.00" (element, whitespace, number)
                match = re.match(r'^\s*([A-Za-z]{1,2})\s+\d', line)
                if match:
                    element_candidates.append(match.group(1))
                    break
    
    if not element_candidates:
        return None
    
    # Normalize: take first candidate, uppercase first letter, lowercase rest
    element = element_candidates[0].strip()
    if len(element) == 1:
        element = element.upper()
    elif len(element) == 2:
        element = element[0].upper() + element[1].lower()
    
    # Validate against periodic table
    if element in VALID_ELEMENTS:
        return element
    
    return None


def parse_element_from_filename(name: str) -> Optional[str]:
    """
    Parse element symbol from filename.
    Examples:
    - "Si.pbe-....UPF" -> "Si"
    - "B-PBE.upf" -> "B"
    - "b_pbe_v1.4.uspp.F.UPF" -> "B" (lowercase start)
    - "B.upf" -> "B" (single letter)
    """
    # Remove extension
    name_no_ext = name.rsplit(".", 1)[0] if "." in name else name
    
    # Handle single-letter filenames (e.g., "B.upf")
    if len(name_no_ext) == 1 and name_no_ext.isalpha():
        elem = name_no_ext.upper()
        return elem if elem in VALID_ELEMENTS else None
    
    # Try to match element at start (case-insensitive): ^([A-Za-z]{1,2})
    match = re.match(r"^([A-Za-z]{1,2})", name_no_ext)
    if match:
        elem = match.group(1)
        # Normalize: uppercase first, lowercase rest
        if len(elem) == 1:
            elem = elem.upper()
        else:
            elem = elem[0].upper() + elem[1:].lower()
        
        if elem in VALID_ELEMENTS:
            return elem
    
    # Try to find element before first dot, dash, or underscore
    match = re.match(r"^([A-Za-z]{1,2})[.\-_]", name_no_ext)
    if match:
        elem = match.group(1)
        if len(elem) == 1:
            elem = elem.upper()
        else:
            elem = elem[0].upper() + elem[1:].lower()
        
        if elem in VALID_ELEMENTS:
            return elem
    
    return None


def detect_upf_format(content_bytes: bytes) -> str:
    """Detect UPF format version."""
    try:
        content = content_bytes[:4096].decode("utf-8", errors="ignore")
    except Exception:
        return "unknown"
    
    if '<PP_HEADER' in content and 'element=' in content:
        return "upf2"
    elif '<PP_HEADER' in content:
        return "upf1"
    else:
        return "unknown"


def extract_archive(archive_path: Path, extract_dir: Path) -> Path:
    """Extract archive to extract_dir/<archive_stem>/ and return extraction root."""
    extract_root = extract_dir / archive_path.stem
    extract_root.mkdir(parents=True, exist_ok=True)
    
    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_root)
    elif archive_path.suffix.lower() in [".tar", ".tgz"] or "".join(archive_path.suffixes[-2:]).lower() == ".tar.gz":
        mode = "r:gz" if archive_path.suffix.lower() in [".tgz", ".gz"] or archive_path.name.endswith(".tar.gz") else "r"
        with tarfile.open(archive_path, mode) as tf:
            tf.extractall(extract_root)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")
    
    return extract_root


def find_all_files(root: Path) -> List[Path]:
    """Recursively find all files in directory."""
    files = []
    for item in root.rglob("*"):
        if item.is_file():
            files.append(item)
    return sorted(files)


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    pseudo_seed_dir = repo_root / "pseudo_seed"
    manifest_path = repo_root / "MANIFEST_PSEUDO_SEED.json"
    extract_dir = repo_root / "temp" / "extract"
    output_path = repo_root / "PSEUDO_FILE_INDEX.json"
    
    if not pseudo_seed_dir.exists():
        print(f"Error: {pseudo_seed_dir} does not exist")
        exit(1)
    
    if not manifest_path.exists():
        print(f"Error: {manifest_path} does not exist")
        exit(1)
    
    # Load manifest
    with open(manifest_path, "rb") as f:
        manifest_bytes = f.read()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    manifest_sha256 = sha256_file(manifest_path)
    
    # Index manifest entries by relative_path
    manifest_index = {}
    for entry in manifest.get("files", []):
        rel_path = entry["relative_path"]
        manifest_index[rel_path] = entry
    
    # Clean extract directory
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    # Data structures
    files_by_sha256: Dict[str, Dict] = {}  # sha256 -> file record
    occurrences: List[Dict] = []  # List of occurrence records
    warnings: List[str] = []
    errors: List[str] = []
    
    # Process each archive entry in manifest
    archive_count = 0
    upf_files_scanned = 0
    
    for rel_path, manifest_entry in sorted(manifest_index.items()):
        # Only process archives
        if not is_archive(Path(rel_path)):
            continue
        
        archive_count += 1
        archive_path = repo_root / rel_path
        
        # Verify archive exists
        if not archive_path.exists():
            errors.append(f"Archive not found: {rel_path}")
            continue
        
        # Validate archive SHA256
        actual_sha256 = sha256_file(archive_path)
        expected_sha256 = manifest_entry.get("sha256")
        
        if expected_sha256 is None:
            errors.append(f"Manifest entry missing sha256: {rel_path}")
            continue
        
        if actual_sha256 != expected_sha256:
            errors.append(
                f"SHA256 mismatch for {rel_path}:\n"
                f"  Expected: {expected_sha256}\n"
                f"  Actual:   {actual_sha256}"
            )
            continue
        
        # Extract archive
        try:
            extract_root = extract_archive(archive_path, extract_dir)
        except Exception as e:
            errors.append(f"Failed to extract archive '{rel_path}': {e}")
            continue
        
        # Find all files in extracted archive
        extracted_files = find_all_files(extract_root)
        
        # Track UPF files and non-UPF files
        upf_files = []
        non_upf_files = []
        
        for filepath in extracted_files:
            # Skip macOS metadata files
            if "__MACOSX" in str(filepath) or filepath.name.startswith("._"):
                continue
            
            # Read file bytes
            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
            except Exception as e:
                warnings.append(f"Failed to read file '{filepath.relative_to(extract_root)}' in archive '{rel_path}': {e}")
                continue
            
            # Check if UPF
            if is_upf_file(filepath, file_bytes):
                upf_files.append((filepath, file_bytes))
            else:
                non_upf_files.append(filepath.relative_to(extract_root))
        
        # Warn about non-UPF files
        if non_upf_files:
            warnings.append(
                f"Archive '{rel_path}' contains {len(non_upf_files)} non-UPF files: "
                + ", ".join(str(p) for p in sorted(non_upf_files)[:10])
                + (f" ... and {len(non_upf_files) - 10} more" if len(non_upf_files) > 10 else "")
            )
        
        # Fail if pseudo archive contains zero UPF files
        if not upf_files:
            errors.append(f"Archive '{rel_path}' contains zero UPF files")
            continue
        
        # Process each UPF file
        for filepath, file_bytes in upf_files:
            upf_files_scanned += 1
            rel_file_path = filepath.relative_to(extract_root)
            
            # Compute hashes
            sha256 = hashlib.sha256(file_bytes).hexdigest()
            
            # Decode bytes to text for sha_family computation
            try:
                file_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Fallback: decode with error replacement
                file_text = file_bytes.decode("utf-8", errors="replace")
            
            # Validate canonical string is not empty (file contains only whitespace)
            canonical = ''.join(ch for ch in file_text if not ch.isspace())
            if not canonical:
                errors.append(
                    f"UPF file '{rel_file_path}' in archive '{rel_path}': "
                    f"File contains only whitespace (invalid/corrupt)"
                )
                continue
            
            # Compute sha_family
            sha_family = compute_sha_family_from_text(file_text)
            
            # Parse element from file content
            element_from_file = parse_element_from_upf(file_bytes)
            
            # Parse element from filename
            element_from_filename = parse_element_from_filename(filepath.name)
            
            # Validate element
            if element_from_file is None and element_from_filename is None:
                errors.append(
                    f"Cannot determine element for UPF file '{rel_file_path}' in archive '{rel_path}'"
                )
                continue
            
            if element_from_file is None:
                # Can infer from filename but not from file
                warnings.append(
                    f"UPF file '{rel_file_path}' in archive '{rel_path}': "
                    f"Could not parse element from file content, using filename: {element_from_filename}"
                )
                element = element_from_filename
            elif element_from_filename is None:
                # Can parse from file but not from filename
                warnings.append(
                    f"UPF file '{rel_file_path}' in archive '{rel_path}': "
                    f"Could not infer element from filename, using file content: {element_from_file}"
                )
                element = element_from_file
            else:
                # Both exist - must match
                if element_from_file != element_from_filename:
                    errors.append(
                        f"Element mismatch for UPF file '{rel_file_path}' in archive '{rel_path}':\n"
                        f"  From file content: {element_from_file}\n"
                        f"  From filename:     {element_from_filename}"
                    )
                    continue
                element = element_from_file
            
            # Detect UPF format
            upf_format = detect_upf_format(file_bytes)
            
            # Add or update file record
            if sha256 not in files_by_sha256:
                files_by_sha256[sha256] = {
                    "sha256": sha256,
                    "sha_family": sha_family,
                    "element": element,
                    "size_bytes": len(file_bytes),
                    "upf_format": upf_format,
                    "basenames": []
                }
            
            # Add basename if not already present
            basename = filepath.name
            if basename not in files_by_sha256[sha256]["basenames"]:
                files_by_sha256[sha256]["basenames"].append(basename)
            
            # Add occurrence
            occurrence = {
                "sha256": sha256,
                "archive": {
                    "name": archive_path.name,
                    "relative_path": rel_path,
                    "sha256": expected_sha256
                },
                "path_in_archive": str(rel_file_path),
                "library": {
                    "library_name": manifest_entry.get("library_name"),
                    "category": manifest_entry.get("category"),
                    "library_version": manifest_entry.get("library_version"),
                    "xc": manifest_entry.get("xc"),
                    "quality": manifest_entry.get("quality"),
                    "relativistic": manifest_entry.get("relativistic"),
                    "type": manifest_entry.get("type")
                }
            }
            occurrences.append(occurrence)
    
    # Check for errors
    if errors:
        print("\n" + "=" * 80)
        print("ERRORS FOUND:")
        print("=" * 80)
        for error in errors:
            print(error)
        print("=" * 80)
        exit(1)
    
    # Sort basenames in file records
    for file_record in files_by_sha256.values():
        file_record["basenames"].sort()
    
    # Build final index
    # Sort files by (element, first_basename, sha256) for stable ordering
    files_list = sorted(
        files_by_sha256.values(),
        key=lambda x: (x["element"], x["basenames"][0] if x["basenames"] else "", x["sha256"])
    )
    occurrences_list = sorted(occurrences, key=lambda x: (x["archive"]["name"], x["path_in_archive"], x["sha256"]))
    
    index = {
        "schema_version": "1.2.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_manifest": {
            "path": "MANIFEST_PSEUDO_SEED.json",
            "sha256": manifest_sha256
        },
        "files": files_list,
        "occurrences": occurrences_list,
        "warnings": warnings if warnings else None
    }
    
    # Validation checks
    validation_errors = []
    
    # Check: all occurrences[*].sha256 exist in files
    files_sha256_set = {f["sha256"] for f in files_list}
    for occ in occurrences_list:
        if occ["sha256"] not in files_sha256_set:
            validation_errors.append(
                f"Occurrence references missing sha256: {occ['sha256']} "
                f"(archive: {occ['archive']['name']}, path: {occ['path_in_archive']})"
            )
    
    # Check: files have non-empty basenames
    for f in files_list:
        if not f["basenames"]:
            validation_errors.append(f"File with sha256 {f['sha256']} has empty basenames list")
    
    # Check: sha_family is valid (64 hex chars, lowercase)
    for f in files_list:
        sha_family = f.get("sha_family")
        if not sha_family:
            validation_errors.append(f"File with sha256 {f['sha256']} missing sha_family")
        elif len(sha_family) != 64:
            validation_errors.append(f"File with sha256 {f['sha256']} has invalid sha_family length: {len(sha_family)} (expected 64)")
        elif not all(c in '0123456789abcdef' for c in sha_family):
            validation_errors.append(f"File with sha256 {f['sha256']} has invalid sha_family format (not hex)")
    
    # Check: each archive has at least 1 occurrence
    archives_with_occurrences = {occ["archive"]["name"] for occ in occurrences_list}
    processed_archives = set()
    for rel_path, manifest_entry in manifest_index.items():
        if is_archive(Path(rel_path)):
            archive_name = Path(rel_path).name
            processed_archives.add(archive_name)
            if archive_name not in archives_with_occurrences:
                validation_errors.append(f"Archive '{archive_name}' has zero occurrences")
    
    if validation_errors:
        print("\n" + "=" * 80)
        print("VALIDATION ERRORS:")
        print("=" * 80)
        for error in validation_errors:
            print(error)
        print("=" * 80)
        exit(1)
    
    # Write index
    with open(output_path, "w") as f:
        json.dump(index, f, indent=2, sort_keys=False)
    
    # Print summary
    print("=" * 80)
    print("SUCCESS")
    print("=" * 80)
    print(f"Archives processed:     {archive_count}")
    print(f"UPF files scanned:      {upf_files_scanned}")
    print(f"Unique sha256 files:    {len(files_list)}")
    print(f"Occurrences:            {len(occurrences_list)}")
    print(f"Warnings:               {len(warnings)}")
    print(f"Index written to:       {output_path}")
    print("=" * 80)
    
    # Clean up extract directory
    if extract_dir.exists():
        shutil.rmtree(extract_dir)


if __name__ == "__main__":
    main()
