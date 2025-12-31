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


def extract_upf_metadata(content_bytes: bytes, filename: str) -> Dict:
    """
    Extract comprehensive UPF metadata from content.
    Returns dict with all metadata fields (type, relativistic, functional, cutoffs, etc.)
    """
    try:
        content = content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return _default_metadata()
    
    result = _default_metadata()
    
    # UPF v2: Parse PP_HEADER attributes (most reliable)
    header_match = re.search(r'<PP_HEADER[^>]*>', content, re.IGNORECASE)
    if header_match:
        header_line = header_match.group(0)
        
        # Extract all attributes
        attrs = {}
        attr_names = [
            "is_ultrasoft", "is_paw", "pseudo_type", "relativistic", "has_so",
            "has_gipaw", "paw_as_gipaw", "core_correction", "functional",
            "z_valence", "number_of_wfc", "number_of_proj", "has_wfc"
        ]
        for attr in attr_names:
            match = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', header_line, re.IGNORECASE)
            if match:
                attrs[attr] = match.group(1).strip()
        
        # Type classification
        if attrs.get("pseudo_type"):
            pt = attrs["pseudo_type"].upper()
            if pt in ["NC", "NORM-CONSERVING"]:
                result["pseudo_type"] = "nc"
                result["metadata_source"]["type_from"] = "upf_v2_attr"
            elif pt in ["US", "ULTRASOFT"]:
                result["pseudo_type"] = "uspp"
                result["metadata_source"]["type_from"] = "upf_v2_attr"
            elif pt == "PAW":
                result["pseudo_type"] = "paw"
                result["metadata_source"]["type_from"] = "upf_v2_attr"
        elif attrs.get("is_paw", "").upper() == "T":
            result["pseudo_type"] = "paw"
            result["is_paw"] = True
            result["metadata_source"]["type_from"] = "upf_v2_attr"
        elif attrs.get("is_ultrasoft", "").upper() == "T":
            result["pseudo_type"] = "uspp"
            result["is_ultrasoft"] = True
            result["metadata_source"]["type_from"] = "upf_v2_attr"
        elif attrs.get("is_ultrasoft", "").upper() == "F" and attrs.get("is_paw", "").upper() == "F":
            result["pseudo_type"] = "nc"
            result["is_ultrasoft"] = False
            result["is_paw"] = False
            result["metadata_source"]["type_from"] = "upf_v2_attr"
        
        # Boolean flags from v2
        if attrs.get("is_ultrasoft"):
            result["is_ultrasoft"] = attrs["is_ultrasoft"].upper() == "T"
        if attrs.get("is_paw"):
            result["is_paw"] = attrs["is_paw"].upper() == "T"
        if attrs.get("has_so"):
            result["has_spin_orbit"] = attrs["has_so"].upper() == "T"
        if attrs.get("has_gipaw"):
            val = attrs["has_gipaw"].upper()
            result["has_gipaw"] = True if val == "T" else False if val == "F" else "unknown"
        if attrs.get("paw_as_gipaw"):
            val = attrs["paw_as_gipaw"].upper()
            result["paw_as_gipaw"] = True if val == "T" else False if val == "F" else "unknown"
        if attrs.get("core_correction"):
            val = attrs["core_correction"].upper()
            result["core_correction"] = True if val == "T" else False if val == "F" else "unknown"
        if attrs.get("has_wfc"):
            val = attrs["has_wfc"].upper()
            result["has_wfc"] = True if val == "T" else False if val == "F" else "unknown"
        
        # Relativistic
        if attrs.get("relativistic"):
            rel = attrs["relativistic"].lower()
            if "scalar" in rel:
                result["relativistic"] = "scalar_rel"
                result["metadata_source"]["relativistic_from"] = "upf_v2_attr"
            elif "full" in rel or "dirac" in rel:
                result["relativistic"] = "full_rel"
                result["metadata_source"]["relativistic_from"] = "upf_v2_attr"
            elif "non" in rel or "no" in rel:
                result["relativistic"] = "nonrel"
                result["metadata_source"]["relativistic_from"] = "upf_v2_attr"
        
        # Functional
        if attrs.get("functional"):
            result["functional_raw"] = attrs["functional"].strip()
            result["functional_norm"] = _normalize_functional(result["functional_raw"])
            result["metadata_source"]["functional_from"] = "upf_v2_attr"
        
        # Z valence
        if attrs.get("z_valence"):
            try:
                result["z_valence"] = float(attrs["z_valence"])
                result["metadata_source"]["z_valence_from"] = "upf_v2_attr"
            except (ValueError, TypeError):
                pass
        
        # Counts
        if attrs.get("number_of_wfc"):
            try:
                result["number_of_wfc"] = int(float(attrs["number_of_wfc"]))
                result["metadata_source"]["number_of_wfc_from"] = "upf_v2_attr"
            except (ValueError, TypeError):
                pass
        if attrs.get("number_of_proj"):
            try:
                result["number_of_proj"] = int(float(attrs["number_of_proj"]))
                result["metadata_source"]["number_of_proj_from"] = "upf_v2_attr"
            except (ValueError, TypeError):
                pass
    
    # UPF v1: Parse from text blocks
    if result["pseudo_type"] == "unknown" or result["functional_raw"] is None:
        _extract_from_upf_v1(content, result, filename)
    
    # Extract cutoffs from UPF (if not already from SSSP)
    _extract_cutoffs_from_upf(content, result)
    
    return result


