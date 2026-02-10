#!/usr/bin/env python3
"""
doc-crawler: General-purpose documentation crawler.

Crawls documentation websites, extracts structured content, saves raw HTML + markdown + metadata,
and builds a SQLite FTS5 search index. Every piece of data is cited with source URL, crawl
timestamp, and content hash.

Usage:
    python3 crawl.py --url "https://docs.example.com/api/" [options]
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque

# Try to import optional dependencies
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import html2text
    HAS_HTML2TEXT = True
except ImportError:
    HAS_HTML2TEXT = False


def ensure_dependencies():
    """Install missing dependencies."""
    missing = []
    if not HAS_REQUESTS:
        missing.append("requests")
    if not HAS_BS4:
        missing.append("beautifulsoup4")
    if not HAS_HTML2TEXT:
        missing.append("html2text")
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)}")
        import subprocess
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--break-system-packages", "-q"
        ] + missing)
        # Re-import after install
        global requests, BeautifulSoup, html2text
        global HAS_REQUESTS, HAS_BS4, HAS_HTML2TEXT
        import requests as _req
        requests = _req
        HAS_REQUESTS = True
        from bs4 import BeautifulSoup as _bs
        BeautifulSoup = _bs
        HAS_BS4 = True
        import html2text as _h2t
        html2text = _h2t
        HAS_HTML2TEXT = True


def sha256(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def path_hash(url_path: str) -> str:
    """Create a filesystem-safe hash of a URL path."""
    return hashlib.sha256(url_path.encode('utf-8')).hexdigest()[:16]


def normalize_url(url: str) -> str:
    """Normalize URL: remove fragments, trailing slashes on paths, lowercase domain."""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/') or '/'
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        parsed.query,
        ''  # Remove fragment
    ))


def matches_patterns(url: str, patterns: list[str]) -> bool:
    """Check if URL path matches any of the given patterns."""
    if not patterns:
        return True
    path = urlparse(url).path
    return any(p in path for p in patterns)


def html_to_markdown(html_content: str, base_url: str = "") -> str:
    """Convert HTML to clean markdown, preserving code blocks and tables."""
    h = html2text.HTML2Text()
    h.body_width = 0  # No wrapping
    h.protect_links = True
    h.wrap_links = False
    h.mark_code = True
    h.default_image_alt = ""
    h.ignore_images = True
    h.baseurl = base_url
    return h.handle(html_content).strip()


def extract_main_content(soup: BeautifulSoup) -> str:
    """Try to extract the main documentation content, excluding nav/header/footer."""
    # Common doc content selectors (ordered by specificity)
    content_selectors = [
        'article[role="main"]',
        'main[role="main"]',
        '.markdown-body',
        '.doc-content',
        '.documentation-content',
        '.api-content',
        '#content',
        'article',
        'main',
        '[role="main"]',
        '.content',
        '.post-content',
        '.entry-content',
    ]
    for selector in content_selectors:
        content = soup.select_one(selector)
        if content and len(content.get_text(strip=True)) > 100:
            return str(content)

    # Fallback: remove nav, header, footer, sidebar and return body
    body = soup.find('body')
    if body:
        for tag in body.find_all(['nav', 'header', 'footer', 'aside',
                                   'script', 'style', 'noscript']):
            tag.decompose()
        # Remove common sidebar/nav classes
        for cls in ['sidebar', 'nav', 'menu', 'toc', 'breadcrumb', 'footer']:
            for el in body.find_all(class_=re.compile(cls, re.I)):
                el.decompose()
        return str(body)

    return str(soup)


def extract_links(soup: BeautifulSoup, base_url: str, domain_scope: str) -> list[dict]:
    """Extract all links from page, resolve to absolute URLs."""
    links = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        absolute = normalize_url(urljoin(base_url, href))
        parsed = urlparse(absolute)
        # Only follow links within domain scope
        if domain_scope and parsed.netloc.lower() != domain_scope.lower():
            continue
        if absolute not in seen:
            seen.add(absolute)
            links.append({
                'url': absolute,
                'text': a.get_text(strip=True)[:200]
            })
    return links


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Read and execute schema
    schema_sql = """
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        domain TEXT NOT NULL,
        path TEXT NOT NULL,
        path_hash TEXT NOT NULL,
        title TEXT,
        content_md TEXT,
        content_hash TEXT,
        prev_content_hash TEXT,
        http_status INTEGER,
        content_type TEXT,
        link_depth INTEGER,
        parent_url TEXT,
        word_count INTEGER,
        has_code_blocks BOOLEAN DEFAULT 0,
        has_tables BOOLEAN DEFAULT 0,
        crawled_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        is_stale BOOLEAN DEFAULT 0
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
        url, title, content_md, domain,
        content='pages', content_rowid='id',
        tokenize='porter unicode61'
    );

    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_url TEXT NOT NULL,
        target_url TEXT NOT NULL,
        link_text TEXT,
        UNIQUE(source_url, target_url)
    );

    CREATE TABLE IF NOT EXISTS crawl_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        entry_url TEXT NOT NULL,
        domain_scope TEXT,
        pages_crawled INTEGER DEFAULT 0,
        pages_new INTEGER DEFAULT 0,
        pages_updated INTEGER DEFAULT 0,
        pages_unchanged INTEGER DEFAULT 0,
        pages_failed INTEGER DEFAULT 0,
        config_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain);
    CREATE INDEX IF NOT EXISTS idx_pages_path_hash ON pages(path_hash);
    CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at);
    CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_url);
    CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_url);
    """
    conn.executescript(schema_sql)

    # Create FTS triggers if they don't exist
    triggers = [
        """CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, url, title, content_md, domain)
            VALUES (new.id, new.url, new.title, new.content_md, new.domain);
        END""",
        """CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
            VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain);
        END""",
        """CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
            VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain);
            INSERT INTO pages_fts(rowid, url, title, content_md, domain)
            VALUES (new.id, new.url, new.title, new.content_md, new.domain);
        END""",
    ]
    for trigger in triggers:
        try:
            conn.execute(trigger)
        except sqlite3.OperationalError:
            pass  # Trigger already exists

    conn.commit()
    return conn


def log_action(log_path: str, action: str, url: str, **kwargs):
    """Append a line to the crawl log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "url": url,
        **kwargs
    }
    with open(log_path, 'a') as f:
        f.write(json.dumps(entry) + '\
')


