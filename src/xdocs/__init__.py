from __future__ import annotations

from pathlib import Path


def verify_import_source(repo_root: Path | str | None = None) -> Path:
    """Verify that the imported xdocs package comes from the expected repo.

    Compares the resolved location of this package against *repo_root*.
    If *repo_root* is ``None``, it is inferred as the git toplevel of the
    current working directory (falling back to cwd itself).

    Returns the resolved package source directory on success.

    Raises ``RuntimeError`` if the package was loaded from a different source
    tree (e.g. a shared venv pointing at another editable install).
    """
    pkg_dir = Path(__file__).resolve().parent  # .../src/xdocs
    pkg_src = pkg_dir.parent.parent            # .../repo-root (two levels up from package)

    if repo_root is None:
        import subprocess

        try:
            repo_root = Path(
                subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
            ).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            repo_root = Path.cwd().resolve()
    else:
        repo_root = Path(repo_root).resolve()

    if pkg_src != repo_root:
        raise RuntimeError(
            f"Wrong source tree imported: xdocs loaded from "
            f"{pkg_src}, but expected {repo_root}. "
            f"Activate the correct venv or reinstall with: "
            f"uv pip install -e \"{repo_root}\""
        )

    return pkg_dir


__all__ = ["verify_import_source"]

