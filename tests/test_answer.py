from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from xdocs.answer import answer_question
from xdocs.db import open_db
from xdocs.hashing import sha256_hex_bytes, sha256_hex_text
from xdocs.markdown import normalize_markdown
from xdocs.registry import load_registry
from xdocs.store import init_store
from xdocs.timeutil import now_iso_utc


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestAnswer(unittest.TestCase):
    def test_answer_clarification_and_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            reg = load_registry(REPO_ROOT / "data" / "exchanges.yaml")
            binance = reg.get_exchange("binance")
            seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in binance.sections if sec.seed_urls}

            spot_prefix = seed_prefixes["spot"]
            pm_prefix = seed_prefixes["portfolio_margin"]

            spot_url = spot_prefix + "rate-limits.html"
            pm_url = pm_prefix + "rate-limits.html"

            spot_md = normalize_markdown("Rate limit weight is 2 per second.\\n")
            pm_md = normalize_markdown("Rate limit weight is 10 per second.\\n")

            crawled_at = now_iso_utc()

            def insert_page(url: str, md: str) -> None:
                canonical_url = url
                domain = (urlsplit(canonical_url).hostname or "").lower()
                path_hash = sha256_hex_text(canonical_url)
                content_hash = sha256_hex_text(md)
                raw_hash = sha256_hex_bytes(b"")

                raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
                md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
                meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(b"")
                md_path.write_text(md, encoding="utf-8")
                meta_path.write_text(
                    json.dumps(
                        {
                            "url": canonical_url,
                            "final_url": canonical_url,
                            "canonical_url": canonical_url,
                            "redirect_chain": [],
                            "crawled_at": crawled_at,
                            "http_status": 200,
                            "content_type": "text/html",
                            "raw_hash": raw_hash,
                            "content_hash": content_hash,
                            "path_hash": path_hash,
                            "render_mode": "http",
                            "extractor": {"name": "html2text", "version": "test", "config": {}, "config_hash": "test"},
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\\n",
                    encoding="utf-8",
                )

                conn = open_db(docs_dir / "db" / "docs.db")
                try:
                    with conn:
                        cur = conn.execute(
                            """
INSERT INTO pages (
  canonical_url, url, final_url, domain, path_hash, title,
  http_status, content_type, render_mode, raw_hash, content_hash,
  crawled_at, raw_path, markdown_path, meta_path, word_count,
  extractor_name, extractor_version, extractor_config_json, extractor_config_hash,
  last_crawl_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                            (
                                canonical_url,
                                canonical_url,
                                canonical_url,
                                domain,
                                path_hash,
                                None,
                                200,
                                "text/html",
                                "http",
                                raw_hash,
                                content_hash,
                                crawled_at,
                                str(raw_path),
                                str(md_path),
                                str(meta_path),
                                len(md.split()),
                                "html2text",
                                "test",
                                "{}",
                                "test",
                                None,
                            ),
                        )
                        page_id = int(cur.lastrowid)
                        conn.execute("INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);", (page_id, canonical_url, "", md))
                    conn.commit()
                finally:
                    conn.close()

            insert_page(spot_url, spot_md)
            insert_page(pm_url, pm_md)

            # Ambiguous question -> needs clarification
            q = "What's the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint?"
            out = answer_question(docs_dir=str(docs_dir), question=q, clarification=None)
            self.assertEqual(out["status"], "needs_clarification")

            # With clarification -> cite-backed + derived diff.
            out2 = answer_question(docs_dir=str(docs_dir), question=q, clarification="binance:portfolio_margin")
            self.assertEqual(out2["status"], "ok")
            derived = [c for c in out2["claims"] if c["kind"] == "DERIVED"]
            self.assertEqual(len(derived), 1)
            self.assertEqual(derived[0]["derived"]["op"], "diff")
            self.assertEqual(len(derived[0]["derived"]["inputs"]), 2)

    def test_wow_query_permissions_missing_is_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            reg = load_registry(REPO_ROOT / "data" / "exchanges.yaml")
            binance = reg.get_exchange("binance")
            seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in binance.sections if sec.seed_urls}

            spot_prefix = seed_prefixes["spot"]
            pm_prefix = seed_prefixes["portfolio_margin"]

            spot_url = spot_prefix + "rate-limits.html"
            pm_url = pm_prefix + "rate-limits.html"

            spot_md = normalize_markdown("Rate limit weight is 2 per second.\\n")
            pm_md = normalize_markdown("Rate limit weight is 10 per second.\\n")
            crawled_at = now_iso_utc()

            def insert_page(url: str, md: str) -> None:
                canonical_url = url
                domain = (urlsplit(canonical_url).hostname or "").lower()
                path_hash = sha256_hex_text(canonical_url)
                content_hash = sha256_hex_text(md)
                raw_hash = sha256_hex_bytes(b"")

                raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
                md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
                meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(b"")
                md_path.write_text(md, encoding="utf-8")
                meta_path.write_text(
                    json.dumps(
                        {
                            "url": canonical_url,
                            "final_url": canonical_url,
                            "canonical_url": canonical_url,
                            "redirect_chain": [],
                            "crawled_at": crawled_at,
                            "http_status": 200,
                            "content_type": "text/html",
                            "raw_hash": raw_hash,
                            "content_hash": content_hash,
                            "path_hash": path_hash,
                            "render_mode": "http",
                            "extractor": {"name": "html2text", "version": "test", "config": {}, "config_hash": "test"},
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\\n",
                    encoding="utf-8",
                )

                conn = open_db(docs_dir / "db" / "docs.db")
                try:
                    with conn:
                        cur = conn.execute(
                            """
INSERT INTO pages (
  canonical_url, url, final_url, domain, path_hash, title,
  http_status, content_type, render_mode, raw_hash, content_hash,
  crawled_at, raw_path, markdown_path, meta_path, word_count,
  extractor_name, extractor_version, extractor_config_json, extractor_config_hash,
  last_crawl_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                            (
                                canonical_url,
                                canonical_url,
                                canonical_url,
                                domain,
                                path_hash,
                                None,
                                200,
                                "text/html",
                                "http",
                                raw_hash,
                                content_hash,
                                crawled_at,
                                str(raw_path),
                                str(md_path),
                                str(meta_path),
                                len(md.split()),
                                "html2text",
                                "test",
                                "{}",
                                "test",
                                None,
                            ),
                        )
                        page_id = int(cur.lastrowid)
                        conn.execute("INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);", (page_id, canonical_url, "", md))
                    conn.commit()
                finally:
                    conn.close()

            insert_page(spot_url, spot_md)
            insert_page(pm_url, pm_md)

            wow = (
                "What's the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? "
                "And in order to look up the balance of our Binance subaccount in Portfolio Margin mode what permissions does the API key need?"
            )

            out = answer_question(docs_dir=str(docs_dir), question=wow, clarification=None)
            self.assertEqual(out["status"], "needs_clarification")

            out2 = answer_question(docs_dir=str(docs_dir), question=wow, clarification="binance:portfolio_margin")
            self.assertNotEqual(out2["status"], "ok")
            self.assertIn("required_permissions", out2.get("missing", []))

    def test_wow_query_ok_when_permissions_evidence_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "cex-docs"
            init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)

            reg = load_registry(REPO_ROOT / "data" / "exchanges.yaml")
            binance = reg.get_exchange("binance")
            seed_prefixes = {sec.section_id: sec.seed_urls[0] for sec in binance.sections if sec.seed_urls}

            spot_prefix = seed_prefixes["spot"]
            pm_prefix = seed_prefixes["portfolio_margin"]

            spot_url = spot_prefix + "rate-limits.html"
            pm_url = pm_prefix + "rate-limits.html"
            perm_url = pm_prefix + "permissions.html"

            spot_md = normalize_markdown("Rate limit weight is 2 per second.\\n")
            pm_md = normalize_markdown("Rate limit weight is 10 per second.\\n")
            perm_md = normalize_markdown("## Permissions\\nPermissions: Read Info\\n")
            crawled_at = now_iso_utc()

            def insert_page(url: str, md: str) -> None:
                canonical_url = url
                domain = (urlsplit(canonical_url).hostname or "").lower()
                path_hash = sha256_hex_text(canonical_url)
                content_hash = sha256_hex_text(md)
                raw_hash = sha256_hex_bytes(b"")

                raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
                md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
                meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(b"")
                md_path.write_text(md, encoding="utf-8")
                meta_path.write_text(
                    json.dumps(
                        {
                            "url": canonical_url,
                            "final_url": canonical_url,
                            "canonical_url": canonical_url,
                            "redirect_chain": [],
                            "crawled_at": crawled_at,
                            "http_status": 200,
                            "content_type": "text/html",
                            "raw_hash": raw_hash,
                            "content_hash": content_hash,
                            "path_hash": path_hash,
                            "render_mode": "http",
                            "extractor": {"name": "html2text", "version": "test", "config": {}, "config_hash": "test"},
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\\n",
                    encoding="utf-8",
                )

                conn = open_db(docs_dir / "db" / "docs.db")
                try:
                    with conn:
                        cur = conn.execute(
                            """
INSERT INTO pages (
  canonical_url, url, final_url, domain, path_hash, title,
  http_status, content_type, render_mode, raw_hash, content_hash,
  crawled_at, raw_path, markdown_path, meta_path, word_count,
  extractor_name, extractor_version, extractor_config_json, extractor_config_hash,
  last_crawl_run_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
""",
                            (
                                canonical_url,
                                canonical_url,
                                canonical_url,
                                domain,
                                path_hash,
                                None,
                                200,
                                "text/html",
                                "http",
                                raw_hash,
                                content_hash,
                                crawled_at,
                                str(raw_path),
                                str(md_path),
                                str(meta_path),
                                len(md.split()),
                                "html2text",
                                "test",
                                "{}",
                                "test",
                                None,
                            ),
                        )
                        page_id = int(cur.lastrowid)
                        conn.execute("INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);", (page_id, canonical_url, "", md))
                    conn.commit()
                finally:
                    conn.close()

            insert_page(spot_url, spot_md)
            insert_page(pm_url, pm_md)
            insert_page(perm_url, perm_md)

            wow = (
                "What's the rate limit difference between Binance unified trading endpoint and the Binance spot endpoint? "
                "And in order to look up the balance of our Binance subaccount in Portfolio Margin mode what permissions does the API key need?"
            )
            out = answer_question(docs_dir=str(docs_dir), question=wow, clarification="binance:portfolio_margin")
            self.assertEqual(out["status"], "ok")
            self.assertTrue(any(c.get("citations") and c["citations"][0].get("field_name") == "required_permissions" for c in out.get("claims", [])))


if __name__ == "__main__":
    unittest.main()
