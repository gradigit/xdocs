#!/usr/bin/env python3
"""
CEX API Query Skill — Coverage Test

Tests whether the cex-api-docs CLI can surface the same level of detail
that the Binance spot skill (binance-skills-hub) pre-bakes into its SKILL.md.

Covers:
  Q1  Endpoint parameters (required / optional / types / constraints)
  Q2  Enum values for key order fields
  Q3  Order-list endpoint variants (OCO, OTO, OTOCO, OPO, OPOCO)
  Q4  Authentication details (signing, headers, recvWindow)
  Q5  Newer endpoints coverage (amend, myFilters, amendments)

Usage:
    source .venv/bin/activate
    python3 test-scripts/test_skill_coverage.py [--docs-dir ./cex-docs] [--run-dir DIR]

Outputs:
    test-scripts/runs/<timestamp>/SKILL_COVERAGE.md   — human + agent readable report
    test-scripts/runs/<timestamp>/results.json         — machine-readable results
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Configuration ────────────────────────────────────────────────────────────

EXCHANGE = "binance"

# Ground-truth from the Binance spot skill SKILL.md (v1.0.1)

GROUND_TRUTH = {
    "q1_order_params": {
        "endpoint": {"method": "POST", "path": "/api/v3/order"},
        "required_params": ["symbol", "side", "type"],
        "optional_params": [
            "timeInForce", "quantity", "quoteOrderQty", "price",
            "newClientOrderId", "strategyId", "strategyType", "stopPrice",
            "trailingDelta", "icebergQty", "newOrderRespType",
            "selfTradePreventionMode", "pegPriceType", "pegOffsetValue",
            "pegOffsetType", "recvWindow",
        ],
    },
    "q2_enums": {
        "side": ["BUY", "SELL"],
        "type": [
            "MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_LIMIT",
            "TAKE_PROFIT", "TAKE_PROFIT_LIMIT", "LIMIT_MAKER",
        ],
        "timeInForce": ["GTC", "IOC", "FOK"],
        "newOrderRespType": ["ACK", "RESULT", "FULL"],
        "selfTradePreventionMode": [
            "NONE", "EXPIRE_TAKER", "EXPIRE_MAKER", "EXPIRE_BOTH",
        ],
    },
    "q3_order_lists": {
        "OCO":   {"method": "POST", "path": "/api/v3/orderList/oco",
                  "required": ["symbol", "side", "quantity", "aboveType", "belowType"]},
        "OTO":   {"method": "POST", "path": "/api/v3/orderList/oto",
                  "required": ["symbol", "workingType", "workingSide", "workingPrice",
                               "workingQuantity", "pendingType", "pendingSide", "pendingQuantity"]},
        "OTOCO": {"method": "POST", "path": "/api/v3/orderList/otoco",
                  "required": ["symbol", "workingType", "workingSide", "workingPrice",
                               "workingQuantity", "pendingSide", "pendingAboveType"]},
        "OPO":   {"method": "POST", "path": "/api/v3/orderList/opo",
                  "required": ["symbol", "workingType", "workingSide", "workingPrice",
                               "workingQuantity", "pendingType", "pendingSide"]},
        "OPOCO": {"method": "POST", "path": "/api/v3/orderList/opoco",
                  "required": ["symbol", "workingType", "workingSide", "workingPrice",
                               "workingQuantity", "pendingSide", "pendingAboveType"]},
    },
    "q4_auth": {
        "header": "X-MBX-APIKEY",
        "signing_algorithms": ["HMAC-SHA256", "RSA", "Ed25519"],
        "recv_window_max": 60000,
    },
    "q5_newer_endpoints": [
        {"method": "PUT",  "path": "/api/v3/order/amend/keepPriority"},
        {"method": "GET",  "path": "/api/v3/myFilters"},
        {"method": "GET",  "path": "/api/v3/order/amendments"},
    ],
}

# Map $ref shorthand names to expected param names
REF_NAME_MAP = {
    "symbol": "symbol",
    "side": "side",
    "orderType": "type",
    "timeInForce": "timeInForce",
    "optionalQuantity": "quantity",
    "quoteOrderQty": "quoteOrderQty",
    "optionalPrice": "price",
    "newClientOrderId": "newClientOrderId",
    "strategyId": "strategyId",
    "strategyType": "strategyType",
    "stopPrice": "stopPrice",
    "optionalTrailingDelta": "trailingDelta",
    "icebergQty": "icebergQty",
    "newOrderRespType": "newOrderRespType",
    "selfTradePreventionMode": "selfTradePreventionMode",
    "recvWindow": "recvWindow",
    "timestamp": "timestamp",
    "signature": "signature",
    "pegPriceType": "pegPriceType",
    "pegOffsetValue": "pegOffsetValue",
    "pegOffsetType": "pegOffsetType",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_cli(args: list[str], docs_dir: str, timeout: int = 30) -> dict[str, Any]:
    """Run a cex-api-docs CLI command. Returns {ok, stdout, stderr, returncode}."""
    cmd = ["cex-api-docs"] + args + ["--docs-dir", docs_dir]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "TIMEOUT", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "cex-api-docs not found — is venv active?", "returncode": -1}


def parse_cli_json(text: str) -> Any:
    """Parse CLI JSON output, handling the {"ok":true,"result":...} wrapper."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    # Unwrap the standard CLI envelope
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


