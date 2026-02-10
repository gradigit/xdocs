#!/usr/bin/env python3
"""
POC: Full Binance API docs fetch — HTTP vs Playwright vs Jina Reader.

Phase 1: Discover all doc URLs via link-following from seed pages.
Phase 2: Fetch every URL via three methods, save results to disk.
Phase 3: Generate comparison report.

Usage:
    # Phase 1 only (discover URLs)
    python scripts/poc_full_binance.py discover

    # Phase 2: fetch via a specific method (uses discovered URLs from phase 1)
    python scripts/poc_full_binance.py fetch-http
    python scripts/poc_full_binance.py fetch-playwright
    python scripts/poc_full_binance.py fetch-jina

    # Phase 3: compare results
    python scripts/poc_full_binance.py compare
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

# ---------- Configuration ----------

SEED_URLS = [
    "https://developers.binance.com/docs/binance-spot-api-docs/",
    "https://developers.binance.com/docs/derivatives/usds-margined-futures/",
    "https://developers.binance.com/docs/derivatives/coin-margined-futures/",
    "https://developers.binance.com/docs/derivatives/portfolio-margin/",
]
ALLOWED_PREFIX = "https://developers.binance.com/docs/"
OUTPUT_DIR = Path("poc-binance-full")
DISCOVER_FILE = OUTPUT_DIR / "discovered_urls.json"
DELAY_S = 0.3  # polite delay between requests
TIMEOUT_S = 30
MAX_PAGES = 5000  # safety cap

# ---------- Helpers ----------

def url_key(url: str) -> str:
    """Normalize URL for dedup (strip fragment, trailing slash)."""
    p = urlsplit(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def safe_filename(url: str) -> str:
    """URL -> filesystem-safe filename."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def count_words(text: str) -> int:
    return len(text.split())

def count_endpoints(text: str) -> int:
    """Count HTTP method + path signatures."""
    pattern = r'\b(GET|POST|PUT|DELETE|PATCH)\s+/\S+'
    return len(re.findall(pattern, text))

def count_headings(text: str) -> int:
    """Count markdown headings."""
    return len(re.findall(r'^#{1,6}\s+', text, re.MULTILINE))

def count_code_blocks(text: str) -> int:
    """Count code blocks (fenced or [code] style)."""
    fenced = len(re.findall(r'^```', text, re.MULTILINE))
    bracketed = len(re.findall(r'\[code\]', text, re.IGNORECASE))
    return fenced // 2 + bracketed

def count_tables(text: str) -> int:
    """Count table rows (pipe-style or html2text style)."""
    pipe_rows = len(re.findall(r'^\|.*\|', text, re.MULTILINE))
    pipeless = len(re.findall(r'^[A-Z]\w+\|', text, re.MULTILINE))
    return pipe_rows + pipeless

# ---------- Phase 1: Discover ----------

