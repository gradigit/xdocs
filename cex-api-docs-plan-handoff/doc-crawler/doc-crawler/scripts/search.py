#!/usr/bin/env python3
"""
doc-crawler search: Query the crawled documentation index.

Usage:
    python3 search.py --query "rate limiting" --docs-dir "./doc-store"
    python3 search.py --query "websocket" --domain "docs.binance.com"
    python3 search.py --url "https://docs.example.com/api/orders"
    python3 search.py --list-domains
    python3 search.py --list-pages --domain "docs.example.com"
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def get_db(docs_dir: str) -> sqlite3.Connection:
    db_path = os.path.join(docs_dir, 'db', 'docs.db')
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        print("Run crawl.py first to build the index.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def search_fts(conn: sqlite3.Connection, query: str, domain: str = None,
               limit: int = 20, output_format: str = 'json') -> list[dict]:
    """Full-text search using FTS5."""
    # Build FTS query \u2014 add domain filter if specified
    if domain:
        fts_query = f'{query} domain:"{domain}"'
    else:
        fts_query = query

    try:
        rows = conn.execute("""
            SELECT p.url, p.title, p.domain, p.content_hash, p.crawled_at,
                   p.word_count, p.link_depth,
                   snippet(pages_fts, 2, '>>>', '<<<', '...', 64) as snippet,
                   rank
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit)).fetchall()
    except sqlite3.OperationalError:
        # Fallback: simpler query without domain in FTS
        rows = conn.execute("""
            SELECT p.url, p.title, p.domain, p.content_hash, p.crawled_at,
                   p.word_count, p.link_depth,
                   snippet(pages_fts, 2, '>>>', '<<<', '...', 64) as snippet,
                   rank
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
            AND (? IS NULL OR p.domain = ?)
            ORDER BY rank
            LIMIT ?
        """, (query, domain, domain, limit)).fetchall()

    results = []
    for row in rows:
        results.append({
            'url': row['url'],
            'title': row['title'],
            'domain': row['domain'],
            'content_hash': row['content_hash'],
            'crawled_at': row['crawled_at'],
            'word_count': row['word_count'],
            'snippet': row['snippet'],
            'relevance_rank': row['rank'],
        })
    return results


def get_page_by_url(conn: sqlite3.Connection, url: str) -> dict | None:
    """Get full page content by URL."""
    row = conn.execute("""
        SELECT url, title, domain, content_md, content_hash, crawled_at,
               word_count, link_depth, parent_url, has_code_blocks, has_tables
        FROM pages WHERE url = ?
    """, (url,)).fetchone()
    if row:
        return dict(row)
    return None


def get_page_content(conn: sqlite3.Connection, url: str) -> str | None:
    """Get just the markdown content of a page."""
    row = conn.execute("SELECT content_md FROM pages WHERE url = ?", (url,)).fetchone()
    return row['content_md'] if row else None


def list_domains(conn: sqlite3.Connection) -> list[dict]:
    """List all crawled domains with page counts."""
    rows = conn.execute("""
        SELECT domain, COUNT(*) as page_count,
               MIN(crawled_at) as first_crawled,
               MAX(crawled_at) as last_crawled,
               SUM(word_count) as total_words
        FROM pages
        WHERE is_stale = 0
        GROUP BY domain
        ORDER BY page_count DESC
    """).fetchall()
    return [dict(r) for r in rows]


def list_pages(conn: sqlite3.Connection, domain: str, limit: int = 500) -> list[dict]:
    """List all pages for a domain."""
    rows = conn.execute("""
        SELECT url, title, word_count, crawled_at, link_depth, content_hash
        FROM pages
        WHERE domain = ? AND is_stale = 0
        ORDER BY link_depth ASC, url ASC
        LIMIT ?
    """, (domain, limit)).fetchall()
    return [dict(r) for r in rows]


def list_crawl_runs(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """List recent crawl runs."""
    rows = conn.execute("""
        SELECT * FROM crawl_runs ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def format_output(data, fmt: str = 'json'):
    """Format output as JSON or readable text."""
    if fmt == 'json':
        print(json.dumps(data, indent=2, default=str))
    elif fmt == 'text':
        if isinstance(data, list):
            for item in data:
                if 'snippet' in item:
                    print(f"\
--- {item.get('title', 'Untitled')} ---")
                    print(f"URL: {item['url']}")
                    print(f"Domain: {item['domain']}")
                    print(f"Crawled: {item['crawled_at']}")
                    print(f"Snippet: {item['snippet']}")
                elif 'page_count' in item:
                    print(f"{item['domain']}: {item['page_count']} pages, "
                          f"{item.get('total_words', 0)} words, "
                          f"last crawled {item['last_crawled']}")
                else:
                    print(f"  [{item.get('link_depth', '?')}] {item.get('title', item.get('url', ''))}")
                    print(f"      {item['url']}")
        elif isinstance(data, dict):
            if 'content_md' in data:
                print(data['content_md'])
            else:
                for k, v in data.items():
                    print(f"{k}: {v}")
        elif isinstance(data, str):
            print(data)
    else:
        print(json.dumps(data, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description='Search crawled documentation')
    parser.add_argument('--query', '-q', help='Full-text search query')
    parser.add_argument('--url', help='Get specific page by URL')
    parser.add_argument('--content', help='Get markdown content of page by URL')
    parser.add_argument('--domain', '-d', help='Filter by domain')
    parser.add_argument('--list-domains', action='store_true', help='List all crawled domains')
    parser.add_argument('--list-pages', action='store_true', help='List pages for a domain')
    parser.add_argument('--list-runs', action='store_true', help='List recent crawl runs')
    parser.add_argument('--docs-dir', default='./doc-store', help='Docs directory')
    parser.add_argument('--limit', '-n', type=int, default=20, help='Max results')
    parser.add_argument('--format', '-f', choices=['json', 'text'], default='json',
                       help='Output format')
    args = parser.parse_args()

    conn = get_db(args.docs_dir)

    try:
        if args.list_domains:
            format_output(list_domains(conn), args.format)
        elif args.list_pages:
            if not args.domain:
                print("Error: --domain required with --list-pages", file=sys.stderr)
                sys.exit(1)
            format_output(list_pages(conn, args.domain, args.limit), args.format)
        elif args.list_runs:
            format_output(list_crawl_runs(conn, args.limit), args.format)
        elif args.url:
            result = get_page_by_url(conn, args.url)
            if result:
                format_output(result, args.format)
            else:
                print(f"Page not found: {args.url}", file=sys.stderr)
                sys.exit(1)
        elif args.content:
            result = get_page_content(conn, args.content)
            if result:
                print(result)
            else:
                print(f"Page not found: {args.content}", file=sys.stderr)
                sys.exit(1)
        elif args.query:
            results = search_fts(conn, args.query, args.domain, args.limit)
            if not results:
                print("No results found.", file=sys.stderr)
            else:
                format_output(results, args.format)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