def _default_metadata() -> Dict:
    """Return default metadata structure."""
    return {
        "pseudo_type": "unknown",
        "pp_family_hint": None,
        "relativistic": "unknown",
        "has_spin_orbit": "unknown",
        "is_ultrasoft": "unknown",
        "is_paw": "unknown",
        "has_gipaw": "unknown",
        "paw_as_gipaw": "unknown",
        "core_correction": "unknown",
        "has_wfc": "unknown",
        "functional_raw": None,
        "functional_norm": None,
        "z_valence": None,
        "number_of_wfc": None,
        "number_of_proj": None,
        "cutoff_source": None,
        "cutoff_wfc_low": "na",
        "cutoff_wfc_normal": "na",
        "cutoff_wfc_high": "na",
        "cutoff_rho_low": "na",
        "cutoff_rho_normal": "na",
        "cutoff_rho_high": "na",
        "cutoff_wfc_upf": "na",
        "cutoff_rho_upf": "na",
        "metadata_source": {
            "type_from": "unknown",
            "relativistic_from": "unknown",
            "so_from": "unknown",
            "functional_from": "unknown",
            "z_valence_from": "unknown"
        }
    }


def _normalize_functional(raw: str) -> str:
    """Normalize functional string to standard label."""
    if not raw:
        return None
    
    raw_upper = raw.upper()
    
    # Check for PBE
    if "PBX" in raw_upper and "PBC" in raw_upper:
        return "pbe"
    if "PBE" in raw_upper and "PBESOL" not in raw_upper:
        return "pbe"
    
    # Check for PBEsol
    if "PBESOL" in raw_upper:
        return "pbesol"
    
    # Check for SCAN
    if "SCAN" in raw_upper:
        return "scan"
    
    # Check for LDA (SLA PW without other functionals)
    if "SLA" in raw_upper and "PW" in raw_upper:
        if not any(x in raw_upper for x in ["PBX", "PBC", "SCAN", "PBE", "PBESOL"]):
            return "lda"
    
    return "unknown"


