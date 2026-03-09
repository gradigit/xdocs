#!/usr/bin/env python3
"""
CEX API Docs CLI — Robustness & Edge Case Tests

Tests CLI behavior across diverse, real-world scenarios that go beyond
the Binance spot skill ground truth. Covers:

  T1  Classify routing accuracy (error, endpoint, question, WS, code, Korean)
  T2  Negative error code lookup (Binance -1021, -1002, -2010)
  T3  Cross-exchange parity (rate limit query on binance, okx, bybit)
  T4  Korean exchange retrieval (Upbit endpoint, semantic search in Korean)
  T5  Answer command end-to-end (cite-only pipeline)
  T6  Futures vs spot disambiguation (/api, /fapi, /dapi)
  T7  Coverage gaps analysis (Binance spot field completeness)
  T8  OKX WebSocket retrieval (error codes 60029/60018, semantic search)

Usage:
    source .venv/bin/activate
    python3 test-scripts/test_cli_robustness.py [--docs-dir ./cex-docs] [--run-dir DIR]

Outputs:
    test-scripts/runs/<timestamp>/CLI_ROBUSTNESS.md   — human + agent readable report
    test-scripts/runs/<timestamp>/robustness.json     — machine-readable results
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_cli(args: list[str], docs_dir: str, timeout: int = 60) -> dict[str, Any]:
    """Run a cex-api-docs CLI command. Returns {ok, stdout, stderr, returncode}."""
    # Insert --docs-dir before any -- separator so argparse sees it as a flag
    if "--" in args:
        idx = args.index("--")
        cmd = ["cex-api-docs"] + args[:idx] + ["--docs-dir", docs_dir] + args[idx:]
    else:
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
        return {"ok": False, "stdout": "", "stderr": "cex-api-docs not found", "returncode": -1}


def parse_cli_json(text: str) -> Any:
    """Parse CLI JSON output, unwrapping the {"ok":true,"result":...} envelope."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


@dataclass
class TestResult:
    test_id: str
    question: str
    grade: str  # PASS / PARTIAL / FAIL / ERROR
    detail: str
    commands_run: list[str] = field(default_factory=list)
    found: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


# ── Test Functions ───────────────────────────────────────────────────────────

def test_t1_classify_routing(docs_dir: str) -> TestResult:
    """T1: Does classify correctly identify input types?"""
    tr = TestResult("T1", "Classify routing accuracy", "FAIL", "")

    cases = [
        {
            "input": 'Getting {"code":-1021,"msg":"Timestamp for this request was 1000ms ahead"} on Binance',
            "expected_type": "error_message",
            "label": "error_with_json",
        },
        {
            "input": "POST /api/v3/order",
            "expected_type": "endpoint_path",
            "label": "endpoint_path",
        },
        {
            "input": "What rate limits does Bybit have for spot orders?",
            "expected_type": "question",
            "label": "natural_question",
        },
        {
            "input": "OKX fills websocket channel subscription",
            "expected_type": "question",  # no ws_channel type exists yet
            "label": "ws_channel_query",
            "note": "Ideally would be ws_channel_name if supported",
        },
        {
            "input": 'headers = {"X-MBX-APIKEY": api_key}; signature = hmac.new(secret, query_string, hashlib.sha256).hexdigest()',
            "expected_type": "code_snippet",
            "label": "code_snippet",
        },
        {
            "input": "\uc5c5\ube44\ud2b8 \uc8fc\ubb38 API\uc5d0\uc11c \uc794\uace0 \ubd80\uc871 \uc5d0\ub7ec",
            "expected_type": "error_message",
            "label": "korean_error",
            "note": "Korean: 'Upbit order API insufficient balance error'",
        },
    ]

    results = {}
    pass_count = 0

    for case in cases:
        cmd_args = ["classify", case["input"]]
        tr.commands_run.append(f"cex-api-docs classify \"{case['input'][:60]}...\"")
        r = run_cli(cmd_args, docs_dir, timeout=15)

        entry = {"expected": case["expected_type"], "got": None, "confidence": 0, "pass": False}

        if r["ok"] and r["stdout"]:
            data = parse_cli_json(r["stdout"])
            if data:
                entry["got"] = data.get("input_type")
                entry["confidence"] = data.get("confidence", 0)
                entry["signals"] = data.get("signals", {})
                if entry["got"] == case["expected_type"]:
                    entry["pass"] = True
                    pass_count += 1
                elif entry["confidence"] <= 0.3:
                    tr.issues.append(
                        f"{case['label']}: low confidence {entry['confidence']} "
                        f"(got {entry['got']}, expected {case['expected_type']})"
                    )
        else:
            entry["error"] = r["stderr"][:100]
            tr.issues.append(f"{case['label']}: CLI error")

        if "note" in case:
            entry["note"] = case["note"]
        results[case["label"]] = entry

    tr.found = results
    total = len(cases)

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} inputs correctly classified."
    elif pass_count >= total * 0.6:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} correctly classified."
    else:
        tr.grade = "FAIL"
        tr.detail = f"Only {pass_count}/{total} correctly classified."

    return tr


