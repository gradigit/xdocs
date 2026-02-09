#!/usr/bin/env python3
"""
cex_search.py: Search CEX API documentation index.

Provides exchange-aware search: by endpoint, canonical operation, error code,
rate limits, permissions, and cross-exchange comparison.

Usage:
    python3 cex_search.py --query "open orders" --exchange binance
    python3 cex_search.py --canonical "get_open_orders"
    python3 cex_search.py --error-code "-1021" --exchange binance
    python3 cex_search.py --list-endpoints --exchange binance --section futures_usdm
    python3 cex_search.py --rate-limits --exchange binance --section spot
    python3 cex_search.py --permissions --endpoint "POST /fapi/v1/order" --exchange binance
"""

import argparse, glob, json, os, sqlite3, sys
from pathlib import Path


def search_fts(docs_dir, query, exchange=None, limit=20):
    """Full-text search in crawled pages."""
    db_path = os.path.join(docs_dir, 'db', 'docs.db')
    if not os.path.exists(db_path):
        print(f"Error: No database at {db_path}", file=sys.stderr)
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT p.url, p.title, p.domain, p.crawled_at, p.word_count,
                   snippet(pages_fts, 2, '>>>', '<<<', '...', 80) as snippet
            FROM pages_fts JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
            ORDER BY rank LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Search error: {e}", file=sys.stderr)
        return []
    finally:
        conn.close()


def search_endpoints(docs_dir, exchange=None, query=None, section=None):
    """Search parsed endpoint JSON files."""
    pattern = os.path.join(docs_dir, 'endpoints')
    if exchange:
        pattern = os.path.join(pattern, exchange)
    if section:
        pattern = os.path.join(pattern, section)
    pattern = os.path.join(pattern, '**', '*.json')

    results = []
    for filepath in glob.glob(pattern, recursive=True):
        if os.path.basename(filepath).startswith('_'):
            continue  # Skip summary files
        try:
            with open(filepath) as f:
                ep = json.load(f)
            if query:
                # Search in path, description, parameter names
                searchable = json.dumps(ep).lower()
                if query.lower() not in searchable:
                    continue
            results.append(ep)
        except (json.JSONDecodeError, IOError):
            continue
    return results


def search_canonical(docs_dir, canonical_op):
    """Find all exchanges that implement a canonical operation."""
    results = {}
    endpoints_dir = os.path.join(docs_dir, 'endpoints')
    if not os.path.exists(endpoints_dir):
        return results

    for exchange_dir in os.listdir(endpoints_dir):
        ex_path = os.path.join(endpoints_dir, exchange_dir)
        if not os.path.isdir(ex_path):
            continue
        for filepath in glob.glob(os.path.join(ex_path, '**', '*.json'), recursive=True):
            if os.path.basename(filepath).startswith('_'):
                continue
            try:
                with open(filepath) as f:
                    ep = json.load(f)
                canon = ep.get('endpoint', {}).get('canonical', {})
                if canon.get('operation') == canonical_op:
                    results.setdefault(exchange_dir, []).append({
                        'method': ep['endpoint']['method'],
                        'path': ep['endpoint']['path'],
                        'section': ep.get('section', ''),
                        'confidence': canon.get('confidence', ''),
                        'source_url': ep['endpoint'].get('source', {}).get('url', ''),
                    })
            except (json.JSONDecodeError, IOError, KeyError):
                continue
    return results


def search_error_code(docs_dir, code, exchange=None):
    """Search for a specific error code across endpoints."""
    results = []
    endpoints = search_endpoints(docs_dir, exchange=exchange)
    for ep in endpoints:
        errors = ep.get('endpoint', {}).get('error_codes', [])
        for err in errors:
            if str(err.get('code', '')) == str(code):
                results.append({
                    'exchange': ep.get('exchange', ''),
                    'endpoint': f"{ep['endpoint']['method']} {ep['endpoint']['path']}",
                    'error': err,
                    'source_url': ep['endpoint'].get('source', {}).get('url', ''),
                })
    return results


def list_endpoints(docs_dir, exchange, section=None):
    """List all endpoints for an exchange."""
    endpoints = search_endpoints(docs_dir, exchange=exchange, section=section)
    summary = []
    for ep in endpoints:
        e = ep.get('endpoint', {})
        summary.append({
            'method': e.get('method', ''),
            'path': e.get('path', ''),
            'section': ep.get('section', ''),
            'description': e.get('description', '')[:100],
            'canonical': e.get('canonical', {}).get('operation', ''),
            'has_rate_limit': bool(e.get('rate_limit')),
            'has_permissions': bool(e.get('required_permissions', {}).get('permissions')),
        })
    return sorted(summary, key=lambda x: (x['section'], x['path']))


