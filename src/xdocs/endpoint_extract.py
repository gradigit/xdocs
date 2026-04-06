"""Extract endpoint candidates from crawled documentation markdown.

Regex-based candidate scanning with high recall. False positive filtering is
the agent's responsibility (via the xdocs-extract skill). The deterministic
parts — citation offsets, record construction, path normalization, dedup, and
save — live here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import open_db
from .endpoints import (
    HARD_MAX_EXCERPT_CHARS,
    REQUIRED_HTTP_FIELD_STATUS_KEYS,
    compute_endpoint_id,
    save_endpoints_bulk,
)
from .lock import acquire_write_lock
from .markdown import extract_block_metadata
from .registry import load_registry
from .store import require_store_db


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EndpointCandidate:
    method: str          # GET, POST, etc.
    raw_path: str        # as found in markdown
    norm_path: str       # after _normalize_path
    char_start: int      # char offset in full markdown
    char_end: int        # end char offset
    pattern: str         # which pattern matched (P1-P5)
    heading_text: str    # nearest heading above the match
    page_url: str        # source page
    line_number: int     # 1-based, for display/review


# ---------------------------------------------------------------------------
# Regex patterns — all compiled with re.MULTILINE
# ---------------------------------------------------------------------------

_HTTP_METHODS = r"GET|POST|PUT|DELETE|PATCH"

# P4: heading IS method+path  (e.g.  # GET /options-history)
_P4 = re.compile(
    rf"^#{{1,4}}\s+({_HTTP_METHODS})\s+(/[^\s\]]+)",
    re.MULTILINE,
)

# P3: heading with HTTP method  (e.g.  ## Place order (HTTP PUT, _prefered_))
# Extracts method only — path comes from next code block via P2/P1.
_P3 = re.compile(
    rf"^#{{1,4}}\s+.+?\(HTTP\s+({_HTTP_METHODS})",
    re.MULTILINE,
)

# P1: inline method+path on own line  (e.g.  POST `/v2/spot/order`)
_P1 = re.compile(
    rf"^\s*({_HTTP_METHODS})\s+`?(/[^\s`?]+)`?",
    re.MULTILINE,
)

# P5: backtick-wrapped on own line  (e.g.  ` POST /v1/order `)
_P5 = re.compile(
    rf"^\s*`\s*({_HTTP_METHODS})\s+(/[^\s`?]+)\s*`",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rate limit extraction
# ---------------------------------------------------------------------------

_RATE_LIMIT_PATTERNS = [
    # "Rate Limit: 20 requests per 2 seconds"
    re.compile(r"Rate\s*Limit[:\s]+(\d+)\s*(?:requests?|times?|calls?)\s*(?:per|/)\s*(\d*)\s*(second|sec|s|minute|min|m|hour|h)", re.IGNORECASE),
    # "Limit: 10 requests per 1 second"
    re.compile(r"\bLimit[:\s]+(\d+)\s*(?:requests?)\s*(?:per|/)\s*(\d*)\s*(second|sec|s|minute|min|m)", re.IGNORECASE),
    # "10 times/1s" (Bitget style)
    re.compile(r"(\d+)\s*(?:times?|次)\s*/\s*(\d*)\s*(s|秒|sec|min|m)", re.IGNORECASE),
]


def extract_rate_limit_near(md: str, char_pos: int, window: int = 500) -> dict[str, Any] | None:
    """Extract rate limit text near a character position in markdown.

    Searches a window around ``char_pos`` for rate limit patterns.
    Returns ``{"text": "20 requests per 2 seconds", "requests": 20, "period_seconds": 2}``
    or None if no pattern found.
    """
    start = max(0, char_pos - window)
    end = min(len(md), char_pos + window)
    region = md[start:end]

    for pat in _RATE_LIMIT_PATTERNS:
        m = pat.search(region)
        if m:
            count = int(m.group(1))
            period_num = int(m.group(2)) if m.group(2) else 1
            period_unit = m.group(3).lower()
            if period_unit in ("s", "sec", "second", "秒"):
                period_seconds = period_num
            elif period_unit in ("m", "min", "minute"):
                period_seconds = period_num * 60
            elif period_unit in ("h", "hour"):
                period_seconds = period_num * 3600
            else:
                period_seconds = period_num
            return {
                "text": m.group(0).strip(),
                "requests": count,
                "period_seconds": period_seconds,
            }
    return None


# ---------------------------------------------------------------------------
# Parameter table extraction
# ---------------------------------------------------------------------------

# Heading patterns that precede request parameter tables.
_PARAM_HEADING_RE = re.compile(
    r"(?:^|\n)"
    r'["\s]*'  # tolerate leading quotes/whitespace (Coinone wraps in quotes)
    r"(?:#{1,4}\s+)?"  # optional markdown heading
    r"(?:"
    r"Request\s+(?:Param(?:eter)?s?|Body|Fields?|Header)"
    r"|Param(?:eter)?s?"
    r"|Query\s+Param(?:eter)?s?"
    r"|Body\s+Param(?:eter)?s?"
    r"|Headers?"
    r")\b",
    re.IGNORECASE,
)

# Column header keywords (case-insensitive).
_NAME_KEYWORDS = {"name", "field", "parameter", "param", "필드", "key"}
_TYPE_KEYWORDS = {"type", "유형", "타입"}
_REQUIRED_KEYWORDS = {"required", "mandatory", "optional", "required/optional", "필수"}
_DESC_KEYWORDS = {"description", "comment", "comments", "desc", "설명", "possible values"}

# Pipe table separator: `---|---|---` (with optional leading/trailing pipe).
_PIPE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$")

# Required field normalization.
_REQUIRED_TRUE = {"true", "yes", "y", "required", "mandatory", "o", "true (mandatory)"}
_REQUIRED_FALSE = {"false", "no", "n", "optional", "x", ""}


def _detect_column_map(cells: list[str]) -> dict[str, int]:
    """Map column semantics to positions from a header row."""
    result: dict[str, int] = {}
    for i, cell in enumerate(cells):
        low = cell.strip().lower()
        if low in _NAME_KEYWORDS and "name" not in result:
            result["name"] = i
        elif low in _TYPE_KEYWORDS and "type" not in result:
            result["type"] = i
        elif low in _REQUIRED_KEYWORDS and "required" not in result:
            result["required"] = i
        elif low in _DESC_KEYWORDS and "description" not in result:
            result["description"] = i
    return result


def _parse_required(val: str) -> bool | str:
    """Normalize a required field value to bool or pass through as string."""
    low = val.strip().lower()
    if low in _REQUIRED_TRUE:
        return True
    if low in _REQUIRED_FALSE:
        return False
    return val.strip()


def _split_pipe_row(line: str) -> list[str]:
    """Split a pipe-delimited table row, stripping outer pipes."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _unescape_coinone(md: str) -> str:
    r"""Pre-process Coinone-style content with literal escape sequences.

    Coinone pages store content with literal two-char sequences: ``\n`` (backslash+n),
    ``\t`` (backslash+t), and ``\"`` (backslash+quote). These are NOT Python escape
    sequences — they are the actual characters stored in the .md file.
    """
    # Detect: if literal \n count exceeds real newline count, this is Coinone format.
    literal_bs_n = md.count("\\n")
    real_newlines = md.count("\n")
    if literal_bs_n > real_newlines:
        md = md.replace("\\t", "\t")
        md = md.replace("\\n", "\n")
    if '\\"' in md:
        md = md.replace('\\"', '"')
    return md