def _extract_from_upf_v1(content: str, result: Dict, filename: str) -> None:
    """Extract metadata from UPF v1 text blocks."""
    # PP_INFO block
    info_match = re.search(r'<PP_INFO>(.*?)</PP_INFO>', content, re.DOTALL | re.IGNORECASE)
    if info_match:
        info_text = info_match.group(1)
        info_lower = info_text.lower()
        
        # Type from PP_INFO
        if result["pseudo_type"] == "unknown":
            if "ultrasoft" in info_lower or "vanderbilt" in info_lower:
                if "paw" in info_lower and ("projector" in info_lower or "augmented" in info_lower):
                    result["pseudo_type"] = "paw"
                    result["metadata_source"]["type_from"] = "upf_v1_info"
                elif "ultrasoft" in info_lower:
                    result["pseudo_type"] = "uspp"
                    result["metadata_source"]["type_from"] = "upf_v1_info"
                elif "vanderbilt" in info_lower:
                    result["pseudo_type"] = "uspp"
                    result["metadata_source"]["type_from"] = "upf_v1_info"
            elif "oncv" in info_lower or "norm-conserving" in info_lower or "norm conserving" in info_lower:
                result["pseudo_type"] = "nc"
                result["metadata_source"]["type_from"] = "upf_v1_info"
            elif "paw" in info_lower and ("projector" in info_lower or "augmented" in info_lower):
                result["pseudo_type"] = "paw"
                result["metadata_source"]["type_from"] = "upf_v1_info"
            elif "atomic" in info_lower and "dal corso" in info_lower:
                if "gipaw" in filename.lower():
                    result["pseudo_type"] = "uspp"
                    result["pp_family_hint"] = "gipaw"
                    result["metadata_source"]["type_from"] = "upf_v1_info_filename"
                elif "paw" in filename.lower():
                    result["pseudo_type"] = "paw"
                    result["metadata_source"]["type_from"] = "upf_v1_info_filename"
        
        # Relativistic from PP_INFO
        if result["relativistic"] == "unknown":
            if "scalar-relativistic" in info_lower or "scalar relativistic" in info_lower:
                result["relativistic"] = "scalar_rel"
                result["metadata_source"]["relativistic_from"] = "upf_v1_info"
            elif "full-relativistic" in info_lower or "full relativistic" in info_lower or "dirac" in info_lower:
                result["relativistic"] = "full_rel"
                result["metadata_source"]["relativistic_from"] = "upf_v1_info"
            elif "non-relativistic" in info_lower or "non relativistic" in info_lower:
                result["relativistic"] = "nonrel"
                result["metadata_source"]["relativistic_from"] = "upf_v1_info"
        
        # Functional from PP_INFO
        if result["functional_raw"] is None:
            # Look for "Exchange-Correlation functional" line
            func_match = re.search(
                r'Exchange-Correlation\s+functional[:\s]*\n?\s*([A-Z\s]+)',
                info_text,
                re.IGNORECASE | re.MULTILINE
            )
            if func_match:
                func_raw = func_match.group(1).strip()
                # Clean up whitespace
                func_raw = ' '.join(func_raw.split())
                if func_raw:
                    result["functional_raw"] = func_raw
                    result["functional_norm"] = _normalize_functional(func_raw)
                    result["metadata_source"]["functional_from"] = "upf_v1_info"
        
        # Z valence from PP_INFO
        if result["z_valence"] is None:
            z_match = re.search(r'Z\s+valence[:\s]*(\d+\.?\d*)', info_text, re.IGNORECASE)
            if z_match:
                try:
                    result["z_valence"] = float(z_match.group(1))
                    result["metadata_source"]["z_valence_from"] = "upf_v1_info"
                except (ValueError, TypeError):
                    pass
    
    # PP_HEADER text block (v1 style)
    header_block_match = re.search(r'<PP_HEADER[^>]*>(.*?)</PP_HEADER>', content, re.DOTALL | re.IGNORECASE)
    if header_block_match and result["pseudo_type"] == "unknown":
        header_text = header_block_match.group(1)
        header_lower = header_text.lower()
        
        # Try to extract type from header text
        if "nc" in header_lower and "norm" in header_lower:
            result["pseudo_type"] = "nc"
            result["metadata_source"]["type_from"] = "upf_v1_header"
        elif "us" in header_lower and "ultrasoft" in header_lower:
            result["pseudo_type"] = "uspp"
            result["metadata_source"]["type_from"] = "upf_v1_header"
        elif "paw" in header_lower:
            result["pseudo_type"] = "paw"
            result["metadata_source"]["type_from"] = "upf_v1_header"
    
    # Filename heuristics (only if still unknown)
    if result["pseudo_type"] == "unknown":
        filename_lower = filename.lower()
        if "oncv" in filename_lower or "oncvpsp" in filename_lower:
            result["pp_family_hint"] = "oncv"
            result["pseudo_type"] = "nc"
            result["metadata_source"]["type_from"] = "filename"
        elif "rrkjus" in filename_lower:
            result["pp_family_hint"] = "rrkjus"
            result["pseudo_type"] = "uspp"
            result["metadata_source"]["type_from"] = "filename"
        elif "uspp" in filename_lower or ".us." in filename_lower:
            result["pseudo_type"] = "uspp"
            result["metadata_source"]["type_from"] = "filename"
        elif "paw" in filename_lower and ".paw." in filename_lower:
            result["pseudo_type"] = "paw"
            result["metadata_source"]["type_from"] = "filename"
        elif "sg15" in filename_lower:
            result["pp_family_hint"] = "sg15"
            result["pseudo_type"] = "nc"
            result["metadata_source"]["type_from"] = "filename"
        elif "psl" in filename_lower or "pslibrary" in filename_lower:
            if "paw" in filename_lower:
                result["pp_family_hint"] = "pslibrary"
                result["pseudo_type"] = "paw"
                result["metadata_source"]["type_from"] = "filename"
            elif ".us." in filename_lower:
                result["pp_family_hint"] = "pslibrary"
                result["pseudo_type"] = "uspp"
                result["metadata_source"]["type_from"] = "filename"
    
    # Relativistic from filename (if not from UPF)
    if result["relativistic"] == "unknown":
        filename_lower = filename.lower()
        if "fr" in filename_lower or "full" in filename_lower:
            result["relativistic"] = "full_rel"
            result["metadata_source"]["relativistic_from"] = "filename"
        elif "sr" in filename_lower or "scalar" in filename_lower:
            result["relativistic"] = "scalar_rel"
            result["metadata_source"]["relativistic_from"] = "filename"


