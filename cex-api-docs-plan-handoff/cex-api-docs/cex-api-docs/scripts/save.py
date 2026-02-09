#!/usr/bin/env python3
"""
save.py: Persistence layer for cex-api-docs.

Handles ONLY deterministic I/O:
- Save raw crawled pages to disk
- Save structured endpoint JSON to disk + SQLite index
- Rebuild FTS5 search index
- Manage human review queue
- Track content hashes for change detection

The AI agent handles all crawling, parsing, and understanding.

Usage:
    python3 save.py --save-page --url URL --title TITLE --content-file page.md --docs-dir ./cex-docs
    python3 save.py --save-endpoint endpoint.json --docs-dir ./cex-docs
    python3 save.py --save-batch ./endpoints/ --docs-dir ./cex-docs
    python3 save.py --reindex --docs-dir ./cex-docs
    python3 save.py --review-queue --docs-dir ./cex-docs
    python3 save.py --approve --id ITEM_ID --docs-dir ./cex-docs
    python3 save.py --stats --docs-dir ./cex-docs
"""

import argparse, glob, hashlib, json, os, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(text):
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def path_hash(url_path):
    return hashlib.sha256(url_path.encode('utf-8')).hexdigest()[:16]


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            domain TEXT NOT NULL,
            title TEXT,
            content_md TEXT,
            content_hash TEXT,
            prev_content_hash TEXT,
            crawled_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_stale BOOLEAN DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            url, title, content_md, domain,
            content='pages', content_rowid='id',
            tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL,
            section TEXT,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            data_json TEXT NOT NULL,
            confidence TEXT DEFAULT 'low',
            review_status TEXT DEFAULT 'pending',
            reviewed_at TEXT,
            source_url TEXT,
            content_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(exchange, method, path)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS endpoints_fts USING fts5(
            exchange, section, method, path, data_json,
            content='endpoints', content_rowid='id',
            tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER REFERENCES endpoints(id),
            field_name TEXT,
            extracted_value TEXT,
            confidence TEXT,
            source_url TEXT,
            status TEXT DEFAULT 'pending',
            reviewer_notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain);
        CREATE INDEX IF NOT EXISTS idx_endpoints_exchange ON endpoints(exchange);
        CREATE INDEX IF NOT EXISTS idx_endpoints_canonical ON endpoints(section);
        CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);
    """)

    # FTS triggers for pages
    for trigger_sql in [
        """CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, url, title, content_md, domain)
            VALUES (new.id, new.url, new.title, new.content_md, new.domain); END""",
        """CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
            VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain); END""",
        """CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, url, title, content_md, domain)
            VALUES ('delete', old.id, old.url, old.title, old.content_md, old.domain);
            INSERT INTO pages_fts(rowid, url, title, content_md, domain)
            VALUES (new.id, new.url, new.title, new.content_md, new.domain); END""",
    ]:
        try:
            conn.execute(trigger_sql)
        except sqlite3.OperationalError:
            pass

    # FTS triggers for endpoints
    for trigger_sql in [
        """CREATE TRIGGER IF NOT EXISTS ep_ai AFTER INSERT ON endpoints BEGIN
            INSERT INTO endpoints_fts(rowid, exchange, section, method, path, data_json)
            VALUES (new.id, new.exchange, new.section, new.method, new.path, new.data_json); END""",
        """CREATE TRIGGER IF NOT EXISTS ep_ad AFTER DELETE ON endpoints BEGIN
            INSERT INTO endpoints_fts(endpoints_fts, rowid, exchange, section, method, path, data_json)
            VALUES ('delete', old.id, old.exchange, old.section, old.method, old.path, old.data_json); END""",
        """CREATE TRIGGER IF NOT EXISTS ep_au AFTER UPDATE ON endpoints BEGIN
            INSERT INTO endpoints_fts(endpoints_fts, rowid, exchange, section, method, path, data_json)
            VALUES ('delete', old.id, old.exchange, old.section, old.method, old.path, old.data_json);
            INSERT INTO endpoints_fts(rowid, exchange, section, method, path, data_json)
            VALUES (new.id, new.exchange, new.section, new.method, new.path, new.data_json); END""",
    ]:
        try:
            conn.execute(trigger_sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    return conn


def save_page(conn, docs_dir, url, title, content_md):
    """Save a crawled page."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    now = datetime.now(timezone.utc).isoformat()
    c_hash = sha256(content_md)
    p_hash = path_hash(parsed.path)

    # Get previous hash
    row = conn.execute("SELECT content_hash FROM pages WHERE url = ?", (url,)).fetchone()
    prev_hash = row[0] if row else None

    # Save markdown file
    pages_dir = Path(docs_dir) / 'pages' / domain
    pages_dir.mkdir(parents=True, exist_ok=True)
    md_content = f"""---
source_url: {url}
title: "{title}"
crawled_at: {now}
content_hash: {c_hash}
---

# {title}

> **Source**: [{url}]({url})
> **Crawled**: {now}

{content_md}
"""
    (pages_dir / f'{p_hash}.md').write_text(md_content, encoding='utf-8')

    # Upsert to database
    conn.execute("""
        INSERT INTO pages (url, domain, title, content_md, content_hash, prev_content_hash,
            crawled_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title, content_md=excluded.content_md,
            content_hash=excluded.content_hash, prev_content_hash=pages.content_hash,
            updated_at=excluded.updated_at, is_stale=0
    """, (url, domain, title, content_md, c_hash, prev_hash, now, now))
    conn.commit()

    changed = prev_hash is None or prev_hash != c_hash
    status = "NEW" if prev_hash is None else ("UPDATED" if changed else "UNCHANGED")
    print(f"  [{status}] {url}")
    return changed