def discover_urls() -> list[str]:
    """BFS link-follow from seed URLs to discover all Binance doc pages."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "cex-api-docs-poc/1.0"

    seen = set()
    queue = []
    for seed in SEED_URLS:
        k = url_key(seed)
        if k not in seen:
            seen.add(k)
            queue.append(seed)

    discovered = []
    idx = 0
    errors = 0

    print(f"Starting discovery from {len(SEED_URLS)} seeds...")
    while idx < len(queue) and len(discovered) < MAX_PAGES:
        url = queue[idx]
        idx += 1

        try:
            r = session.get(url, timeout=TIMEOUT_S, allow_redirects=True)
            status = r.status_code
        except Exception as e:
            print(f"  ERR {url}: {e}")
            errors += 1
            continue

        if status != 200:
            print(f"  {status} {url}")
            errors += 1
            continue

        ct = r.headers.get("content-type", "")
        if "html" not in ct:
            continue

        discovered.append(url)

        # Extract links
        try:
            soup = BeautifulSoup(r.content, "html.parser")
        except Exception:
            continue

        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            href = href.split("#")[0].split("?")[0]  # strip fragment and query
            if not href.startswith(ALLOWED_PREFIX):
                continue
            k = url_key(href)
            if k not in seen:
                seen.add(k)
                queue.append(href)

        if len(discovered) % 25 == 0:
            print(f"  Discovered {len(discovered)} pages, queue depth {len(queue) - idx}...")

        time.sleep(DELAY_S)

    print(f"\nDiscovery complete: {len(discovered)} pages ({errors} errors)")

    # Persist
    with open(DISCOVER_FILE, "w") as f:
        json.dump({"urls": discovered, "count": len(discovered), "errors": errors}, f, indent=2)
    print(f"Saved to {DISCOVER_FILE}")
    return discovered


# ---------- Phase 2: Fetch methods ----------

def _load_urls() -> list[str]:
    if not DISCOVER_FILE.exists():
        print(f"ERROR: {DISCOVER_FILE} not found. Run 'discover' first.")
        sys.exit(1)
    data = json.loads(DISCOVER_FILE.read_text())
    return data["urls"]


def fetch_http(urls: list[str]) -> None:
    """Fetch all URLs via plain HTTP + html2text."""
    import html2text

    out_dir = OUTPUT_DIR / "http"
    out_dir.mkdir(parents=True, exist_ok=True)

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    h.ignore_images = True

    session = requests.Session()
    session.headers["User-Agent"] = "cex-api-docs-poc/1.0"

    results = []
    total = len(urls)
    for i, url in enumerate(urls):
        t0 = time.time()
        try:
            r = session.get(url, timeout=TIMEOUT_S)
            elapsed = time.time() - t0
            if r.status_code != 200:
                results.append({"url": url, "status": r.status_code, "error": True, "elapsed_s": elapsed})
                continue

            html = r.text
            md = h.handle(html)

            # Also try article-only extraction
            soup = BeautifulSoup(html, "html.parser")
            article = soup.select_one("article")
            md_article = h.handle(str(article)) if article else ""

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            fname = safe_filename(url)
            (out_dir / f"{fname}.md").write_text(md)
            if md_article:
                (out_dir / f"{fname}_article.md").write_text(md_article)

            rec = {
                "url": url,
                "status": 200,
                "error": False,
                "elapsed_s": round(elapsed, 3),
                "title": title,
                "word_count_full": count_words(md),
                "word_count_article": count_words(md_article),
                "endpoints": count_endpoints(md),
                "headings": count_headings(md),
                "code_blocks": count_code_blocks(md),
                "tables": count_tables(md),
                "md_bytes": len(md.encode()),
                "html_bytes": len(html.encode()),
            }
            results.append(rec)
        except Exception as e:
            elapsed = time.time() - t0
            results.append({"url": url, "error": True, "exception": str(e), "elapsed_s": round(elapsed, 3)})

        if (i + 1) % 25 == 0 or (i + 1) == total:
            print(f"  HTTP: {i+1}/{total}")

        time.sleep(DELAY_S)

    meta_path = out_dir / "results.json"
    with open(meta_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"HTTP fetch done. {len([r for r in results if not r.get('error')])} success, "
          f"{len([r for r in results if r.get('error')])} errors. Saved to {meta_path}")


def fetch_playwright(urls: list[str]) -> None:
    """Fetch all URLs via headless Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    out_dir = OUTPUT_DIR / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(urls)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="cex-api-docs-poc/1.0 (Playwright)",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        for i, url in enumerate(urls):
            t0 = time.time()
            try:
                resp = page.goto(url, timeout=TIMEOUT_S * 1000, wait_until="networkidle")
                elapsed = time.time() - t0
                status = resp.status if resp else 0

                if status != 200:
                    results.append({"url": url, "status": status, "error": True, "elapsed_s": round(elapsed, 3)})
                    continue

                # Wait for Docusaurus hydration
                page.wait_for_timeout(500)

                # Extract article content
                article_text = page.evaluate("""() => {
                    const article = document.querySelector('article');
                    return article ? article.innerText : document.body.innerText;
                }""")

                # Extract article HTML for markdown conversion
                article_html = page.evaluate("""() => {
                    const article = document.querySelector('article');
                    return article ? article.outerHTML : '';
                }""")

                title = page.title()

                # Count structured elements via DOM
                dom_stats = page.evaluate("""() => {
                    const article = document.querySelector('article') || document.body;
                    return {
                        headings: article.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
                        code_blocks: article.querySelectorAll('pre code').length,
                        table_rows: article.querySelectorAll('tr').length,
                        links: article.querySelectorAll('a[href]').length,
                    };
                }""")

                fname = safe_filename(url)
                (out_dir / f"{fname}.txt").write_text(article_text)
                if article_html:
                    (out_dir / f"{fname}.html").write_text(article_html)

                rec = {
                    "url": url,
                    "status": 200,
                    "error": False,
                    "elapsed_s": round(elapsed, 3),
                    "title": title,
                    "word_count": count_words(article_text),
                    "endpoints": count_endpoints(article_text),
                    "headings_dom": dom_stats["headings"],
                    "code_blocks_dom": dom_stats["code_blocks"],
                    "table_rows_dom": dom_stats["table_rows"],
                    "links_dom": dom_stats["links"],
                    "text_bytes": len(article_text.encode()),
                    "html_bytes": len(article_html.encode()) if article_html else 0,
                }
                results.append(rec)
            except Exception as e:
                elapsed = time.time() - t0
                results.append({"url": url, "error": True, "exception": str(e), "elapsed_s": round(elapsed, 3)})

            if (i + 1) % 25 == 0 or (i + 1) == total:
                print(f"  Playwright: {i+1}/{total}")

        browser.close()

    meta_path = out_dir / "results.json"
    with open(meta_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Playwright fetch done. {len([r for r in results if not r.get('error')])} success, "
          f"{len([r for r in results if r.get('error')])} errors. Saved to {meta_path}")