def _extract_cutoffs_from_upf(content: str, result: Dict) -> None:
    """Extract suggested cutoffs from UPF content and store in cutoff_wfc_upf/cutoff_rho_upf."""
    # Look for suggested cutoff patterns in PP_INFO
    # Pattern: "Suggested minimum cutoff for wavefunctions:  48. Ry"
    wfc_match = re.search(
        r'Suggested\s+(?:minimum\s+)?cutoff\s+for\s+wavefunctions?[:\s]+(\d+\.?\d*)\s*Ry',
        content,
        re.IGNORECASE
    )
    if wfc_match:
        try:
            result["cutoff_wfc_upf"] = float(wfc_match.group(1))
        except (ValueError, TypeError):
            pass
    
    # Pattern: "Suggested minimum cutoff for charge density: 328. Ry"
    rho_match = re.search(
        r'Suggested\s+(?:minimum\s+)?cutoff\s+for\s+charge\s+density[:\s]+(\d+\.?\d*)\s*Ry',
        content,
        re.IGNORECASE
    )
    if rho_match:
        try:
            result["cutoff_rho_upf"] = float(rho_match.group(1))
        except (ValueError, TypeError):
            pass
    
    # Alternative pattern: "Suggested cutoff for wfc and rho: 48 328"
    combined_match = re.search(
        r'Suggested\s+cutoff\s+for\s+wfc\s+and\s+rho[:\s]+(\d+\.?\d*)\s+(\d+\.?\d*)',
        content,
        re.IGNORECASE
    )
    if combined_match:
        try:
            if result.get("cutoff_wfc_upf") == "na" or result.get("cutoff_wfc_upf") is None:
                result["cutoff_wfc_upf"] = float(combined_match.group(1))
            if result.get("cutoff_rho_upf") == "na" or result.get("cutoff_rho_upf") is None:
                result["cutoff_rho_upf"] = float(combined_match.group(2))
        except (ValueError, TypeError):
            pass


def classify_pseudo_type_from_upf(content_bytes: bytes, filename: str) -> Dict:
    """
    Legacy function - now calls extract_upf_metadata for backward compatibility.
    """
    metadata = extract_upf_metadata(content_bytes, filename)
    # Return in old format for compatibility
    return {
        "pseudo_type": metadata["pseudo_type"],
        "pp_family_hint": metadata["pp_family_hint"],
        "relativistic": metadata["relativistic"],
        "has_spin_orbit": metadata["has_spin_orbit"],
        "metadata_source": metadata["metadata_source"]
    }


def extract_cutoffs_from_sssp_json(sssp_json_path: Path, filename: str) -> Optional[Dict]:
    """Extract cutoffs from SSSP JSON metadata if available."""
    try:
        with open(sssp_json_path) as f:
            sssp_data = json.load(f)
        
        # Find entry by filename
        for element, metadata in sssp_data.items():
            if metadata.get("filename") == filename:
                json_name = sssp_json_path.name
                return {
                    "cutoff_wfc_normal": metadata.get("cutoff_wfc"),
                    "cutoff_rho_normal": metadata.get("cutoff_rho"),
                    "cutoff_wfc_low": "na",
                    "cutoff_wfc_high": "na",
                    "cutoff_rho_low": "na",
                    "cutoff_rho_high": "na",
                    "cutoff_source": f"sssp_json:{json_name}"
                }
    except Exception:
        pass
    
    return None


