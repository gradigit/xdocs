from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import html2text

from .hashing import sha256_hex_text


HTML2TEXT_CONFIG_V1: dict[str, Any] = {
    # Minimal stable config: avoid wrapping, keep code fences, protect links.
    "body_width": 0,
    "protect_links": True,
    "wrap_links": False,
    "mark_code": True,
    "default_image_alt": "",
    "ignore_images": True,
}


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class ExtractorInfo:
    name: str
    version: str
    config: dict[str, Any]
    config_hash: str


def extractor_info_v1() -> ExtractorInfo:
    cfg_json = _canonical_json(HTML2TEXT_CONFIG_V1)
    raw_ver = getattr(html2text, "__version__", "unknown")
    if isinstance(raw_ver, tuple):
        ver = ".".join(str(p) for p in raw_ver)
    else:
        ver = str(raw_ver)
    return ExtractorInfo(
        name="html2text",
        version=ver,
        config=HTML2TEXT_CONFIG_V1,
        config_hash=sha256_hex_text(cfg_json),
    )


def html_to_markdown(html: str, *, base_url: str) -> str:
    h = html2text.HTML2Text()
    h.body_width = int(HTML2TEXT_CONFIG_V1["body_width"])
    h.protect_links = bool(HTML2TEXT_CONFIG_V1["protect_links"])
    h.wrap_links = bool(HTML2TEXT_CONFIG_V1["wrap_links"])
    h.mark_code = bool(HTML2TEXT_CONFIG_V1["mark_code"])
    h.default_image_alt = str(HTML2TEXT_CONFIG_V1["default_image_alt"])
    h.ignore_images = bool(HTML2TEXT_CONFIG_V1["ignore_images"])
    h.baseurl = base_url
    return h.handle(html)


def normalize_markdown(md: str) -> str:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in md.split("\n")]

    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
            continue
        blank_run = 0
        out.append(line)

    return "\n".join(out)
