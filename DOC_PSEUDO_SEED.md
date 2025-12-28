# Pseudopotential Seed Directory

## Overview

The `pseudo_seed/` directory contains curated pseudopotential libraries and metadata tables for use with QMatSuite. This directory serves as a **seed** or **reference collection** that can be used for offline installation, local project setup, and ensuring reproducibility in computational materials science workflows.

## What This Directory Is

- **A curated collection** of well-established pseudopotential libraries
- **A seed for offline workflows** when network access is limited or unavailable
- **A reference for reproducibility** - specific versions are tracked for consistent results
- **A starting point** for project-local pseudopotential management

## What This Directory Is NOT

- **Not a complete database** - it contains selected libraries, not all available pseudopotentials
- **Not automatically updated** - contents are manually curated and versioned
- **Not a replacement** for upstream sources - users should refer to original providers for latest versions and documentation
- **Not a license grant** - all materials remain property of their respective upstream providers

## How QMatSuite Uses This Seed

QMatSuite can use `pseudo_seed/` in several ways:

1. **Offline Installation**: Copy pseudopotentials from the seed into a local store or cache directory
2. **Project Setup**: Extract specific pseudopotentials into project-local directories for reproducibility
3. **Verification**: Use SHA256 hashes in the manifest to verify file integrity
4. **Discovery**: Reference the manifest to find available pseudopotentials by category, functional, or quality

**Note for Main QMatSuite Repository**: In the main QMatSuite repository, any local copy of this seed (e.g., `temp/assets/pseudo_seed` or similar) should be added to `.gitignore` to avoid committing large binary files. This `qmatsuite-assets` repository is the canonical source for these assets.

## Library Contents

### 1. SSSP (Standard Solid-State Pseudopotentials)

**Purpose**: High-quality, tested pseudopotentials optimized for solid-state calculations with Quantum ESPRESSO.

**Flavors**:
- **Efficiency**: Lower energy cutoffs, faster calculations, suitable for high-throughput screening
- **Precision**: Higher energy cutoffs, more accurate results, suitable for final production calculations

**Files in this directory**:
- `SSSP_1.3.0_PBE_efficiency.tar.gz` - Archive containing efficiency pseudopotentials
- `SSSP_1.3.0_PBE_efficiency.json` - Cutoff table metadata
- `SSSP_1.3.0_PBE_precision.tar.gz` - Archive containing precision pseudopotentials
- `SSSP_1.3.0_PBE_precision.json` - Cutoff table metadata

**Upstream References**:
- Efficiency table: https://legacy.materialscloud.org/discover/sssp/table/efficiency
- Precision table: https://legacy.materialscloud.org/discover/sssp/table/precision

### 2. PseudoDojo

**Purpose**: Comprehensive pseudopotential library with multiple flavors for different use cases, including both norm-conserving (ONCVPSP) and PAW (JTH v1.1) pseudopotentials.

**Naming Convention**:
- **Type**: `nc-` = norm-conserving (ONCVPSP), `paw-` = PAW (JTH v1.1)
- **Relativistic**: `sr` = scalar-relativistic, `fr` = full-relativistic
- **Version**: `04` = ONCVPSP v0.4, `11` = JTH v1.1
- **XC Functional**: `pbe`, `pbesol`, `lda`, `pw` (LDA with PW exchange)
- **Quality**: `standard` = standard quality, `stringent` = higher quality (stricter tests)

**Files in this directory**:
- **Norm-conserving (nc)**: Multiple archives with patterns like:
  - `nc-sr-04_*_standard_upf.tgz` / `nc-sr-04_*_stringent_upf.tgz` (scalar-relativistic)
  - `nc-fr-04_*_standard_upf.tar` / `nc-fr-04_*_stringent_upf.tar` (full-relativistic)
  - XC functionals: PBE, PBEsol, PW (LDA)
- **PAW (paw)**: Multiple archives with patterns like:
  - `paw-sr-11_*_standard_upf.tgz` / `paw-sr-11_*_stringent_upf.tgz` (scalar-relativistic)
  - XC functionals: LDA, PBE, PBEsol

**Upstream References**:
- Main site: https://www.pseudo-dojo.org
- FAQ: https://www.pseudo-dojo.org/faq.html

### 3. GIPAW Pseudopotentials (Davide Ceresoli)

**Purpose**: Pseudopotentials optimized for GIPAW (Gauge Including Projector Augmented Wave) calculations, particularly useful for NMR and EPR spectroscopy.

**Files in this directory**:
- `GIPAW_DavideCeresoli.zip` - Archive containing GIPAW pseudopotentials

**Upstream References**:
- https://sites.google.com/site/dceresoli/pseudopotentials

