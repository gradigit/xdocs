#!/usr/bin/env python3
"""
cex_update.py: Check for documentation changes across exchanges.

Designed to run as a cron job. Re-crawls exchange docs, compares against previous crawl,
and reports changes. Can output to JSON file or (future) alert to Slack.

Usage:
    python3 cex_update.py --exchange binance --docs-dir ./cex-docs
    python3 cex_update.py --all --docs-dir ./cex-docs --output changes.json
    python3 cex_update.py --all --docs-dir ./cex-docs --slack-webhook https://hooks.slack.com/...

Cron example (hourly):
    0 * * * * cd /path/to/workspace && python3 cex_update.py --all --docs-dir ./cex-docs --output /tmp/cex-changes.json
"""

import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_crawl(exchange_id, docs_dir, section=None):
    """Run cex_crawl.py for an exchange and return exit code."""
    cmd = [sys.executable, str(SCRIPT_DIR / 'cex_crawl.py'),
           '--exchange', exchange_id, '--output-dir', docs_dir, '--delay', '0.5']
    if section:
        cmd.extend(['--section', section])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result.returncode, result.stdout, result.stderr


def run_diff(docs_dir, domain=None):
    """Run doc-crawler diff and return changes."""
    # Try to find diff.py
    diff_candidates = [
        SCRIPT_DIR.parent.parent / 'doc-crawler' / 'doc-crawler' / 'scripts' / 'diff.py',
        Path.home() / 'doc-crawler' / 'scripts' / 'diff.py',
    ]
    diff_script = None
    for c in diff_candidates:
        if c.exists():
            diff_script = str(c)
            break

    if not diff_script:
        return {'error': 'diff.py not found'}

    cmd = [sys.executable, diff_script, '--docs-dir', docs_dir, '--format', 'json']
    if domain:
        cmd.extend(['--domain', domain])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {'raw_output': result.stdout}
    return {'error': result.stderr or 'No output'}


def send_slack_alert(webhook_url, changes, exchange_id):
    """Send change alert to Slack webhook."""
    try:
        import requests
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               '--break-system-packages', '-q', 'requests'])
        import requests

    total_new = len(changes.get('new', []))
    total_updated = len(changes.get('updated', []))
    total_stale = len(changes.get('stale', []))
    total = total_new + total_updated + total_stale

    if total == 0:
        return  # No changes, no alert

    blocks = [
        {"type": "header", "text": {
            "type": "plain_text",
            "text": f"\ud83d\udd04 API Doc Changes: {exchange_id.upper()}"
        }},
        {"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*{total_new}* new pages, *{total_updated}* updated, *{total_stale}* removed"
        }},
    ]

    # Add details for updated pages (most important for API changes)
    if changes.get('updated'):
        details = "\
".join(
            f"\u2022 <{p['url']}|{p.get('title', p['url'][:50])}>"
            for p in changes['updated'][:10]
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": details}})

    payload = {"blocks": blocks}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"Slack alert failed: {resp.status_code} {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"Slack alert error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Check for CEX API doc updates')
    parser.add_argument('--exchange', '-e', help='Exchange ID')
    parser.add_argument('--all', action='store_true', help='Check all exchanges')
    parser.add_argument('--docs-dir', '-d', default='./cex-docs')
    parser.add_argument('--output', '-o', help='Output changes to JSON file')
    parser.add_argument('--slack-webhook', help='Slack webhook URL for alerts')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be crawled')
    args = parser.parse_args()

    # Load registry
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        # Ensure yaml is available
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--break-system-packages',
                        '-q', 'pyyaml'], capture_output=True)
        from cex_crawl import parse_registry
        exchanges = parse_registry()
    except Exception as e:
        print(f"Error loading registry: {e}", file=sys.stderr)
        sys.exit(1)

    targets = []
    if args.all:
        targets = list(exchanges.keys())
    elif args.exchange:
        targets = [args.exchange]
    else:
        parser.print_help()
        return

    all_changes = {}
    timestamp = datetime.now(timezone.utc).isoformat()

    for ex_id in targets:
        if ex_id not in exchanges:
            print(f"Warning: {ex_id} not in registry, skipping")
            continue

        ex = exchanges[ex_id]
        domain = ex.get('domain_scope', '')
        print(f"\
{'='*40}")
        print(f"Checking {ex_id}...")

        if args.dry_run:
            print(f"  Would crawl: {list(ex.get('doc_urls', {}).values())}")
            continue

        # Crawl
        exit_code, stdout, stderr = run_crawl(ex_id, args.docs_dir)
        if exit_code != 0:
            print(f"  Crawl failed: {stderr[:200]}")
            all_changes[ex_id] = {'error': 'crawl_failed'}
            continue

        # Diff
        changes = run_diff(args.docs_dir, domain)
        all_changes[ex_id] = changes

        total = sum(len(changes.get(k, [])) for k in ('new', 'updated', 'stale'))
        print(f"  Changes: {total} "
              f"({len(changes.get('new', []))} new, "
              f"{len(changes.get('updated', []))} updated, "
              f"{len(changes.get('stale', []))} stale)")

        # Slack alert
        if args.slack_webhook and total > 0:
            send_slack_alert(args.slack_webhook, changes, ex_id)

    # Save output
    if args.output:
        output = {
            'timestamp': timestamp,
            'exchanges_checked': targets,
            'changes': all_changes,
        }
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\
Changes saved to: {args.output}")

    # Summary
    print(f"\
{'='*40}")
    print(f"Update check complete: {len(targets)} exchanges")
    for ex_id, changes in all_changes.items():
        if 'error' in changes:
            print(f"  {ex_id}: ERROR \u2014 {changes['error']}")
        else:
            total = sum(len(changes.get(k, [])) for k in ('new', 'updated', 'stale'))
            print(f"  {ex_id}: {total} changes")


if __name__ == '__main__':
    main()