def extract_params_near(
    md: str,
    char_pos: int,
    method: str = "POST",
    *,
    forward_window: int = 3000,
    backward_window: int = 500,
) -> list[dict[str, Any]]:
    """Extract parameter records from a table near ``char_pos`` in markdown.

    Searches forward (then backward) from ``char_pos`` for a "Request
    Parameters" heading, detects pipe or tab tables, and parses rows into
    structured parameter dicts.

    Returns an empty list when no parameter table is found.
    """
    # Pre-process for Coinone literal \n content.
    md_proc = _unescape_coinone(md)

    # Search forward first, then backward.
    search_start = char_pos
    search_end = min(len(md_proc), char_pos + forward_window)
    region = md_proc[search_start:search_end]

    heading_match = _PARAM_HEADING_RE.search(region)
    if not heading_match:
        # Try backward.
        back_start = max(0, char_pos - backward_window)
        region = md_proc[back_start:char_pos]
        heading_match = _PARAM_HEADING_RE.search(region)
        if not heading_match:
            return []
        table_search_start = back_start + heading_match.end()
    else:
        table_search_start = search_start + heading_match.end()

    # Grab the region after the heading to parse.
    table_region = md_proc[table_search_start:min(len(md_proc), table_search_start + 2000)]

    lines = table_region.split("\n")

    # Detect format: pipe or tab.
    params = _try_parse_pipe_table(lines, method)
    if not params:
        params = _try_parse_tab_table(lines, method)

    return params


