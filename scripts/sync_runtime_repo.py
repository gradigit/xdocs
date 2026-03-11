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
import sys
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


def _generate_runtime_pyproject(src_toml: Path, dst_toml: Path) -> None:
    """Generate a runtime pyproject.toml with semantic-query deps in base dependencies.

    The runtime repo is query-only — semantic search is core functionality, not optional.
    This merges the ``semantic-query`` extra into ``dependencies`` and drops extras that
    are irrelevant to the runtime (dev, playwright, semantic, ccxt).
    """
    lines = src_toml.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    # Collect semantic-query deps from the source file.
    sq_deps: list[str] = []
    in_sq = False
    for line in lines:
        stripped = line.strip()
        if stripped == "semantic-query = [":
            in_sq = True
            continue
        if in_sq:
            if stripped == "]":
                in_sq = False
            else:
                sq_deps.append(line)
            continue
    # Re-emit with semantic-query deps merged and extras trimmed.
    in_deps = False
    in_optional = False
    skip_extra = False
    for line in lines:
        stripped = line.strip()
        # Detect base dependencies block.
        if stripped == "dependencies = [":
            in_deps = True
            out.append(line)
            continue
        if in_deps:
            if stripped == "]":
                # Append semantic-query deps before closing bracket.
                for dep in sq_deps:
                    out.append(dep)
                out.append(line)
                in_deps = False
                continue
            out.append(line)
            continue
        # Drop all optional-dependencies (not needed in runtime).
        if stripped == "[project.optional-dependencies]":
            in_optional = True
            continue
        if in_optional:
            # End of optional-dependencies: next section header.
            if stripped.startswith("[") and stripped != "[project.optional-dependencies]":
                in_optional = False
                out.append(line)
            continue
        out.append(line)
    dst_toml.parent.mkdir(parents=True, exist_ok=True)
    dst_toml.write_text("".join(out), encoding="utf-8")


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


def _fmt_bytes(b: int) -> str:
    """Format byte count as a human-readable string."""
    if b >= 1_000_000_000:
        return f"{b / 1_000_000_000:.1f} GB"
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    if b >= 1_000:
        return f"{b / 1_000:.1f} KB"
    return f"{b} B"


def _fmt_delta_bytes(delta: int) -> str:
    """Format a byte delta with +/- prefix."""
    sign = "+" if delta >= 0 else "-"
    return f"{sign}{_fmt_bytes(abs(delta))}"


def _component_key(comp: dict[str, Any]) -> str:
    """Return the hash-like key for a component (sha256 or tree_sha256)."""
    return comp.get("sha256") or comp.get("tree_sha256") or ""


