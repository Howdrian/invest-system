# -*- coding: utf-8 -*-
"""CIO-requested read-only evidence enrichment.

The CIO pass may ask for a small number of missing facts after reading the
department memos.  This module is deliberately narrow: it only reads existing
DSA data providers or already-built run artifacts, writes ledgers, and never
changes portfolio/trade state.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from src.source_health.daily_universe import load_daily_universe
from src.source_health.evidence_ledger import has_fact_source, load_evidence_ledger, write_evidence_ledger
from src.source_health.policy import build_source_health_v2
from src.source_health.provider_ledger import load_provider_ledger, write_provider_ledger
from src.source_health.run_matrix import sha256_file, upsert_run_matrix_stage


CIO_ENRICHMENT_SCHEMA = "cio_enrichment_v1"
REQUEST_SCHEMA = "cio_data_requests_v1"
MAX_REQUESTS = 8


def run_cio_enrichment(
    docs_dir: str | Path,
    run_date: str,
    initial_cio_memo: Mapping[str, Any],
    *,
    max_requests: int = MAX_REQUESTS,
    manager: Any = None,
) -> Dict[str, Any]:
    """Run one bounded CIO enrichment pass and update run ledgers."""

    docs = Path(docs_dir)
    out_dir = docs / "run_status" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    existing_facts = load_evidence_ledger(out_dir / "evidence_ledger.jsonl")
    provider_rows = [
        row
        for row in load_provider_ledger(out_dir / "provider_runs.jsonl")
        if not _is_cio_provider_row(row)
    ]
    source_health = _read_json(out_dir / "source_health_v2.json")
    universe = load_daily_universe(docs, run_date)
    requests = build_cio_data_requests(
        initial_cio_memo,
        source_health=source_health,
        universe=universe,
        max_requests=max_requests,
    )
    request_payload = {
        "schema": REQUEST_SCHEMA,
        "runDate": run_date,
        "requested": bool(requests),
        "requests": requests,
    }
    (out_dir / "cio_data_requests.json").write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    added_facts: List[Dict[str, Any]] = []
    run_rows: List[Dict[str, Any]] = []
    mgr = manager
    for request in requests:
        row, facts = _execute_request(docs, run_date, request, existing_facts + added_facts, mgr)
        run_rows.append(row)
        added_facts.extend(facts)
    added_facts = _dedupe_facts(added_facts)
    _write_jsonl(out_dir / "cio_enrichment_runs.jsonl", run_rows)

    merged = _dedupe_facts([*existing_facts, *added_facts])
    if added_facts:
        write_evidence_ledger(out_dir / "evidence_ledger.jsonl", merged)
    current_provider_rows = [row for row in run_rows if row.get("status") != "reused"]
    enriched_provider_rows = _dedupe_provider_rows([*provider_rows, *current_provider_rows])
    write_provider_ledger(out_dir / "provider_runs.jsonl", enriched_provider_rows)
    _rebuild_source_health(docs, run_date, enriched_provider_rows, merged)

    summary = {
        "schema": CIO_ENRICHMENT_SCHEMA,
        "runDate": run_date,
        "requested": bool(requests),
        "requestCount": len(requests),
        "successCount": sum(1 for row in run_rows if row.get("status") == "success"),
        "reusedCount": sum(1 for row in run_rows if row.get("status") == "reused"),
        "failedCount": sum(1 for row in run_rows if row.get("status") == "failed"),
        "addedEvidenceIds": _unique_ids(added_facts),
        "reusedEvidenceIds": _unique_ids_from_values(
            row.get("reused_evidence_ids") for row in run_rows
        ),
        "remainingGaps": _remaining_gaps(requests, run_rows),
        "requestsPath": f"run_status/{run_date}/cio_data_requests.json",
        "runsPath": f"run_status/{run_date}/cio_enrichment_runs.jsonl",
    }
    request_payload.update({"summary": summary})
    (out_dir / "cio_data_requests.json").write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not requests:
        stage_status = "skipped"
    elif summary["failedCount"]:
        stage_status = "partial"
    elif summary["successCount"]:
        stage_status = "success"
    else:
        stage_status = "skipped"
    upsert_run_matrix_stage(
        docs,
        run_date,
        {
            "name": "cio_enrichment",
            "status": stage_status,
            "blocking": False,
            "inputs": [
                f"run_status/{run_date}/evidence_ledger.jsonl",
                f"agent_memos/{run_date}/market/11_cio_report.json",
            ],
            "outputs": [
                f"run_status/{run_date}/cio_data_requests.json",
                f"run_status/{run_date}/cio_enrichment_runs.jsonl",
            ],
            "errorType": None if summary["failedCount"] == 0 else "cio_enrichment_partial",
            "sha256": sha256_file(out_dir / "cio_enrichment_runs.jsonl"),
        },
    )
    return summary


def build_cio_data_requests(
    initial_cio_memo: Mapping[str, Any],
    *,
    source_health: Mapping[str, Any],
    universe: Mapping[str, Any],
    max_requests: int = MAX_REQUESTS,
) -> List[Dict[str, Any]]:
    """Build a bounded, deterministic request list from CIO gaps + health."""

    symbols = [str(item).strip() for item in universe.get("subjectSymbols") or [] if str(item).strip()]
    domains = _missing_domains(initial_cio_memo, source_health)
    requests: List[Dict[str, Any]] = []
    for domain in domains:
        if domain in {"price", "fundamentals", "filings_events"}:
            for symbol in _request_symbols_for_domain(domain, symbols, source_health):
                requests.append(_request(domain, symbol=symbol))
                if len(requests) >= max_requests:
                    break
        elif domain == "macro":
            requests.append(_request("macro", symbol="macro"))
        elif domain == "news_sentiment":
            requests.append(_request("news_sentiment", symbol="market"))
        elif domain == "portfolio":
            requests.append(_request("portfolio", symbol="portfolio"))
        if len(requests) >= max_requests:
            break
    return requests[: max(0, max_requests)]


def _request_symbols_for_domain(
    domain: str, symbols: List[str], source_health: Mapping[str, Any]
) -> List[str]:
    domains = source_health.get("domains") if isinstance(source_health.get("domains"), Mapping) else {}
    payload = domains.get(domain) if isinstance(domains.get(domain), Mapping) else {}
    missing = [str(item).strip() for item in payload.get("missingSubjects") or [] if str(item).strip()]
    if not missing:
        return symbols
    universe_by_key = {symbol.upper(): symbol for symbol in symbols}
    return [universe_by_key.get(symbol.upper(), symbol) for symbol in missing]


def _request(domain: str, *, symbol: str) -> Dict[str, Any]:
    return {
        "id": f"cio-request:{domain}:{symbol}",
        "domain": domain,
        "symbol": symbol,
        "reason": f"CIO requested {domain} evidence for {symbol}",
    }


def _missing_domains(initial_cio_memo: Mapping[str, Any], source_health: Mapping[str, Any]) -> List[str]:
    found: List[str] = []
    claims = ((source_health.get("claimEvidence") or {}).get("claims") or {}) if isinstance(source_health.get("claimEvidence"), Mapping) else {}
    for claim in claims.values():
        if isinstance(claim, Mapping):
            for domain in claim.get("missingDomains") or []:
                _append_unique(found, str(domain))
    domain_payload = source_health.get("domains") if isinstance(source_health.get("domains"), Mapping) else {}
    for domain, payload in domain_payload.items():
        if isinstance(payload, Mapping) and str(payload.get("status") or "") in {"missing", "partial", "degraded"}:
            _append_unique(found, str(domain))
    gap_text = " ".join(str(item) for item in initial_cio_memo.get("data_gaps") or [])
    keyword_domains = {
        "行情": "price",
        "价格": "price",
        "K线": "price",
        "基本面": "fundamentals",
        "估值": "fundamentals",
        "公告": "filings_events",
        "SEC": "filings_events",
        "新闻": "news_sentiment",
        "舆情": "news_sentiment",
        "宏观": "macro",
        "持仓": "portfolio",
        "组合": "portfolio",
    }
    for key, domain in keyword_domains.items():
        if key.lower() in gap_text.lower():
            _append_unique(found, domain)
    return [domain for domain in found if domain in {"price", "fundamentals", "filings_events", "macro", "news_sentiment", "portfolio"}]


def _execute_request(
    docs: Path,
    run_date: str,
    request: Mapping[str, Any],
    known_facts: Iterable[Mapping[str, Any]],
    manager: Any,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    start = time.time()
    domain = str(request.get("domain") or "")
    symbol = str(request.get("symbol") or "")
    existing = _matching_existing_facts(known_facts, domain, symbol)
    if existing:
        row = {
            "provider": "EvidenceLedger",
            "operation": "cio_enrichment",
            "domain": domain,
            "data_type": domain,
            "symbol": symbol,
            "status": "reused",
            "success": False,
            "record_count": 0,
            "reused_record_count": len(existing),
            "reused_evidence_ids": _unique_ids(existing),
            "latency_ms": int((time.time() - start) * 1000),
            "source_scope": "cio_enrichment",
            "request_id": request.get("id"),
        }
        return {key: value for key, value in row.items() if value not in (None, "")}, []
    try:
        facts = _dedupe_facts(_facts_for_request(docs, run_date, domain, symbol, manager))
        existing_ids = {str(row.get("id") or "") for row in known_facts if row.get("id")}
        facts = [row for row in facts if not row.get("id") or str(row.get("id")) not in existing_ids]
        success = bool(facts)
        row = {
            "provider": _provider_for_domain(domain),
            "operation": "cio_enrichment",
            "domain": domain,
            "data_type": domain,
            "symbol": symbol,
            "status": "success" if success else "failed",
            "success": success,
            "record_count": len(facts),
            "latency_ms": int((time.time() - start) * 1000),
            "source_scope": "cio_enrichment",
            "request_id": request.get("id"),
            "error_type": None if success else "empty",
            "error_message_sanitized": "" if success else "no matching read-only evidence",
        }
        return {key: value for key, value in row.items() if value not in (None, "")}, facts
    except Exception as exc:  # noqa: BLE001 - diagnostics only; report must continue
        return {
            "provider": _provider_for_domain(domain),
            "operation": "cio_enrichment",
            "domain": domain,
            "data_type": domain,
            "symbol": symbol,
            "status": "failed",
            "success": False,
            "record_count": 0,
            "latency_ms": int((time.time() - start) * 1000),
            "source_scope": "cio_enrichment",
            "request_id": request.get("id"),
            "error_type": _error_type(exc),
            "error_message_sanitized": str(exc)[:240],
        }, []


def _facts_for_request(
    docs: Path,
    run_date: str,
    domain: str,
    symbol: str,
    manager: Any,
) -> List[Dict[str, Any]]:
    if domain == "filings_events":
        return _facts_from_official_events(docs, run_date, symbol)
    if domain == "portfolio":
        return _portfolio_fact(docs, run_date)
    if manager is None and domain in {"price", "fundamentals", "news_sentiment"}:
        from data_provider import DataFetcherManager

        manager = DataFetcherManager()
    if domain == "price" and manager is not None:
        quote = manager.get_realtime_quote(symbol, log_final_failure=False)
        value = _quote_evidence_value(quote)
        if value:
            return [_cio_fact(run_date, domain, symbol, "DataFetcherManager", value, "derived_fact")]
    if domain == "fundamentals" and manager is not None:
        payload = manager.get_fundamental_context(symbol, budget_seconds=8)
        value = _fundamental_evidence_value(payload)
        if value:
            return [_cio_fact(run_date, domain, symbol, "DataFetcherManager", value, "derived_fact")]
    if domain == "news_sentiment" and manager is not None:
        payload = manager.get_belong_boards(symbol) if symbol not in {"market", ""} else manager.get_hot_stocks(n=10)
        value = _analysis_payload_summary(payload)
        if value:
            return [_cio_fact(run_date, domain, symbol, "DataFetcherManager", f"news_context {value}", "derived_fact")]
    return []


def _facts_from_official_events(docs: Path, run_date: str, symbol: str) -> List[Dict[str, Any]]:
    payload = _read_json(docs / "official_events" / f"{run_date}.json")
    facts = payload.get("evidenceFacts") if isinstance(payload.get("evidenceFacts"), list) else []
    out: List[Dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        fact_symbol = str(fact.get("symbol") or fact.get("subject") or "")
        if symbol not in {"", "market"} and fact_symbol.upper() != symbol.upper():
            continue
        out.append(
            _cio_fact(
                run_date,
                "filings_events",
                symbol or fact_symbol,
                str(fact.get("provider") or "official_events"),
                str(fact.get("value") or fact.get("title") or "official event fact available"),
                str(fact.get("fact_type") or "verified_fact"),
                source_url=str(fact.get("source_url") or fact.get("sourceUrl") or ""),
                raw_path=str(fact.get("raw_path") or fact.get("rawPath") or f"official_events/{run_date}.json"),
            )
        )
        if len(out) >= 2:
            break
    return out


def _portfolio_fact(docs: Path, run_date: str) -> List[Dict[str, Any]]:
    universe = load_daily_universe(docs, run_date)
    groups = universe.get("groups") if isinstance(universe.get("groups"), list) else []
    symbols: List[str] = []
    for group in groups:
        if isinstance(group, Mapping) and str(group.get("name") or "") in {"portfolio", "watchlist"}:
            symbols.extend(str(item) for item in group.get("symbols") or [] if str(item))
    if not symbols:
        return []
    return [_cio_fact(run_date, "portfolio", "portfolio", "DailyUniverse", f"portfolio/watchlist symbols: {', '.join(symbols[:8])}", "derived_fact")]


def _cio_fact(
    run_date: str,
    domain: str,
    symbol: str,
    provider: str,
    value: str,
    fact_type: str,
    *,
    source_url: str = "",
    raw_path: str = "",
) -> Dict[str, Any]:
    return {
        "id": f"cio:{domain}:{symbol}:{provider}:{run_date}",
        "domain": domain,
        "symbol": symbol,
        "subject": symbol,
        "value": value,
        "as_of": run_date,
        "provider": provider,
        "raw_path": raw_path or f"run_status/{run_date}/cio_enrichment_runs.jsonl",
        "source_url": source_url,
        "confidence": "medium" if fact_type != "verified_fact" else "high",
        "fact_type": fact_type,
        "evidence_scope": "subject_evidence",
        "origin": "CIO_REQUESTED",
        "requestedBy": "CIOAgent",
    }


def _matches_domain_symbol(row: Mapping[str, Any], domain: str, symbol: str) -> bool:
    if str(row.get("domain") or "") != domain:
        return False
    if symbol in {"", "market", "macro", "portfolio"}:
        return True
    row_symbol = str(row.get("symbol") or row.get("subject") or "")
    return row_symbol.upper() == symbol.upper()


def _matching_existing_facts(
    rows: Iterable[Mapping[str, Any]], domain: str, symbol: str
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or not _matches_domain_symbol(row, domain, symbol):
            continue
        if str(row.get("evidence_scope") or row.get("evidenceScope") or "subject_evidence") != "subject_evidence":
            continue
        fact_type = str(row.get("fact_type") or row.get("factType") or "").lower()
        if fact_type not in {"verified_fact", "derived_fact"}:
            continue
        if fact_type == "verified_fact" and not has_fact_source(row):
            continue
        out.append(dict(row))
    return _dedupe_facts(out)


def _provider_for_domain(domain: str) -> str:
    return {
        "price": "DataFetcherManager",
        "fundamentals": "DataFetcherManager",
        "filings_events": "official_events",
        "macro": "EvidenceLedger",
        "news_sentiment": "DataFetcherManager",
        "portfolio": "DailyUniverse",
    }.get(domain, "DataFetcherManager")


def _remaining_gaps(requests: Iterable[Mapping[str, Any]], rows: Iterable[Mapping[str, Any]]) -> List[str]:
    success_ids = {
        str(row.get("request_id") or "")
        for row in rows
        if row.get("status") in {"success", "reused"}
    }
    out: List[str] = []
    for request in requests:
        request_id = str(request.get("id") or "")
        if request_id and request_id not in success_ids:
            out.append(f"{request.get('domain')}:{request.get('symbol')}")
    return out


def _rebuild_source_health(docs: Path, run_date: str, provider_rows: List[Dict[str, Any]], evidence_rows: List[Dict[str, Any]]) -> None:
    legacy_health = _read_json(docs / "market_cycle" / run_date / "13_source_health.json")
    if not isinstance(legacy_health, Mapping):
        legacy_health = {}
    source_health = build_source_health_v2(
        legacy_health,
        provider_runs=provider_rows,
        evidence_facts=evidence_rows,
        agent_origin_counts=_agent_origin_counts(docs, run_date),
        subject_symbols=load_daily_universe(docs, run_date).get("subjectSymbols") or [],
    )
    (docs / "run_status" / run_date / "source_health_v2.json").write_text(
        json.dumps(source_health, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _agent_origin_counts(docs: Path, run_date: str) -> Dict[str, int]:
    counts = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    memo_dir = docs / "agent_memos" / run_date
    for path in memo_dir.rglob("*.json"):
        payload = _read_json(path)
        if isinstance(payload, Mapping):
            origin = str(payload.get("origin") or "DERIVED_FROM_ARTIFACT")
            counts[origin] = counts.get(origin, 0) + 1
    return counts


def _dedupe_facts(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(dict(row))
    return out


def _unique_ids(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    return _unique_ids_from_values(row.get("id") for row in rows)


def _unique_ids_from_values(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        items = value if isinstance(value, (list, tuple, set)) else [value]
        for item in items:
            text = str(item or "")
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _dedupe_provider_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = "|".join(str(row.get(item) or "") for item in ("provider", "operation", "domain", "symbol", "request_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def _is_cio_provider_row(row: Mapping[str, Any]) -> bool:
    scope = str(row.get("source_scope") or row.get("sourceScope") or "")
    operation = str(row.get("operation") or "")
    return scope == "cio_enrichment" or operation == "cio_enrichment"


_QUOTE_FIELDS = (
    "price",
    "change_pct",
    "currency",
    "open_price",
    "high",
    "low",
    "pre_close",
    "volume",
    "amount",
    "pe_ratio",
    "pb_ratio",
    "provider_timestamp",
)

_FUNDAMENTAL_FIELDS = {
    "pe",
    "pe_ratio",
    "pb",
    "pb_ratio",
    "ps",
    "ps_ratio",
    "market_cap",
    "total_mv",
    "circ_mv",
    "dividend_yield",
    "dividend_yield_pct",
    "revenue_yoy",
    "net_profit_yoy",
    "roe",
    "gross_margin",
    "report_date",
    "revenue",
    "net_profit",
    "net_profit_parent",
    "operating_cash_flow",
    "eps",
    "currency",
    "ttm_cash_dividend_per_share",
    "ttm_dividend_yield_pct",
    "summary",
}

_METADATA_FIELDS = {
    "status",
    "source",
    "source_chain",
    "coverage",
    "errors",
    "error",
    "provider",
    "duration_ms",
    "latency_ms",
    "market",
    "data_quality",
}


def _quote_evidence_value(quote: Any) -> str:
    price = _payload_field(quote, "price")
    if not _positive_number(price):
        return ""
    parts: List[str] = []
    for field in _QUOTE_FIELDS:
        value = _payload_field(quote, field)
        if _analytic_scalar(value):
            parts.append(f"{field}={_compact_value(value)}")
    return "quote " + " ".join(parts) if parts else ""


def _fundamental_evidence_value(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    parts: List[str] = []

    def collect(value: Any) -> None:
        if len(parts) >= 12 or not isinstance(value, Mapping):
            return
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FUNDAMENTAL_FIELDS and _analytic_scalar(item):
                token = f"{normalized}={_compact_value(item)}"
                if token not in parts:
                    parts.append(token)
            elif isinstance(item, Mapping):
                collect(item)
            if len(parts) >= 12:
                break

    collect(payload)
    return "fundamentals " + " ".join(parts) if parts else ""


def _analysis_payload_summary(payload: Any, *, limit: int = 8) -> str:
    parts: List[str] = []

    def collect(value: Any) -> None:
        if len(parts) >= limit:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower()
                if normalized in _METADATA_FIELDS:
                    continue
                if _analytic_scalar(item):
                    parts.append(f"{normalized}={_compact_value(item)}")
                elif isinstance(item, (Mapping, list, tuple)):
                    collect(item)
                if len(parts) >= limit:
                    break
        elif isinstance(value, (list, tuple)):
            for item in value[:3]:
                collect(item)
                if len(parts) >= limit:
                    break

    collect(payload)
    return " ".join(parts)


def _payload_field(payload: Any, field: str) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(field)
    return getattr(payload, field, None)


def _positive_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _analytic_scalar(value: Any) -> bool:
    if value in (None, "") or isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    text = str(value).strip()
    return bool(text) and text.lower() not in {
        "available",
        "ok",
        "success",
        "partial",
        "refreshed",
        "unknown",
        "not_supported",
        "missing",
        "failed",
    }


def _compact_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()[:160]


def _error_type(exc: Exception) -> str:
    text = str(exc).lower()
    if "permission" in text or "权限" in text:
        return "permission_limited"
    if "auth" in text or "token" in text or "key" in text or "unauthorized" in text:
        return "auth_missing"
    if "429" in text or "quota" in text or "rate" in text:
        return "rate_limited"
    if "not_supported" in text or "unsupported" in text:
        return "not_supported"
    return "failed"


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
