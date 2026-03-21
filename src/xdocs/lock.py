from __future__ import annotations

import errno
import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterator

from .errors import XDocsError
from .timeutil import now_iso_utc


@dataclass(frozen=True, slots=True)
class WriteLock:
    path: Path
    file: IO[str]


def _try_flock_exclusive_nonblocking(f: IO[str]) -> bool:
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise


def cleanup_stale_lock(lock_path: Path) -> bool:
    """Remove a stale lock file if the holding process is dead.

    Returns True if a stale lock was cleaned up.
    """
    if not lock_path.exists():
        return False
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
        if not content:
            lock_path.unlink(missing_ok=True)
            return True
        data = json.loads(content)
        pid = data.get("pid")
        if pid and not _is_pid_alive(int(pid)):
            lock_path.unlink(missing_ok=True)
            return True
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return False


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is alive (works on Linux/macOS)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def acquire_write_lock(lock_path: Path, timeout_s: float) -> Iterator[WriteLock]:
    """
    Advisory exclusive lock to enforce single-writer semantics across processes.

    The lock is held for the lifetime of the context manager.
    """
    if timeout_s < 0:
        raise ValueError("timeout_s must be >= 0")

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Auto-cleanup stale locks from dead processes (M38).
    cleanup_stale_lock(lock_path)
    f = open(lock_path, "a+", encoding="utf-8")
    acquired = False
    start = time.monotonic()

    try:
        while True:
            acquired = _try_flock_exclusive_nonblocking(f)
            if acquired:
                f.seek(0)
                f.truncate()
                f.write(
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "acquired_at": now_iso_utc(),
                        },
                        sort_keys=True,
                    )
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
                break

            if time.monotonic() - start >= timeout_s:
                raise XDocsError(
                    code="ELOCKED",
                    message="Store is locked for writes by another process.",
                    details={"lock_path": str(lock_path), "timeout_s": timeout_s},
                )
            time.sleep(0.1)

        yield WriteLock(path=lock_path, file=f)
    finally:
        try:
            if acquired:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    # Best-effort; close will also drop the lock.
                    pass
        finally:
            try:
                f.close()
            except OSError:
                pass