def extract_cutoffs_from_pseudodojo_json(pseudodojo_json_path: Path, element: str) -> Optional[Dict]:
    """
    Extract cutoffs from PseudoDojo JSON metadata if available.
    
    PseudoDojo JSON contains hl, hn, hh in Ha units.
    Convert to Ry by multiplying by 2.
    """
    try:
        with open(pseudodojo_json_path) as f:
            dojo_data = json.load(f)
        
        # Find entry by element symbol
        # Handle special cases like "H_r", "He_r" for full-relativistic
        element_data = None
        if element in dojo_data:
            element_data = dojo_data[element]
        else:
            # Try with _r suffix for full-relativistic
            element_r = f"{element}_r"
            if element_r in dojo_data:
                element_data = dojo_data[element_r]
        
        if element_data:
            hl = element_data.get("hl")
            hn = element_data.get("hn")
            hh = element_data.get("hh")
            
            json_name = pseudodojo_json_path.name
            result = {
                "cutoff_wfc_low": "na",
                "cutoff_wfc_normal": "na",
                "cutoff_wfc_high": "na",
                "cutoff_rho_low": "na",
                "cutoff_rho_normal": "na",
                "cutoff_rho_high": "na",
                "cutoff_source": f"pseudodojo_json:{json_name}"
            }
            
            # Convert from Ha to Ry (multiply by 2)
            if hl is not None and hl != "na":
                try:
                    result["cutoff_wfc_low"] = float(hl) * 2.0
                except (ValueError, TypeError):
                    pass
            
            if hn is not None and hn != "na":
                try:
                    result["cutoff_wfc_normal"] = float(hn) * 2.0
                except (ValueError, TypeError):
                    pass
            
            if hh is not None and hh != "na":
                try:
                    result["cutoff_wfc_high"] = float(hh) * 2.0
                except (ValueError, TypeError):
                    pass
            
            return result
    except Exception:
        pass
    
    return None