def test_t2_negative_error_codes(docs_dir: str) -> TestResult:
    """T2: Can search-error handle Binance negative error codes?"""
    tr = TestResult("T2", "Negative error code lookup (Binance)", "FAIL", "")

    codes = [
        ("-1021", "INVALID_TIMESTAMP"),
        ("-1002", "UNAUTHORIZED"),
        ("-2010", "NEW_ORDER_REJECTED"),
    ]

    results = {}
    pass_count = 0

    for code, label in codes:
        # Flags before -- for negative codes
        cmd_args = ["search-error", "--exchange", "binance", "--", code]
        tr.commands_run.append(f"cex-api-docs search-error --exchange binance -- {code}")
        r = run_cli(cmd_args, docs_dir, timeout=15)

        entry = {"code": code, "label": label, "match_count": 0, "pass": False}

        if r["ok"] and r["stdout"]:
            data = parse_cli_json(r["stdout"])
            if data:
                matches = data.get("matches", [])
                entry["match_count"] = len(matches)
                if matches:
                    entry["top_title"] = matches[0].get("title", "")
                    entry["top_snippet"] = matches[0].get("snippet", "")[:100]
                    # Check snippet actually contains the error code
                    code_digits = code.lstrip("-")
                    if any(code_digits in (m.get("snippet", "") + m.get("title", ""))
                           for m in matches):
                        entry["pass"] = True
                        pass_count += 1
        else:
            entry["error"] = r["stderr"][:100]
            tr.issues.append(f"{code} ({label}): CLI error")

        results[code] = entry

    tr.found = results
    total = len(codes)

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} negative error codes found with relevant snippets."
    elif pass_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} error codes returned relevant results."
    else:
        tr.grade = "FAIL"
        tr.detail = "No negative error codes returned results."

    return tr


def test_t3_cross_exchange_rate_limits(docs_dir: str) -> TestResult:
    """T3: Does semantic search work across exchanges for the same concept?"""
    tr = TestResult("T3", "Cross-exchange rate limit query", "FAIL", "")

    exchanges = [
        ("binance", "spot order rate limit weight"),
        ("okx", "spot order rate limit"),
        ("bybit", "spot order rate limit"),
    ]

    results = {}
    pass_count = 0

    for exchange, query in exchanges:
        cmd_args = ["semantic-search", query,
                    "--exchange", exchange, "--mode", "hybrid", "--limit", "3"]
        tr.commands_run.append(f"cex-api-docs semantic-search \"{query}\" --exchange {exchange}")
        r = run_cli(cmd_args, docs_dir, timeout=90)

        entry = {"exchange": exchange, "result_count": 0, "pass": False,
                 "rerank_applied": False, "top_heading": None}

        if r["ok"] and r["stdout"]:
            data = parse_cli_json(r["stdout"])
            if data:
                results_list = data.get("results", [])
                entry["result_count"] = len(results_list)
                entry["rerank_applied"] = data.get("rerank_applied", False)
                if results_list:
                    top = results_list[0]
                    entry["top_heading"] = top.get("heading", "")
                    entry["top_title"] = top.get("title", "")
                    entry["top_score"] = top.get("blended_score", top.get("score", 0))
                    # Check if heading/title mentions rate limit
                    combined = (entry["top_heading"] + " " + entry.get("top_title", "")).lower()
                    if "rate" in combined or "limit" in combined:
                        entry["pass"] = True
                        pass_count += 1
                    else:
                        tr.issues.append(
                            f"{exchange}: top result '{entry['top_heading']}' "
                            f"doesn't mention rate limit"
                        )
        else:
            entry["error"] = r["stderr"][:100]
            tr.issues.append(f"{exchange}: CLI error")

        results[exchange] = entry

    tr.found = results
    total = len(exchanges)

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} exchanges returned rate limit results."
    elif pass_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} exchanges returned relevant rate limit results."
    else:
        tr.grade = "FAIL"
        tr.detail = "No exchanges returned relevant rate limit results."

    return tr


