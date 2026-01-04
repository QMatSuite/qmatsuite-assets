# Scripts

This directory contains utility scripts for managing pseudopotential assets.

## scrape_qe_legacy_upf.py

Scrapes and downloads UPF pseudopotential files from Quantum ESPRESSO legacy tables.

### Sources

1. **ps-library** - PSLibrary pseudopotentials
2. **hartwigesen-goedecker-hutter-pp** - Hartwigsen-Goedecker-Hutter pseudopotentials
3. **fhi-pp-from-abinit-web-site** - FHI pseudopotentials from ABINIT website

### Usage

```bash
# Dry-run to see what would be downloaded
python3 scripts/scrape_qe_legacy_upf.py --dry-run

# Download all files (default: all three sources)
python3 scripts/scrape_qe_legacy_upf.py

# Download from specific sources only
python3 scripts/scrape_qe_legacy_upf.py --sources ps-library

# Limit for testing
python3 scripts/scrape_qe_legacy_upf.py --limit-elements 5 --limit-files 10

# Custom destination and rate limiting
python3 scripts/scrape_qe_legacy_upf.py --dest custom/path --rate 3 --max-workers 4
```

### Output Structure

```
temp/qe-legacy-upf/
├── ps-library/
│   ├── manifest.json
│   ├── file1.UPF
│   ├── file2.UPF
│   └── ...
├── hartwigesen-goedecker-hutter-pp/
│   ├── manifest.json
│   ├── file1.UPF
│   └── ...
└── fhi-pp-from-abinit-web-site/
    ├── manifest.json
    ├── file1.UPF
    └── ...
```

### Manifest Format

Each `manifest.json` contains an array of entries:

```json
[
  {
    "source": "ps-library",
    "element": "ac",
    "filename": "Ac.pbe-spfn-kjpaw_psl.1.0.0.UPF",
    "url": "https://pseudopotentials.quantum-espresso.org/upf_files/...",
    "bytes": 3592613,
    "sha256": "c3b3cb9c817eb7a3f658d1650949106852db0eeecbaa6833142aadacc0eab5ac"
  }
]
```

### Features

- **Idempotent**: Re-running skips already-downloaded files (checks manifest)
- **Rate limiting**: Respects server with configurable requests/second
- **Retry logic**: Exponential backoff on transient errors
- **Validation**: Quick sanity check for UPF file format
- **Filename collision handling**: Adds hash suffix if same filename from different URLs
- **Progress reporting**: Shows progress every 50 files

### Options

- `--dest`: Destination directory (default: `temp/qe-legacy-upf`)
- `--sources`: Sources to scrape (default: all three)
- `--max-workers`: Concurrent downloads (default: 8)
- `--rate`: Rate limit in requests/second (default: 5.0)
- `--timeout`: Request timeout in seconds (default: 30)
- `--retries`: Number of retries (default: 5)
- `--dry-run`: Print counts only, don't download
- `--limit-elements`: Limit elements per source (for testing)
- `--limit-files`: Limit files per source (for testing)
- `--force`: Re-download existing files

### Statistics (from dry-run)

- **ps-library**: 94 elements, ~1422 UPF files
- **hartwigesen-goedecker-hutter-pp**: 85 elements, ~266 UPF files
- **fhi-pp-from-abinit-web-site**: 99 elements, ~202 UPF files
- **Total**: 278 elements, ~1890 UPF files

