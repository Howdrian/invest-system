"""Evidence ledger builders for daily source-health snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .daily_common import (
    as_list,
    dedupe,
    domain_from_path,
    int_or_none,
    normalize_domain,
    official_events_payloads,
    read_json,
)


def evidence_from_official_events(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for payload in official_events_payloads(docs, run_date):
        scope = str(payload.get("sourceScope") or "subject_evidence")
        for item in as_list(payload.get("evidenceFacts")):
            if isinstance(item, Mapping):
                rows.append({**dict(item), "evidence_scope": str(item.get("evidence_scope") or scope)})
    return rows


def evidence_from_agent_memos(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    """Agent memo references are citations, not independent evidence facts."""

    return []


def evidence_from_market_cycle(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    base = docs / "market_cycle" / run_date
    if not base.exists():
        return facts
    for path in sorted(base.glob("*.json")):
        payload = read_json(path)
        if not isinstance(payload, Mapping):
            continue
        rel = path.relative_to(docs).as_posix()
        domain = domain_from_path(path.name)
        refs = as_list(payload.get("evidence_refs"))
        for idx, ref in enumerate(refs or [path.stem]):
            facts.append({
                "id": f"market_cycle:{path.stem}:{idx}",
                "domain": domain,
                "value": str(ref),
                "as_of": run_date,
                "provider": "market_cycle",
                "raw_path": rel,
                "confidence": "medium",
                "fact_type": "derived_fact",
            })
    return facts


def evidence_from_macro_context(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    """Convert refreshed official macro cache into verified macro facts."""
    payload = read_json(docs.parent / "data" / "macro_cache" / "macro_context_latest.json")
    if not isinstance(payload, Mapping):
        return []
    components = payload.get("components") if isinstance(payload.get("components"), Mapping) else {}
    fred = components.get("fred") if isinstance(components.get("fred"), Mapping) else {}
    rows: List[Dict[str, Any]] = []
    for item in as_list(fred.get("series")):
        if not isinstance(item, Mapping):
            continue
        series_id = str(item.get("series_id") or "").strip()
        if not series_id:
            continue
        date = str(item.get("date") or run_date)
        fetched_at = str(item.get("fetched_at") or payload.get("as_of") or payload.get("fetched_at") or "")
        history = item.get("history") if isinstance(item.get("history"), list) else []
        rows.append({
            "id": f"fred:{series_id}:{date}",
            "domain": "macro",
            "symbol": series_id,
            "value": f"{series_id}={item.get('value')} @ {date}",
            "as_of": date,
            "event_time": date,
            "fetched_at": fetched_at,
            "provider": "FRED",
            "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
            "confidence": "high",
            "fact_type": "verified_fact",
            "fact_subtype": str(item.get("factor") or "macro"),
            "metric": series_id,
            "history": history,
            "evidence_scope": "subject_evidence",
        })
        comparison = _macro_history_comparison(series_id, history)
        if comparison:
            rows.append({
                "id": f"fred:{series_id}:history_comparison:{date}",
                "domain": "macro",
                "symbol": series_id,
                "metric": f"{series_id}_history_comparison",
                "value": " ".join(f"{key}={value}" for key, value in comparison.items()),
                "comparison": comparison,
                "as_of": date,
                "event_time": date,
                "fetched_at": fetched_at,
                "provider": "FRED",
                "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
                "confidence": "medium",
                "fact_type": "derived_fact",
                "fact_subtype": str(item.get("factor") or "macro"),
                "evidence_scope": "subject_evidence",
            })
    return rows


def _macro_history_comparison(series_id: str, history: List[Any]) -> Dict[str, Any]:
    numeric: List[float] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        try:
            numeric.append(float(item.get("value")))
        except (TypeError, ValueError):
            continue
    if len(numeric) < 2:
        return {}
    latest = numeric[0]
    comparison: Dict[str, Any] = {
        "latest": round(latest, 4),
        "delta_prev_observation": round(latest - numeric[1], 4),
        "history_observations": len(numeric),
    }
    if len(numeric) >= 13:
        comparison["delta_12_observations"] = round(latest - numeric[12], 4)
    if len(numeric) >= 10:
        less_or_equal = sum(1 for value in numeric if value <= latest)
        comparison["history_percentile_pct"] = round(less_or_equal / len(numeric) * 100, 1)
    comparison["series"] = series_id
    return comparison


def evidence_from_pages_validation(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    payload = read_json(docs / "run_status" / run_date / "pages_validation.json")
    if not isinstance(payload, Mapping) or not payload.get("ok"):
        return []
    return [{
        "id": f"pages_bundle:{run_date}:validation",
        "domain": "publish_bundle",
        "value": (
            f"required={payload.get('required_files_checked')} "
            f"links={payload.get('links_checked')} legacy={len(as_list(payload.get('legacy_public_files')))}"
        ),
        "as_of": run_date,
        "provider": "PagesValidator",
        "raw_path": f"run_status/{run_date}/pages_validation.json",
        "confidence": "high",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }]


def evidence_from_successful_provider_runs(
    provider_rows: Iterable[Mapping[str, Any]],
    *,
    run_date: str,
    docs_relative_provider_ledger: str,
) -> List[Dict[str, Any]]:
    """Convert successful subject provider reads into derived evidence.

    Provider runs are not ``verified_fact``. They only prove that the current
    subject/run had usable data available for a domain, so they become
    ``derived_fact`` with a raw path back to the provider ledger.
    """

    facts: List[Dict[str, Any]] = []
    for row in provider_rows:
        if not isinstance(row, Mapping):
            continue
        success = bool(row.get("success"))
        status = str(row.get("status") or "").lower()
        if not success and status != "success":
            continue
        domain = normalize_domain(row.get("domain") or row.get("data_type") or row.get("operation"))
        if domain not in {"price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"}:
            continue
        scope = str(row.get("source_scope") or row.get("sourceScope") or "subject_evidence")
        provider = str(row.get("provider") or "provider")
        operation = str(row.get("operation") or row.get("data_type") or "provider_run")
        record_count = int_or_none(row.get("record_count") or row.get("recordCount"))
        if record_count is not None and record_count <= 0:
            continue
        facts.append(
            {
                "id": f"provider_run:{scope}:{provider}:{operation}:{domain}",
                "domain": domain,
                "symbol": str(row.get("symbol") or row.get("symbols") or ""),
                "value": (
                    f"{provider}/{operation} returned "
                    f"{record_count if record_count is not None else 'usable'} records"
                ),
                "as_of": run_date,
                "fetched_at": row.get("observed_at") or row.get("observedAt"),
                "provider": provider,
                "raw_path": docs_relative_provider_ledger,
                "confidence": "medium",
                "fact_type": "derived_fact",
                "evidence_scope": scope,
            }
        )
    return facts


def dedupe_evidence_facts(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return dedupe(rows, keys=("id",))
