#!/usr/bin/env python3
"""
Scrape and download UPF pseudopotential files from Quantum ESPRESSO legacy tables.

Sources:
1. ps-library
2. hartwigesen-goedecker-hutter-pp
3. fhi-pp-from-abinit-web-site
"""

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://pseudopotentials.quantum-espresso.org/legacy_tables"
UPF_BASE_URL = "https://pseudopotentials.quantum-espresso.org/upf_files"
USER_AGENT = "Mozilla/5.0 (compatible; QE-UPF-Scraper/1.0; +https://github.com/qmat-suite/qmatsuite-assets)"


class ElementLinkParser(HTMLParser):
    """Parse element page links from a source base page."""
    
    def __init__(self, source_path):
        super().__init__()
        self.source_path = source_path
        self.element_links = []
        self.in_table = False
        self.current_link = None
        self.current_text = ""
    
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href:
                self.current_link = href
                self.current_text = ""
    
    def handle_data(self, data):
        if self.current_link:
            self.current_text += data.strip()
    
    def handle_endtag(self, tag):
        if tag == 'a' and self.current_link:
            # Element links are typically single or two-letter symbols (H, He, Li, etc.)
            # They should point to paths under the source
            text = self.current_text.strip()
            href = self.current_link.strip()
            
            # Check if this looks like an element link
            # Element symbols are 1-2 letters, sometimes with numbers (e.g., "H", "He", "Li")
            if re.match(r'^[A-Z][a-z]?[0-9]?$', text, re.IGNORECASE):
                # Check if href points to an element page under this source
                if self.source_path in href or href.startswith('/'):
                    # Normalize: remove leading slash, convert to lowercase
                    element = text.lower()
                    if element:
                        self.element_links.append((element, href))
            
            self.current_link = None
            self.current_text = ""


class UPFLinkParser(HTMLParser):
    """Parse UPF file links from an element page."""
    
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.upf_links = []
        self.current_link = None
        self.current_text = ""
    
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href:
                self.current_link = href
                self.current_text = ""
    
    def handle_data(self, data):
        if self.current_link:
            self.current_text += data.strip()
    
    def handle_endtag(self, tag):
        if tag == 'a' and self.current_link:
            href = self.current_link.strip()
            text = self.current_text.strip()
            
            # Check if this is a UPF link (case-insensitive)
            if re.search(r'\.upf(\.gz)?$', href, re.IGNORECASE) or \
               re.search(r'\.upf(\.gz)?$', text, re.IGNORECASE):
                # Resolve relative URLs
                full_url = urljoin(self.base_url, href)
                self.upf_links.append((text, full_url))
            
            self.current_link = None
            self.current_text = ""


class RateLimiter:
    """Simple token bucket rate limiter."""
    
    def __init__(self, rate_per_sec):
        self.rate = rate_per_sec
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0
        self.last_request_time = 0
        self.lock = __import__('threading').Lock()
    
    def wait(self):
        """Wait if necessary to respect rate limit."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()


def fetch_url(url, timeout=30, retries=5, rate_limiter=None):
    """Fetch URL with retries and rate limiting."""
    if rate_limiter:
        rate_limiter.wait()
    
    # Create SSL context that doesn't verify certificates (for legacy sites)
    # In production, you might want to use ssl.create_default_context()
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    for attempt in range(retries):
        try:
            req = Request(url, headers={'User-Agent': USER_AGENT})
            with urlopen(req, timeout=timeout, context=ssl_context) as response:
                return response.read()
        except (HTTPError, URLError, OSError) as e:
            if attempt < retries - 1:
                # Exponential backoff
                wait_time = (2 ** attempt) * 0.5
                time.sleep(wait_time)
            else:
                raise
    return None


def get_element_pages(source, base_url=BASE_URL):
    """Get all element page URLs for a source."""
    source_url = f"{base_url}/{source}"
    print(f"Fetching element pages from: {source_url}")
    
    try:
        content = fetch_url(source_url)
        if not content:
            print(f"  ERROR: Failed to fetch {source_url}")
            return []
        
        parser = ElementLinkParser(source)
        parser.feed(content.decode('utf-8', errors='ignore'))
        
        # Deduplicate and normalize
        seen = set()
        element_pages = []
        for element, href in parser.element_links:
            # Resolve relative URLs
            full_url = urljoin(source_url + "/", href)
            if full_url not in seen:
                seen.add(full_url)
                element_pages.append((element, full_url))
        
        print(f"  Found {len(element_pages)} element pages")
        return sorted(element_pages, key=lambda x: x[0])
    
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def get_upf_links_from_element_page(element_url, element=None):
    """Extract all UPF file links from an element page."""
    try:
        content = fetch_url(element_url)
        if not content:
            return []
        
        parser = UPFLinkParser(element_url)
        parser.feed(content.decode('utf-8', errors='ignore'))
        
        # Deduplicate by URL
        seen = set()
        upf_links = []
        for text, url in parser.upf_links:
            if url not in seen:
                seen.add(url)
                upf_links.append((text, url))
        
        return upf_links
    
    except Exception as e:
        print(f"  WARNING: Failed to fetch {element_url}: {e}")
        return []


def compute_sha256(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_upf_file(filepath):
    """Quick validation: check if file contains 'UPF' in first 4KB."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(4096)
            text = chunk.decode('utf-8', errors='ignore')
            return 'UPF' in text or '<UPF' in text
    except Exception:
        return False