def _compare_manifests(
    old_manifest: dict[str, Any] | None,
    new_manifest: dict[str, Any],
) -> tuple[str, bool]:
    """Compare old and new manifests. Return (human-readable diff, all_unchanged)."""
    if old_manifest is None:
        lines = ["=== Sync Delta (first run -- no previous manifest) ==="]
        for comp in new_manifest.get("components", []):
            path = comp["path"]
            if comp["kind"] == "file":
                lines.append(f"  {path:30s} {_fmt_bytes(comp['bytes']):>12s} [NEW]")
            else:
                lines.append(f"  {path:30s} {comp['files']:,} files, {_fmt_bytes(comp['bytes'])} [NEW]")
        new_commit = new_manifest.get("source_repo", {}).get("git_commit")
        if new_commit:
            lines.append(f"  {'source commit':30s} (none) -> {new_commit[:7]}")
        return "\n".join(lines), False

    old_by_path: dict[str, dict[str, Any]] = {}
    for comp in old_manifest.get("components", []):
        old_by_path[comp["path"]] = comp

    new_by_path: dict[str, dict[str, Any]] = {}
    for comp in new_manifest.get("components", []):
        new_by_path[comp["path"]] = comp

    all_paths = sorted(set(old_by_path.keys()) | set(new_by_path.keys()))
    lines = ["=== Sync Delta ==="]
    all_unchanged = True

    for path in all_paths:
        old_comp = old_by_path.get(path)
        new_comp = new_by_path.get(path)

        if old_comp is None and new_comp is not None:
            all_unchanged = False
            if new_comp["kind"] == "file":
                lines.append(f"  {path:30s} {_fmt_bytes(new_comp['bytes']):>12s} [NEW]")
            else:
                lines.append(f"  {path:30s} {new_comp['files']:,} files [NEW]")
        elif old_comp is not None and new_comp is None:
            all_unchanged = False
            lines.append(f"  {path:30s} [REMOVED]")
        else:
            assert old_comp is not None and new_comp is not None
            old_key = _component_key(old_comp)
            new_key = _component_key(new_comp)
            if old_key and new_key and old_key == new_key:
                if new_comp["kind"] == "file":
                    lines.append(f"  {path:30s} {_fmt_bytes(new_comp['bytes']):>12s} unchanged")
                else:
                    lines.append(f"  {path:30s} {new_comp['files']:,} files unchanged")
            elif not old_key and not new_key:
                # No hash available — compare by file count and byte size
                if (old_comp.get("files") == new_comp.get("files")
                        and old_comp.get("bytes") == new_comp.get("bytes")):
                    if new_comp["kind"] == "file":
                        lines.append(f"  {path:30s} {_fmt_bytes(new_comp['bytes']):>12s} unchanged (no hash)")
                    else:
                        lines.append(f"  {path:30s} {new_comp['files']:,} files unchanged (no hash)")
                else:
                    all_unchanged = False
            else:
                all_unchanged = False
                if new_comp["kind"] == "file":
                    old_b = old_comp.get("bytes", 0)
                    new_b = new_comp.get("bytes", 0)
                    delta = new_b - old_b
                    lines.append(
                        f"  {path:30s} {_fmt_bytes(old_b)} -> {_fmt_bytes(new_b)} "
                        f"({_fmt_delta_bytes(delta)}) [CHANGED]"
                    )
                else:
                    old_f = old_comp.get("files", 0)
                    new_f = new_comp.get("files", 0)
                    delta_f = new_f - old_f
                    sign = "+" if delta_f >= 0 else ""
                    lines.append(
                        f"  {path:30s} {old_f:,} files -> {new_f:,} files "
                        f"({sign}{delta_f:,}) [CHANGED]"
                    )

    old_commit = old_manifest.get("source_repo", {}).get("git_commit")
    new_commit = new_manifest.get("source_repo", {}).get("git_commit")
    if old_commit != new_commit:
        all_unchanged = False
        old_short = old_commit[:7] if old_commit else "(none)"
        new_short = new_commit[:7] if new_commit else "(none)"
        lines.append(f"  {'source commit':30s} {old_short} -> {new_short}")
    else:
        short = new_commit[:7] if new_commit else "(none)"
        lines.append(f"  {'source commit':30s} {short} unchanged")

    return "\n".join(lines), all_unchanged