def test_t4_korean_exchange(docs_dir: str) -> TestResult:
    """T4: Can the CLI retrieve from Korean exchange docs (Upbit)?"""
    tr = TestResult("T4", "Korean exchange retrieval (Upbit)", "FAIL", "")

    subtests = {}
    pass_count = 0

    # Subtest A: lookup Upbit order endpoint
    cmd_a = ["lookup-endpoint", "/v1/orders", "--method", "POST", "--exchange", "upbit"]
    tr.commands_run.append("cex-api-docs lookup-endpoint /v1/orders --method POST --exchange upbit")
    r_a = run_cli(cmd_a, docs_dir, timeout=15)
    entry_a = {"label": "lookup_endpoint", "pass": False}

    if r_a["ok"] and r_a["stdout"]:
        data_a = parse_cli_json(r_a["stdout"])
        if data_a:
            matches = data_a.get("matches", [])
            if matches:
                ep = matches[0]
                entry_a["found"] = True
                entry_a["method"] = (ep.get("http") or {}).get("method", "")
                entry_a["path"] = (ep.get("http") or {}).get("path", "")
                entry_a["description"] = ep.get("description", "")
                entry_a["field_status"] = ep.get("field_status", {})
                if entry_a["method"] == "POST":
                    entry_a["pass"] = True
                    pass_count += 1
                fs = entry_a["field_status"]
                undoc = [k for k, v in fs.items() if v in ("undocumented", "unknown")]
                if undoc:
                    tr.issues.append(f"Upbit POST /v1/orders: undocumented fields: {', '.join(undoc)}")
    else:
        entry_a["error"] = r_a["stderr"][:100]
    subtests["lookup_endpoint"] = entry_a

    # Subtest B: semantic search in Korean
    cmd_b = ["semantic-search", "Upbit \uc8fc\ubb38 API \ub9e4\uc218 \ub9e4\ub3c4",
             "--exchange", "upbit", "--mode", "hybrid", "--limit", "3"]
    tr.commands_run.append("cex-api-docs semantic-search \"Upbit \uc8fc\ubb38 API \ub9e4\uc218 \ub9e4\ub3c4\" --exchange upbit")
    r_b = run_cli(cmd_b, docs_dir, timeout=90)
    entry_b = {"label": "korean_semantic_search", "pass": False}

    if r_b["ok"] and r_b["stdout"]:
        data_b = parse_cli_json(r_b["stdout"])
        if data_b:
            results_list = data_b.get("results", [])
            entry_b["result_count"] = len(results_list)
            if results_list:
                top = results_list[0]
                entry_b["top_heading"] = top.get("heading", "")
                entry_b["top_title"] = top.get("title", "")
                entry_b["top_score"] = top.get("blended_score", top.get("score", 0))
                for res in results_list:
                    title = (res.get("title") or "").lower()
                    heading = (res.get("heading") or "").lower()
                    combined = title + " " + heading
                    if "\uc8fc\ubb38" in combined or "order" in combined:
                        entry_b["pass"] = True
                        entry_b["matched_on"] = res.get("title", "")
                        pass_count += 1
                        break
                if not entry_b["pass"]:
                    tr.issues.append(
                        f"Korean semantic search: top result '{entry_b['top_title']}' "
                        f"not about orders"
                    )
    else:
        entry_b["error"] = r_b["stderr"][:100]
    subtests["korean_semantic"] = entry_b

    # Subtest C: search-endpoints for Upbit
    cmd_c = ["search-endpoints", "order", "--exchange", "upbit"]
    tr.commands_run.append("cex-api-docs search-endpoints order --exchange upbit")
    r_c = run_cli(cmd_c, docs_dir, timeout=15)
    entry_c = {"label": "search_endpoints", "pass": False}

    if r_c["ok"] and r_c["stdout"]:
        data_c = parse_cli_json(r_c["stdout"])
        if data_c:
            matches = data_c.get("matches", []) if isinstance(data_c, dict) else data_c
            if isinstance(matches, list):
                entry_c["match_count"] = len(matches)
                if len(matches) > 0:
                    entry_c["pass"] = True
                    pass_count += 1
                    entry_c["sample_paths"] = [
                        (m.get("http") or {}).get("path", m.get("path", "?"))
                        for m in matches[:5]
                    ]
    else:
        entry_c["error"] = r_c["stderr"][:100]
    subtests["search_endpoints"] = entry_c

    tr.found = subtests
    total = 3

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} Upbit subtests passed."
    elif pass_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} Upbit subtests passed."
    else:
        tr.grade = "FAIL"
        tr.detail = "No Upbit subtests passed."

    return tr