def find_pseudodojo_json_for_archive(archive_name: str, pseudo_info_dir: Path) -> Optional[Path]:
    """
    Find the corresponding PseudoDojo JSON file for an archive.
    
    Rule: Remove _upf.{ext} from archive name to get JSON name.
    """
    # Remove _upf.tgz or _upf.tar
    json_name = archive_name.replace("_upf.tgz", ".json").replace("_upf.tar", ".json")
    json_path = pseudo_info_dir / json_name
    
    if json_path.exists():
        return json_path
    
    return None


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
    
    # Classification tracking for report
    unknown_types: List[Dict] = []  # Files with unknown pseudo_type
    ambiguous_cases: List[Dict] = []  # Files with conflicting type indicators
    
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
            
            # Extract comprehensive UPF metadata
            metadata = extract_upf_metadata(file_bytes, filepath.name)
            
            # Extract cutoffs from SSSP JSON if available (overrides UPF if present)
            if manifest_entry.get("category") == "sssp":
                quality = manifest_entry.get("quality")
                if quality:
                    sssp_json_name = f"SSSP_1.3.0_PBE_{quality}.json"
                    # Try pseudo_info first, then pseudo_seed
                    sssp_json_path = repo_root / "pseudo_info" / sssp_json_name
                    if not sssp_json_path.exists():
                        sssp_json_path = pseudo_seed_dir / sssp_json_name
                    if sssp_json_path.exists():
                        cutoff_data = extract_cutoffs_from_sssp_json(sssp_json_path, filepath.name)
                        if cutoff_data:
                            metadata["cutoff_source"] = cutoff_data.get("cutoff_source")
                            # Set the 6 cutoff fields
                            metadata["cutoff_wfc_low"] = cutoff_data.get("cutoff_wfc_low", "na")
                            metadata["cutoff_wfc_normal"] = cutoff_data.get("cutoff_wfc_normal", "na")
                            metadata["cutoff_wfc_high"] = cutoff_data.get("cutoff_wfc_high", "na")
                            metadata["cutoff_rho_low"] = cutoff_data.get("cutoff_rho_low", "na")
                            metadata["cutoff_rho_normal"] = cutoff_data.get("cutoff_rho_normal", "na")
                            metadata["cutoff_rho_high"] = cutoff_data.get("cutoff_rho_high", "na")
            
            # Extract cutoffs from PseudoDojo JSON if available
            if manifest_entry.get("category") == "pseudo-dojo":
                archive_name = Path(manifest_entry["relative_path"]).name
                pseudo_info_dir = repo_root / "pseudo_info"
                dojo_json_path = find_pseudodojo_json_for_archive(archive_name, pseudo_info_dir)
                if dojo_json_path and dojo_json_path.exists():
                    cutoff_data = extract_cutoffs_from_pseudodojo_json(dojo_json_path, element)
                    if cutoff_data:
                        # Update the 6 cutoff fields
                        metadata["cutoff_wfc_low"] = cutoff_data.get("cutoff_wfc_low", "na")
                        metadata["cutoff_wfc_normal"] = cutoff_data.get("cutoff_wfc_normal", "na")
                        metadata["cutoff_wfc_high"] = cutoff_data.get("cutoff_wfc_high", "na")
                        metadata["cutoff_rho_low"] = cutoff_data.get("cutoff_rho_low", "na")
                        metadata["cutoff_rho_normal"] = cutoff_data.get("cutoff_rho_normal", "na")
                        metadata["cutoff_rho_high"] = cutoff_data.get("cutoff_rho_high", "na")
                        metadata["cutoff_source"] = cutoff_data.get("cutoff_source")
            
            # Add or update file record
            if sha256 not in files_by_sha256:
                file_record = {
                    "sha256": sha256,
                    "sha_family": sha_family,
                    "element": element,
                    "size_bytes": len(file_bytes),
                    "upf_format": upf_format,
                    "pseudo_type": metadata["pseudo_type"],
                    "relativistic": metadata["relativistic"],
                    "has_spin_orbit": metadata["has_spin_orbit"],
                    "is_ultrasoft": metadata["is_ultrasoft"],
                    "is_paw": metadata["is_paw"],
                    "has_gipaw": metadata["has_gipaw"],
                    "paw_as_gipaw": metadata["paw_as_gipaw"],
                    "core_correction": metadata["core_correction"],
                    "has_wfc": metadata["has_wfc"],
                    "functional_raw": metadata["functional_raw"],
                    "functional_norm": metadata["functional_norm"],
                    "z_valence": metadata["z_valence"],
                    "number_of_wfc": metadata["number_of_wfc"],
                    "number_of_proj": metadata["number_of_proj"],
                    "cutoff_source": metadata["cutoff_source"],
                    "cutoff_wfc_low": metadata["cutoff_wfc_low"],
                    "cutoff_wfc_normal": metadata["cutoff_wfc_normal"],
                    "cutoff_wfc_high": metadata["cutoff_wfc_high"],
                    "cutoff_rho_low": metadata["cutoff_rho_low"],
                    "cutoff_rho_normal": metadata["cutoff_rho_normal"],
                    "cutoff_rho_high": metadata["cutoff_rho_high"],
                    "cutoff_wfc_upf": metadata["cutoff_wfc_upf"],
                    "cutoff_rho_upf": metadata["cutoff_rho_upf"],
                    "basenames": []
                }
                
                # Add optional fields
                if metadata["pp_family_hint"]:
                    file_record["pp_family_hint"] = metadata["pp_family_hint"]
                
                file_record["metadata_source"] = metadata["metadata_source"]
                
                files_by_sha256[sha256] = file_record
                
                # Track unknown types for report
                if metadata["pseudo_type"] == "unknown":
                    unknown_types.append({
                        "sha256": sha256,
                        "basename": filepath.name,
                        "archive": rel_path,
                        "path_in_archive": str(rel_file_path),
                        "upf_format": upf_format,
                        "header_snippet": file_text[:500] if len(file_text) > 500 else file_text
                    })
            
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
        "schema_version": "1.5.0",
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
    
    # Generate classification report
    report_path = repo_root / "docs" / "PSEUDO_CLASSIFICATION_REPORT.md"
    report_path.parent.mkdir(exist_ok=True)
    
    # Statistics
    type_counts = defaultdict(int)
    rel_counts = defaultdict(int)
    functional_norm_counts = defaultdict(int)
    has_gipaw_counts = defaultdict(int)
    z_valence_present = 0
    functional_raw_present = 0
    cutoff_wfc_normal_present = 0
    cutoff_rho_normal_present = 0
    
    for f in files_list:
        type_counts[f.get("pseudo_type", "unknown")] += 1
        rel_counts[f.get("relativistic", "unknown")] += 1
        if f.get("functional_norm"):
            functional_norm_counts[f.get("functional_norm")] += 1
        if f.get("has_gipaw") != "unknown":
            has_gipaw_counts[str(f.get("has_gipaw"))] += 1
        if f.get("z_valence") is not None:
            z_valence_present += 1
        if f.get("functional_raw") is not None:
            functional_raw_present += 1
        if f.get("cutoff_wfc_normal") != "na" and f.get("cutoff_wfc_normal") is not None:
            cutoff_wfc_normal_present += 1
        if f.get("cutoff_rho_normal") != "na" and f.get("cutoff_rho_normal") is not None:
            cutoff_rho_normal_present += 1
    
    with open(report_path, "w") as f:
        f.write("# Pseudopotential Classification Report\n\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Total unique files: {len(files_list)}\n")
        f.write(f"- Total occurrences: {len(occurrences_list)}\n\n")
        
        f.write("## Pseudopotential Type Distribution\n\n")
        for ptype, count in sorted(type_counts.items()):
            f.write(f"- **{ptype.upper()}**: {count} files\n")
        
        f.write("\n## Relativistic Treatment Distribution\n\n")
        for rel, count in sorted(rel_counts.items()):
            f.write(f"- **{rel}**: {count} files\n")
        
        f.write("\n## Functional Distribution\n\n")
        f.write(f"- Files with functional_raw: {functional_raw_present} / {len(files_list)}\n")
        if functional_norm_counts:
            for func, count in sorted(functional_norm_counts.items()):
                f.write(f"- **{func}**: {count} files\n")
        
        f.write("\n## Metadata Coverage\n\n")
        f.write(f"- Z valence present: {z_valence_present} / {len(files_list)} ({100*z_valence_present/len(files_list):.1f}%)\n")
        f.write(f"- Functional raw present: {functional_raw_present} / {len(files_list)} ({100*functional_raw_present/len(files_list):.1f}%)\n")
        f.write(f"- Cutoff WFC normal present: {cutoff_wfc_normal_present} / {len(files_list)} ({100*cutoff_wfc_normal_present/len(files_list):.1f}%)\n")
        f.write(f"- Cutoff rho normal present: {cutoff_rho_normal_present} / {len(files_list)} ({100*cutoff_rho_normal_present/len(files_list):.1f}%)\n")
        f.write(f"- Has GIPAW flag: {sum(has_gipaw_counts.values())} / {len(files_list)} ({100*sum(has_gipaw_counts.values())/len(files_list):.1f}%)\n")
        
        f.write("\n## Unknown Type Cases\n\n")
        if unknown_types:
            f.write(f"Found {len(unknown_types)} files with unknown pseudo_type:\n\n")
            for case in unknown_types[:20]:  # Limit to first 20
                f.write(f"### {case['basename']}\n\n")
                f.write(f"- Archive: `{case['archive']}`\n")
                f.write(f"- Path: `{case['path_in_archive']}`\n")
                f.write(f"- UPF Format: {case['upf_format']}\n")
                f.write(f"- Header snippet:\n```\n{case['header_snippet'][:300]}...\n```\n\n")
            if len(unknown_types) > 20:
                f.write(f"\n... and {len(unknown_types) - 20} more unknown cases.\n\n")
        else:
            f.write("✅ All files successfully classified!\n\n")
        
        f.write("## Ambiguous Cases\n\n")
        if ambiguous_cases:
            f.write(f"Found {len(ambiguous_cases)} files with conflicting type indicators:\n\n")
            for case in ambiguous_cases:
                f.write(f"- {case['basename']}: {case['conflict']}\n")
        else:
            f.write("✅ No ambiguous cases found.\n\n")
    
    # Print summary
    print("=" * 80)
    print("SUCCESS")
    print("=" * 80)
    print(f"Archives processed:     {archive_count}")
    print(f"UPF files scanned:      {upf_files_scanned}")
    print(f"Unique sha256 files:    {len(files_list)}")
    print(f"Occurrences:            {len(occurrences_list)}")
    print(f"Warnings:               {len(warnings)}")
    print(f"Unknown types:         {len(unknown_types)}")
    print(f"Index written to:       {output_path}")
    print(f"Report written to:     {report_path}")
    print("=" * 80)
    
    # Clean up extract directory
    if extract_dir.exists():
        shutil.rmtree(extract_dir)


if __name__ == "__main__":
    main()