def _build_delta_summary(
    old_manifest: dict[str, Any] | None,
    new_manifest: dict[str, Any],
) -> str:
    """Build a one-line commit-message-friendly delta summary."""
    if old_manifest is None:
        parts = []
        for comp in new_manifest.get("components", []):
            if comp["kind"] == "file":
                parts.append(f"{comp['path']}={_fmt_bytes(comp['bytes'])}")
            else:
                parts.append(f"{comp['path']}={comp['files']} files")
        return "initial sync (" + ", ".join(parts[:4]) + ")"

    old_by_path = {c["path"]: c for c in old_manifest.get("components", [])}
    new_by_path = {c["path"]: c for c in new_manifest.get("components", [])}

    changes: list[str] = []
    for path in sorted(set(old_by_path.keys()) | set(new_by_path.keys())):
        old_comp = old_by_path.get(path)
        new_comp = new_by_path.get(path)
        if old_comp is None and new_comp is not None:
            changes.append(f"+{path}")
        elif old_comp is not None and new_comp is None:
            changes.append(f"-{path}")
        else:
            assert old_comp is not None and new_comp is not None
            old_key = _component_key(old_comp)
            new_key = _component_key(new_comp)
            if old_key and new_key and old_key == new_key:
                continue
            if not old_key and not new_key:
                # No hash — compare by file count and byte size
                if (old_comp.get("files") == new_comp.get("files")
                        and old_comp.get("bytes") == new_comp.get("bytes")):
                    continue
            if new_comp["kind"] == "file":
                delta = new_comp.get("bytes", 0) - old_comp.get("bytes", 0)
                changes.append(f"{path} ({_fmt_delta_bytes(delta)})")
            else:
                delta_f = new_comp.get("files", 0) - old_comp.get("files", 0)
                sign = "+" if delta_f >= 0 else ""
                changes.append(f"{path} ({sign}{delta_f} files)")

    if not changes:
        return "no data changes"

    new_commit = new_manifest.get("source_repo", {}).get("git_commit", "")
    short = new_commit[:7] if new_commit else "unknown"
    return f"{short}: " + ", ".join(changes[:5])


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

    # Generate runtime pyproject.toml with semantic-query deps merged into base.
    runtime_toml = runtime_root / "pyproject.toml"
    _generate_runtime_pyproject(repo_root / "pyproject.toml", runtime_toml)
    copied.append(str(runtime_toml))

    # Copy both smoke test variants (Python is primary, shell kept for backwards compat).
    smoke_py_dst = runtime_root / "scripts" / "runtime_query_smoke.py"
    _copy_path(repo_root / "docs" / "templates" / "runtime-query-smoke.py", smoke_py_dst, clean=clean)
    copied.append(str(smoke_py_dst))

    smoke_sh_src = repo_root / "docs" / "templates" / "runtime-query-smoke.sh"
    if smoke_sh_src.exists():
        smoke_sh_dst = runtime_root / "scripts" / "runtime_query_smoke.sh"
        _copy_path(smoke_sh_src, smoke_sh_dst, clean=clean)
        smoke_sh_dst.chmod(0o755)
        copied.append(str(smoke_sh_dst))

    gitignore = runtime_root / ".gitignore"
    gitignore.write_text(".DS_Store\n.venv/\nlogs/\nreports/\n__pycache__/\n*.pyc\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n*.egg-info/\n", encoding="utf-8")
    copied.append(str(gitignore))
    return copied


def _checkpoint_source_db(cfg: SyncConfig) -> None:
    """Checkpoint the source database WAL before copying to avoid losing uncommitted data."""
    src_db = cfg.docs_dir / "db" / "docs.db"
    if not src_db.exists():
        return
    conn = sqlite3.connect(str(src_db), isolation_level=None)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()


def _prepare_runtime_db(dst_db: Path) -> None:
    """VACUUM, checkpoint, and optimize the runtime DB copy."""
    if not dst_db.exists():
        return
    conn = sqlite3.connect(str(dst_db), isolation_level=None)
    try:
        conn.execute("VACUUM;")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.execute("PRAGMA optimize;")
    finally:
        conn.close()


def _copy_runtime_data(cfg: SyncConfig) -> list[str]:
    copied: list[str] = []
    dst_root = cfg.runtime_root / "cex-docs"

    # Only compact LanceDB if any fragment exceeds the LFS size limit.
    # Avoids creating new transaction/manifest churn on every sync.
    _LFS_MAX_BYTES = 1_900_000_000  # 1.9 GB -- safe margin under 2 GB
    if cfg.include_lancedb:
        lance_data_dir = cfg.docs_dir / "lancedb-index" / "pages.lance" / "data"
        needs_compact = False
        if lance_data_dir.is_dir():
            for f in lance_data_dir.iterdir():
                if f.suffix == ".lance" and f.stat().st_size > _LFS_MAX_BYTES:
                    needs_compact = True
                    break
        if needs_compact:
            try:
                from cex_api_docs.semantic import compact_index
                logger.info("Fragment exceeds LFS limit -- compacting (max_bytes_per_file=%s)...", _LFS_MAX_BYTES)
                result = compact_index(docs_dir=str(cfg.docs_dir), max_bytes_per_file=_LFS_MAX_BYTES)
                for frag in result.get("fragments", []):
                    logger.info("  fragment %s: %.1f MB", frag["file"], frag["bytes"] / 1e6)
            except ImportError:
                logger.warning("lancedb not installed; skipping compaction")
            except Exception as e:
                logger.warning("Compaction failed (non-fatal): %s", e)
        else:
            logger.info("LanceDB fragments all under LFS limit -- skipping compaction")

    # Checkpoint source DB WAL before copying
    _checkpoint_source_db(cfg)

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
    dst_db = dst_root / "db" / "docs.db"
    if cfg.strip_maintenance and dst_db.exists():
        conn = sqlite3.connect(str(dst_db))
        for table in ("inventories", "inventory_entries", "coverage_gaps"):
            try:
                conn.execute(f"DELETE FROM {table};")
            except sqlite3.OperationalError:
                pass  # Table may not exist in older schemas
        conn.commit()
        conn.close()

    # Always prepare the runtime DB (VACUUM, checkpoint, optimize)
    _prepare_runtime_db(dst_db)

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
        "scripts/runtime_query_smoke.py",
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