def test_t5_answer_e2e(docs_dir: str) -> TestResult:
    """T5: Does the answer command produce a useful cited answer?"""
    tr = TestResult("T5", "Answer command end-to-end", "FAIL", "")

    question = "What permissions does the Binance API key need to place a spot order?"
    cmd_args = ["answer", question]
    tr.commands_run.append(f"cex-api-docs answer \"{question}\"")
    r = run_cli(cmd_args, docs_dir, timeout=120)

    entry = {"pass": False, "has_citations": False, "status": None, "claim_count": 0}

    if r["ok"] and r["stdout"]:
        try:
            data = json.loads(r["stdout"])
        except json.JSONDecodeError:
            tr.detail = "answer returned non-JSON output"
            tr.grade = "ERROR"
            tr.found = {"raw_output": r["stdout"][:500]}
            return tr

        entry["status"] = data.get("status")
        claims = data.get("claims", [])
        entry["claim_count"] = len(claims)

        for claim in claims:
            citations = claim.get("citations", [])
            if citations:
                entry["has_citations"] = True
                entry["citation_urls"] = [c.get("url", "") for c in citations[:3]]
                break

        all_text = " ".join(c.get("text", "") for c in claims).lower()
        relevance_keywords = ["api key", "permission", "trading", "spot", "enable"]
        entry["keyword_hits"] = [kw for kw in relevance_keywords if kw in all_text]

        # Check section precision: spot question should cite spot docs, not derivatives
        section_correct = True
        for claim in claims:
            for cite in claim.get("citations", []):
                url = cite.get("url", "")
                if "derivatives" in url and "spot" not in url:
                    section_correct = False
                    entry["section_mismatch"] = url
                    tr.issues.append(f"Section mismatch: cites derivatives page for spot question: {url}")
                    break

        if entry["has_citations"] and len(entry["keyword_hits"]) >= 2:
            entry["pass"] = True
            if section_correct:
                tr.grade = "PASS"
                tr.detail = (
                    f"Answer with {entry['claim_count']} claim(s), "
                    f"cited from correct section, mentions {', '.join(entry['keyword_hits'])}."
                )
            else:
                tr.grade = "PARTIAL"
                tr.detail = (
                    f"Answer with {entry['claim_count']} claim(s) and citations, "
                    f"but cites derivatives instead of spot docs."
                )
        elif entry["has_citations"]:
            tr.grade = "PARTIAL"
            tr.detail = (
                f"Answer has citations but may lack specificity. "
                f"Keywords found: {entry['keyword_hits']}."
            )
        elif entry["claim_count"] > 0:
            tr.grade = "PARTIAL"
            tr.detail = f"Answer has {entry['claim_count']} claim(s) but no citations."
        else:
            tr.grade = "FAIL"
            tr.detail = "Answer returned no claims."
    else:
        entry["error"] = r["stderr"][:200]
        tr.grade = "ERROR"
        tr.detail = f"answer command failed: {r['stderr'][:100]}"

    tr.found = entry
    return tr