def extract_param_name(param: dict) -> str | None:
    """Extract parameter name from an endpoint param entry (inline or $ref)."""
    if "name" in param:
        return param["name"]
    ref = param.get("$ref", "")
    if ref:
        # "#/components/parameters/symbol" → "symbol"
        ref_key = ref.rsplit("/", 1)[-1]
        return REF_NAME_MAP.get(ref_key, ref_key)
    return None


def find_endpoint(result: dict, method: str, path: str) -> dict | None:
    """Find a matching endpoint from a lookup-endpoint result."""
    matches = result.get("matches", [])
    if not matches:
        return None

    # Prefer the one without {{url}} prefix
    for m in matches:
        ep_path = (m.get("http") or {}).get("path", m.get("path", ""))
        ep_method = (m.get("http") or {}).get("method", m.get("method", ""))
        if ep_path == path and ep_method == method:
            return m

    # Accept {{url}} prefixed version
    for m in matches:
        ep_path = (m.get("http") or {}).get("path", m.get("path", ""))
        ep_method = (m.get("http") or {}).get("method", m.get("method", ""))
        if ep_path.endswith(path) and ep_method == method:
            return m

    # Fall back to first match
    return matches[0] if matches else None


def get_endpoint_detail(endpoint_id: str, docs_dir: str) -> tuple[dict | None, str]:
    """Fetch full endpoint record by ID. Returns (data, cli_command)."""
    cmd = ["get-endpoint", endpoint_id]
    cli_str = f"cex-api-docs {' '.join(cmd)}"
    r = run_cli(cmd, docs_dir)
    if r["ok"]:
        return parse_cli_json(r["stdout"]), cli_str
    return None, cli_str


@dataclass
class TestResult:
    question: str
    grade: str  # FULL / PARTIAL / EMPTY / ERROR
    detail: str
    commands_run: list[str] = field(default_factory=list)
    found: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


# ── Test Functions ───────────────────────────────────────────────────────────