def download_file(url, dest_path, force=False, rate_limiter=None, timeout=30):
    """Download a file with atomic write and validation."""
    # Check if file exists and is non-empty
    if not force and dest_path.exists() and dest_path.stat().st_size > 0:
        return {'status': 'skipped', 'path': str(dest_path)}
    
    try:
        # Download to temp file first
        temp_path = dest_path.with_suffix(dest_path.suffix + '.tmp')
        
        content = fetch_url(url, timeout=timeout, rate_limiter=rate_limiter)
        if not content:
            return {'status': 'failed', 'error': 'Failed to fetch'}
        
        # Write to temp file and compute hash
        sha256 = hashlib.sha256()
        with open(temp_path, 'wb') as f:
            f.write(content)
            sha256.update(content)
        
        # Validate
        if not validate_upf_file(temp_path):
            temp_path.unlink()
            return {'status': 'failed', 'error': 'Invalid UPF file'}
        
        # Atomic rename
        temp_path.replace(dest_path)
        
        return {
            'status': 'downloaded',
            'path': str(dest_path),
            'bytes': len(content),
            'sha256': sha256.hexdigest()
        }
    
    except Exception as e:
        # Clean up temp file if it exists
        temp_path = dest_path.with_suffix(dest_path.suffix + '.tmp')
        if temp_path.exists():
            temp_path.unlink()
        return {'status': 'failed', 'error': str(e)}


def handle_filename_collision(dest_dir, filename, url):
    """Handle filename collisions by adding a short hash suffix."""
    base_path = dest_dir / filename
    
    if not base_path.exists():
        return base_path
    
    # Generate short hash from URL
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        new_filename = f"{name_parts[0]}_{url_hash}.{name_parts[1]}"
    else:
        new_filename = f"{filename}_{url_hash}"
    
    return dest_dir / new_filename