def test_t6_futures_spot_disambiguation(docs_dir: str) -> TestResult:
    """T6: Does lookup-endpoint correctly separate spot/futures/coin-m?"""
    tr = TestResult("T6", "Futures vs spot disambiguation", "FAIL", "")

    lookups = [
        {"path": "/api/v3/order", "method": "POST", "expected_section": "spot"},
        {"path": "/fapi/v1/order", "method": "POST", "expected_section": "futures_usdm"},
        {"path": "/dapi/v1/order", "method": "POST", "expected_section": "futures_coinm"},
    ]

    results = {}
    pass_count = 0

    for spec in lookups:
        cmd_args = ["lookup-endpoint", spec["path"],
                    "--method", spec["method"], "--exchange", "binance"]
        tr.commands_run.append(
            f"cex-api-docs lookup-endpoint {spec['path']} --method {spec['method']} --exchange binance"
        )
        r = run_cli(cmd_args, docs_dir, timeout=15)

        label = f"{spec['method']} {spec['path']}"
        entry = {"expected_section": spec["expected_section"], "pass": False}

        if r["ok"] and r["stdout"]:
            data = parse_cli_json(r["stdout"])
            if data:
                matches = data.get("matches", [])
                entry["match_count"] = len(matches)
                sections_found = set()
                for m in matches:
                    s = m.get("section", "")
                    sections_found.add(s)
                entry["sections_found"] = sorted(sections_found)
                if spec["expected_section"] in sections_found:
                    entry["pass"] = True
                    pass_count += 1
                wrong_sections = sections_found - {spec["expected_section"]}
                if wrong_sections:
                    entry["other_sections"] = sorted(wrong_sections)
        else:
            entry["error"] = r["stderr"][:100]
            tr.issues.append(f"{label}: CLI error")

        results[label] = entry

    tr.found = results
    total = len(lookups)

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} path prefixes resolve to correct sections."
    elif pass_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} correctly disambiguated."
    else:
        tr.grade = "FAIL"
        tr.detail = "No paths correctly disambiguated."

    return tr


def test_t7_coverage_gaps(docs_dir: str) -> TestResult:
    """T7: What fields are documented vs unknown for Binance spot?"""
    tr = TestResult("T7", "Coverage gaps (Binance spot)", "FAIL", "")

    cmd_args = ["coverage-gaps", "--exchange", "binance", "--section", "spot"]
    tr.commands_run.append("cex-api-docs coverage-gaps --exchange binance --section spot")
    r = run_cli(cmd_args, docs_dir, timeout=30)

    if not r["ok"]:
        tr.grade = "ERROR"
        tr.detail = f"coverage-gaps command failed: {r['stderr'][:100]}"
        return tr

    data = parse_cli_json(r["stdout"])
    if not data:
        tr.grade = "ERROR"
        tr.detail = "coverage-gaps returned unparseable output"
        return tr

    counts = data.get("counts", {})
    total_endpoints = counts.get("endpoints", 0)
    sample = data.get("sample", [])

    field_summary = {}

    for row in sample:
        field_name = row.get("field_name", "?")
        status_counts = row.get("status_counts", {})
        doc_count = status_counts.get("documented", 0)
        unknown_count = status_counts.get("unknown", 0) + status_counts.get("undocumented", 0)
        total = doc_count + unknown_count

        field_summary[field_name] = {
            "documented": doc_count,
            "unknown": unknown_count,
            "total": total,
            "pct": round(doc_count / total * 100, 1) if total > 0 else 0,
        }

    tr.found = {
        "total_endpoints": total_endpoints,
        "fields": field_summary,
    }

    critical_fields = ["request_schema", "response_schema", "description", "rate_limit"]
    critical_documented = sum(
        1 for f in critical_fields
        if field_summary.get(f, {}).get("pct", 0) > 50
    )

    for f in critical_fields:
        pct = field_summary.get(f, {}).get("pct", 0)
        if pct == 0:
            tr.issues.append(f"{f}: 0% documented across {total_endpoints} endpoints")
        elif pct < 50:
            tr.issues.append(f"{f}: only {pct}% documented")

    if critical_documented == len(critical_fields):
        tr.grade = "PASS"
        tr.detail = f"All critical fields >50% documented across {total_endpoints} endpoints."
    elif critical_documented > 0:
        tr.grade = "PARTIAL"
        tr.detail = (
            f"{critical_documented}/{len(critical_fields)} critical fields >50% documented. "
            f"{total_endpoints} total endpoints."
        )
    else:
        tr.grade = "FAIL"
        tr.detail = (
            f"No critical fields >50% documented across {total_endpoints} endpoints."
        )

    return tr