def test_q1_parameters(docs_dir: str) -> TestResult:
    """Q1: Can the CLI surface all required/optional params for POST /api/v3/order?"""
    tr = TestResult(question="Q1: POST /api/v3/order parameters", grade="EMPTY", detail="")
    gt = GROUND_TRUTH["q1_order_params"]

    # Step 1: lookup-endpoint
    cmd1_args = ["lookup-endpoint", gt["endpoint"]["path"],
                 "--method", gt["endpoint"]["method"], "--exchange", EXCHANGE]
    tr.commands_run.append(f"cex-api-docs {' '.join(cmd1_args)}")
    r1 = run_cli(cmd1_args, docs_dir)
    if not r1["ok"]:
        tr.detail = f"lookup-endpoint failed: {r1['stderr'][:100]}"
        tr.grade = "ERROR"
        return tr

    result1 = parse_cli_json(r1["stdout"])
    if not result1:
        tr.detail = "lookup-endpoint returned unparseable output"
        tr.grade = "ERROR"
        return tr

    ep = find_endpoint(result1, gt["endpoint"]["method"], gt["endpoint"]["path"])
    if not ep:
        tr.detail = "No matching endpoint in lookup results"
        tr.grade = "ERROR"
        return tr

    endpoint_id = ep.get("endpoint_id")
    if not endpoint_id:
        tr.detail = "No endpoint_id in match"
        tr.grade = "ERROR"
        return tr

    # Step 2: get-endpoint for full record
    ep_data, cmd2_str = get_endpoint_detail(endpoint_id, docs_dir)
    tr.commands_run.append(cmd2_str)
    if not ep_data:
        tr.detail = "get-endpoint failed or returned empty"
        tr.grade = "ERROR"
        return tr

    # Extract parameters (handle both inline and $ref)
    request_schema = ep_data.get("request_schema") or {}
    raw_params = request_schema.get("parameters") or []
    params_found: list[str] = []
    ref_only = 0
    inline = 0

    for p in raw_params:
        name = extract_param_name(p)
        if name:
            params_found.append(name)
            if "$ref" in p:
                ref_only += 1
            else:
                inline += 1

    # Grade against expected params
    all_expected = set(gt["required_params"] + gt["optional_params"])
    found_set = set(params_found)
    matched = all_expected & found_set
    missing_params = all_expected - found_set

    tr.found = {
        "endpoint_id": endpoint_id,
        "params_total": len(params_found),
        "params_ref_only": ref_only,
        "params_inline": inline,
        "params": sorted(params_found),
        "matched": len(matched),
        "expected": len(all_expected),
    }
    tr.missing = sorted(missing_params)

    if len(missing_params) == 0:
        tr.grade = "FULL"
        tr.detail = (
            f"All {len(all_expected)} expected params found. "
            f"{ref_only} via $ref, {inline} inline."
        )
    elif len(matched) >= len(all_expected) * 0.6:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"{len(matched)}/{len(all_expected)} params found "
            f"({ref_only} $ref, {inline} inline). "
            f"Missing: {', '.join(sorted(missing_params))}"
        )
    elif len(matched) > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"Only {len(matched)}/{len(all_expected)} params found."
    else:
        tr.grade = "EMPTY"
        tr.detail = f"No expected params found. Raw params: {len(raw_params)}."

    # Note about $ref resolution
    if ref_only > 0 and tr.grade in ("FULL", "PARTIAL"):
        tr.detail += (
            f" Note: {ref_only} params are unresolved $ref — "
            f"names extractable but types/enums/constraints require page read."
        )

    return tr


