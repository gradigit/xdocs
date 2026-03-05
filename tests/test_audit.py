"""Tests for fsck extended checks and the audit orchestrator."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cex_api_docs.db import open_db
from cex_api_docs.store import init_store

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _setup_store(tmp_path: Path) -> Path:
    """Create an initialized store in tmp_path and return docs_dir."""
    docs_dir = tmp_path / "cex-docs"
    init_store(docs_dir=str(docs_dir), schema_sql_path=REPO_ROOT / "schema" / "schema.sql", lock_timeout_s=1.0)
    return docs_dir


def _insert_page(conn, *, docs_dir: Path, url: str, domain: str, title: str, markdown: str) -> None:
    """Insert a page with matching markdown file.  Stores absolute paths (same as page_store.py)."""
    path_hash = hashlib.sha256(url.encode()).hexdigest()
    content_hash = _sha256_text(markdown)

    md_path = docs_dir / "pages" / domain / f"{path_hash}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    raw_path = docs_dir / "raw" / domain / f"{path_hash}.bin"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"<html>" + markdown.encode() + b"</html>")

    meta_path = docs_dir / "meta" / domain / f"{path_hash}.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("{}", encoding="utf-8")

    word_count = len(markdown.split())
    conn.execute(
        """INSERT INTO pages (canonical_url, url, final_url, domain, path_hash, title, word_count,
                              raw_path, markdown_path, meta_path, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
        (url, url, url, domain, path_hash, title, word_count,
         str(raw_path), str(md_path), str(meta_path), content_hash),
    )

    # Insert matching FTS row.
    page_id = conn.execute("SELECT id FROM pages WHERE canonical_url = ?;", (url,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO pages_fts (rowid, canonical_url, title, markdown) VALUES (?, ?, ?, ?);",
        (page_id, url, title, markdown),
    )
    conn.commit()


def _insert_endpoint(conn, *, docs_dir: Path, endpoint_id: str, exchange: str, section: str, record: dict) -> None:
    """Insert an endpoint with matching on-disk JSON file."""
    json_str = json.dumps(record, sort_keys=True, ensure_ascii=False)
    method = record.get("method", "")
    path = record.get("path", "")

    conn.execute(
        """INSERT INTO endpoints (endpoint_id, exchange, section, protocol, json, updated_at)
           VALUES (?, ?, ?, 'http', ?, datetime('now'));""",
        (endpoint_id, exchange, section, json_str),
    )

    # Insert matching FTS row.
    rowid = conn.execute("SELECT rowid FROM endpoints WHERE endpoint_id = ?;", (endpoint_id,)).fetchone()["rowid"]
    conn.execute(
        "INSERT INTO endpoints_fts (rowid, endpoint_id, exchange, section, method, path, search_text) VALUES (?, ?, ?, ?, ?, ?, ?);",
        (rowid, endpoint_id, exchange, section, method, path, json_str),
    )
    conn.commit()

    # Write on-disk JSON file.
    ep_dir = docs_dir / "endpoints" / exchange / section
    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / f"{endpoint_id}.json").write_text(json_str, encoding="utf-8")


# --- fsck extended check tests ---