### 4. SCAN TM Pseudopotentials (Yao Yi 2017)

**Purpose**: Pseudopotentials for the SCAN (Strongly Constrained and Appropriately Normed) meta-GGA functional, including transition metals.

**Files in this directory**:
- `SCAN_TM_YiYao_2017.zip` - Archive containing SCAN pseudopotentials for transition metals

**Upstream References**:
- https://yaoyi92.github.io/scan-tm-pseudopotentials.html

### 5. Quantum ESPRESSO Resources (Reference)

**Purpose**: Reference pages maintained by the Quantum ESPRESSO project listing pseudopotential resources and best practices.

**Upstream References**:
- Other resources: https://www.quantum-espresso.org/other-resources/
- Pseudopotentials page: https://www.quantum-espresso.org/pseudopotentials/

## Manifest and Automation

### Archive Manifest

The `MANIFEST_PSEUDO_SEED.json` file contains:
- File paths, sizes, and SHA256 checksums for verification
- Metadata (category, library name, version, flavors)
- Upstream URLs for attribution
- License information (when available)

To regenerate or update the manifest, run:
```bash
python3 scripts/build_manifest_pseudo_seed.py
```

The script is deterministic and platform-independent, ensuring consistent manifests across different systems.

### Per-UPF File Index

The `PSEUDO_FILE_INDEX.json` file provides a normalized index of every individual UPF pseudopotential file extracted from all archives. The index uses **SHA256 as the primary key**, allowing one file (same content) to appear in multiple archives with different names.

**Schema (v1.1.0):**
- `files[]`: Unique file records keyed by SHA256, containing:
  - `sha256`: Content identity hash
  - `sha_token`: Normalized content fingerprint (whitespace-removed)
  - `element`: Element symbol (validated from both filename and UPF header)
  - `size_bytes`: File size
  - `upf_format`: "upf1", "upf2", or "unknown"
  - `basenames[]`: All basenames seen for this file across archives (sorted)
- `occurrences[]`: One record per (sha256, archive, path) combination, containing:
  - `sha256`: Reference to file record
  - `archive`: Archive metadata (name, relative_path, sha256)
  - `path_in_archive`: Path within the archive
  - `library`: Library metadata (category, name, version, XC, quality, etc.)
- `source_manifest`: Reference to the manifest used (path and SHA256)

To regenerate the index, run:
```bash
python3 scripts/build_pseudo_file_index.py
```

This script:
- **Validates archive SHA256** against `MANIFEST_PSEUDO_SEED.json` before extraction
- Extracts all archives to `temp/extract/` (gitignored)
- Validates UPF files (element parsing from both header and filename must match)
- Creates normalized index with deduplication by content (SHA256)
- Performs validation checks (all occurrences reference valid files, etc.)
- Fails with detailed error reports if any validation fails

The index is useful for:
- Discovering available pseudopotentials by element, library, or functional
- Detecting duplicate files across archives (same SHA256)
- Building lookup tables for pseudopotential selection
- Ensuring reproducibility across installations
- Understanding which files appear in multiple libraries

**Current Statistics** (as of last generation):
- 1,523 UPF files scanned across 20 archives
- 1,016 unique files (by SHA256) - showing 507 duplicate files across archives
- 2 files have multiple basenames (same content, different names in different archives)

**Example Usage:**
```python
import json

# Load the index
with open('PSEUDO_FILE_INDEX.json') as f:
    index = json.load(f)

# Find all files for a specific element
ag_files = [f for f in index['files'] if f['element'] == 'Ag']
print(f"Found {len(ag_files)} unique Ag pseudopotentials")

# Find all occurrences of a specific file (by SHA256)
sha256 = "4aa92f22d77ad73be9b30764510837fc49e4479636a796ae1e56aed5a464745f"
occurrences = [o for o in index['occurrences'] if o['sha256'] == sha256]
print(f"File appears in {len(occurrences)} archive(s)")

# Find all PBE pseudopotentials
pbe_files = [o for o in index['occurrences'] if o['library'].get('xc') == 'pbe']
print(f"Found {len(pbe_files)} PBE pseudopotential occurrences")
```

## File Verification

All files in this directory have SHA256 checksums recorded in `MANIFEST_PSEUDO_SEED.json`. These can be used to:
- Verify file integrity after download or transfer
- Detect corruption or tampering
- Ensure reproducibility across installations

## License and Attribution

See `COPYRIGHT_AND_DISCLAIMER.md` for detailed attribution and legal notices. All pseudopotentials remain the property of their respective upstream providers. This repository provides them for user convenience under the terms specified by the original providers.

