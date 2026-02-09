#!/usr/bin/env python3
"""
doc-crawler diff: Detect changes between crawls.

Usage:
    python3 diff.py --docs-dir "./doc-store" --domain "docs.example.com"
    python3 diff.py --docs-dir "./doc-store" --since "2026-02-01"
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_db(docs_dir: str) -> sqlite3.Connection:
    db_path = os.path.join(docs_dir, 'db', 'docs.db')
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def find_changes(conn: sqlite3.Connection, domain: str = None,
                 since: str = None) -> dict:
    """Find pages that changed between crawls."""
    results = {'new': [], 'updated': [], 'stale': []}

    # Pages where content_hash != prev_content_hash (updated)
    query = """
        SELECT url, title, domain, content_hash, prev_content_hash,
               crawled_at, word_count
        FROM pages
        WHERE prev_content_hash IS NOT NULL
          AND content_hash != prev_content_hash
          AND is_stale = 0
    """
    params = []
    if domain:
        query += " AND domain = ?"
        params.append(domain)
    if since:
        query += " AND crawled_at >= ?"
        params.append(since)
    query += " ORDER BY crawled_at DESC"

    for row in conn.execute(query, params).fetchall():
        results['updated'].append(dict(row))

    # New pages (no prev_content_hash)
    query = """
        SELECT url, title, domain, content_hash, crawled_at, word_count
        FROM pages
        WHERE prev_content_hash IS NULL
          AND is_stale = 0
    """
    params = []
    if domain:
        query += " AND domain = ?"
        params.append(domain)
    if since:
        query += " AND crawled_at >= ?"
        params.append(since)
    query += " ORDER BY crawled_at DESC"

    for row in conn.execute(query, params).fetchall():
        results['new'].append(dict(row))

    # Stale pages (404 on last crawl)
    query = "SELECT url, title, domain, crawled_at FROM pages WHERE is_stale = 1"
    params = []
    if domain:
        query += " AND domain = ?"
        params.append(domain)

    for row in conn.execute(query, params).fetchall():
        results['stale'].append(dict(row))

    return results


def main():
    parser = argparse.ArgumentParser(description='Detect documentation changes')
    parser.add_argument('--docs-dir', default='./doc-store', help='Docs directory')
    parser.add_argument('--domain', '-d', help='Filter by domain')
    parser.add_argument('--since', help='Only changes since this date (ISO format)')
    parser.add_argument('--format', '-f', choices=['json', 'text'], default='text')
    args = parser.parse_args()

    conn = get_db(args.docs_dir)
    changes = find_changes(conn, args.domain, args.since)
    conn.close()

    if args.format == 'json':
        print(json.dumps(changes, indent=2, default=str))
    else:
        total = sum(len(v) for v in changes.values())
        if total == 0:
            print("No changes detected.")
            return

        if changes['new']:
            print(f"\
=== NEW PAGES ({len(changes['new'])}) ===")
            for p in changes['new']:
                print(f"  + {p['url']}")
                print(f"    Title: {p['title']}, Words: {p['word_count']}")

        if changes['updated']:
            print(f"\
=== UPDATED PAGES ({len(changes['updated'])}) ===")
            for p in changes['updated']:
                print(f"  ~ {p['url']}")
                print(f"    Title: {p['title']}")
                print(f"    Old hash: {p['prev_content_hash']}")
                print(f"    New hash: {p['content_hash']}")

        if changes['stale']:
            print(f"\
=== STALE/REMOVED PAGES ({len(changes['stale'])}) ===")
            for p in changes['stale']:
                print(f"  - {p['url']}")

        print(f"\
Total: {len(changes['new'])} new, {len(changes['updated'])} updated, "
              f"{len(changes['stale'])} stale")


if __name__ == '__main__':
    main()
