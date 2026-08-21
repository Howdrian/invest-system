"""Bridge the upstream IntelligenceService into the research evidence ledger."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from src.safe_diagnostics import sanitize_diagnostic_text

from .evidence_ledger import write_evidence_ledger
from .provider_ledger import write_provider_ledger
from .temporal import date_part, iso_timestamp, utc_now_iso


SAFE_BOOTSTRAP_TEMPLATES = (
    "sec-company-news",
    "hkex-news",
    "global-marketwatch",
)


def collect_intelligence_evidence(
    docs_dir: str | Path,
    run_date: str,
    *,
    service: Any | None = None,
    bootstrap_safe_sources: bool = True,
    history_days: int = 30,
    max_items: int = 300,
) -> Dict[str, Any]:
    """Fetch enabled upstream intelligence feeds and persist discovery facts.

    Existing source configuration is respected. Safe public templates are only
    bootstrapped when the source table is completely empty.
    """

    if service is None:
        from src.services.intelligence_service import IntelligenceService

        service = IntelligenceService()

    source_snapshot = _list_sources(service)
    bootstrapped: List[str] = []
    bootstrap_errors: List[Dict[str, str]] = []
    if bootstrap_safe_sources and int(source_snapshot.get("total") or 0) == 0:
        for template_id in SAFE_BOOTSTRAP_TEMPLATES:
            try:
                service.create_source_from_template(template_id, {"enabled": True})
                bootstrapped.append(template_id)
            except Exception as exc:
                bootstrap_errors.append({
                    "template": template_id,
                    "error": sanitize_diagnostic_text(exc),
                })
        source_snapshot = _list_sources(service)

    source_map = {
        str(item.get("id")): item
        for item in source_snapshot.get("items") or []
        if isinstance(item, Mapping)
    }
    observed_at = utc_now_iso()
    try:
        fetch_result = service.fetch_enabled_sources()
    except Exception as exc:
        fetch_result = {
            "ok": False,
            "source_count": 0,
            "results": [],
            "error": sanitize_diagnostic_text(exc),
        }

    provider_rows = _provider_rows(fetch_result, source_map, observed_at)
    items = _list_recent_items(service, days=history_days, max_items=max_items)
    evidence_rows = [_item_evidence(item, run_date) for item in items]
    evidence_rows = [row for row in evidence_rows if row]
    comparison = _intelligence_comparison(run_date, evidence_rows)
    if comparison:
        evidence_rows.append(comparison)

    out_dir = Path(docs_dir) / "run_status" / run_date
    provider_path = out_dir / "intelligence_provider_runs.jsonl"
    evidence_path = out_dir / "intelligence_evidence.jsonl"
    write_provider_ledger(provider_path, provider_rows)
    write_evidence_ledger(evidence_path, evidence_rows)
    summary = {
        "schema": "intelligence_evidence_collection_v1",
        "runDate": run_date,
        "safeTemplates": list(SAFE_BOOTSTRAP_TEMPLATES),
        "bootstrapped": bootstrapped,
        "bootstrapErrors": bootstrap_errors,
        "configuredSources": int(source_snapshot.get("total") or 0),
        "enabledSourcesFetched": int(fetch_result.get("source_count") or 0),
        "providerRuns": len(provider_rows),
        "items": len(items),
        "evidenceFacts": len(evidence_rows),
        "providerLedger": f"run_status/{run_date}/intelligence_provider_runs.jsonl",
        "evidenceLedger": f"run_status/{run_date}/intelligence_evidence.jsonl",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "intelligence_evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def load_intelligence_provider_runs(docs_dir: str | Path, run_date: str) -> List[Dict[str, Any]]:
    return _read_jsonl(Path(docs_dir) / "run_status" / run_date / "intelligence_provider_runs.jsonl")


def load_intelligence_evidence_facts(docs_dir: str | Path, run_date: str) -> List[Dict[str, Any]]:
    return _read_jsonl(Path(docs_dir) / "run_status" / run_date / "intelligence_evidence.jsonl")


def _list_sources(service: Any) -> Dict[str, Any]:
    payload = service.list_sources(page=1, page_size=100)
    return dict(payload) if isinstance(payload, Mapping) else {"items": [], "total": 0}


def _list_recent_items(service: Any, *, days: int, max_items: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page = 1
    while len(rows) < max_items:
        payload = service.list_items(days=days, page=page, page_size=min(100, max_items - len(rows)))
        items = payload.get("items") if isinstance(payload, Mapping) else []
        current = [dict(item) for item in items or [] if isinstance(item, Mapping)]
        rows.extend(current)
        total = int(payload.get("total") or 0) if isinstance(payload, Mapping) else len(rows)
        if not current or len(rows) >= total:
            break
        page += 1
    return rows[:max_items]


def _provider_rows(fetch_result: Mapping[str, Any], source_map: Mapping[str, Mapping[str, Any]], observed_at: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in fetch_result.get("results") or []:
        if not isinstance(item, Mapping):
            continue
        source = source_map.get(str(item.get("source_id"))) or {}
        success = bool(item.get("ok"))
        record_count = int(item.get("fetched_count") or 0)
        error = sanitize_diagnostic_text(item.get("error") or "")
        rows.append({
            "provider": str(source.get("name") or f"IntelligenceSource:{item.get('source_id')}"),
            "operation": "intelligence_feed_fetch",
            "data_type": "news_sentiment",
            "domain": "news_sentiment",
            "symbol": str(source.get("scope_value") or "market"),
            "success": success,
            "record_count": record_count,
            "error_type": None if success else _error_type(error),
            "error_message_sanitized": "" if success else error or "feed fetch failed",
            "source_scope": "subject_evidence",
            "observed_at": observed_at,
        })
    if not rows and not fetch_result.get("ok"):
        error = sanitize_diagnostic_text(fetch_result.get("error") or "intelligence fetch failed")
        rows.append({
            "provider": "IntelligenceService",
            "operation": "intelligence_feed_fetch",
            "data_type": "news_sentiment",
            "domain": "news_sentiment",
            "symbol": "market",
            "success": False,
            "record_count": 0,
            "error_type": _error_type(error),
            "error_message_sanitized": error,
            "source_scope": "subject_evidence",
            "observed_at": observed_at,
        })
    return rows


def _item_evidence(item: Mapping[str, Any], run_date: str) -> Dict[str, Any] | None:
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title and not url:
        return None
    published_at = iso_timestamp(item.get("published_at"))
    # IntelligenceService persists ``datetime.now()`` as a naive local DB
    # timestamp.  Treating it as UTC shifts fetch time several hours into the
    # future on non-UTC hosts.  Feed publication timestamps remain UTC-aware or
    # UTC-naive and are normalized separately above.
    local_timezone = datetime.now().astimezone().tzinfo
    fetched_at = iso_timestamp(item.get("fetched_at"), naive_timezone=local_timezone)
    item_id = str(item.get("id") or hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()[:20])
    subject = str(item.get("scope_value") or "").strip()
    if subject in {"", "__NULL_SCOPE__"}:
        subject = "market"
    summary = str(item.get("summary") or "").strip()
    return {
        "id": f"intelligence:{item_id}",
        "domain": "news_sentiment",
        "symbol": subject,
        "subject": subject,
        "value": title if not summary else f"{title} — {summary[:500]}",
        "as_of": date_part(published_at or fetched_at, run_date),
        "event_time": published_at,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "provider": str(item.get("source_name") or item.get("source") or "IntelligenceService"),
        "source_url": url if url.startswith(("http://", "https://")) else "",
        "raw_path": f"run_status/{run_date}/intelligence_evidence.jsonl",
        "confidence": "low",
        "fact_type": "discovery",
        "evidence_scope": "subject_evidence",
        "market": str(item.get("market") or "global"),
    }


def _intelligence_comparison(run_date: str, facts: List[Mapping[str, Any]]) -> Dict[str, Any] | None:
    end = datetime.fromisoformat(f"{run_date}T23:59:59+00:00")
    counts = {"24h": 0, "7d": 0, "30d": 0}
    sources: set[str] = set()
    newest = ""
    for fact in facts:
        stamp = iso_timestamp(fact.get("published_at") or fact.get("fetched_at"))
        if not stamp:
            continue
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (end - parsed.astimezone(timezone.utc)).total_seconds()
        if 0 <= age <= 24 * 3600:
            counts["24h"] += 1
        if 0 <= age <= 7 * 24 * 3600:
            counts["7d"] += 1
        if 0 <= age <= 30 * 24 * 3600:
            counts["30d"] += 1
        sources.add(str(fact.get("provider") or "IntelligenceService"))
        newest = max(newest, stamp)
    if not facts:
        return None
    return {
        "id": f"intelligence:history_comparison:{run_date}",
        "domain": "news_sentiment",
        "subject": "market",
        "metric": "intelligence_recency_comparison",
        "value": (
            f"items_24h={counts['24h']} items_7d={counts['7d']} "
            f"items_30d={counts['30d']} source_count={len(sources)}"
        ),
        "as_of": date_part(newest, run_date),
        "event_time": newest,
        "fetched_at": max((str(fact.get("fetched_at") or "") for fact in facts), default=""),
        "provider": "IntelligenceService",
        "raw_path": f"run_status/{run_date}/intelligence_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _error_type(text: str) -> str:
    lower = text.lower()
    if "429" in lower or "rate" in lower or "quota" in lower:
        return "rate_limited"
    if "auth" in lower or "401" in lower or "403" in lower:
        return "auth_missing"
    if "not supported" in lower or "unsupported" in lower:
        return "not_supported"
    if "empty" in lower:
        return "empty"
    return "failed"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows
