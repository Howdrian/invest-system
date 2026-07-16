"""Provider ledger builders for daily source-health snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .daily_common import (
    as_list,
    dedupe,
    int_or_none,
    iter_agent_memos,
    iter_attempts,
    normalize_domain,
    official_events_payloads,
)


def provider_runs_from_official_events(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for payload in official_events_payloads(docs, run_date):
        scope = str(payload.get("sourceScope") or "subject_evidence")
        for item in as_list(payload.get("providerRuns")):
            if isinstance(item, Mapping):
                rows.append({**dict(item), "source_scope": str(item.get("source_scope") or scope)})
    return rows


def provider_runs_from_agent_memos(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _path, memo in iter_agent_memos(docs, run_date):
        for attempt in iter_attempts(memo):
            rows.append(attempt_to_provider_run(attempt, memo))
    return rows


def provider_runs_from_macro_context(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    path = docs.parent / "data" / "macro_cache" / "macro_context_latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [{
            "provider": "FRED",
            "domain": "macro",
            "data_type": "macro",
            "operation": "macro_context",
            "success": False,
            "record_count": 0,
            "error_type": "empty",
            "error_message_sanitized": "macro_context_cache_missing",
            "source_scope": "subject_evidence",
        }]
    components = payload.get("components") if isinstance(payload, Mapping) else {}
    fred = components.get("fred") if isinstance(components, Mapping) and isinstance(components.get("fred"), Mapping) else {}
    series = fred.get("series") if isinstance(fred.get("series"), list) else []
    success = str(payload.get("status") or "").upper() == "REFRESHED" and bool(series)
    return [{
        "provider": "FRED",
        "domain": "macro",
        "data_type": "macro",
        "operation": "macro_context",
        "success": success,
        "record_count": len(series),
        "error_type": None if success else ("auth_missing" if fred.get("needs_key") else "empty"),
        "error_message_sanitized": None if success else "macro_context_not_refreshed",
        "source_scope": "subject_evidence",
    }]


def provider_runs_from_pages_validation(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    path = docs / "run_status" / run_date / "pages_validation.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    ok = bool(payload.get("ok"))
    return [{
        "provider": "PagesValidator",
        "domain": "publish_bundle",
        "data_type": "publish_bundle",
        "operation": "validate_pages_bundle",
        "success": ok,
        "record_count": int(payload.get("required_files_checked") or 0),
        "error_type": None if ok else "failed",
        "error_message_sanitized": None if ok else "pages_bundle_validation_failed",
        "source_scope": "subject_evidence",
    }]


def attempt_to_provider_run(attempt: Mapping[str, Any], memo: Mapping[str, Any]) -> Dict[str, Any]:
    status = str(attempt.get("status") or "").upper()
    provider = str(attempt.get("source") or attempt.get("provider") or attempt.get("tool") or "unknown")
    domain = normalize_domain(
        attempt.get("domain")
        or attempt.get("data_type")
        or attempt.get("operation")
        or attempt.get("tool")
        or attempt.get("query")
        or memo.get("scope")
        or memo.get("agent")
    )
    success = status in {"OK", "SUCCESS", "REFRESHED", "AVAILABLE"}
    error_type = provider_error_type(status, attempt.get("failure_reason"))
    row = {
        "data_type": domain,
        "domain": domain,
        "provider": provider,
        "operation": str(attempt.get("tool") or attempt.get("query") or "source_attempt"),
        "success": success,
        "record_count": int_or_none(attempt.get("results_count")),
        "error_type": error_type,
        "error_message_sanitized": str(attempt.get("failure_reason") or "") if error_type else None,
    }
    return {key: value for key, value in row.items() if value not in (None, "", [])}


def provider_error_type(status: str, reason: Any) -> str | None:
    reason_text = str(reason or "").lower()
    if status in {"OK", "SUCCESS", "REFRESHED", "AVAILABLE"}:
        return None
    if "429" in reason_text or "rate" in reason_text or "quota" in reason_text:
        return "rate_limited"
    if "auth" in reason_text or "key" in reason_text or "token" in reason_text:
        return "auth_missing"
    if status in {"EMPTY", "NO_DATA"}:
        return "empty"
    if status in {"NOT_SUPPORTED", "UNSUPPORTED", "AVAILABLE_NO_MATCHING_MARKET"}:
        return "not_supported"
    return "failed"


def dedupe_provider_runs(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return dedupe(rows, keys=("trace_id", "provider", "operation", "data_type", "success", "error_type", "record_count"))