class Crawler:
    def __init__(self, args):
        self.entry_url = normalize_url(args.url)
        self.domain_scope = args.domain_scope or urlparse(self.entry_url).netloc.lower()
        self.output_dir = Path(args.output_dir)
        self.max_depth = args.max_depth
        self.include_patterns = [p.strip() for p in args.include_patterns.split(',') if p.strip()] if args.include_patterns else []
        self.exclude_patterns = [p.strip() for p in args.exclude_patterns.split(',') if p.strip()] if args.exclude_patterns else []
        self.delay = args.delay
        self.force_recrawl = args.force_recrawl
        self.verbose = args.verbose

        # Setup directories
        self.raw_dir = self.output_dir / 'raw'
        self.pages_dir = self.output_dir / 'pages'
        self.meta_dir = self.output_dir / 'meta'
        self.db_dir = self.output_dir / 'db'
        for d in [self.raw_dir, self.pages_dir, self.meta_dir, self.db_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.db_path = str(self.db_dir / 'docs.db')
        self.log_path = str(self.output_dir / 'crawl-log.jsonl')
        self.conn = init_db(self.db_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'doc-crawler/1.0 (documentation indexer)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })

        # Stats
        self.stats = {
            'crawled': 0, 'new': 0, 'updated': 0,
            'unchanged': 0, 'failed': 0, 'skipped': 0
        }

    def should_crawl(self, url: str) -> bool:
        """Check if URL should be crawled based on filters."""
        parsed = urlparse(url)
        if parsed.netloc.lower() != self.domain_scope:
            return False
        # Skip non-doc file extensions
        skip_ext = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.css', '.js',
                    '.woff', '.woff2', '.ttf', '.eot', '.pdf', '.zip', '.tar', '.gz'}
        if any(parsed.path.lower().endswith(ext) for ext in skip_ext):
            return False
        if self.include_patterns and not matches_patterns(url, self.include_patterns):
            return False
        if self.exclude_patterns and matches_patterns(url, self.exclude_patterns):
            return False
        return True

    def get_existing_hash(self, url: str) -> str | None:
        """Get content hash of previously crawled page."""
        row = self.conn.execute(
            "SELECT content_hash FROM pages WHERE url = ?", (url,)
        ).fetchone()
        return row[0] if row else None

    def fetch_page(self, url: str) -> dict | None:
        """Fetch a single page and return parsed data."""
        try:
            start = time.time()
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            duration_ms = int((time.time() - start) * 1000)

            if resp.status_code != 200:
                log_action(self.log_path, 'error', url,
                          status=resp.status_code, duration_ms=duration_ms)
                self.stats['failed'] += 1
                return None

            content_type = resp.headers.get('content-type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                log_action(self.log_path, 'skip', url,
                          reason=f'non-html: {content_type}')
                self.stats['skipped'] += 1
                return None

            html_content = resp.text
            content_hash_val = sha256(html_content)

            # Check if content changed
            existing_hash = self.get_existing_hash(url)
            if existing_hash == content_hash_val and not self.force_recrawl:
                log_action(self.log_path, 'skip', url,
                          reason='unchanged', content_hash=content_hash_val,
                          duration_ms=duration_ms)
                self.stats['unchanged'] += 1
                if self.verbose:
                    print(f"  UNCHANGED: {url}")
                return None

            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else ''

            # Extract main content and convert to markdown
            main_html = extract_main_content(soup)
            content_md = html_to_markdown(main_html, base_url=url)

            # Extract links
            links = extract_links(soup, url, self.domain_scope)

            # Detect features
            has_code = bool(soup.find_all(['code', 'pre']))
            has_tables = bool(soup.find_all('table'))
            word_count = len(content_md.split())

            return {
                'url': url,
                'html': html_content,
                'content_md': content_md,
                'content_hash': content_hash_val,
                'prev_hash': existing_hash,
                'title': title,
                'links': links,
                'http_status': resp.status_code,
                'content_type': content_type,
                'word_count': word_count,
                'has_code_blocks': has_code,
                'has_tables': has_tables,
                'duration_ms': duration_ms,
                'headers': {
                    'last-modified': resp.headers.get('last-modified'),
                    'etag': resp.headers.get('etag'),
                },
                'is_new': existing_hash is None,
            }

        except Exception as e:
            log_action(self.log_path, 'error', url, error=str(e))
            self.stats['failed'] += 1
            if self.verbose:
                print(f"  ERROR: {url} \u2014 {e}")
            return None

    def save_page(self, data: dict, depth: int, parent_url: str | None):
        """Save page data to files and database."""
        parsed = urlparse(data['url'])
        domain = parsed.netloc.lower()
        p_hash = path_hash(parsed.path + '?' + parsed.query if parsed.query else parsed.path)
        now = datetime.now(timezone.utc).isoformat()

        # Save raw HTML
        raw_domain_dir = self.raw_dir / domain
        raw_domain_dir.mkdir(parents=True, exist_ok=True)
        (raw_domain_dir / f'{p_hash}.html').write_text(data['html'], encoding='utf-8')

        # Save markdown
        pages_domain_dir = self.pages_dir / domain
        pages_domain_dir.mkdir(parents=True, exist_ok=True)

        md_header = f"""---
source_url: {data['url']}
title: "{data['title']}"
crawled_at: {now}
content_hash: {data['content_hash']}
---

# {data['title']}

> **Source**: [{data['url']}]({data['url']})
> **Crawled**: {now}

"""
        (pages_domain_dir / f'{p_hash}.md').write_text(
            md_header + data['content_md'], encoding='utf-8')

        # Save metadata JSON
        meta_domain_dir = self.meta_dir / domain
        meta_domain_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            'url': data['url'],
            'domain': domain,
            'path': parsed.path,
            'path_hash': p_hash,
            'title': data['title'],
            'crawled_at': now,
            'content_hash': data['content_hash'],
            'prev_content_hash': data['prev_hash'],
            'http_status': data['http_status'],
            'content_type': data['content_type'],
            'link_depth': depth,
            'parent_url': parent_url,
            'outbound_links': [l['url'] for l in data['links']],
            'word_count': data['word_count'],
            'has_code_blocks': data['has_code_blocks'],
            'has_tables': data['has_tables'],
            'headers': data['headers'],
        }
        (meta_domain_dir / f'{p_hash}.json').write_text(
            json.dumps(meta, indent=2), encoding='utf-8')

        # Upsert into database
        self.conn.execute("""
            INSERT INTO pages (url, domain, path, path_hash, title, content_md,
                content_hash, prev_content_hash, http_status, content_type,
                link_depth, parent_url, word_count, has_code_blocks, has_tables,
                crawled_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, content_md=excluded.content_md,
                content_hash=excluded.content_hash,
                prev_content_hash=excluded.prev_content_hash,
                http_status=excluded.http_status, link_depth=excluded.link_depth,
                word_count=excluded.word_count, has_code_blocks=excluded.has_code_blocks,
                has_tables=excluded.has_tables, updated_at=excluded.updated_at,
                is_stale=0
        """, (data['url'], domain, parsed.path, p_hash, data['title'],
              data['content_md'], data['content_hash'], data['prev_hash'],
              data['http_status'], data['content_type'], depth, parent_url,
              data['word_count'], data['has_code_blocks'], data['has_tables'],
              now, now))

        # Save links
        for link in data['links']:
            self.conn.execute("""
                INSERT OR IGNORE INTO links (source_url, target_url, link_text)
                VALUES (?, ?, ?)
            """, (data['url'], link['url'], link['text']))

        self.conn.commit()

        # Update stats
        if data['is_new']:
            self.stats['new'] += 1
        else:
            self.stats['updated'] += 1
        self.stats['crawled'] += 1

        # Log
        changed = data['is_new'] or data['prev_hash'] != data['content_hash']
        log_action(self.log_path, 'fetch', data['url'],
                  status=data['http_status'],
                  content_hash=data['content_hash'],
                  changed=changed,
                  duration_ms=data['duration_ms'])

    def crawl(self):
        """BFS crawl starting from entry URL."""
        print(f"\
{'='*60}")
        print(f"doc-crawler starting")
        print(f"  Entry:  {self.entry_url}")
        print(f"  Scope:  {self.domain_scope}")
        print(f"  Output: {self.output_dir}")
        print(f"  Depth:  {self.max_depth or 'unlimited'}")
        print(f"{'='*60}\
")

        started_at = datetime.now(timezone.utc).isoformat()

        # BFS queue: (url, depth, parent_url)
        queue = deque([(self.entry_url, 0, None)])
        visited = {self.entry_url}

        while queue:
            url, depth, parent_url = queue.popleft()

            if self.max_depth and depth > self.max_depth:
                continue

            if not self.should_crawl(url):
                self.stats['skipped'] += 1
                continue

            if self.verbose:
                print(f"[depth={depth}] Crawling: {url}")
            else:
                print(f"  [{self.stats['crawled']+1}] {url[:80]}...")

            data = self.fetch_page(url)

            if data:
                self.save_page(data, depth, parent_url)

                # Add discovered links to queue
                for link in data['links']:
                    link_url = link['url']
                    if link_url not in visited and self.should_crawl(link_url):
                        visited.add(link_url)
                        queue.append((link_url, depth + 1, url))

            # Rate limiting
            if self.delay > 0:
                time.sleep(self.delay)

        # Record crawl run
        completed_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            INSERT INTO crawl_runs (started_at, completed_at, entry_url, domain_scope,
                pages_crawled, pages_new, pages_updated, pages_unchanged, pages_failed, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (started_at, completed_at, self.entry_url, self.domain_scope,
              self.stats['crawled'], self.stats['new'], self.stats['updated'],
              self.stats['unchanged'], self.stats['failed'],
              json.dumps(vars(args))))
        self.conn.commit()

        # Print summary
        print(f"\
{'='*60}")
        print(f"Crawl complete!")
        print(f"  Pages crawled:   {self.stats['crawled']}")
        print(f"  New pages:       {self.stats['new']}")
        print(f"  Updated pages:   {self.stats['updated']}")
        print(f"  Unchanged:       {self.stats['unchanged']}")
        print(f"  Failed:          {self.stats['failed']}")
        print(f"  Skipped:         {self.stats['skipped']}")
        print(f"  URLs discovered: {len(visited)}")
        print(f"{'='*60}\
")

        self.conn.close()


def main():
    global args
    parser = argparse.ArgumentParser(description='doc-crawler: crawl and index documentation')
    parser.add_argument('--url', required=True, help='Entry point URL')
    parser.add_argument('--domain-scope', help='Restrict crawl to this domain (default: from URL)')
    parser.add_argument('--output-dir', default='./doc-store', help='Output directory')
    parser.add_argument('--max-depth', type=int, default=10, help='Max link depth (0=unlimited)')
    parser.add_argument('--include-patterns', help='Only crawl URLs matching these (comma-sep)')
    parser.add_argument('--exclude-patterns', help='Skip URLs matching these (comma-sep)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests (seconds)')
    parser.add_argument('--force-recrawl', action='store_true', help='Re-fetch unchanged pages')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    if args.max_depth == 0:
        args.max_depth = None

    ensure_dependencies()
    crawler = Crawler(args)
    crawler.crawl()


if __name__ == '__main__':
    main()