def _try_parse_pipe_table(
    lines: list[str], method: str,
) -> list[dict[str, Any]]:
    """Try to parse a pipe-delimited parameter table."""
    # Find separator row (---|---|---).
    sep_idx = -1
    for i, line in enumerate(lines[:15]):  # look within first 15 lines
        if _PIPE_SEP_RE.match(line.strip()):
            sep_idx = i
            break
    if sep_idx < 1:
        return []

    # Header is the line before separator.
    header_cells = _split_pipe_row(lines[sep_idx - 1])
    col_map = _detect_column_map(header_cells)

    if "name" not in col_map:
        return []

    # Parse data rows after separator.
    params: list[dict[str, Any]] = []
    last_parent: str | None = None
    in_param = method.upper() in ("GET", "DELETE", "HEAD")

    for line in lines[sep_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            break
        # Stop on next heading.
        if stripped.startswith("#"):
            break
        # Must contain a pipe to be a table row.
        if "|" not in stripped:
            break

        cells = _split_pipe_row(stripped)
        if len(cells) < 2:
            continue

        name_raw = cells[col_map["name"]].strip() if col_map["name"] < len(cells) else ""
        if not name_raw or name_raw.startswith("---"):
            continue

        # Detect nesting: dash-prefix.
        parent = None
        if name_raw.startswith("- "):
            name_raw = name_raw[2:].strip()
            parent = last_parent
        elif name_raw.startswith("-"):
            name_raw = name_raw[1:].strip()
            parent = last_parent
        else:
            last_parent = name_raw

        # Strip backticks from name.
        name_raw = name_raw.strip("`")

        param: dict[str, Any] = {
            "name": name_raw,
            "in": "query" if in_param else "body",
        }

        if "type" in col_map and col_map["type"] < len(cells):
            param["type"] = cells[col_map["type"]].strip()

        if "required" in col_map and col_map["required"] < len(cells):
            param["required"] = _parse_required(cells[col_map["required"]])

        if "description" in col_map and col_map["description"] < len(cells):
            desc = cells[col_map["description"]].strip()
            if desc:
                param["description"] = desc

        if parent is not None:
            param["parent"] = parent

        params.append(param)

    return params


def _try_parse_tab_table(
    lines: list[str], method: str,
) -> list[dict[str, Any]]:
    """Try to parse a tab-delimited parameter table (Coinone, Aster)."""
    # Find a line with tabs that looks like a header.
    header_idx = -1
    for i, line in enumerate(lines[:10]):
        if "\t" in line:
            cells = [c.strip() for c in line.split("\t")]
            col_map = _detect_column_map(cells)
            if "name" in col_map:
                header_idx = i
                break

    if header_idx < 0:
        return []

    header_cells = [c.strip() for c in lines[header_idx].split("\t")]
    col_map = _detect_column_map(header_cells)
    in_param = method.upper() in ("GET", "DELETE", "HEAD")

    params: list[dict[str, Any]] = []
    last_parent: str | None = None

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("#"):
            break
        if "\t" not in stripped:
            # Allow continuation lines starting with - (nested params).
            if stripped.startswith("- ") and params:
                continue
            break

        cells = [c.strip() for c in stripped.split("\t")]
        if len(cells) < 2:
            continue

        name_raw = cells[col_map["name"]].strip() if col_map["name"] < len(cells) else ""
        if not name_raw:
            continue

        # Detect nesting.
        parent = None
        if name_raw.startswith("- "):
            name_raw = name_raw[2:].strip()
            parent = last_parent
        elif name_raw.startswith("-"):
            name_raw = name_raw[1:].strip()
            parent = last_parent
        else:
            last_parent = name_raw

        name_raw = name_raw.strip("`")

        param: dict[str, Any] = {
            "name": name_raw,
            "in": "query" if in_param else "body",
        }

        if "type" in col_map and col_map["type"] < len(cells):
            param["type"] = cells[col_map["type"]].strip()

        if "required" in col_map and col_map["required"] < len(cells):
            param["required"] = _parse_required(cells[col_map["required"]])

        if "description" in col_map and col_map["description"] < len(cells):
            desc = cells[col_map["description"]].strip()
            if desc:
                param["description"] = desc

        if parent is not None:
            param["parent"] = parent

        params.append(param)

    return params


_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")
_PARAM_ANGLE = re.compile(r"<([^>]+)>")
_PARAM_COLON = re.compile(r":([A-Za-z_]\w*)")


def _normalize_path(raw: str) -> str:
    """Normalize an API path for dedup comparison.

    Strips query params, zero-width chars, trailing markdown punctuation,
    and normalizes path parameter styles to ``{param}``.
    """
    path = _ZERO_WIDTH_RE.sub("", raw)

    # Strip query string.
    if "?" in path:
        path = path.split("?", 1)[0]

    # Normalize path parameters: <param> and :param → {param}.
    # Already-braced {param} is left as-is.
    path = _PARAM_ANGLE.sub(r"{\1}", path)
    path = _PARAM_COLON.sub(r"{\1}", path)

    # Strip trailing markdown punctuation.
    path = path.rstrip(")],.")

    # Strip trailing slash.
    return path.rstrip("/") or "/"


def _normalize_path_for_dedup(path: str) -> str:
    """Normalize for dedup comparison — collapses param names to ``{}``."""
    p = _normalize_path(path)
    # Also strip scheme+host if present.
    if p.startswith("http://") or p.startswith("https://"):
        from urllib.parse import urlsplit
        p = urlsplit(p).path
    # Strip Postman {{variable}} prefix.
    p = re.sub(r"^\{\{[^}]*\}\}", "", p)
    # Collapse param names: {param} → {}
    p = re.sub(r"\{[^}]+\}", "{}", p)
    return p.rstrip("/") or "/"


# ---------------------------------------------------------------------------
# Line offset utilities
# ---------------------------------------------------------------------------

def _build_line_offsets(md: str) -> list[int]:
    """Return char offset for the start of each 1-based line.

    ``offsets[0]`` is unused (placeholder). ``offsets[1]`` is the char offset
    of line 1, etc. Uses ``splitlines()`` for consistency with
    ``extract_block_metadata``.
    """
    offsets = [0]  # placeholder for 0-index
    pos = 0
    for line in md.splitlines(keepends=True):
        offsets.append(pos)
        pos += len(line)
    return offsets


def _line_to_char(offsets: list[int], line: int) -> int:
    """Convert a 1-based line number to a character offset."""
    if 1 <= line < len(offsets):
        return offsets[line]
    return offsets[-1] if offsets else 0


# ---------------------------------------------------------------------------
# Heading lookup
# ---------------------------------------------------------------------------

def _find_heading_for_offset(
    headings: list[dict[str, Any]],
    line_offsets: list[int],
    char_offset: int,
) -> str:
    """Find the nearest heading above ``char_offset``."""
    best = ""
    for h in headings:
        h_offset = _line_to_char(line_offsets, h["line"])
        if h_offset <= char_offset:
            best = h["text"]
        else:
            break
    return best


# ---------------------------------------------------------------------------
# Citation builder
# ---------------------------------------------------------------------------

_EXCERPT_WINDOW = 550


def _build_citation(
    *,
    page_url: str,
    crawled_at: str,
    content_hash: str,
    path_hash: str,
    md: str,
    char_start: int,
    field_name: str,
) -> dict[str, Any]:
    """Build a citation dict with a 550-char excerpt window."""
    excerpt_end = min(char_start + _EXCERPT_WINDOW, len(md))
    excerpt = md[char_start:excerpt_end]
    if len(excerpt) > HARD_MAX_EXCERPT_CHARS:
        excerpt = excerpt[:HARD_MAX_EXCERPT_CHARS]
        excerpt_end = char_start + HARD_MAX_EXCERPT_CHARS
    return {
        "url": page_url,
        "crawled_at": crawled_at,
        "content_hash": content_hash,
        "path_hash": path_hash,
        "excerpt": excerpt,
        "excerpt_start": char_start,
        "excerpt_end": excerpt_end,
        "field_name": field_name,
    }


# ---------------------------------------------------------------------------
# Page-level scanning
# ---------------------------------------------------------------------------

def scan_endpoints_from_page(
    *,
    md: str,
    page_url: str,
    crawled_at: str,
    content_hash: str,
    path_hash: str,
    exchange: str,
    section: str,
    base_url: str,
    api_version: str | None = None,
) -> list[EndpointCandidate]:
    """Regex scan of one page. Returns ALL candidates (high recall).

    False positive filtering is the agent's job, not this function's.
    """
    block_meta = extract_block_metadata(md)
    line_offsets = _build_line_offsets(md)
    lines = md.splitlines()

    # Build a set of (start_line, end_line) for code blocks so we can
    # attribute matches inside code blocks to P2.
    code_ranges: list[tuple[int, int]] = [
        (cb["start_line"], cb["end_line"]) for cb in block_meta["code_blocks"]
    ]

    seen: set[tuple[str, str]] = set()  # (method_upper, norm_path) dedup
    candidates: list[EndpointCandidate] = []

    def _add(method: str, raw_path: str, char_start: int, char_end: int,
             pattern: str, line_num: int) -> None:
        m_up = method.upper()
        norm = _normalize_path(raw_path)
        key = (m_up, _normalize_path_for_dedup(raw_path))
        if key in seen:
            return
        seen.add(key)
        heading = _find_heading_for_offset(block_meta["headings"], line_offsets, char_start)
        candidates.append(EndpointCandidate(
            method=m_up,
            raw_path=raw_path,
            norm_path=norm,
            char_start=char_start,
            char_end=char_end,
            pattern=pattern,
            heading_text=heading,
            page_url=page_url,
            line_number=line_num,
        ))

    def _char_to_line(offset: int) -> int:
        """Convert char offset to 1-based line number."""
        for i in range(len(line_offsets) - 1, 0, -1):
            if line_offsets[i] <= offset:
                return i
        return 1

    # --- P4: heading IS method+path ---
    for m in _P4.finditer(md):
        _add(m.group(1), m.group(2), m.start(), m.end(), "P4", _char_to_line(m.start()))

    # --- P3: heading with HTTP method (method only, path from next code block) ---
    for m in _P3.finditer(md):
        method = m.group(1)
        heading_line = _char_to_line(m.start())
        # Find the next code block after this heading.
        for cb_start, cb_end in code_ranges:
            if cb_start > heading_line:
                # Scan first non-blank line of code block for a path.
                for ln in range(cb_start + 1, min(cb_end, cb_start + 5)):
                    if 1 <= ln <= len(lines):
                        line_text = lines[ln - 1]
                        pm = _P1.match(line_text)
                        if pm:
                            cb_char = _line_to_char(line_offsets, ln)
                            _add(method, pm.group(2), cb_char + pm.start(2),
                                 cb_char + pm.end(2), "P3", ln)
                            break
                        # Also try just a bare path (method already from heading).
                        bare = re.match(r"\s*(/[^\s?]+)", line_text)
                        if bare:
                            cb_char = _line_to_char(line_offsets, ln)
                            _add(method, bare.group(1), cb_char + bare.start(1),
                                 cb_char + bare.end(1), "P3", ln)
                            break
                break  # Only check the first code block after the heading.

    # --- P2: method+path inside code blocks ---
    for cb_start, cb_end in code_ranges:
        for ln in range(cb_start + 1, min(cb_end, cb_start + 5)):
            if 1 <= ln <= len(lines):
                line_text = lines[ln - 1]
                pm = _P1.match(line_text)
                if pm:
                    cb_char = _line_to_char(line_offsets, ln)
                    _add(pm.group(1), pm.group(2), cb_char + pm.start(),
                         cb_char + pm.end(), "P2", ln)
                    break

    # --- P1: inline method+path outside code blocks ---
    code_line_set = set()
    for cb_start, cb_end in code_ranges:
        for ln in range(cb_start, cb_end + 1):
            code_line_set.add(ln)

    for m in _P1.finditer(md):
        line_num = _char_to_line(m.start())
        if line_num not in code_line_set:
            _add(m.group(1), m.group(2), m.start(), m.end(), "P1", line_num)

    # --- P5: backtick-wrapped ---
    for m in _P5.finditer(md):
        line_num = _char_to_line(m.start())
        if line_num not in code_line_set:
            _add(m.group(1), m.group(2), m.start(), m.end(), "P5", line_num)

    return candidates


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

def _clean_heading_for_description(heading: str, method: str, path: str) -> str | None:
    """Derive a description from a heading by stripping method/path/parens."""
    if not heading:
        return None
    desc = heading
    # Remove method references (case-sensitive — only strip uppercase HTTP methods).
    desc = re.sub(rf"\(?HTTP\s+({_HTTP_METHODS})[^)]*\)?", "", desc)
    desc = re.sub(rf"\b({_HTTP_METHODS})\b", "", desc)
    # Remove path references.
    if path:
        desc = desc.replace(path, "")
        desc = desc.replace(f"`{path}`", "")
    # Clean up.
    desc = re.sub(r"[_*`]", "", desc)  # Strip markdown formatting
    desc = re.sub(r"\s+", " ", desc).strip()
    desc = desc.strip("- ()")
    return desc if desc else None


def _build_endpoint_record(
    *,
    candidate: EndpointCandidate,
    md: str,
    crawled_at: str,
    content_hash: str,
    path_hash: str,
    exchange: str,
    section: str,
    base_url: str,
    api_version: str | None,
) -> dict[str, Any]:
    """Construct a complete endpoint record following openapi_import.py pattern."""
    method = candidate.method.upper()
    path = candidate.norm_path
    description = _clean_heading_for_description(candidate.heading_text, method, candidate.raw_path)

    # Build field_status: only method/path are "documented" (have citations).
    field_status: dict[str, str] = {}
    for k in REQUIRED_HTTP_FIELD_STATUS_KEYS:
        if k in ("http.method", "http.path"):
            field_status[k] = "documented"
        else:
            field_status[k] = "unknown"

    # Build citations for method and path (share same excerpt).
    citation_method = _build_citation(
        page_url=candidate.page_url,
        crawled_at=crawled_at,
        content_hash=content_hash,
        path_hash=path_hash,
        md=md,
        char_start=candidate.char_start,
        field_name="http.method",
    )
    citation_path = _build_citation(
        page_url=candidate.page_url,
        crawled_at=crawled_at,
        content_hash=content_hash,
        path_hash=path_hash,
        md=md,
        char_start=candidate.char_start,
        field_name="http.path",
    )

    # Try to extract rate limit near the endpoint definition.
    rate_limit_data = extract_rate_limit_near(md, candidate.char_start)
    if rate_limit_data:
        field_status["rate_limit"] = "documented"
        rl_citation = _build_citation(
            page_url=candidate.page_url,
            crawled_at=crawled_at,
            content_hash=content_hash,
            path_hash=path_hash,
            md=md,
            char_start=max(0, candidate.char_start - 500),
            field_name="rate_limit",
        )

    # Try to extract request parameters from nearby table.
    params = extract_params_near(md, candidate.char_start, method=method)
    request_schema: dict[str, Any] | None = None
    if params:
        request_schema = {"parameters": params}
        field_status["request_schema"] = "documented"

    record: dict[str, Any] = {
        "exchange": exchange,
        "section": section,
        "protocol": "http",
        "http": {
            "method": method,
            "path": path,
            "base_url": base_url,
            "api_version": api_version,
        },
        "description": description,
        "request_schema": request_schema,
        "response_schema": None,
        "required_permissions": None,
        "rate_limit": rate_limit_data,
        "error_codes": None,
        "sources": [citation_method, citation_path] + ([rl_citation] if rate_limit_data else []),
        "field_status": field_status,
        "extraction": {
            "model": "extract-markdown",
            "temperature": 0,
            "prompt_hash": "n/a",
            "input_content_hash": content_hash,
        },
    }
    record["endpoint_id"] = compute_endpoint_id(record)
    return record


# ---------------------------------------------------------------------------
# Save wrapper
# ---------------------------------------------------------------------------

def save_extracted_endpoints(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    candidates: list[dict[str, Any]],
    exchange: str,
    section: str,
    base_url: str,
    skip_existing: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Save agent-approved candidates via ``save_endpoints_bulk()``.

    Each candidate dict must have: method, path, char_start, char_end,
    page_url, md, crawled_at, content_hash, path_hash.
    May include ``base_url`` to override the function-level default.
    """
    db_path = require_store_db(docs_dir)
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "endpoint.schema.json"

    conn = open_db(db_path)
    try:
        # Load existing endpoints for dedup.
        existing: set[tuple[str, str]] = set()
        if skip_existing:
            rows = conn.execute(
                "SELECT method, path FROM endpoints WHERE exchange = ? AND section = ?;",
                (exchange, section),
            ).fetchall()
            existing = {
                (str(r["method"]).upper(), _normalize_path_for_dedup(str(r["path"] or "")))
                for r in rows
            }

        records: list[dict[str, Any]] = []
        skipped = 0
        for c in candidates:
            method = str(c["method"]).upper()
            raw_path = str(c["path"])
            dedup_key = (method, _normalize_path_for_dedup(raw_path))
            if dedup_key in existing:
                skipped += 1
                continue
            existing.add(dedup_key)

            cand_base_url = str(c.get("base_url", base_url))
            api_version = c.get("api_version")
            md = str(c["md"])

            ec = EndpointCandidate(
                method=method,
                raw_path=raw_path,
                norm_path=_normalize_path(raw_path),
                char_start=int(c["char_start"]),
                char_end=int(c["char_end"]),
                pattern=str(c.get("pattern", "agent")),
                heading_text=str(c.get("heading", "")),
                page_url=str(c["page_url"]),
                line_number=int(c.get("line", 0)),
            )
            record = _build_endpoint_record(
                candidate=ec,
                md=md,
                crawled_at=str(c["crawled_at"]),
                content_hash=str(c["content_hash"]),
                path_hash=str(c["path_hash"]),
                exchange=exchange,
                section=section,
                base_url=cand_base_url,
                api_version=api_version,
            )
            records.append(record)

        bulk = save_endpoints_bulk(
            docs_dir=docs_dir,
            lock_timeout_s=lock_timeout_s,
            schema_path=schema_path,
            records=records,
            continue_on_error=continue_on_error,
        )

        # Post-save: set docs_url for newly saved endpoints.
        saved_ids: list[tuple[str, str]] = []
        for rec in records:
            page_url = ""
            for s in rec.get("sources", []):
                if isinstance(s, dict) and s.get("url"):
                    page_url = str(s["url"])
                    break
            saved_ids.append((rec["endpoint_id"], page_url))

        lock_path = Path(docs_dir) / "db" / ".write.lock"
        with acquire_write_lock(lock_path, timeout_s=lock_timeout_s):
            conn2 = open_db(db_path)
            try:
                for eid, url in saved_ids:
                    if url:
                        conn2.execute("UPDATE endpoints SET docs_url = ? WHERE endpoint_id = ?;", (url, eid))
                conn2.commit()
            finally:
                conn2.close()

        return {
            "cmd": "save-extracted-endpoints",
            "ok": bulk["counts"]["errors"] == 0,
            "extracted": bulk["counts"]["ok"],
            "skipped_existing": skipped,
            "errors": bulk["errors"],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def scan_endpoints(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange: str,
    section: str,
    dry_run: bool = False,
    skip_existing: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Load pages for an exchange, run regex scan, dedup, optionally save."""
    db_path = require_store_db(docs_dir)
    registry_path = Path(__file__).resolve().parents[2] / "data" / "exchanges.yaml"
    registry = load_registry(registry_path)

    exchange_obj = registry.get_exchange(exchange)
    section_obj = registry.get_section(exchange, section)
    domains = exchange_obj.allowed_domains
    base_url = section_obj.base_urls[0] if section_obj.base_urls else ""
    api_version = None  # Phase 1: no api_version detection

    conn = open_db(db_path)
    try:
        placeholders = ",".join("?" * len(domains))
        rows = conn.execute(
            f"SELECT canonical_url, path_hash, content_hash, markdown_path, crawled_at, word_count "
            f"FROM pages WHERE domain IN ({placeholders}) "
            f"AND markdown_path IS NOT NULL AND word_count > 0",
            domains,
        ).fetchall()
    finally:
        conn.close()

    all_candidates: list[EndpointCandidate] = []
    pages_scanned = 0

    for row in rows:
        md_path = Path(row["markdown_path"])
        if not md_path.exists():
            continue
        md = md_path.read_text(encoding="utf-8")
        pages_scanned += 1

        page_candidates = scan_endpoints_from_page(
            md=md,
            page_url=str(row["canonical_url"]),
            crawled_at=str(row["crawled_at"]),
            content_hash=str(row["content_hash"]),
            path_hash=str(row["path_hash"]),
            exchange=exchange,
            section=section,
            base_url=base_url,
            api_version=api_version,
        )
        all_candidates.extend(page_candidates)

    # Cross-page dedup.
    seen: set[tuple[str, str]] = set()
    deduped: list[EndpointCandidate] = []
    for c in all_candidates:
        key = (c.method, _normalize_path_for_dedup(c.raw_path))
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    if dry_run:
        items = [
            {
                "method": c.method,
                "path": c.norm_path,
                "raw_path": c.raw_path,
                "heading": c.heading_text,
                "page_url": c.page_url,
                "line": c.line_number,
                "pattern": c.pattern,
            }
            for c in deduped
        ]
        return {
            "cmd": "scan-endpoints",
            "exchange": exchange,
            "section": section,
            "dry_run": True,
            "pages_scanned": pages_scanned,
            "candidates": len(all_candidates),
            "after_dedup": len(deduped),
            "items": items,
        }

    # Build candidate dicts for save_extracted_endpoints.
    cand_dicts: list[dict[str, Any]] = []
    for c in deduped:
        # Re-read markdown for the candidate's page.
        for row in rows:
            if str(row["canonical_url"]) == c.page_url:
                md_path = Path(row["markdown_path"])
                md = md_path.read_text(encoding="utf-8")
                cand_dicts.append({
                    "method": c.method,
                    "path": c.raw_path,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "page_url": c.page_url,
                    "md": md,
                    "crawled_at": str(row["crawled_at"]),
                    "content_hash": str(row["content_hash"]),
                    "path_hash": str(row["path_hash"]),
                    "pattern": c.pattern,
                    "heading": c.heading_text,
                    "line": c.line_number,
                })
                break

    result = save_extracted_endpoints(
        docs_dir=docs_dir,
        lock_timeout_s=lock_timeout_s,
        candidates=cand_dicts,
        exchange=exchange,
        section=section,
        base_url=base_url,
        skip_existing=skip_existing,
        continue_on_error=continue_on_error,
    )
    result["cmd"] = "scan-endpoints"
    result["pages_scanned"] = pages_scanned
    result["candidates_raw"] = len(all_candidates)
    result["after_dedup"] = len(deduped)
    return result


# ---------------------------------------------------------------------------
# Backfill: add request_schema to existing endpoints
# ---------------------------------------------------------------------------

def backfill_params(
    *,
    docs_dir: str,
    lock_timeout_s: float,
    exchange: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill request_schema for existing endpoints that have None.

    Finds endpoints with null request_schema, loads their source page,
    searches for parameter tables near the endpoint position, and updates
    the record.
    """
    import json as _json

    db_path = require_store_db(docs_dir)
    conn = open_db(db_path)

    try:
        # Find endpoints with null request_schema.
        if exchange:
            rows = conn.execute(
                "SELECT endpoint_id, json FROM endpoints "
                "WHERE json_extract(json, '$.request_schema') IS NULL "
                "AND json_extract(json, '$.exchange') = ?",
                (exchange,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT endpoint_id, json FROM endpoints "
                "WHERE json_extract(json, '$.request_schema') IS NULL",
            ).fetchall()
    finally:
        conn.close()

    updated = 0
    skipped = 0
    no_table = 0
    no_page = 0
    details: list[dict[str, str]] = []

    for row in rows:
        ep_id = row[0]
        rec = _json.loads(row[1])
        method = rec.get("http", {}).get("method", "GET")
        path = rec.get("http", {}).get("path", "")
        ep_exchange = rec.get("exchange", "")

        # Find the source page URL from citations.
        sources = rec.get("sources", [])
        page_url = None
        char_start = None
        for src in sources:
            url = src.get("url") or src.get("page_url", "")
            if url:
                page_url = url
                char_start = src.get("excerpt_start", 0)
                break

        if not page_url:
            # Try docs_url fallback.
            page_url = rec.get("docs_url")
            char_start = 0

        if not page_url:
            no_page += 1
            continue

        # Load page markdown.
        conn2 = open_db(db_path)
        try:
            page_row = conn2.execute(
                "SELECT markdown_path FROM pages WHERE url = ? OR canonical_url = ?",
                (page_url, page_url),
            ).fetchone()
        finally:
            conn2.close()

        if not page_row or not page_row[0]:
            no_page += 1
            continue

        md_path = Path(page_row[0])
        if not md_path.exists():
            no_page += 1
            continue

        md = md_path.read_text(encoding="utf-8")

        # If we don't have a char_start from citations, search for the endpoint.
        if char_start is None or char_start == 0:
            # Search for METHOD /path in the markdown.
            pattern = re.compile(
                rf"\b{re.escape(method)}\b\s+[`]?{re.escape(path)}",
                re.IGNORECASE,
            )
            m = pattern.search(md)
            if m:
                char_start = m.start()
            else:
                # Try just the path.
                idx = md.find(path)
                if idx >= 0:
                    char_start = idx
                else:
                    no_table += 1
                    continue

        # Extract params.
        params = extract_params_near(md, char_start, method=method)
        if not params:
            no_table += 1
            continue

        if dry_run:
            details.append({
                "exchange": ep_exchange,
                "method": method,
                "path": path,
                "params_found": len(params),
            })
            updated += 1
            continue

        # Update the endpoint record.
        rec["request_schema"] = {"parameters": params}
        fs = rec.get("field_status", {})
        fs["request_schema"] = "documented"
        rec["field_status"] = fs

        conn3 = open_db(db_path)
        try:
            lock_path = Path(docs_dir) / "db" / ".write.lock"
            with acquire_write_lock(lock_path, lock_timeout_s):
                conn3.execute(
                    "UPDATE endpoints SET json = ? WHERE endpoint_id = ?",
                    (_json.dumps(rec, ensure_ascii=False), ep_id),
                )
                conn3.commit()
            updated += 1
        finally:
            conn3.close()

    result: dict[str, Any] = {
        "cmd": "backfill-params",
        "total_candidates": len(rows),
        "updated": updated,
        "no_table": no_table,
        "no_page": no_page,
        "skipped": skipped,
    }
    if dry_run:
        result["dry_run"] = True
        result["details"] = details
    return result