def _load_existing_manifest(runtime_root: Path) -> dict[str, Any] | None:
    """Load the existing runtime manifest if present."""
    manifest_path = runtime_root / "runtime-manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Could not read existing manifest: {e}", file=sys.stderr)
        return None


def _run_smoke_test(runtime_root: Path) -> int:
    """Run the runtime smoke test. Prefers Python version (no sqlite3 CLI needed)."""
    smoke_py = runtime_root / "scripts" / "runtime_query_smoke.py"
    smoke_sh = runtime_root / "scripts" / "runtime_query_smoke.sh"
    if smoke_py.exists():
        cmd = [sys.executable, str(smoke_py), str(runtime_root / "cex-docs")]
    elif smoke_sh.exists():
        cmd = [str(smoke_sh), str(runtime_root / "cex-docs")]
    else:
        print("ERROR: No smoke test script found in " + str(runtime_root / "scripts"), file=sys.stderr)
        return 1
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SMOKE TEST FAILED:\n{result.stdout}\n{result.stderr}", file=sys.stderr)
        return 1
    print(f"Smoke test passed:\n{result.stdout}")
    return 0


def _git_commit_runtime(runtime_root: Path, commit_msg: str) -> int:
    """Stage all changes and commit in the runtime repo. Returns 0 on success."""
    # Check git-lfs is available
    lfs_check = subprocess.run(
        ["git", "lfs", "version"],
        cwd=str(runtime_root),
        capture_output=True,
    )
    if lfs_check.returncode != 0:
        print("ERROR: git-lfs not installed (required for runtime repo)", file=sys.stderr)
        return 1

    # Stage all changes
    result = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git add failed: {result.stderr}", file=sys.stderr)
        return 1

    # Check if there is anything to commit
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(runtime_root),
        capture_output=True,
    )
    if status.returncode == 0:
        print("Nothing to commit (working tree clean after staging).")
        return 0

    # Commit
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git commit failed: {result.stderr}", file=sys.stderr)
        return 1
    print(f"Committed: {commit_msg}")
    return 0


