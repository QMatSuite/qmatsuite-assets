# PseudoDojo JSON Metadata File Mapping

## Overview

Based on analysis of the [PseudoDojo website source code](https://github.com/abinit/pseudo_dojo/tree/master/website), this document maps JSON metadata files to archive files. The JSON files are used by the website to display metadata (cutoff hints, test results) on the periodic table interface, and the download button links to the corresponding archive files.

## How the Website Works

### JSON File Loading
The website loads JSON files based on user selections (type, XC functional, accuracy):
- JavaScript function `load_set_info()` (line 142-152 in `dojo-tools.js`) constructs the JSON filename as: `{type}_{xcf}_{acc}.json`
- This JSON is used to populate the periodic table with metadata for each element

### Download Button Behavior
When clicking the "Download" button (line 1690-1705 in `index.html`):
- The website constructs the download URL as: `pseudos/{typ}_{xcf}_{acc}_{fmt}.tgz`
- For UPF format, this becomes: `pseudos/{typ}_{xcf}_{acc}_upf.tgz`
- The archive is downloaded from the `pseudos/` directory on the server

### Type Selector Mapping
The website uses simplified type names in the selector, which map to archive names:
- `nc-sr-04` → archives: `nc-sr-04_*_upf.tgz`
- `nc-fr-04` → archives: `nc-fr-04_*_upf.tar`
- `paw` → archives: `paw-sr-11_*_upf.tgz` (note: website uses "paw" but archives use "paw-sr-11")

**Note**: The actual JSON files downloaded from the official website use the full naming convention (e.g., `paw-sr-11_pbe_standard.json`), not the simplified format used in the website's JavaScript code.

## Complete JSON to Archive Mapping

All JSON files are located in `pseudo_info/` and follow a simple naming pattern: remove `_upf.{ext}` from the archive name to get the JSON filename.

### Norm-Conserving (nc-*) Archives

| JSON File | Archive File |
|----------|-------------|
| `nc-sr-04_pbe_standard.json` | `nc-sr-04_pbe_standard_upf.tgz` |
| `nc-sr-04_pbe_stringent.json` | `nc-sr-04_pbe_stringent_upf.tgz` |
| `nc-sr-04_pbesol_standard.json` | `nc-sr-04_pbesol_standard_upf.tgz` |
| `nc-sr-04_pbesol_stringent.json` | `nc-sr-04_pbesol_stringent_upf.tgz` |
| `nc-sr-04_pw_standard.json` | `nc-sr-04_pw_standard_upf.tgz` |
| `nc-sr-04_pw_stringent.json` | `nc-sr-04_pw_stringent_upf.tgz` |
| `nc-fr-04_pbe_standard.json` | `nc-fr-04_pbe_standard_upf.tar` |
| `nc-fr-04_pbe_stringent.json` | `nc-fr-04_pbe_stringent_upf.tar` |
| `nc-fr-04_pbesol_standard.json` | `nc-fr-04_pbesol_standard_upf.tar` |
| `nc-fr-04_pbesol_stringent.json` | `nc-fr-04_pbesol_stringent_upf.tar` |

### PAW (paw-*) Archives

| JSON File | Archive File |
|----------|-------------|
| `paw-sr-11_lda_standard.json` | `paw-sr-11_lda_standard_upf.tgz` |
| `paw-sr-11_lda_stringent.json` | `paw-sr-11_lda_stringent_upf.tgz` |
| `paw-sr-11_pbe_standard.json` | `paw-sr-11_pbe_standard_upf.tgz` |
| `paw-sr-11_pbe_stringent.json` | `paw-sr-11_pbe_stringent_upf.tgz` |
| `paw-sr-11_pbesol_standard.json` | `paw-sr-11_pbesol_standard_upf.tgz` |
| `paw-sr-11_pbesol_stringent.json` | `paw-sr-11_pbesol_stringent_upf.tgz` |

**Summary**: 16 JSON files mapping to 16 archives (100% coverage)

## JSON File Pattern

**For all archives**: JSON filename = `{type}-{relativistic}-{version}_{xc}_{quality}.json`
- Remove `_upf.{ext}` from archive name to get JSON name
- Example: `nc-sr-04_pbe_standard_upf.tgz` → `nc-sr-04_pbe_standard.json`
- Example: `paw-sr-11_pbe_standard_upf.tgz` → `paw-sr-11_pbe_standard.json`

**Note**: While the website's JavaScript code uses simplified names (e.g., `paw_pbe_standard.json`), the actual JSON files downloaded from the official website use the full naming convention matching the archive names.

## JSON File Structure

The JSON files contain element-by-element metadata with the following keys:
- `hh`: High cutoff energy hint (Ha)
- `hn`: Normal cutoff energy hint (Ha)  
- `hl`: Low cutoff energy hint (Ha)
- `nv`: Number of valence shells
- `d`: Delta gauge test result (meV)
- `dp`: Normalized delta gauge
- `gb`: GBRV fcc/bcc average (%)

Example entry:
```json
{
  "Ni": {
    "d": "1.1",
    "hh": 55.0,
    "hn": 49.0,
    "nv": 4,
    "hl": 45.0,
    "dp": "1.5",
    "gb": "-0.10"
  }
}
```

## Mapping Rules

**Simple rule for all archives**: Remove `_upf.{ext}` (or `_upf.tar`) from archive name to get JSON name.

Examples:
- `nc-sr-04_pbe_standard_upf.tgz` → `nc-sr-04_pbe_standard.json`
- `nc-fr-04_pbe_standard_upf.tar` → `nc-fr-04_pbe_standard.json`
- `paw-sr-11_pbe_standard_upf.tgz` → `paw-sr-11_pbe_standard.json`
- `paw-sr-11_lda_standard_upf.tgz` → `paw-sr-11_lda_standard.json`

**Note**: The website's JavaScript code uses simplified type names in the selector (e.g., `paw` instead of `paw-sr-11`), but the actual JSON files use the full naming convention that matches the archive names.

## Current Status

**JSON Files Location**: All PseudoDojo JSON metadata files are stored in the `pseudo_info/` directory:
- 10 NC JSON files (matching all NC archives)
- 6 PAW JSON files (matching all PAW archives)
- Total: 16 JSON files, all matching the 16 PseudoDojo archives

**Coverage**: 100% - Every PseudoDojo archive has a corresponding JSON metadata file.

The JSON files contain element-by-element metadata including cutoff hints (`hh`, `hn`, `hl`), test results (`d`, `dp`, `gb`), and valence shell information (`nv`).

## References

- PseudoDojo Main Site: https://www.pseudo-dojo.org
- PseudoDojo FAQ: https://www.pseudo-dojo.org/faq.html
- PseudoDojo GitHub: https://github.com/abinit/pseudo_dojo
- Website Folder: https://github.com/abinit/pseudo_dojo/tree/master/website

