"""Classify changelog entries by impact type and extract affected endpoints.

Deterministic regex-based classification — no LLM dependency. Consistent
with the cite-only architecture.

Taxonomy (adapted from oasdiff + Keep a Changelog):
  ERR:  endpoint_removed, breaking_change, parameter_removed
  WARN: endpoint_deprecated, rate_limit_change, parameter_change
  INFO: endpoint_added, field_added, informational
"""
from __future__ import annotations

import re
from typing import Any

# Impact patterns: regex → (impact_type, severity)
_IMPACT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # ERR severity — requires immediate attention
    ("endpoint_removed", re.compile(
        r"(?:endpoint|api|path|route).*?(?:removed|retired|deleted|sunset|will\s+be\s+removed|will\s+be\s+retired)",
        re.IGNORECASE,
    ), "err"),
    ("breaking_change", re.compile(
        r"(?:breaking\s+change|incompatible|no\s+longer\s+(?:support|accept)|must\s+(?:update|migrate))",
        re.IGNORECASE,
    ), "err"),
    ("parameter_removed", re.compile(
        r"(?:parameter|field|property|column).*?(?:removed|deleted|will\s+be\s+removed)",
        re.IGNORECASE,
    ), "err"),
    # WARN severity — review required
    ("endpoint_deprecated", re.compile(
        r"(?:endpoint|api|path|route).*?deprecated|deprecated.*?(?:endpoint|api|path)",
        re.IGNORECASE,
    ), "warn"),
    ("rate_limit_change", re.compile(
        r"rate\s+limit|weight.*?(?:changed|updated|increased|decreased|adjusted)",
        re.IGNORECASE,
    ), "warn"),
    ("parameter_change", re.compile(
        r"(?:parameter|field).*?(?:renamed|changed|updated|now\s+required|type\s+changed|mandatory)",
        re.IGNORECASE,
    ), "warn"),
    # INFO severity — informational
    ("endpoint_added", re.compile(
        r"(?:new|added)\s+(?:an?\s+)?(?:endpoint|api|path|route)|(?:new|added)\s+(?:an?\s+)?(?:GET|POST|PUT|DELETE|PATCH)\s+/",
        re.IGNORECASE,
    ), "info"),
    ("field_added", re.compile(
        r"(?:new|added)\s+(?:an?\s+)?(?:field|parameter|response\s+field|column|attribute)",
        re.IGNORECASE,
    ), "info"),
]

# Extract HTTP method + path from changelog text.
_PATH_WITH_METHOD_RE = re.compile(
    r"(GET|POST|PUT|DELETE|PATCH)\s+(/[a-zA-Z0-9/_{}.\-:]+)",
    re.IGNORECASE,
)
_PATH_BARE_RE = re.compile(
    r"(?<!\w)(/(?:api|sapi|fapi|dapi|v[1-5])/[a-zA-Z0-9/_{}.\-]+)",
)


def classify_entry(text: str) -> list[dict[str, Any]]:
    """Classify a changelog entry by impact type.

    Returns a list of classification dicts, each with:
      - impact_type: str (e.g., "endpoint_removed")
      - severity: str ("err", "warn", "info")
      - matched_text: str (the regex match)

    An entry can match multiple patterns (e.g., both endpoint_added and
    endpoint_deprecated). If no patterns match, returns a single
    "informational" classification.
    """
    results: list[dict[str, Any]] = []
    seen_types: set[str] = set()

    for impact_type, pattern, severity in _IMPACT_PATTERNS:
        m = pattern.search(text)
        if m and impact_type not in seen_types:
            results.append({
                "impact_type": impact_type,
                "severity": severity,
                "matched_text": m.group(0),
            })
            seen_types.add(impact_type)

    if not results:
        results.append({
            "impact_type": "informational",
            "severity": "info",
            "matched_text": "",
        })

    return results


def extract_endpoint_paths(text: str) -> list[tuple[str | None, str]]:
    """Extract API endpoint paths from changelog text.

    Returns list of (method_or_None, path) tuples.
    """
    paths: list[tuple[str | None, str]] = []
    seen: set[str] = set()

    # First: paths with explicit HTTP methods
    for m in _PATH_WITH_METHOD_RE.finditer(text):
        method = m.group(1).upper()
        path = m.group(2).rstrip(".,;:)")
        key = f"{method} {path}"
        if key not in seen:
            paths.append((method, path))
            seen.add(key)

    # Then: bare API paths (no method)
    for m in _PATH_BARE_RE.finditer(text):
        path = m.group(1).rstrip(".,;:)")
        if path not in seen and f"GET {path}" not in seen and f"POST {path}" not in seen:
            paths.append((None, path))
            seen.add(path)

    return paths


def max_severity(classifications: list[dict[str, Any]]) -> str:
    """Return the highest severity from a list of classifications."""
    order = {"err": 3, "warn": 2, "info": 1}
    return max((c["severity"] for c in classifications), key=lambda s: order.get(s, 0), default="info")
