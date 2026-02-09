from __future__ import annotations

from datetime import datetime, timezone


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