def _git_push_runtime(runtime_root: Path) -> int:
    """Fetch, check for divergence, configure LFS, and push. Returns 0 on success."""
    # Fetch remote
    result = subprocess.run(
        ["git", "fetch"],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git fetch failed: {result.stderr}", file=sys.stderr)
        return 1

    # Check if local is behind remote
    behind = subprocess.run(
        ["git", "rev-list", "--count", "HEAD..origin/main"],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if behind.returncode == 0 and behind.stdout.strip() != "0":
        print(
            f"ERROR: Local is {behind.stdout.strip()} commits behind remote. Pull first.",
            file=sys.stderr,
        )
        return 1

    # Configure LFS timeouts for large uploads
    subprocess.run(
        ["git", "config", "lfs.activitytimeout", "600"],
        cwd=str(runtime_root),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "lfs.concurrenttransfers", "1"],
        cwd=str(runtime_root),
        capture_output=True,
    )

    # Push
    result = subprocess.run(
        ["git", "push"],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git push failed: {result.stderr}", file=sys.stderr)
        return 1
    print("Pushed to remote.")
    return 0


def _git_tag_runtime(
    runtime_root: Path, delta_summary: str, source_commit: str | None, *, push: bool
) -> int:
    """Create a CalVer annotated tag. Returns 0 on success."""
    today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    tag_base = f"data-{today}"

    # Check for existing tags today
    existing = subprocess.run(
        ["git", "tag", "-l", f"{tag_base}*"],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    existing_tags = [t for t in existing.stdout.strip().split("\n") if t]

    if not existing_tags:
        tag_name = tag_base
    else:
        max_n = 0
        for t in existing_tags:
            if t == tag_base:
                max_n = max(max_n, 0)
            elif t.startswith(tag_base + "."):
                try:
                    n = int(t.rsplit(".", 1)[-1])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
        tag_name = f"{tag_base}.{max_n + 1}"

    # Create annotated tag
    source_line = f"\nSource: {source_commit}" if source_commit else ""
    tag_msg = f"Data sync: {delta_summary}{source_line}"
    result = subprocess.run(
        ["git", "tag", "-a", tag_name, "-m", tag_msg],
        cwd=str(runtime_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git tag failed: {result.stderr}", file=sys.stderr)
        return 1
    print(f"Tagged: {tag_name}")

    # Push tag if requested
    if push:
        result = subprocess.run(
            ["git", "push", "origin", tag_name],
            cwd=str(runtime_root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR: git push tag failed: {result.stderr}", file=sys.stderr)
            return 1
        print(f"Pushed tag: {tag_name}")

    return 0


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
    parser.add_argument("--skip-unchanged", action="store_true", help="Skip manifest write and commit when nothing changed.")
    parser.add_argument("--smoke-test", action="store_true", help="Run smoke test script after data copy.")
    parser.add_argument("--commit", action="store_true", help="Auto-stage and commit changes in the runtime repo.")
    parser.add_argument("--push", action="store_true", help="Push to remote after commit (requires --commit).")
    parser.add_argument("--tag", action="store_true", help="Create a CalVer annotated tag after commit (requires --commit).")
    args = parser.parse_args()

    if args.push and not args.commit:
        print("ERROR: --push requires --commit", file=sys.stderr)
        return 1

    if args.tag and not args.commit:
        print("ERROR: --tag requires --commit", file=sys.stderr)
        return 1

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

    # Load existing manifest before any changes
    old_manifest = _load_existing_manifest(runtime_root)

    runtime_root.mkdir(parents=True, exist_ok=True)
    copied_core = _copy_runtime_core(repo_root, runtime_root, clean=cfg.clean)
    copied_data: list[str] = []
    if cfg.include_data:
        copied_data = _copy_runtime_data(cfg)

    # Build new manifest
    manifest = _build_manifest(repo_root, cfg)

    # Compare manifests and print delta
    delta_text, all_unchanged = _compare_manifests(old_manifest, manifest)
    delta_summary = _build_delta_summary(old_manifest, manifest)
    print(delta_text)

    if all_unchanged:
        print("\nWARNING: Nothing changed since last sync.", file=sys.stderr)
        if args.skip_unchanged:
            print("--skip-unchanged: skipping manifest write and commit.")
            return 0

    # Write the new manifest
    manifest_path = runtime_root / "runtime-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"runtime_root={runtime_root}")
    print(f"data_version={cfg.data_version}")
    print(f"core_paths_copied={len(copied_core)}")
    print(f"data_paths_copied={len(copied_data)}")
    print(f"manifest={manifest_path}")

    # Smoke test
    if args.smoke_test:
        rc = _run_smoke_test(runtime_root)
        if rc != 0:
            return rc

    # Commit
    if args.commit:
        if all_unchanged:
            print("Skipping commit: nothing changed.")
        else:
            commit_msg = f"sync: {delta_summary}"
            rc = _git_commit_runtime(runtime_root, commit_msg)
            if rc != 0:
                return rc

            # Tag
            if args.tag:
                source_commit = manifest.get("source_repo", {}).get("git_commit")
                rc = _git_tag_runtime(
                    runtime_root,
                    delta_summary,
                    source_commit,
                    push=args.push,
                )
                if rc != 0:
                    return rc

            # Push
            if args.push:
                rc = _git_push_runtime(runtime_root)
                if rc != 0:
                    return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
