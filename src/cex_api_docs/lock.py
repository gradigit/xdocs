from __future__ import annotations

import errno
import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator

from .errors import CexApiDocsError


@dataclass(frozen=True, slots=True)
class WriteLock:
    path: Path
    file: IO[str]


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _try_flock_exclusive_nonblocking(f: IO[str]) -> bool:
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise


@contextmanager
def acquire_write_lock(lock_path: Path, timeout_s: float) -> Iterator[WriteLock]:
    """
    Advisory exclusive lock to enforce single-writer semantics across processes.

    The lock is held for the lifetime of the context manager.
    """
    if timeout_s < 0:
        raise ValueError("timeout_s must be >= 0")

    lock_path.parent.mkdir(parents=True, exist_ok=True)
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
                            "acquired_at": _now_iso_utc(),
                        },
                        sort_keys=True,
                    )
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
                break

            if time.monotonic() - start >= timeout_s:
                raise CexApiDocsError(
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