def test_t8_okx_websocket(docs_dir: str) -> TestResult:
    """T8: Can the CLI retrieve OKX WebSocket channel info?"""
    tr = TestResult("T8", "OKX WebSocket retrieval", "FAIL", "")

    subtests = {}
    pass_count = 0

    # Subtest A: search-error 60029 (fills VIP6)
    # Note: positive error code — do NOT use -- separator
    cmd_a = ["search-error", "--exchange", "okx", "60029"]
    tr.commands_run.append("cex-api-docs search-error --exchange okx 60029")
    r_a = run_cli(cmd_a, docs_dir, timeout=15)
    entry_a = {"label": "error_60029", "pass": False}

    if r_a["ok"] and r_a["stdout"]:
        data = parse_cli_json(r_a["stdout"])
        if data:
            matches = data.get("matches", [])
            entry_a["match_count"] = len(matches)
            if matches:
                entry_a["top_snippet"] = matches[0].get("snippet", "")[:150]
                if "60029" in entry_a["top_snippet"]:
                    entry_a["pass"] = True
                    pass_count += 1
    subtests["error_60029"] = entry_a

    # Subtest B: search-error 60018 (wrong URL)
    cmd_b = ["search-error", "--exchange", "okx", "60018"]
    tr.commands_run.append("cex-api-docs search-error --exchange okx 60018")
    r_b = run_cli(cmd_b, docs_dir, timeout=15)
    entry_b = {"label": "error_60018", "pass": False}

    if r_b["ok"] and r_b["stdout"]:
        data = parse_cli_json(r_b["stdout"])
        if data:
            matches = data.get("matches", [])
            entry_b["match_count"] = len(matches)
            if matches:
                entry_b["top_snippet"] = matches[0].get("snippet", "")[:150]
                if "60018" in entry_b["top_snippet"]:
                    entry_b["pass"] = True
                    pass_count += 1
    subtests["error_60018"] = entry_b

    # Subtest C: semantic search for fills channel
    cmd_c = ["semantic-search", "OKX fills channel VIP6 websocket subscription",
             "--exchange", "okx", "--mode", "hybrid", "--limit", "5"]
    tr.commands_run.append(
        "cex-api-docs semantic-search \"OKX fills channel VIP6 websocket subscription\" --exchange okx"
    )
    r_c = run_cli(cmd_c, docs_dir, timeout=90)
    entry_c = {"label": "semantic_fills_channel", "pass": False}

    if r_c["ok"] and r_c["stdout"]:
        data = parse_cli_json(r_c["stdout"])
        if data:
            results_list = data.get("results", [])
            entry_c["result_count"] = len(results_list)
            entry_c["rerank_applied"] = data.get("rerank_applied", False)
            if results_list:
                top = results_list[0]
                entry_c["top_heading"] = top.get("heading", "")
                entry_c["top_score"] = top.get("blended_score", top.get("score", 0))
                heading_lower = entry_c["top_heading"].lower()
                if "fills" in heading_lower and "channel" in heading_lower:
                    entry_c["pass"] = True
                    pass_count += 1
                else:
                    tr.issues.append(
                        f"Fills channel: top heading '{entry_c['top_heading']}' "
                        f"doesn't match 'Fills channel'"
                    )
    subtests["semantic_fills"] = entry_c

    # Subtest D: semantic search for deposit-info channel
    cmd_d = ["semantic-search",
             "OKX deposit-info withdrawal-info websocket channel business endpoint",
             "--exchange", "okx", "--mode", "hybrid", "--limit", "5"]
    tr.commands_run.append(
        "cex-api-docs semantic-search \"OKX deposit-info withdrawal-info...\" --exchange okx"
    )
    r_d = run_cli(cmd_d, docs_dir, timeout=90)
    entry_d = {"label": "semantic_deposit_withdrawal", "pass": False}

    if r_d["ok"] and r_d["stdout"]:
        data = parse_cli_json(r_d["stdout"])
        if data:
            results_list = data.get("results", [])
            entry_d["result_count"] = len(results_list)
            entry_d["rerank_applied"] = data.get("rerank_applied", False)
            if results_list:
                for res in results_list:
                    heading = (res.get("heading") or "").lower()
                    if "deposit" in heading or "withdrawal" in heading:
                        entry_d["pass"] = True
                        entry_d["matched_heading"] = res.get("heading", "")
                        pass_count += 1
                        break
                if not entry_d["pass"]:
                    headings = [r.get("heading", "") for r in results_list]
                    entry_d["all_headings"] = headings
                    tr.issues.append(
                        f"Deposit/withdrawal: no result heading mentions deposit or withdrawal. "
                        f"Headings: {headings}"
                    )
    subtests["semantic_deposit_withdrawal"] = entry_d

    tr.found = subtests
    total = 4

    if pass_count == total:
        tr.grade = "PASS"
        tr.detail = f"All {total} OKX WebSocket subtests passed."
    elif pass_count >= 3:
        tr.grade = "PARTIAL"
        tr.detail = f"{pass_count}/{total} OKX WebSocket subtests passed."
    elif pass_count > 0:
        tr.grade = "PARTIAL"
        tr.detail = f"Only {pass_count}/{total} OKX WebSocket subtests passed."
    else:
        tr.grade = "FAIL"
        tr.detail = "No OKX WebSocket subtests passed."

    return tr


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(results: list[TestResult], run_dir: Path) -> str:
    """Generate CLI_ROBUSTNESS.md report."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# CEX API Docs CLI — Robustness & Edge Case Test Results",
        "",
        f"**Run timestamp:** {ts}",
        f"**Script:** `test-scripts/test_cli_robustness.py`",
        f"**Run directory:** `{run_dir}`",
        "",
        "## Summary",
        "",
        "| # | Test | Grade | Detail |",
        "| --- | --- | --- | --- |",
    ]

    for tr in results:
        lines.append(f"| {tr.test_id} | {tr.question} | **{tr.grade}** | {tr.detail} |")

    pass_count = sum(1 for r in results if r.grade == "PASS")
    partial_count = sum(1 for r in results if r.grade == "PARTIAL")
    fail_count = sum(1 for r in results if r.grade in ("FAIL", "ERROR"))
    total = len(results)

    lines.extend([
        "",
        f"**Overall:** {pass_count} PASS, {partial_count} PARTIAL, {fail_count} FAIL/ERROR out of {total}",
        "",
    ])

    for tr in results:
        lines.extend([
            f"## {tr.test_id}: {tr.question}",
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
            lines.append(json.dumps(tr.found, indent=2, ensure_ascii=False, default=str))
            lines.append("```")
            lines.append("")

        if tr.issues:
            lines.append("**Issues:**")
            lines.append("")
            for issue in tr.issues:
                lines.append(f"- {issue}")
            lines.append("")

    lines.extend([
        "## Grading Criteria",
        "",
        "- **PASS**: Command returns correct, actionable results",
        "- **PARTIAL**: Results exist but have quality issues (wrong section, low confidence, missing fields)",
        "- **FAIL**: Command returns no useful results or wrong results",
        "- **ERROR**: Command failed to execute",
        "",
    ])

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test cex-api-docs CLI robustness")
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

    print("CEX API Docs CLI — Robustness & Edge Case Tests")
    print("=" * 50)
    print(f"Docs dir: {docs_dir}")
    print(f"Run dir:  {run_dir}")
    print()

    tests = [
        ("T1: Classify", test_t1_classify_routing),
        ("T2: Neg Error Codes", test_t2_negative_error_codes),
        ("T3: Cross-Exchange", test_t3_cross_exchange_rate_limits),
        ("T4: Korean (Upbit)", test_t4_korean_exchange),
        ("T5: Answer E2E", test_t5_answer_e2e),
        ("T6: Futures/Spot", test_t6_futures_spot_disambiguation),
        ("T7: Coverage Gaps", test_t7_coverage_gaps),
        ("T8: OKX WebSocket", test_t8_okx_websocket),
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
    report_path = run_dir / "CLI_ROBUSTNESS.md"
    report_path.write_text(report, encoding="utf-8")

    results_json = run_dir / "robustness.json"
    results_json.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # Print summary
    print("=" * 50)
    print()
    pass_count = sum(1 for r in results if r.grade == "PASS")
    partial_count = sum(1 for r in results if r.grade == "PARTIAL")
    fail_count = sum(1 for r in results if r.grade in ("FAIL", "ERROR"))

    for r in results:
        pad = max(1, 40 - len(r.question))
        print(f"  {r.question}{' ' * pad}[{r.grade:7s}]  {r.detail[:75]}")

    print()
    print(f"  Score: {pass_count} PASS / {partial_count} PARTIAL / {fail_count} FAIL")
    print()
    print(f"  Report: {report_path}")
    print(f"  JSON:   {results_json}")


if __name__ == "__main__":
    main()
