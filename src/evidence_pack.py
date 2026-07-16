# -*- coding: utf-8 -*-
"""EvidencePack v1 helpers.

Small, deterministic helpers used by report-only agent memos.  They turn tool
traces and source-health rows into an auditable evidence contract so limited
information does not look like a full research report.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

EVIDENCE_PACK_SCHEMA = "evidence_pack_v1"
SOURCE_ATTEMPT_SCHEMA = "source_attempt_v1"

SEARCH_TOOLS = {"search_stock_news", "search_comprehensive_intel"}
DATA_SOURCE_TOOLS = {
    "get_realtime_quote",
    "get_daily_history",
    "get_stock_info",
    "get_capital_flow",
    "get_chip_distribution",
}


def failure_reason_from_text(text: Any) -> str:
    value = str(text or "").lower()
    if not value:
        return ""
    if "usage limit" in value or "too many requests" in value or "429" in value or "rate" in value:
        return "rate_limited"
    if "api key" in value or "no search engine" in value or "missing_key" in value:
        return "missing_key"
    if "permission" in value or "forbidden" in value or "403" in value or "plan" in value:
        return "permission_limited"
    if "timeout" in value or "timed out" in value:
        return "timeout"
    if "anti" in value or "captcha" in value:
        return "anti_bot"
    if "parse" in value or "json" in value:
        return "parse_error"
    if "no matching" in value or "no_matching" in value:
        return "no_matching_market"
    if "disconnect" in value or "endpoint" in value or "404" in value:
        return "endpoint_changed"
    return "unknown"


def _tool_domain(tool: str) -> str:
    if tool in SEARCH_TOOLS:
        return "news_reports"
    if tool in DATA_SOURCE_TOOLS:
        return "market_data"
    return "runtime_tool"


def source_attempts_from_tool_calls(tool_calls: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    attempts: List[Dict[str, Any]] = []
    for entry in tool_calls or []:
        if not isinstance(entry, dict):
            continue
        tool = str(entry.get("tool") or "").strip()
        if not tool:
            continue
        args = entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {}
        result_success = entry.get("result_success")
        if result_success is None:
            result_success = entry.get("success")
        success = bool(entry.get("success")) and bool(result_success)
        error = entry.get("result_error") or entry.get("error") or ""
        results_count = _int_or_zero(entry.get("results_count"))
        if not success:
            status = "FAILED"
        elif results_count > 0:
            status = "REFRESHED"
        else:
            status = "DEGRADED"
        attempts.append(
            {
                "schema": SOURCE_ATTEMPT_SCHEMA,
                "source": str(entry.get("provider") or tool),
                "tool": tool,
                "domain": _tool_domain(tool),
                "query": str(entry.get("query") or _query_from_args(tool, args)),
                "status": status,
                "failure_reason": failure_reason_from_text(error) if status == "FAILED" else "",
                "error": str(error or ""),
                "results_count": results_count,
                "duration": entry.get("duration"),
                "stock_code": args.get("stock_code", ""),
                "stock_name": args.get("stock_name", ""),
                "impact_scope": _impact_scope_for_tool(tool),
            }
        )
    return attempts


def build_evidence_pack(
    *,
    scope: str,
    symbol: str = "",
    source_attempts: Optional[List[Dict[str, Any]]] = None,
    evidence_items: Optional[List[Any]] = None,
    missing_evidence: Optional[List[str]] = None,
    critical_missing: bool = False,
) -> Dict[str, Any]:
    attempts = [a for a in (source_attempts or []) if isinstance(a, dict)]
    items = _normalize_evidence_items(evidence_items or [])
    missing = [str(item) for item in (missing_evidence or []) if str(item)]
    level = evidence_level(items, attempts, missing, critical_missing=critical_missing)
    limited = level in {"LIMITED", "FAILED"}
    return {
        "schema": EVIDENCE_PACK_SCHEMA,
        "scope": scope,
        "symbol": symbol,
        "source_attempts": attempts,
        "evidence_items": items,
        "missing_evidence": missing,
        "evidence_level": level,
        "confidence": confidence_for_level(level),
        "limited_report": limited,
        "can_go_redblue": level in {"FULL", "PARTIAL"} and not critical_missing,
        "can_trade_review": level == "FULL" and not critical_missing,
        "no_trade_execution": True,
    }


def evidence_level(
    evidence_items: List[Dict[str, Any]],
    source_attempts: List[Dict[str, Any]],
    missing_evidence: List[str],
    *,
    critical_missing: bool = False,
) -> str:
    if critical_missing:
        return "LIMITED" if source_attempts or evidence_items else "FAILED"
    refreshed = sum(1 for item in source_attempts if item.get("status") == "REFRESHED")
    failed = sum(1 for item in source_attempts if item.get("status") == "FAILED")
    if evidence_items and not missing_evidence and refreshed >= 2:
        return "FULL"
    if evidence_items and (refreshed or not failed):
        return "PARTIAL"
    if source_attempts:
        return "LIMITED"
    return "FAILED"


def confidence_for_level(level: str) -> str:
    return {"FULL": "high", "PARTIAL": "medium", "LIMITED": "low", "FAILED": "low"}.get(level, "low")


def _normalize_evidence_items(items: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        elif item:
            normalized.append({"fact": str(item), "confidence": "low"})
    return normalized


def _query_from_args(tool: str, args: Dict[str, Any]) -> str:
    code = str(args.get("stock_code") or "").strip()
    name = str(args.get("stock_name") or "").strip()
    if tool in SEARCH_TOOLS:
        return " ".join(x for x in [name, code, "最新消息"] if x).strip()
    return " ".join(x for x in [tool, code, name] if x).strip()


def _impact_scope_for_tool(tool: str) -> List[str]:
    if tool in SEARCH_TOOLS:
        return ["news", "reports", "catalyst", "evidence_gate"]
    if tool == "get_capital_flow":
        return ["fund_flow", "risk", "evidence_gate"]
    if tool in DATA_SOURCE_TOOLS:
        return ["market_data", "technical", "risk"]
    return ["agent_runtime"]


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def safe_json_loads(text: Any) -> Any:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None