def fetch_jina(urls: list[str]) -> None:
    """Fetch all URLs via Jina Reader API (r.jina.ai)."""
    out_dir = OUTPUT_DIR / "jina"
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    # Jina Reader: prefix URL with r.jina.ai to get markdown
    session.headers["User-Agent"] = "cex-api-docs-poc/1.0"
    session.headers["Accept"] = "text/markdown"

    # Check for Jina API key in environment
    api_key = os.environ.get("JINA_API_KEY", "")
    if api_key:
        session.headers["Authorization"] = f"Bearer {api_key}"
        print("  Using Jina API key from JINA_API_KEY env var")
    else:
        print("  No JINA_API_KEY set — using free tier (rate limits apply)")

    results = []
    total = len(urls)
    rate_limited = 0

    for i, url in enumerate(urls):
        t0 = time.time()
        jina_url = f"https://r.jina.ai/{url}"
        try:
            r = session.get(jina_url, timeout=60)
            elapsed = time.time() - t0

            if r.status_code == 429:
                rate_limited += 1
                # Back off
                retry_after = int(r.headers.get("Retry-After", "10"))
                print(f"  Rate limited at {i+1}/{total}, backing off {retry_after}s...")
                time.sleep(retry_after)
                # Retry once
                t0 = time.time()
                r = session.get(jina_url, timeout=60)
                elapsed = time.time() - t0

            if r.status_code != 200:
                results.append({"url": url, "status": r.status_code, "error": True, "elapsed_s": round(elapsed, 3)})
                continue

            md = r.text

            fname = safe_filename(url)
            (out_dir / f"{fname}.md").write_text(md)

            rec = {
                "url": url,
                "status": 200,
                "error": False,
                "elapsed_s": round(elapsed, 3),
                "word_count": count_words(md),
                "endpoints": count_endpoints(md),
                "headings": count_headings(md),
                "code_blocks": count_code_blocks(md),
                "tables": count_tables(md),
                "md_bytes": len(md.encode()),
            }
            results.append(rec)
        except Exception as e:
            elapsed = time.time() - t0
            results.append({"url": url, "error": True, "exception": str(e), "elapsed_s": round(elapsed, 3)})

        if (i + 1) % 25 == 0 or (i + 1) == total:
            ok = len([r for r in results if not r.get('error')])
            print(f"  Jina: {i+1}/{total} ({ok} ok, {rate_limited} rate-limited)")

        time.sleep(DELAY_S)

    meta_path = out_dir / "results.json"
    with open(meta_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Jina fetch done. {len([r for r in results if not r.get('error')])} success, "
          f"{len([r for r in results if r.get('error')])} errors, "
          f"{rate_limited} rate-limited. Saved to {meta_path}")


# ---------- Phase 3: Compare ----------

