#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _dir_stats(path: Path, *, hash_tree: bool) -> dict[str, Any]:
    files = 0
    total = 0
    tree_h = hashlib.sha256() if hash_tree else None
    for p in sorted(path.rglob("*")):
        if not p.is_file():
            continue
        files += 1
        size = int(p.stat().st_size)
        total += size
        if tree_h is not None:
            rel = str(p.relative_to(path)).replace(os.sep, "/")
            tree_h.update(rel.encode("utf-8"))
            tree_h.update(b"\0")
            tree_h.update(_sha256_file(p).encode("utf-8"))
            tree_h.update(b"\0")
    out = {"files": files, "bytes": total}
    if tree_h is not None:
        out["tree_sha256"] = tree_h.hexdigest()
    return out


def _git_commit(repo_root: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode != 0:
            return None
        return p.stdout.strip() or None
    except Exception:
        return None


def _copy_path(src: Path, dst: Path, *, clean: bool) -> None:
    if not src.exists():
        raise SystemExit(f"Missing source path: {src}")
    if clean and dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


@dataclass(frozen=True)
class SyncConfig:
    runtime_root: Path
    docs_dir: Path
    include_data: bool
    include_lancedb: bool
    include_raw: bool
    clean: bool
    hash_tree: bool
    data_version: str
    strip_maintenance: bool = False


def _copy_runtime_core(repo_root: Path, runtime_root: Path, *, clean: bool) -> list[str]:
    copied: list[str] = []
    pairs: list[tuple[Path, Path]] = [
        (repo_root / "src", runtime_root / "src"),
        (repo_root / "pyproject.toml", runtime_root / "pyproject.toml"),
        (repo_root / ".claude" / "skills" / "cex-api-query" / "SKILL.md", runtime_root / ".claude" / "skills" / "cex-api-query" / "SKILL.md"),
        (
            repo_root / ".claude" / "skills" / "cex-api-query" / "EVALUATIONS.md",
            runtime_root / ".claude" / "skills" / "cex-api-query" / "EVALUATIONS.md",
        ),
        (repo_root / "docs" / "templates" / "runtime-repo-README.md", runtime_root / "README.md"),
        (repo_root / "docs" / "templates" / "runtime-AGENTS.md", runtime_root / "AGENTS.md"),
    ]
    for src, dst in pairs:
        _copy_path(src, dst, clean=clean)
        copied.append(str(dst))

    smoke_dst = runtime_root / "scripts" / "runtime_query_smoke.sh"
    _copy_path(repo_root / "docs" / "templates" / "runtime-query-smoke.sh", smoke_dst, clean=clean)
    smoke_dst.chmod(0o755)
    copied.append(str(smoke_dst))

    gitignore = runtime_root / ".gitignore"
    gitignore.write_text(".DS_Store\n.venv/\nlogs/\nreports/\n__pycache__/\n*.pyc\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n*.egg-info/\n", encoding="utf-8")
    copied.append(str(gitignore))
    return copied


def _copy_runtime_data(cfg: SyncConfig) -> list[str]:
    copied: list[str] = []
    dst_root = cfg.runtime_root / "cex-docs"

    # Compact LanceDB index before copy.  Use max_bytes_per_file to keep
    # individual .lance data files under the GitHub LFS 2 GB per-file limit.
    _LFS_MAX_BYTES = 1_900_000_000  # 1.9 GB — safe margin under 2 GB
    if cfg.include_lancedb:
        try:
            from cex_api_docs.semantic import compact_index
            logger.info("Compacting LanceDB index (max_bytes_per_file=%s)...", _LFS_MAX_BYTES)
            result = compact_index(docs_dir=str(cfg.docs_dir), max_bytes_per_file=_LFS_MAX_BYTES)
            for frag in result.get("fragments", []):
                logger.info("  fragment %s: %.1f MB", frag["file"], frag["bytes"] / 1e6)
        except ImportError:
            logger.warning("lancedb not installed; skipping compaction")
        except Exception as e:
            logger.warning("Compaction failed (non-fatal): %s", e)

    required: list[tuple[Path, Path]] = [
        (cfg.docs_dir / "db" / "docs.db", dst_root / "db" / "docs.db"),
        (cfg.docs_dir / "pages", dst_root / "pages"),
        (cfg.docs_dir / "meta", dst_root / "meta"),
    ]
    if cfg.include_lancedb:
        required.append((cfg.docs_dir / "lancedb-index", dst_root / "lancedb-index"))
    if cfg.include_raw:
        required.append((cfg.docs_dir / "raw", dst_root / "raw"))

    for src, dst in required:
        _copy_path(src, dst, clean=cfg.clean)
        copied.append(str(dst))

    # Strip maintenance-only tables from the runtime copy (not the source).
    if cfg.strip_maintenance:
        dst_db = dst_root / "db" / "docs.db"
        if dst_db.exists():
            conn = sqlite3.connect(str(dst_db))
            for table in ("inventories", "inventory_entries", "coverage_gaps"):
                try:
                    conn.execute(f"DELETE FROM {table};")
                except sqlite3.OperationalError:
                    pass  # Table may not exist in older schemas
            conn.commit()
            conn.close()
            # VACUUM must run outside a transaction
            conn = sqlite3.connect(str(dst_db), isolation_level=None)
            conn.execute("VACUUM;")
            conn.close()

    return copied


def _build_manifest(repo_root: Path, cfg: SyncConfig) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    runtime_rel_paths = [
        "pyproject.toml",
        "src",
        ".claude/skills/cex-api-query/SKILL.md",
        ".claude/skills/cex-api-query/EVALUATIONS.md",
        "README.md",
        "AGENTS.md",
        "scripts/runtime_query_smoke.sh",
    ]
    if cfg.include_data:
        runtime_rel_paths += [
            "cex-docs/db/docs.db",
            "cex-docs/pages",
            "cex-docs/meta",
        ]
        if cfg.include_lancedb:
            runtime_rel_paths.append("cex-docs/lancedb-index")
        if cfg.include_raw:
            runtime_rel_paths.append("cex-docs/raw")

    for rel in runtime_rel_paths:
        p = cfg.runtime_root / rel
        if not p.exists():
            continue
        if p.is_file():
            components.append(
                {
                    "path": rel,
                    "kind": "file",
                    "bytes": int(p.stat().st_size),
                    "sha256": _sha256_file(p),
                }
            )
        else:
            st = _dir_stats(p, hash_tree=cfg.hash_tree)
            components.append(
                {
                    "path": rel,
                    "kind": "dir",
                    **st,
                }
            )

    manifest: dict[str, Any] = {
        "schema_version": "runtime-manifest-v1",
        "generated_at": _iso_now(),
        "data_version": cfg.data_version,
        "source_repo": {
            "path": str(repo_root),
            "git_commit": _git_commit(repo_root),
        },
        "runtime_root": str(cfg.runtime_root),
        "embedding_model": "jinaai/jina-embeddings-v5-text-small",
        "embedding_dims": 1024,
        "components": components,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync a query-only runtime repo from maintainer repo + local snapshot.")
    parser.add_argument(
        "--runtime-root",
        required=True,
        help="Target runtime repo root path.",
    )
    parser.add_argument("--docs-dir", default="./cex-docs", help="Source docs snapshot directory.")
    parser.add_argument("--data-version", default=None, help="Data version label (default: UTC timestamp).")
    parser.add_argument("--no-data", action="store_true", help="Do not copy snapshot data directories.")
    parser.add_argument("--no-lancedb", action="store_true", help="Exclude semantic lancedb index from runtime snapshot.")
    parser.add_argument("--include-raw", action="store_true", help="Include raw HTML binaries (usually not needed for query-only runtime).")
    parser.add_argument("--clean", action="store_true", help="Delete destination managed paths before copying.")
    parser.add_argument("--hash-tree", action="store_true", help="Compute tree_sha256 for copied directories (slower).")
    parser.add_argument("--strip-maintenance", action="store_true", help="Delete inventories/coverage_gaps from runtime DB copy.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runtime_root = Path(args.runtime_root).resolve()
    docs_dir = Path(args.docs_dir).resolve()

    cfg = SyncConfig(
        runtime_root=runtime_root,
        docs_dir=docs_dir,
        include_data=not bool(args.no_data),
        include_lancedb=not bool(args.no_lancedb),
        include_raw=bool(args.include_raw),
        clean=bool(args.clean),
        hash_tree=bool(args.hash_tree),
        data_version=str(args.data_version or _iso_now().replace(":", "").replace("-", "")),
        strip_maintenance=bool(args.strip_maintenance),
    )

    runtime_root.mkdir(parents=True, exist_ok=True)
    copied_core = _copy_runtime_core(repo_root, runtime_root, clean=cfg.clean)
    copied_data: list[str] = []
    if cfg.include_data:
        copied_data = _copy_runtime_data(cfg)

    manifest = _build_manifest(repo_root, cfg)
    manifest_path = runtime_root / "runtime-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"runtime_root={runtime_root}")
    print(f"data_version={cfg.data_version}")
    print(f"core_paths_copied={len(copied_core)}")
    print(f"data_paths_copied={len(copied_data)}")
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