def save_endpoint(conn, docs_dir, endpoint_data):
    """Save a structured endpoint."""
    now = datetime.now(timezone.utc).isoformat()
    ep = endpoint_data.get('endpoint', endpoint_data)
    exchange = endpoint_data.get('exchange', ep.get('exchange', 'unknown'))
    section = endpoint_data.get('section', ep.get('section', 'general'))
    method = ep.get('method', '')
    path = ep.get('path', '')
    source_url = ep.get('source', {}).get('url', '')
    content_hash = ep.get('source', {}).get('content_hash', '')

    # Determine overall confidence (lowest confidence of any field)
    confidences = []
    for field in ['required_permissions', 'rate_limit', 'canonical']:
        field_data = ep.get(field, {})
        if isinstance(field_data, dict) and 'confidence' in field_data:
            confidences.append(field_data['confidence'])
    overall_confidence = 'high'
    if 'low' in confidences or 'undocumented' in confidences:
        overall_confidence = 'low'
    elif 'medium' in confidences:
        overall_confidence = 'medium'

    data_json = json.dumps(endpoint_data, indent=2, default=str)

    # Save JSON file
    ep_dir = Path(docs_dir) / 'endpoints' / exchange / section
    ep_dir.mkdir(parents=True, exist_ok=True)
    path_safe = path.replace('/', '_').strip('_')
    filename = f"{method}_{path_safe}.json"
    (ep_dir / filename).write_text(data_json, encoding='utf-8')

    # Upsert to database
    conn.execute("""
        INSERT INTO endpoints (exchange, section, method, path, data_json, confidence,
            review_status, source_url, content_hash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exchange, method, path) DO UPDATE SET
            section=excluded.section, data_json=excluded.data_json,
            confidence=excluded.confidence, source_url=excluded.source_url,
            content_hash=excluded.content_hash, updated_at=excluded.updated_at
    """, (exchange, section, method, path, data_json, overall_confidence,
          'pending' if overall_confidence != 'high' else 'auto_approved',
          source_url, content_hash, now, now))

    # Add to review queue if not high confidence
    if overall_confidence != 'high':
        endpoint_id = conn.execute(
            "SELECT id FROM endpoints WHERE exchange=? AND method=? AND path=?",
            (exchange, method, path)
        ).fetchone()[0]

        for field_name in ['required_permissions', 'rate_limit', 'error_codes', 'canonical']:
            field_data = ep.get(field_name, {})
            conf = field_data.get('confidence', 'low') if isinstance(field_data, dict) else 'low'
            if conf in ('medium', 'low', 'undocumented'):
                conn.execute("""
                    INSERT INTO review_queue (endpoint_id, field_name, extracted_value,
                        confidence, source_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (endpoint_id, field_name, json.dumps(field_data, default=str),
                      conf, source_url, now))

    conn.commit()
    status = "REVIEW" if overall_confidence != 'high' else "OK"
    print(f"  [{status}] {exchange} {method} {path} (confidence: {overall_confidence})")


def show_review_queue(conn, exchange=None):
    """Show items pending human review."""
    query = """
        SELECT rq.id, rq.field_name, rq.confidence, rq.extracted_value,
               e.exchange, e.method, e.path, rq.source_url
        FROM review_queue rq
        JOIN endpoints e ON e.id = rq.endpoint_id
        WHERE rq.status = 'pending'
    """
    params = []
    if exchange:
        query += " AND e.exchange = ?"
        params.append(exchange)
    query += " ORDER BY rq.confidence ASC, e.exchange, e.path"

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No items pending review.")
        return

    print(f"\
{'='*60}")
    print(f"REVIEW QUEUE: {len(rows)} items pending")
    print(f"{'='*60}\
")
    for row in rows:
        print(f"  ID: {row[0]}")
        print(f"  Endpoint: {row[4]} {row[5]} {row[6]}")
        print(f"  Field: {row[1]} (confidence: {row[2]})")
        print(f"  Value: {row[3][:200]}")
        print(f"  Source: {row[7]}")
        print()


def approve_item(conn, item_id, notes=""):
    """Approve a review queue item."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        UPDATE review_queue SET status='approved', reviewer_notes=?
        WHERE id = ?
    """, (notes, item_id))

    # Check if all items for this endpoint are approved
    row = conn.execute(
        "SELECT endpoint_id FROM review_queue WHERE id = ?", (item_id,)
    ).fetchone()
    if row:
        pending = conn.execute("""
            SELECT COUNT(*) FROM review_queue
            WHERE endpoint_id = ? AND status = 'pending'
        """, (row[0],)).fetchone()[0]
        if pending == 0:
            conn.execute("""
                UPDATE endpoints SET review_status='verified', reviewed_at=?
                WHERE id = ?
            """, (now, row[0]))

    conn.commit()
    print(f"  Approved item {item_id}")


def show_stats(conn, docs_dir):
    """Show statistics about the doc store."""
    pages = conn.execute("SELECT COUNT(*) FROM pages WHERE is_stale=0").fetchone()[0]
    endpoints = conn.execute("SELECT COUNT(*) FROM endpoints").fetchone()[0]
    verified = conn.execute(
        "SELECT COUNT(*) FROM endpoints WHERE review_status='verified'"
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM review_queue WHERE status='pending'"
    ).fetchone()[0]

    exchanges = conn.execute(
        "SELECT exchange, COUNT(*) as cnt FROM endpoints GROUP BY exchange ORDER BY cnt DESC"
    ).fetchall()

    print(f"\
{'='*40}")
    print(f"CEX API Docs Store: {docs_dir}")
    print(f"{'='*40}")
    print(f"  Pages crawled:    {pages}")
    print(f"  Endpoints:        {endpoints}")
    print(f"  Verified:         {verified}")
    print(f"  Pending review:   {pending}")
    print(f"\
  By exchange:")
    for ex, cnt in exchanges:
        verified_cnt = conn.execute(
            "SELECT COUNT(*) FROM endpoints WHERE exchange=? AND review_status='verified'",
            (ex,)
        ).fetchone()[0]
        print(f"    {ex:15s} {cnt:4d} endpoints ({verified_cnt} verified)")


def reindex(conn):
    """Rebuild FTS indexes."""
    print("Rebuilding FTS indexes...")
    try:
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
    except:
        pass
    try:
        conn.execute("INSERT INTO endpoints_fts(endpoints_fts) VALUES('rebuild')")
    except:
        pass
    conn.commit()
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description='cex-api-docs persistence layer')
    parser.add_argument('--save-page', action='store_true', help='Save a crawled page')
    parser.add_argument('--save-endpoint', help='Save endpoint JSON file')
    parser.add_argument('--save-batch', help='Save all JSON files in directory')
    parser.add_argument('--url', help='Page URL (with --save-page)')
    parser.add_argument('--title', help='Page title (with --save-page)', default='')
    parser.add_argument('--content-file', help='Markdown content file (with --save-page)')
    parser.add_argument('--content', help='Inline markdown content (with --save-page)')
    parser.add_argument('--reindex', action='store_true', help='Rebuild FTS indexes')
    parser.add_argument('--review-queue', action='store_true', help='Show pending reviews')
    parser.add_argument('--approve', help='Approve review item by ID')
    parser.add_argument('--reject', help='Reject review item by ID')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--exchange', '-e', help='Filter by exchange')
    parser.add_argument('--docs-dir', '-d', default='./cex-docs', help='Docs directory')
    args = parser.parse_args()

    db_path = os.path.join(args.docs_dir, 'db', 'docs.db')
    conn = init_db(db_path)

    try:
        if args.save_page:
            if not args.url:
                print("Error: --url required with --save-page", file=sys.stderr)
                sys.exit(1)
            if args.content_file:
                content = Path(args.content_file).read_text(encoding='utf-8')
            elif args.content:
                content = args.content
            else:
                content = sys.stdin.read()
            save_page(conn, args.docs_dir, args.url, args.title, content)

        elif args.save_endpoint:
            with open(args.save_endpoint) as f:
                data = json.load(f)
            save_endpoint(conn, args.docs_dir, data)

        elif args.save_batch:
            for filepath in sorted(glob.glob(os.path.join(args.save_batch, '**/*.json'),
                                             recursive=True)):
                if os.path.basename(filepath).startswith('_'):
                    continue
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                    save_endpoint(conn, args.docs_dir, data)
                except Exception as e:
                    print(f"  Error saving {filepath}: {e}", file=sys.stderr)

        elif args.reindex:
            reindex(conn)

        elif args.review_queue:
            show_review_queue(conn, args.exchange)

        elif args.approve:
            approve_item(conn, int(args.approve))

        elif args.reject:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE review_queue SET status='rejected' WHERE id=?",
                        (int(args.reject),))
            conn.commit()
            print(f"  Rejected item {args.reject}")

        elif args.stats:
            show_stats(conn, args.docs_dir)

        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
