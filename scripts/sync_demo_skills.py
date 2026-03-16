#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _pairs(repo_root: Path) -> list[tuple[Path, Path]]:
    return [
        (
            repo_root / ".claude" / "skills" / "xdocs-query" / "SKILL.md",
            Path(".claude/skills/xdocs-query/SKILL.md"),
        ),
        (
            repo_root / ".claude" / "skills" / "xdocs-query" / "EVALUATIONS.md",
            Path(".claude/skills/xdocs-query/EVALUATIONS.md"),
        ),
        (
            repo_root / ".claude" / "skills" / "xdocs-maintain" / "SKILL.md",
            Path(".claude/skills/xdocs-maintain/SKILL.md"),
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync core skill files from this repo into a demo workspace.")
    parser.add_argument(
        "--demo-root",
        required=True,
        help="Demo workspace root path.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    demo_root = Path(args.demo_root).resolve()
    if not demo_root.exists():
        raise SystemExit(f"Demo root does not exist: {demo_root}")

    copied = 0
    for src, rel_dst in _pairs(repo_root):
        if not src.exists():
            raise SystemExit(f"Missing source skill file: {src}")
        dst = demo_root / rel_dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        print(f"{src} -> {dst}")

    print(f"Synced {copied} skill files into {demo_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