class TestFsckVerifyHashes(unittest.TestCase):
    def test_clean_hashes(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nSome content here.")
            finally:
                conn.close()

            r = fsck_store(docs_dir=str(docs_dir), verify_hashes=True)
            self.assertEqual(r["hash_verification"]["mismatches"], 0)
            self.assertEqual(r["hash_verification"]["checked"], 1)
            hash_issues = [i for i in r["issues"] if i["kind"] == "content_hash_mismatch"]
            self.assertEqual(len(hash_issues), 0)

    def test_mismatch_detected(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nOriginal content.")
            finally:
                conn.close()

            # Corrupt the markdown file.
            md_files = list((docs_dir / "pages").rglob("*.md"))
            self.assertEqual(len(md_files), 1)
            md_files[0].write_text("# Page A\n\nCorrupted content!", encoding="utf-8")

            r = fsck_store(docs_dir=str(docs_dir), verify_hashes=True)
            self.assertEqual(r["hash_verification"]["mismatches"], 1)
            hash_issues = [i for i in r["issues"] if i["kind"] == "content_hash_mismatch"]
            self.assertEqual(len(hash_issues), 1)
            self.assertIn("db_hash", hash_issues[0])
            self.assertIn("file_hash", hash_issues[0])
            self.assertNotEqual(hash_issues[0]["db_hash"], hash_issues[0]["file_hash"])


class TestFsckVerifyFts(unittest.TestCase):
    def test_clean_fts(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nSome content.")
            finally:
                conn.close()

            r = fsck_store(docs_dir=str(docs_dir), verify_fts=True)
            fts_issues = [i for i in r["issues"] if i["kind"].startswith("fts_")]
            self.assertEqual(len(fts_issues), 0)
            self.assertEqual(r["fts_verification"]["pages_fts_missing"], 0)
            self.assertEqual(r["fts_verification"]["pages_fts_orphans"], 0)

    def test_missing_fts_entry(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nSome content here.")
                # Delete the FTS entry to simulate drift.
                page_id = conn.execute("SELECT id FROM pages WHERE canonical_url = ?;",
                                       ("https://ex.com/a",)).fetchone()["id"]
                conn.execute("DELETE FROM pages_fts WHERE rowid = ?;", (page_id,))
                conn.commit()
            finally:
                conn.close()

            r = fsck_store(docs_dir=str(docs_dir), verify_fts=True)
            self.assertGreater(r["fts_verification"]["pages_fts_missing"], 0)
            fts_issues = [i for i in r["issues"] if i["kind"] == "fts_missing_entries"]
            self.assertEqual(len(fts_issues), 1)


class TestFsckVerifyEndpointJson(unittest.TestCase):
    def test_clean_endpoint_json(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            record = {"method": "GET", "path": "/api/v1/ticker"}
            try:
                _insert_endpoint(conn, docs_dir=docs_dir, endpoint_id="ep001",
                                 exchange="testex", section="spot", record=record)
            finally:
                conn.close()

            r = fsck_store(docs_dir=str(docs_dir), verify_endpoint_json=True)
            self.assertEqual(r["endpoint_json_verification"]["mismatches"], 0)
            self.assertEqual(r["endpoint_json_verification"]["checked"], 1)
            ej_issues = [i for i in r["issues"] if i["kind"].startswith("endpoint_json_")]
            self.assertEqual(len(ej_issues), 0)

    def test_mismatch_detected(self) -> None:
        from cex_api_docs.fsck import fsck_store

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            record = {"method": "GET", "path": "/api/v1/ticker"}
            try:
                _insert_endpoint(conn, docs_dir=docs_dir, endpoint_id="ep001",
                                 exchange="testex", section="spot", record=record)
            finally:
                conn.close()

            # Modify the on-disk JSON file.
            ep_file = docs_dir / "endpoints" / "testex" / "spot" / "ep001.json"
            modified = {"method": "POST", "path": "/api/v1/ticker"}
            ep_file.write_text(json.dumps(modified, sort_keys=True, ensure_ascii=False), encoding="utf-8")

            r = fsck_store(docs_dir=str(docs_dir), verify_endpoint_json=True)
            self.assertEqual(r["endpoint_json_verification"]["mismatches"], 1)
            ej_issues = [i for i in r["issues"] if i["kind"] == "endpoint_json_mismatch"]
            self.assertEqual(len(ej_issues), 1)


# --- audit orchestrator tests ---


class TestAudit(unittest.TestCase):
    def test_clean_store_passes(self) -> None:
        from cex_api_docs.audit import run_audit

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nEnough content to pass quality gate with more than fifty words. " * 3)
            finally:
                conn.close()

            r = run_audit(docs_dir=str(docs_dir), limit=100)
            self.assertEqual(r["overall_status"], "pass")
            self.assertGreater(r["summary"]["pass"], 0)
            # validate-registry, validate-base-urls, ccxt-xref, validate-retrieval,
            # sitemap-health, link-reachability, crawl-coverage, live-site-validation skipped.
            self.assertEqual(r["summary"]["skip"], 8)

    def test_hash_mismatch_fails_audit(self) -> None:
        from cex_api_docs.audit import run_audit

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = _setup_store(Path(tmp))
            conn = open_db(docs_dir / "db" / "docs.db")
            try:
                _insert_page(conn, docs_dir=docs_dir, url="https://ex.com/a", domain="ex.com",
                             title="Page A", markdown="# Page A\n\nEnough content to pass quality gate with more than fifty words. " * 3)
            finally:
                conn.close()

            # Corrupt the markdown file.
            md_files = list((docs_dir / "pages").rglob("*.md"))
            md_files[0].write_text("# CORRUPTED\n\nThis is corrupted.", encoding="utf-8")

            r = run_audit(docs_dir=str(docs_dir), limit=100)
            self.assertEqual(r["overall_status"], "fail")
            fsck_check = next(c for c in r["checks"] if c["name"] == "fsck")
            self.assertEqual(fsck_check["status"], "fail")
            self.assertGreater(fsck_check["issues_count"], 0)


if __name__ == "__main__":
    unittest.main()
