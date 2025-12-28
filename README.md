# qmatsuite-assets

Repository containing curated pseudopotential libraries and metadata for QMatSuite.

## Contents

- **`pseudo_seed/`**: Curated pseudopotential archives and metadata files
  - SSSP (Standard Solid-State Pseudopotentials)
  - PseudoDojo collections (ONCVPSP and PAW)
  - GIPAW pseudopotentials
  - SCAN TM pseudopotentials

## Index Files

- **`MANIFEST_PSEUDO_SEED.json`**: Archive-level manifest with SHA256 checksums and metadata
- **`PSEUDO_FILE_INDEX.json`**: Normalized per-UPF file index (SHA256-keyed, deduplicated)

## Documentation

See [`DOC_PSEUDO_SEED.md`](DOC_PSEUDO_SEED.md) for detailed documentation on:
- Library contents and naming conventions
- How to regenerate manifests and indices
- File verification and usage examples

## Scripts

- `scripts/build_manifest_pseudo_seed.py`: Generate archive manifest
- `scripts/build_pseudo_file_index.py`: Generate normalized UPF file index

## License

See [`COPYRIGHT_AND_DISCLAIMER.md`](COPYRIGHT_AND_DISCLAIMER.md) for attribution and legal notices.