def test_q2_enums(docs_dir: str) -> TestResult:
    """Q2: Can the CLI surface enum values for side, type, timeInForce, etc.?"""
    tr = TestResult(question="Q2: Enum values for order fields", grade="EMPTY", detail="")
    gt = GROUND_TRUTH["q2_enums"]

    # Strategy 1: Get endpoint record — check if inline enums exist
    cmd1_args = ["lookup-endpoint", "/api/v3/order",
                 "--method", "POST", "--exchange", EXCHANGE]
    tr.commands_run.append(f"cex-api-docs {' '.join(cmd1_args)}")
    r1 = run_cli(cmd1_args, docs_dir)

    enum_from_schema: dict[str, list[str]] = {}

    if r1["ok"]:
        result1 = parse_cli_json(r1["stdout"])
        if result1:
            ep = find_endpoint(result1, "POST", "/api/v3/order")
            if ep:
                eid = ep.get("endpoint_id")
                if eid:
                    ep_data, cmd2 = get_endpoint_detail(eid, docs_dir)
                    tr.commands_run.append(cmd2)
                    if ep_data:
                        for p in (ep_data.get("request_schema") or {}).get("parameters") or []:
                            name = extract_param_name(p)
                            schema = p.get("schema", {})
                            enum_vals = schema.get("enum", [])
                            if name and enum_vals and name in gt:
                                enum_from_schema[name] = enum_vals

    # Strategy 2: semantic search for enums page
    cmd3_args = ["semantic-search",
                 "spot order type side timeInForce enum values definitions",
                 "--exchange", EXCHANGE, "--mode", "hybrid", "--limit", "5"]
    tr.commands_run.append(f"cex-api-docs {' '.join(cmd3_args)}")
    r3 = run_cli(cmd3_args, docs_dir, timeout=60)

    pages_found = 0
    page_has_enum_content = False
    if r3["ok"] and r3["stdout"]:
        result3 = parse_cli_json(r3["stdout"])
        if result3:
            results_list = result3.get("results", [])
            pages_found = len(results_list)
            # Check if any page title/content suggests enum definitions
            for pg in results_list:
                title = (pg.get("title") or "").lower()
                heading = (pg.get("heading") or "").lower()
                if any(kw in title or kw in heading for kw in ["enum", "definition", "common"]):
                    page_has_enum_content = True

    # Score
    fields_graded: dict[str, str] = {}
    for field_name, expected_vals in gt.items():
        expected_set = set(expected_vals)
        found_vals = set(enum_from_schema.get(field_name, []))
        if found_vals >= expected_set:
            fields_graded[field_name] = "FULL"
        elif found_vals & expected_set:
            fields_graded[field_name] = "PARTIAL"
        else:
            fields_graded[field_name] = "EMPTY"

    full_count = sum(1 for v in fields_graded.values() if v == "FULL")
    partial_count = sum(1 for v in fields_graded.values() if v == "PARTIAL")
    empty_count = sum(1 for v in fields_graded.values() if v == "EMPTY")

    tr.found = {
        "enums_from_schema": {k: v for k, v in enum_from_schema.items()},
        "fields_graded": fields_graded,
        "semantic_pages_found": pages_found,
        "page_has_enum_content": page_has_enum_content,
    }
    tr.missing = [f for f, g in fields_graded.items() if g != "FULL"]

    if full_count == len(gt):
        tr.grade = "FULL"
        tr.detail = f"All {len(gt)} enum fields found with correct values in endpoint schema."
    elif full_count + partial_count > 0:
        tr.grade = "PARTIAL"
        parts = []
        if full_count:
            parts.append(f"{full_count} FULL")
        if partial_count:
            parts.append(f"{partial_count} PARTIAL")
        if empty_count:
            parts.append(f"{empty_count} EMPTY")
        tr.detail = f"From schema: {', '.join(parts)} of {len(gt)} fields."
        if page_has_enum_content:
            tr.detail += " Enum definition pages found — agent could read page markdown."
    elif page_has_enum_content:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"No enums in endpoint schema ($ref unresolved), "
            f"but enum definition pages found via semantic search. "
            f"Agent must read page markdown to extract values."
        )
    elif pages_found > 0:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"No enums in schema. {pages_found} pages found but may not contain "
            f"enum definitions. Agent needs page read."
        )
    else:
        tr.grade = "EMPTY"
        tr.detail = "No enums in schema, no relevant pages found."

    return tr


def test_q3_order_lists(docs_dir: str) -> TestResult:
    """Q3: Can the CLI find all order list types (OCO/OTO/OTOCO/OPO/OPOCO)?"""
    tr = TestResult(question="Q3: Order list types", grade="EMPTY", detail="")
    gt = GROUND_TRUTH["q3_order_lists"]

    results: dict[str, dict] = {}

    for name, spec in gt.items():
        cmd_args = ["lookup-endpoint", spec["path"],
                    "--method", spec["method"], "--exchange", EXCHANGE]
        tr.commands_run.append(f"cex-api-docs {' '.join(cmd_args)}")
        r = run_cli(cmd_args, docs_dir)

        entry: dict[str, Any] = {
            "found": False, "has_schema": False,
            "param_count": 0, "params": [], "source": None,
        }

        if r["ok"] and r["stdout"]:
            result = parse_cli_json(r["stdout"])
            if result:
                ep = find_endpoint(result, spec["method"], spec["path"])
                if ep:
                    entry["found"] = True
                    eid = ep.get("endpoint_id")
                    if eid:
                        ep_data, cmd2 = get_endpoint_detail(eid, docs_dir)
                        tr.commands_run.append(cmd2)
                        if ep_data:
                            raw_params = (ep_data.get("request_schema") or {}).get("parameters") or []
                            params = [extract_param_name(p) for p in raw_params]
                            params = [p for p in params if p]
                            entry["has_schema"] = len(params) > 0
                            entry["param_count"] = len(params)
                            entry["params"] = params
                            # Check required params coverage
                            found_params = set(params)
                            expected_required = set(spec["required"])
                            entry["required_found"] = sorted(expected_required & found_params)
                            entry["required_missing"] = sorted(expected_required - found_params)
                            # Detect source
                            sources = ep_data.get("sources") or []
                            source_urls = [s.get("url", "") for s in sources]
                            if any("postman" in u.lower() for u in source_urls):
                                entry["source"] = "postman"
                            else:
                                entry["source"] = "openapi" if entry["has_schema"] else "web"

        results[name] = entry

    tr.found = results

    found_count = sum(1 for v in results.values() if v["found"])
    schema_count = sum(1 for v in results.values() if v["has_schema"])
    total = len(gt)

    tr.missing = [
        f"{name}" + (" (no schema)" if results[name]["found"] else " (not found)")
        for name in gt
        if not results[name]["found"] or not results[name]["has_schema"]
    ]

    if found_count == total and schema_count == total:
        tr.grade = "FULL"
        tr.detail = f"All {total} order list types found with schemas."
    elif found_count == total:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"All {total} found, but only {schema_count} have request schemas. "
            f"Postman-only: {', '.join(n for n, v in results.items() if not v['has_schema'])}."
        )
    elif found_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"{found_count}/{total} found, {schema_count} with schemas. "
            f"Not found: {', '.join(n for n, v in results.items() if not v['found'])}."
        )
    else:
        tr.grade = "EMPTY"
        tr.detail = "No order list endpoints found."

    return tr


