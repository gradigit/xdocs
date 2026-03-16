from __future__ import annotations

import hashlib


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_text(text: str) -> str:
    return sha256_hex_bytes(text.encode("utf-8"))