def get_rate_limits(docs_dir, exchange, section=None):
    """Get all rate limit info for an exchange."""
    endpoints = search_endpoints(docs_dir, exchange=exchange, section=section)
    limits = []
    for ep in endpoints:
        e = ep.get('endpoint', {})
        rl = e.get('rate_limit', {})
        if rl:
            limits.append({
                'endpoint': f"{e.get('method', '')} {e.get('path', '')}",
                'section': ep.get('section', ''),
                'rate_limit': rl,
                'source_url': e.get('source', {}).get('url', ''),
            })
    return limits


def get_permissions(docs_dir, exchange, endpoint_str=None):
    """Get permission requirements."""
    endpoints = search_endpoints(docs_dir, exchange=exchange)
    perms = []
    for ep in endpoints:
        e = ep.get('endpoint', {})
        p = e.get('required_permissions', {})
        ep_str = f"{e.get('method', '')} {e.get('path', '')}"
        if endpoint_str and endpoint_str.lower() not in ep_str.lower():
            continue
        if p and p.get('permissions'):
            perms.append({
                'endpoint': ep_str,
                'section': ep.get('section', ''),
                'permissions': p,
                'source_url': e.get('source', {}).get('url', ''),
            })
    return perms


def main():
    parser = argparse.ArgumentParser(description='Search CEX API documentation')
    parser.add_argument('--query', '-q', help='Full-text search query')
    parser.add_argument('--exchange', '-e', help='Exchange ID')
    parser.add_argument('--section', '-s', help='API section filter')
    parser.add_argument('--canonical', help='Search by canonical operation name')
    parser.add_argument('--error-code', help='Search for error code')
    parser.add_argument('--list-endpoints', action='store_true', help='List all endpoints')
    parser.add_argument('--rate-limits', action='store_true', help='Show rate limits')
    parser.add_argument('--permissions', action='store_true', help='Show permissions')
    parser.add_argument('--endpoint', help='Filter by endpoint string (with --permissions)')
    parser.add_argument('--docs-dir', '-d', default='./cex-docs', help='Docs directory')
    parser.add_argument('--limit', '-n', type=int, default=20)
    parser.add_argument('--format', '-f', choices=['json', 'text'], default='json')
    args = parser.parse_args()

    result = None

    if args.canonical:
        result = search_canonical(args.docs_dir, args.canonical)
    elif args.error_code:
        result = search_error_code(args.docs_dir, args.error_code, args.exchange)
    elif args.list_endpoints:
        if not args.exchange:
            print("Error: --exchange required with --list-endpoints", file=sys.stderr)
            sys.exit(1)
        result = list_endpoints(args.docs_dir, args.exchange, args.section)
    elif args.rate_limits:
        if not args.exchange:
            print("Error: --exchange required with --rate-limits", file=sys.stderr)
            sys.exit(1)
        result = get_rate_limits(args.docs_dir, args.exchange, args.section)
    elif args.permissions:
        if not args.exchange:
            print("Error: --exchange required with --permissions", file=sys.stderr)
            sys.exit(1)
        result = get_permissions(args.docs_dir, args.exchange, args.endpoint)
    elif args.query:
        # First search parsed endpoints, then fall back to FTS
        result = search_endpoints(args.docs_dir, exchange=args.exchange,
                                  query=args.query, section=args.section)
        if not result:
            result = search_fts(args.docs_dir, args.query, args.exchange, args.limit)
    else:
        parser.print_help()
        return

    if result is None:
        print("No results found.", file=sys.stderr)
    elif args.format == 'json':
        print(json.dumps(result, indent=2, default=str))
    else:
        # Simple text output
        if isinstance(result, list):
            for item in result:
                if 'endpoint' in item and isinstance(item['endpoint'], dict):
                    e = item['endpoint']
                    print(f"{e.get('method','')} {e.get('path','')} \u2014 {e.get('description','')[:80]}")
                elif 'method' in item:
                    canon = f" [{item['canonical']}]" if item.get('canonical') else ''
                    print(f"  {item['method']} {item['path']}{canon} ({item['section']})")
                else:
                    print(json.dumps(item, indent=2, default=str))
        elif isinstance(result, dict):
            for key, val in result.items():
                print(f"\
=== {key} ===")
                if isinstance(val, list):
                    for v in val:
                        print(f"  {v.get('method','')} {v.get('path','')} ({v.get('section','')})")
                else:
                    print(f"  {val}")


if __name__ == '__main__':
    main()