def test_q4_auth(docs_dir: str) -> TestResult:
    """Q4: Can the CLI surface Binance spot authentication details?"""
    tr = TestResult(question="Q4: Authentication details", grade="EMPTY", detail="")
    gt = GROUND_TRUTH["q4_auth"]

    checklist: dict[str, bool] = {
        "header_X-MBX-APIKEY": False,
        "algo_HMAC-SHA256": False,
        "algo_RSA": False,
        "algo_Ed25519": False,
        "recvWindow": False,
    }

    all_text_parts: list[str] = []

    # Strategy 1: semantic search
    cmd1_args = ["semantic-search",
                 "Binance spot API authentication signature HMAC SHA256 RSA Ed25519 X-MBX-APIKEY",
                 "--exchange", EXCHANGE, "--mode", "hybrid", "--limit", "8"]
    tr.commands_run.append(f"cex-api-docs {' '.join(cmd1_args)}")
    r1 = run_cli(cmd1_args, docs_dir, timeout=60)

    pages_found = 0
    if r1["ok"] and r1["stdout"]:
        result1 = parse_cli_json(r1["stdout"])
        if result1:
            results_list = result1.get("results", [])
            pages_found = len(results_list)
            for pg in results_list:
                for key in ("title", "heading", "snippet", "content"):
                    val = pg.get(key, "")
                    if val:
                        all_text_parts.append(str(val))

    # Strategy 2: search-pages (note: no --exchange flag)
    cmd2_args = ["search-pages", "X-MBX-APIKEY HMAC SHA256 signature recvWindow binance"]
    tr.commands_run.append(f"cex-api-docs {' '.join(cmd2_args)}")
    r2 = run_cli(cmd2_args, docs_dir)

    if r2["ok"] and r2["stdout"]:
        result2 = parse_cli_json(r2["stdout"])
        if result2:
            page_results = result2 if isinstance(result2, list) else result2.get("results", [])
            for pg in page_results:
                for key in ("title", "heading", "snippet", "content"):
                    val = pg.get(key, "")
                    if val:
                        all_text_parts.append(str(val))
            pages_found += len(page_results)

    # Check text for auth terms
    combined = " ".join(all_text_parts).upper()

    if "X-MBX-APIKEY" in combined:
        checklist["header_X-MBX-APIKEY"] = True
    if "HMAC" in combined or "SHA256" in combined or "SHA-256" in combined:
        checklist["algo_HMAC-SHA256"] = True
    if "RSA" in combined:
        checklist["algo_RSA"] = True
    if "ED25519" in combined:
        checklist["algo_Ed25519"] = True
    if "RECVWINDOW" in combined:
        checklist["recvWindow"] = True

    found_count = sum(1 for v in checklist.values() if v)
    total = len(checklist)
    tr.found = {
        "pages_found": pages_found,
        "checklist": checklist,
        "text_sample_len": len(combined),
    }
    tr.missing = [k for k, v in checklist.items() if not v]

    if found_count == total:
        tr.grade = "FULL"
        tr.detail = (
            f"All {total} auth items detected in search snippets. "
            f"{pages_found} relevant pages found."
        )
    elif found_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"{found_count}/{total} auth items in snippets. "
            f"Missing: {', '.join(tr.missing)}. "
            f"Agent could read full page for details."
        )
    elif pages_found > 0:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"Pages found ({pages_found}) but auth terms not in snippets. "
            f"Agent needs to read page markdown."
        )
    else:
        tr.grade = "EMPTY"
        tr.detail = "No auth-related pages found."

    return tr


