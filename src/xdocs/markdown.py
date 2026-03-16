from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import html2text
from bs4 import BeautifulSoup

from .hashing import sha256_hex_text


HTML2TEXT_CONFIG_V2: dict[str, Any] = {
    # Minimal stable config: avoid wrapping, keep code fences, protect links.
    "body_width": 0,
    "protect_links": True,
    "wrap_links": False,
    "mark_code": True,
    "default_image_alt": "",
    "ignore_images": True,
}

MARKDOWN_PIPELINE_CONFIG_V2: dict[str, Any] = {
    "html2text": HTML2TEXT_CONFIG_V2,
    "normalize": {
        "collapse_blank_lines_max": 2,
        "convert_code_tags_to_fences": True,
        "table_fallback_from_html": True,
    },
    "quality_fallback": {
        "enabled": True,
        "min_word_count": 40,
        "require_structural_markers": ["pre", "code", "table"],
    },
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
    cfg_json = _canonical_json(MARKDOWN_PIPELINE_CONFIG_V2)
    raw_ver = getattr(html2text, "__version__", "unknown")
    if isinstance(raw_ver, tuple):
        ver = ".".join(str(p) for p in raw_ver)
    else:
        ver = str(raw_ver)
    return ExtractorInfo(
        name="html2text+normalize",
        version=f"{ver}+pipeline-v2",
        config=MARKDOWN_PIPELINE_CONFIG_V2,
        config_hash=sha256_hex_text(cfg_json),
    )


def html_to_markdown(html: str, *, base_url: str) -> str:
    h = html2text.HTML2Text()
    h.body_width = int(HTML2TEXT_CONFIG_V2["body_width"])
    h.protect_links = bool(HTML2TEXT_CONFIG_V2["protect_links"])
    h.wrap_links = bool(HTML2TEXT_CONFIG_V2["wrap_links"])
    h.mark_code = bool(HTML2TEXT_CONFIG_V2["mark_code"])
    h.default_image_alt = str(HTML2TEXT_CONFIG_V2["default_image_alt"])
    h.ignore_images = bool(HTML2TEXT_CONFIG_V2["ignore_images"])
    h.baseurl = base_url
    return h.handle(html)


def _convert_code_tags_to_fences(md: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        body = m.group(1).strip("\n")
        return f"\n```text\n{body}\n```\n"

    return re.sub(r"\[code\]\s*(.*?)\s*\[/code\]", _repl, md, flags=re.IGNORECASE | re.DOTALL)


def _normalize_cell_text(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.replace("|", "\\|")


def _table_to_markdown_lines(table) -> list[str]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        rows.append([_normalize_cell_text(c.get_text(" ", strip=True)) for c in cells])
    if not rows:
        return []

    max_cols = max(len(r) for r in rows)
    padded = [r + [""] * (max_cols - len(r)) for r in rows]
    has_th = bool(table.find("th"))

    if has_th:
        header = padded[0]
        body = padded[1:] if len(padded) > 1 else []
    else:
        header = [f"col_{i+1}" for i in range(max_cols)]
        body = padded

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _extract_table_fallback_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return ""
    blocks: list[str] = []
    for idx, tbl in enumerate(tables, start=1):
        lines = _table_to_markdown_lines(tbl)
        if not lines:
            continue
        blocks.append(f"### Table {idx}")
        blocks.extend(lines)
        blocks.append("")
    if not blocks:
        return ""
    return "## Extracted Tables\n\n" + "\n".join(blocks).strip()


def _extract_structural_fallback_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []

    pres = soup.find_all("pre")
    for i, pre in enumerate(pres, start=1):
        txt = pre.get_text("\n", strip=False).strip("\n")
        if not txt:
            continue
        out.append(f"### Code Block {i}")
        out.append("```text")
        out.append(txt)
        out.append("```")
        out.append("")

    table_md = _extract_table_fallback_markdown(html)
    if table_md:
        out.append(table_md)

    return "\n".join(out).strip()


def apply_quality_fallback(md: str, *, html: str) -> str:
    qcfg = MARKDOWN_PIPELINE_CONFIG_V2["quality_fallback"]
    if not bool(qcfg.get("enabled", True)):
        return md

    has_structural_html = bool(re.search(r"<(?:pre|code|table)\b", html, flags=re.IGNORECASE))
    if not has_structural_html:
        return md

    words = len(md.split())
    has_structural_md = bool(re.search(r"(?:```|~~~)|^\|.+\|", md, flags=re.MULTILINE))
    if words >= int(qcfg.get("min_word_count", 40)) and has_structural_md:
        return md

    fallback = _extract_structural_fallback_markdown(html)
    if not fallback:
        return md

    merged = md.strip()
    if merged:
        merged += "\n\n---\n\n## Structured Fallback Extract\n\n"
    merged += fallback
    return merged


def normalize_markdown(md: str, *, html: str | None = None) -> str:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    if bool(MARKDOWN_PIPELINE_CONFIG_V2["normalize"].get("convert_code_tags_to_fences", True)):
        md = _convert_code_tags_to_fences(md)

    if html and bool(MARKDOWN_PIPELINE_CONFIG_V2["normalize"].get("table_fallback_from_html", True)):
        has_table_like = bool(re.search(r"^\|.+\|", md, flags=re.MULTILINE))
        if not has_table_like:
            table_fallback = _extract_table_fallback_markdown(html)
            if table_fallback:
                md = md.rstrip() + "\n\n" + table_fallback + "\n"

    lines = [line.rstrip() for line in md.split("\n")]

    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= int(MARKDOWN_PIPELINE_CONFIG_V2["normalize"].get("collapse_blank_lines_max", 2)):
                out.append("")
            continue
        blank_run = 0
        out.append(line)

    return "\n".join(out)


def extract_block_metadata(md: str) -> dict[str, Any]:
    lines = md.splitlines()
    headings: list[dict[str, Any]] = []
    code_blocks: list[dict[str, int]] = []
    table_blocks: list[dict[str, int]] = []

    in_code = False
    code_start = 0
    code_fence_char = ""
    code_fence_len = 0
    table_start: int | None = None

    for i, line in enumerate(lines, start=1):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            fence = fence_match.group(1)
            fence_char = fence[0]
            fence_len = len(fence)
            if not in_code:
                if table_start is not None and (i - table_start) >= 2:
                    table_blocks.append({"start_line": table_start, "end_line": i - 1})
                    table_start = None
                in_code = True
                code_start = i
                code_fence_char = fence_char
                code_fence_len = fence_len
            else:
                if fence_char == code_fence_char and fence_len >= code_fence_len:
                    code_blocks.append({"start_line": code_start, "end_line": i})
                    in_code = False
                    code_start = 0
                    code_fence_char = ""
                    code_fence_len = 0
            continue

        if in_code:
            continue

        m = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
        if m:
            headings.append({"line": i, "level": len(m.group(1)), "text": m.group(2).strip()})

        is_table_line = "|" in line and len(line.strip()) > 2
        if is_table_line:
            if table_start is None:
                table_start = i
        else:
            if table_start is not None and (i - table_start) >= 2:
                table_blocks.append({"start_line": table_start, "end_line": i - 1})
            table_start = None

    if in_code and code_start > 0:
        code_blocks.append({"start_line": code_start, "end_line": len(lines)})
    if table_start is not None and (len(lines) + 1 - table_start) >= 2:
        table_blocks.append({"start_line": table_start, "end_line": len(lines)})

    return {
        "headings": headings,
        "code_blocks": code_blocks,
        "table_blocks": table_blocks,
        "counts": {
            "headings": len(headings),
            "code_blocks": len(code_blocks),
            "table_blocks": len(table_blocks),
        },
    }