def compare() -> None:
    """Load results from all three methods and generate comparison report."""
    report_lines = ["# POC: Full Binance Docs — HTTP vs Playwright vs Jina\n"]
    report_lines.append(f"**Date:** {time.strftime('%Y-%m-%d')}\n")

    methods = {}
    for method in ["http", "playwright", "jina"]:
        rpath = OUTPUT_DIR / method / "results.json"
        if rpath.exists():
            methods[method] = json.loads(rpath.read_text())
            report_lines.append(f"- **{method}**: {len(methods[method])} URLs attempted")
        else:
            report_lines.append(f"- **{method}**: not run")

    report_lines.append("")

    # Summary stats per method
    report_lines.append("## Summary\n")
    report_lines.append("| Metric | " + " | ".join(methods.keys()) + " |")
    report_lines.append("|--------|" + "|".join(["-----"] * len(methods)) + "|")

    for metric_name, key, agg in [
        ("Pages fetched OK", None, "count_ok"),
        ("Errors", None, "count_err"),
        ("Total words", "word_count", "sum"),
        ("Total endpoints found", "endpoints", "sum"),
        ("Avg words/page", "word_count", "avg"),
        ("Avg elapsed (s)", "elapsed_s", "avg"),
        ("Total elapsed (s)", "elapsed_s", "sum"),
        ("Total bytes (MB)", "md_bytes", "sum_mb"),
    ]:
        row = [metric_name]
        for method, data in methods.items():
            ok = [r for r in data if not r.get("error")]
            err = [r for r in data if r.get("error")]
            if agg == "count_ok":
                row.append(str(len(ok)))
            elif agg == "count_err":
                row.append(str(len(err)))
            elif agg == "sum":
                # Handle different key names per method
                vals = []
                for r in ok:
                    # Try method-specific keys
                    if key == "word_count":
                        v = r.get("word_count") or r.get("word_count_full") or r.get("word_count_article", 0)
                    else:
                        v = r.get(key, 0)
                    vals.append(v or 0)
                row.append(f"{sum(vals):,.0f}")
            elif agg == "avg":
                vals = []
                for r in ok:
                    if key == "word_count":
                        v = r.get("word_count") or r.get("word_count_full") or r.get("word_count_article", 0)
                    else:
                        v = r.get(key, 0)
                    vals.append(v or 0)
                avg = sum(vals) / len(vals) if vals else 0
                row.append(f"{avg:,.1f}")
            elif agg == "sum_mb":
                vals = [r.get(key, 0) or 0 for r in ok]
                row.append(f"{sum(vals) / 1024 / 1024:.1f}")
            else:
                row.append("?")
        report_lines.append("| " + " | ".join(row) + " |")

    report_lines.append("")

    # Per-URL comparison (if all methods present)
    if len(methods) >= 2:
        report_lines.append("## Per-URL Word Count Comparison\n")

        # Build URL -> method -> word_count map
        url_words: dict[str, dict[str, int]] = defaultdict(dict)
        for method, data in methods.items():
            for r in data:
                if r.get("error"):
                    continue
                url = r["url"]
                wc = r.get("word_count") or r.get("word_count_full", 0)
                url_words[url][method] = wc or 0

        # Top pages by word count (from any method)
        all_urls = sorted(url_words.keys(), key=lambda u: max(url_words[u].values()), reverse=True)

        report_lines.append(f"Total unique URLs with content: {len(all_urls)}\n")
        report_lines.append("### Top 20 pages by word count\n")
        report_lines.append("| URL (short) | " + " | ".join(methods.keys()) + " |")
        report_lines.append("|-------------|" + "|".join(["-----"] * len(methods)) + "|")

        for url in all_urls[:20]:
            short = url.replace("https://developers.binance.com/docs/", "")
            row = [short[:60]]
            for method in methods:
                row.append(str(url_words[url].get(method, "-")))
            report_lines.append("| " + " | ".join(row) + " |")

        # Pages missing in one method but present in another
        report_lines.append("\n### Coverage gaps\n")
        for method in methods:
            method_urls = {r["url"] for r in methods[method] if not r.get("error")}
            for other in methods:
                if other == method:
                    continue
                other_urls = {r["url"] for r in methods[other] if not r.get("error")}
                missing = other_urls - method_urls
                if missing:
                    report_lines.append(f"- **{method}** missing {len(missing)} URLs that **{other}** has")

    report_lines.append("")

    # Article vs full page (HTTP only)
    if "http" in methods:
        report_lines.append("## HTTP: Full Page vs Article-only\n")
        ok = [r for r in methods["http"] if not r.get("error")]
        full_wc = sum(r.get("word_count_full", 0) for r in ok)
        art_wc = sum(r.get("word_count_article", 0) for r in ok)
        if full_wc > 0:
            noise_pct = (1 - art_wc / full_wc) * 100
            report_lines.append(f"- Full page total words: {full_wc:,}")
            report_lines.append(f"- Article-only total words: {art_wc:,}")
            report_lines.append(f"- Navigation noise: {noise_pct:.1f}%")
        report_lines.append("")

    # Write report
    report_path = OUTPUT_DIR / "comparison_report.md"
    report_path.write_text("\n".join(report_lines))
    print(f"\nReport saved to {report_path}")

    # Also print it
    print("\n" + "=" * 60)
    print("\n".join(report_lines))


# ---------- Main ----------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "discover":
        discover_urls()
    elif cmd == "fetch-http":
        urls = _load_urls()
        fetch_http(urls)
    elif cmd == "fetch-playwright":
        urls = _load_urls()
        fetch_playwright(urls)
    elif cmd == "fetch-jina":
        urls = _load_urls()
        fetch_jina(urls)
    elif cmd == "compare":
        compare()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