def test_q5_newer_endpoints(docs_dir: str) -> TestResult:
    """Q5: Can the CLI find newer endpoints (amend, myFilters, amendments)?"""
    tr = TestResult(question="Q5: Newer endpoints", grade="EMPTY", detail="")
    gt = GROUND_TRUTH["q5_newer_endpoints"]

    results: list[dict] = []

    for ep_spec in gt:
        cmd_args = ["lookup-endpoint", ep_spec["path"],
                     "--method", ep_spec["method"], "--exchange", EXCHANGE]
        tr.commands_run.append(f"cex-api-docs {' '.join(cmd_args)}")
        r = run_cli(cmd_args, docs_dir)

        entry: dict[str, Any] = {
            "method": ep_spec["method"],
            "path": ep_spec["path"],
            "found": False,
            "has_schema": False,
            "param_count": 0,
            "source": None,
        }

        if r["ok"] and r["stdout"]:
            result = parse_cli_json(r["stdout"])
            if result:
                ep = find_endpoint(result, ep_spec["method"], ep_spec["path"])
                if ep:
                    entry["found"] = True
                    eid = ep.get("endpoint_id")
                    if eid:
                        ep_data, cmd2 = get_endpoint_detail(eid, docs_dir)
                        tr.commands_run.append(cmd2)
                        if ep_data:
                            raw_params = (ep_data.get("request_schema") or {}).get("parameters") or []
                            params = [extract_param_name(p) for p in raw_params if extract_param_name(p)]
                            entry["has_schema"] = len(params) > 0
                            entry["param_count"] = len(params)
                            # Detect source
                            sources = ep_data.get("sources") or []
                            source_urls = [s.get("url", "") for s in sources]
                            if any("postman" in u.lower() for u in source_urls):
                                entry["source"] = "postman"
                            elif any("openapi" in u.lower() or "swagger" in u.lower()
                                     for u in source_urls):
                                entry["source"] = "openapi"
                            else:
                                entry["source"] = "web" if source_urls else "unknown"

        results.append(entry)

    tr.found = {"endpoints": results}

    found_count = sum(1 for e in results if e["found"])
    schema_count = sum(1 for e in results if e["has_schema"])
    total = len(gt)

    tr.missing = [
        f"{e['method']} {e['path']}" + (" (no schema)" if e["found"] else " (not found)")
        for e in results
        if not e["found"] or not e["has_schema"]
    ]

    if found_count == total and schema_count == total:
        tr.grade = "FULL"
        tr.detail = f"All {total} newer endpoints found with request schemas."
    elif found_count == total:
        sources = [e.get("source", "?") for e in results if not e["has_schema"]]
        tr.grade = "PARTIAL"
        tr.detail = (
            f"All {total} found, but only {schema_count} have schemas. "
            f"Missing schemas sourced from: {', '.join(set(sources))}."
        )
    elif found_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"{found_count}/{total} found, {schema_count} with schemas."
    else:
        tr.grade = "EMPTY"
        tr.detail = "None of the newer endpoints found."

    return tr


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(results: list[TestResult], run_dir: Path) -> str:
    """Generate SKILL_COVERAGE.md report."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# CEX API Query Skill — Coverage Test Results",
        "",
        f"**Run timestamp:** {ts}",
        f"**Script:** `test-scripts/test_skill_coverage.py`",
        f"**Run directory:** `{run_dir}`",
        f"**Baseline:** Binance Spot Skill (binance-skills-hub) v1.0.1",
        "",
        "## Summary",
        "",
        "| # | Question | Grade | Detail |",
        "| --- | --- | --- | --- |",
    ]

    for i, tr in enumerate(results, 1):
        lines.append(f"| Q{i} | {tr.question} | **{tr.grade}** | {tr.detail} |")

    # Overall score
    full = sum(1 for r in results if r.grade == "FULL")
    partial = sum(1 for r in results if r.grade == "PARTIAL")
    empty = sum(1 for r in results if r.grade in ("EMPTY", "ERROR"))
    total = len(results)

    lines.extend([
        "",
        f"**Overall:** {full} FULL, {partial} PARTIAL, {empty} EMPTY/ERROR out of {total}",
        "",
    ])

    # Detail sections
    for i, tr in enumerate(results, 1):
        lines.extend([
            f"## Q{i}: {tr.question}",
            "",
            f"**Grade:** {tr.grade}",
            "",
            f"**Detail:** {tr.detail}",
            "",
            "**Commands run:**",
            "",
        ])
        for cmd in tr.commands_run:
            lines.append(f"- `{cmd}`")

        lines.append("")

        if tr.found:
            lines.append("**Data found:**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(tr.found, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

        if tr.missing:
            lines.append("**Missing:**")
            lines.append("")
            for m in tr.missing:
                lines.append(f"- {m}")
            lines.append("")

    # Interpretation guide
    lines.extend([
        "## Grading Criteria",
        "",
        "- **FULL**: CLI returns structured data with the expected information",
        "- **PARTIAL**: Data exists but requires page reads, $ref resolution, or is incomplete",
        "- **EMPTY**: Data not found through any CLI command",
        "- **ERROR**: CLI command failed",
        "",
        "## What This Tests",
        "",
        "Whether an agent using ONLY the `cex-api-docs` CLI can discover the same details",
        "that the Binance spot skill pre-bakes into its SKILL.md reference table:",
        "",
        "1. Parameter names, types, required/optional status, constraints",
        "2. Enum values for key fields (side, type, timeInForce, etc.)",
        "3. All order list variants with their required parameters",
        "4. Authentication method details (headers, signing, recvWindow)",
        "5. Coverage of newer endpoints (amend, myFilters, amendments)",
        "",
        "Ground truth: Binance Spot Skill SKILL.md (v1.0.1) from binance-skills-hub.",
        "",
    ])

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test cex-api-query skill coverage")
    parser.add_argument("--docs-dir", default="./cex-docs",
                        help="Path to cex-docs directory (default: ./cex-docs)")
    parser.add_argument("--run-dir", default=None,
                        help="Output directory (default: test-scripts/runs/<timestamp>)")
    args = parser.parse_args()

    docs_dir = os.path.abspath(args.docs_dir)
    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = Path("test-scripts/runs") / ts

    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"CEX API Query Skill — Coverage Test")
    print(f"{'=' * 50}")
    print(f"Docs dir: {docs_dir}")
    print(f"Run dir:  {run_dir}")
    print()

    tests = [
        ("Q1: Parameters", test_q1_parameters),
        ("Q2: Enums", test_q2_enums),
        ("Q3: Order Lists", test_q3_order_lists),
        ("Q4: Auth", test_q4_auth),
        ("Q5: Newer Endpoints", test_q5_newer_endpoints),
    ]

    results: list[TestResult] = []
    for name, test_fn in tests:
        print(f"  Running {name}...", end=" ", flush=True)
        tr = test_fn(docs_dir)
        results.append(tr)
        print(f"[{tr.grade}]")

    print()

    # Write outputs
    report = generate_report(results, run_dir)
    report_path = run_dir / "SKILL_COVERAGE.md"
    report_path.write_text(report, encoding="utf-8")

    results_json = run_dir / "results.json"
    results_json.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Print summary
    print(f"{'=' * 50}")
    print()
    full = sum(1 for r in results if r.grade == "FULL")
    partial = sum(1 for r in results if r.grade == "PARTIAL")
    empty = sum(1 for r in results if r.grade in ("EMPTY", "ERROR"))

    for r in results:
        pad = max(1, 35 - len(r.question))
        print(f"  {r.question}{' ' * pad}[{r.grade:7s}]  {r.detail[:80]}")

    print()
    print(f"  Score: {full} FULL / {partial} PARTIAL / {empty} EMPTY")
    print()
    print(f"  Report: {report_path}")
    print(f"  JSON:   {results_json}")


if __name__ == "__main__":
    main()