def load_existing_manifest(dest_path):
    """Load existing manifest if it exists."""
    manifest_path = dest_path / 'manifest.json'
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def scrape_source(source, dest_dir, dry_run=False, rate_limiter=None, 
                  limit_elements=None, limit_files=None, timeout=30, max_workers=8):
    """Scrape a single source."""
    print(f"\n{'='*80}")
    print(f"Processing source: {source}")
    print(f"{'='*80}")
    
    dest_path = Path(dest_dir) / source
    dest_path.mkdir(parents=True, exist_ok=True)
    
    # Load existing manifest to check for already-downloaded URLs
    existing_manifest = load_existing_manifest(dest_path)
    downloaded_urls = {entry['url']: entry for entry in existing_manifest}
    
    # Step 1: Get element pages
    element_pages = get_element_pages(source)
    
    if limit_elements:
        element_pages = element_pages[:limit_elements]
        print(f"  Limited to {len(element_pages)} elements")
    
    if not element_pages:
        print(f"  No element pages found for {source}")
        return {'source': source, 'elements': 0, 'upf_links': 0, 'downloaded': 0, 
                'skipped': 0, 'failed': 0, 'manifest': []}
    
    # Step 2: Collect all UPF links
    print(f"\nCollecting UPF links from {len(element_pages)} element pages...")
    all_upf_links = []
    elements_visited = 0
    
    for element, element_url in element_pages:
        upf_links = get_upf_links_from_element_page(element_url, element)
        for text, url in upf_links:
            all_upf_links.append((element, text, url))
        elements_visited += 1
        if elements_visited % 10 == 0:
            print(f"  Processed {elements_visited}/{len(element_pages)} element pages...")
    
    # Deduplicate by URL
    seen_urls = {}
    unique_upf_links = []
    for element, text, url in all_upf_links:
        if url not in seen_urls:
            seen_urls[url] = (element, text)
            unique_upf_links.append((element, text, url))
    
    print(f"  Found {len(unique_upf_links)} unique UPF links")
    
    if limit_files:
        unique_upf_links = unique_upf_links[:limit_files]
        print(f"  Limited to {len(unique_upf_links)} files")
    
    if dry_run:
        print(f"\nDRY RUN: Would download {len(unique_upf_links)} files")
        manifest = []
        for element, text, url in unique_upf_links:
            # Extract filename from URL
            filename = url.split('/')[-1]
            manifest.append({
                'source': source,
                'element': element,
                'filename': filename,
                'url': url,
                'bytes': None,
                'sha256': None
            })
        return {'source': source, 'elements': len(element_pages), 
                'upf_links': len(unique_upf_links), 'downloaded': 0, 
                'skipped': 0, 'failed': 0, 'manifest': manifest}
    
    # Step 3: Download files
    print(f"\nDownloading {len(unique_upf_links)} files...")
    manifest = []
    downloaded = 0
    skipped = 0
    failed = 0
    
    def download_task(item):
        element, text, url = item
        
        # Check if URL was already downloaded (from manifest)
        if url in downloaded_urls:
            existing_entry = downloaded_urls[url]
            existing_file = dest_path / existing_entry['filename']
            if existing_file.exists() and existing_file.stat().st_size > 0:
                return {'status': 'skipped', 'path': str(existing_file)}, existing_entry
        
        filename = url.split('/')[-1]
        dest_file = handle_filename_collision(dest_path, filename, url)
        result = download_file(url, dest_file, force=False, rate_limiter=rate_limiter, timeout=timeout)
        
        manifest_entry = {
            'source': source,
            'element': element,
            'filename': dest_file.name,
            'url': url,
            'bytes': result.get('bytes'),
            'sha256': result.get('sha256')
        }
        
        return result, manifest_entry
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_task, item): item for item in unique_upf_links}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"  Progress: {completed}/{len(unique_upf_links)} files processed...")
            
            try:
                result, manifest_entry = future.result()
                manifest.append(manifest_entry)
                
                if result['status'] == 'downloaded':
                    downloaded += 1
                elif result['status'] == 'skipped':
                    skipped += 1
                else:
                    failed += 1
                    print(f"  FAILED: {manifest_entry['filename']} - {result.get('error', 'Unknown error')}")
            except Exception as e:
                failed += 1
                print(f"  ERROR processing {futures[future][2]}: {e}")
    
    # Merge with existing manifest (deduplicate by URL)
    all_manifest_entries = {entry['url']: entry for entry in existing_manifest}
    for entry in manifest:
        all_manifest_entries[entry['url']] = entry
    
    # Write manifest (sorted)
    final_manifest = sorted(all_manifest_entries.values(), key=lambda x: (x['filename'], x['url']))
    manifest_path = dest_path / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(final_manifest, f, indent=2)
    
    print(f"\nSummary for {source}:")
    print(f"  Elements visited: {len(element_pages)}")
    print(f"  UPF links found: {len(unique_upf_links)}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Manifest: {manifest_path}")
    
    return {
        'source': source,
        'elements': len(element_pages),
        'upf_links': len(unique_upf_links),
        'downloaded': downloaded,
        'skipped': skipped,
        'failed': failed,
        'manifest': manifest
    }


def main():
    parser = argparse.ArgumentParser(
        description='Scrape and download UPF files from Quantum ESPRESSO legacy tables'
    )
    parser.add_argument(
        '--dest',
        default='temp/qe-legacy-upf',
        help='Destination directory (default: temp/qe-legacy-upf)'
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        default=['ps-library', 'hartwigesen-goedecker-hutter-pp'],
        help='Sources to scrape (default: ps-library, hartwigesen-goedecker-hutter-pp)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=8,
        help='Maximum concurrent downloads (default: 8)'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=5.0,
        help='Rate limit in requests per second (default: 5.0)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=5,
        help='Number of retries for failed requests (default: 5)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print counts only, do not download'
    )
    parser.add_argument(
        '--limit-elements',
        type=int,
        help='Limit number of elements to process per source (for testing)'
    )
    parser.add_argument(
        '--limit-files',
        type=int,
        help='Limit number of files to download per source (for testing)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download existing files'
    )
    
    args = parser.parse_args()
    
    # Create rate limiter
    rate_limiter = RateLimiter(args.rate) if args.rate > 0 else None
    
    # Process each source
    results = []
    for source in args.sources:
        result = scrape_source(
            source,
            args.dest,
            dry_run=args.dry_run,
            rate_limiter=rate_limiter,
            limit_elements=args.limit_elements,
            limit_files=args.limit_files,
            timeout=args.timeout,
            max_workers=args.max_workers
        )
        results.append(result)
    
    # Print overall summary
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY")
    print(f"{'='*80}")
    total_elements = sum(r['elements'] for r in results)
    total_links = sum(r['upf_links'] for r in results)
    total_downloaded = sum(r['downloaded'] for r in results)
    total_skipped = sum(r['skipped'] for r in results)
    total_failed = sum(r['failed'] for r in results)
    
    print(f"Sources processed: {len(results)}")
    print(f"Total elements visited: {total_elements}")
    print(f"Total UPF links found: {total_links}")
    if not args.dry_run:
        print(f"Total downloaded: {total_downloaded}")
        print(f"Total skipped: {total_skipped}")
        print(f"Total failed: {total_failed}")
    
    return 0 if total_failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

