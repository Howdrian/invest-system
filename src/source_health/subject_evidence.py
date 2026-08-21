"""Collect subject evidence from the upstream data-provider stack."""

from __future__ import annotations

import json
import math
import signal
import statistics
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .daily_universe import load_daily_universe
from .provider_ledger import write_provider_ledger
from .evidence_ledger import write_evidence_ledger
from .temporal import date_part, first_timestamp, utc_now_iso
from src.safe_diagnostics import sanitize_diagnostic_text

if TYPE_CHECKING:
    from data_provider import DataFetcherManager


QUOTE_SOURCE_TO_PROVIDER = {
    "efinance": "EfinanceFetcher",
    "tencent": "TencentFetcher",
    "akshare_em": "AkshareFetcher",
    "akshare_sina": "AkshareFetcher",
    "akshare_qq": "AkshareFetcher",
    "tushare": "TushareFetcher",
    "tickflow": "TickFlowFetcher",
    "yfinance": "YfinanceFetcher",
    "longbridge": "LongbridgeFetcher",
    "fallback": "DataFetcherManager",
}


def collect_subject_evidence(
    docs_dir: str | Path,
    run_date: str,
    *,
    symbols: Iterable[str] | None = None,
    market: str | None = None,
    max_symbols: int | None = None,
    market_only: bool = False,
    manager: DataFetcherManager | None = None,
) -> Dict[str, Any]:
    """Collect current-run provider/evidence rows for the daily universe."""

    docs = Path(docs_dir)
    universe = load_daily_universe(docs, run_date)
    all_subject_symbols = list(symbols or universe.get("subjectSymbols") or [])
    subject_symbols = list(all_subject_symbols)
    if max_symbols is not None and max_symbols >= 0:
        subject_symbols = subject_symbols[:max_symbols]
    region = market or str(universe.get("market") or "cn")
    if manager is None:
        from data_provider import DataFetcherManager

        mgr = DataFetcherManager()
    else:
        mgr = manager

    refreshed_operations = {"main_indices"} if market_only else {
        "main_indices", "market_stats", "sector_rankings", "concept_rankings", "hot_stocks"
    }
    if market_only:
        provider_rows = [
            row for row in load_subject_provider_runs(docs, run_date)
            if str(row.get("operation") or "") not in refreshed_operations
        ]
        evidence_rows = [
            row for row in load_subject_evidence_facts(docs, run_date)
            if str(row.get("metric") or "") not in refreshed_operations
        ]
    else:
        provider_rows = []
        evidence_rows = []

    market_regions = _market_regions(region, all_subject_symbols)
    for market_region in market_regions:
        provider_rows.extend(_collect_market_scope(
            mgr,
            run_date,
            market_region,
            evidence_rows,
            indices_only=market_only,
        ))
    if not market_only:
        for symbol in subject_symbols:
            provider_rows.extend(_collect_symbol_scope(mgr, run_date, str(symbol), evidence_rows))
        universe_comparison = _universe_price_comparison_evidence(run_date, evidence_rows)
        if universe_comparison:
            evidence_rows.append(universe_comparison)
        sector_history = _sector_history_evidence(docs, run_date, evidence_rows)
        if sector_history:
            evidence_rows.append(sector_history)
        market_stats_history = _market_stats_history_evidence(docs, run_date, evidence_rows)
        if market_stats_history:
            evidence_rows.append(market_stats_history)
        evidence_rows.extend(_valuation_history_evidence(docs, run_date, evidence_rows))

    out_dir = docs / "run_status" / run_date
    provider_path = out_dir / "subject_provider_runs.jsonl"
    evidence_path = out_dir / "subject_evidence.jsonl"
    write_provider_ledger(provider_path, provider_rows)
    write_evidence_ledger(evidence_path, evidence_rows)
    summary = {
        "schema": "subject_evidence_collection_v1",
        "runDate": run_date,
        "market": region,
        "marketRegions": market_regions,
        "marketOnly": market_only,
        "symbols": subject_symbols,
        "providerRuns": len(provider_rows),
        "evidenceFacts": len(evidence_rows),
        "providerLedger": f"run_status/{run_date}/subject_provider_runs.jsonl",
        "evidenceLedger": f"run_status/{run_date}/subject_evidence.jsonl",
    }
    (out_dir / "subject_evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def load_subject_provider_runs(docs_dir: str | Path, run_date: str) -> List[Dict[str, Any]]:
    return _read_jsonl(Path(docs_dir) / "run_status" / run_date / "subject_provider_runs.jsonl")


def load_subject_evidence_facts(docs_dir: str | Path, run_date: str) -> List[Dict[str, Any]]:
    return _read_jsonl(Path(docs_dir) / "run_status" / run_date / "subject_evidence.jsonl")


def _collect_symbol_scope(
    mgr: DataFetcherManager,
    run_date: str,
    symbol: str,
    evidence_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    quote, quote_run = _timed_call(
        "realtime_quote",
        lambda: mgr.get_realtime_quote(symbol, log_final_failure=False),
        timeout_seconds=20,
    )
    rows.append(_provider_row_from_quote(symbol, quote, quote_run))
    if quote is not None:
        evidence_rows.append(_quote_evidence(symbol, run_date, quote))

    daily, daily_run = _timed_call(
        "daily_data",
        lambda: mgr.get_daily_data(symbol, days=260),
        timeout_seconds=30,
    )
    rows.append(_provider_row_from_daily(symbol, daily, daily_run))
    daily_df = daily[0] if isinstance(daily, tuple) and daily else None
    daily_source = daily[1] if isinstance(daily, tuple) and len(daily) > 1 else ""
    if _row_count(daily_df) > 0:
        evidence_rows.append(
            _dataframe_evidence(
                symbol,
                run_date,
                "price",
                _provider_name(daily_source),
                "daily_data",
                daily_df,
                fetched_at=str(daily_run.get("observed_at") or ""),
            )
        )
        evidence_rows.extend(
            _price_comparison_evidence(
                symbol,
                run_date,
                _provider_name(daily_source),
                daily_df,
                fetched_at=str(daily_run.get("observed_at") or ""),
            )
        )

    fundamental_budget = _fundamental_budget_seconds(symbol)
    fundamental, fund_run = _timed_call(
        "fundamental_context",
        lambda: mgr.get_fundamental_context(symbol, budget_seconds=fundamental_budget),
        timeout_seconds=fundamental_budget + 5,
    )
    rows.extend(_provider_rows_from_context(symbol, "fundamentals", "fundamental_context", fundamental, fund_run))
    fundamental_facts = _fundamental_evidence(
        symbol,
        run_date,
        fundamental,
        fetched_at=str(fund_run.get("observed_at") or ""),
    )
    evidence_rows.extend(fundamental_facts)
    fundamental_metrics = {str(item.get("metric") or "") for item in fundamental_facts}
    has_valuation_ratios = _has_valuation_ratios(fundamental_facts)
    needs_cn_supplement = _is_cn_equity_symbol(symbol) and (
        "fundamental_growth" not in fundamental_metrics or not has_valuation_ratios
    )
    needs_offshore_supplement = _is_offshore_equity_symbol(symbol) and (
        "fundamental_growth" not in fundamental_metrics or not has_valuation_ratios
    )
    if needs_cn_supplement:
        fallback, fallback_run = _timed_call(
            "fundamental_context_akshare_core",
            lambda: _akshare_cn_fundamental_context(symbol),
            timeout_seconds=15,
        )
        fallback_facts = _fundamental_evidence(
            symbol,
            run_date,
            fallback,
            provider="AkshareFundamentalAdapter",
            fetched_at=str(fallback_run.get("observed_at") or ""),
        )
        rows.append(
            _provider_row(
                symbol,
                "AkshareFundamentalAdapter",
                "fundamentals",
                "fundamental_context_akshare_core",
                fallback_run,
                record_count=len(fallback_facts),
            )
        )
        evidence_rows.extend(_merge_fundamental_facts(fundamental_facts, fallback_facts))
    elif needs_offshore_supplement:
        fallback, fallback_run = _timed_call(
            "fundamental_context_yfinance_public",
            lambda: _yfinance_public_fundamental_context(symbol),
            timeout_seconds=35,
        )
        fallback_facts = _fundamental_evidence(
            symbol,
            run_date,
            fallback,
            provider="YfinanceFundamentalAdapter",
            fetched_at=str(fallback_run.get("observed_at") or ""),
        )
        rows.append(
            _provider_row(
                symbol,
                "YfinanceFundamentalAdapter",
                "fundamentals",
                "fundamental_context_yfinance_public",
                fallback_run,
                record_count=len(fallback_facts),
            )
        )
        evidence_rows.extend(_merge_fundamental_facts(fundamental_facts, fallback_facts))

    capital, capital_run = _timed_call(
        "capital_flow",
        lambda: mgr.get_capital_flow_context(symbol, budget_seconds=4),
        timeout_seconds=8,
    )
    rows.extend(_provider_rows_from_context(symbol, "news_sentiment", "capital_flow", capital, capital_run))
    if _context_success(capital):
        evidence_rows.append(
            _context_evidence(
                symbol,
                run_date,
                "news_sentiment",
                "DataFetcherManager",
                "capital_flow",
                capital,
                fetched_at=str(capital_run.get("observed_at") or ""),
            )
        )

    boards, boards_run = _timed_call(
        "belong_boards",
        lambda: mgr.get_belong_boards(symbol),
        timeout_seconds=15,
    )
    rows.append(_provider_row(symbol, "DataFetcherManager", "news_sentiment", "belong_boards", boards_run, record_count=len(boards) if isinstance(boards, list) else None))
    if isinstance(boards, list) and boards:
        evidence_rows.append(
            _context_evidence(
                symbol,
                run_date,
                "news_sentiment",
                "DataFetcherManager",
                "belong_boards",
                {"boards": boards[:10]},
                fetched_at=str(boards_run.get("observed_at") or ""),
            )
        )
    return rows


def _collect_market_scope(
    mgr: DataFetcherManager,
    run_date: str,
    market: str,
    evidence_rows: List[Dict[str, Any]],
    *,
    indices_only: bool = False,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    market = str(market or "cn").lower()
    operations: List[Tuple[str, str, Callable[[], Any]]] = [
        ("main_indices", "price", lambda: mgr.get_main_indices(market)),
    ]
    if market == "cn" and not indices_only:
        operations.extend([
            ("market_stats", "price", lambda: mgr.get_market_stats(purpose="daily_universe")),
            ("sector_rankings", "news_sentiment", lambda: mgr.get_sector_rankings(n=8)),
            ("concept_rankings", "news_sentiment", lambda: mgr.get_concept_rankings(n=8)),
            ("hot_stocks", "news_sentiment", lambda: mgr.get_hot_stocks(n=10)),
        ])
    subject = "market" if market == "cn" else f"market_{market}"
    for operation, domain, fn in operations:
        timeout_seconds = 60 if operation == "market_stats" else 30
        payload, run = _timed_call(operation, fn, timeout_seconds=timeout_seconds)
        count = _market_record_count(payload)
        rows.append(_provider_row(subject, "DataFetcherManager", domain, operation, run, record_count=count))
        if count > 0:
            measurements = _market_measurements(operation, payload)
            fact = {
                    "id": f"subject:{subject}:{operation}:{run_date}",
                    "domain": domain,
                    "subject": subject,
                    "market": market,
                    "metric": operation,
                    "value": _market_evidence_value(operation, payload, count, measurements=measurements),
                    "measurements": measurements,
                    "as_of": _market_snapshot_date(
                        market,
                        run_date,
                        str(run.get("observed_at") or ""),
                        source_date=_market_payload_date(payload),
                    ),
                    "fetched_at": run.get("observed_at"),
                    "provider": "DataFetcherManager",
                    "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
                    "confidence": "medium",
                    "fact_type": "derived_fact",
                    "evidence_scope": "subject_evidence",
                }
            samples = _market_sample_records(payload)
            if samples:
                fact["records"] = samples
            evidence_rows.append(fact)
    return rows


def _market_regions(primary: str, symbols: Iterable[str]) -> List[str]:
    """Return ordered market scopes required by the actual daily universe."""

    from src.core.trading_calendar import get_market_for_stock

    ordered: List[str] = []
    for candidate in [str(primary or "cn").lower(), *(get_market_for_stock(str(symbol)) for symbol in symbols)]:
        if candidate in {"cn", "hk", "us", "jp", "kr", "tw"} and candidate not in ordered:
            ordered.append(candidate)
    return ordered or ["cn"]


def _market_snapshot_date(
    market: str,
    run_date: str,
    observed_at: str,
    *,
    source_date: str = "",
) -> str:
    """Prefer the provider's bar date and never relabel current data as a backtest date."""

    from datetime import datetime

    normalized_source_date = date_part(source_date, "")
    if normalized_source_date:
        return normalized_source_date
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        from zoneinfo import ZoneInfo

        zones = {
            "cn": "Asia/Shanghai",
            "hk": "Asia/Hong_Kong",
            "us": "America/New_York",
            "jp": "Asia/Tokyo",
            "kr": "Asia/Seoul",
            "tw": "Asia/Taipei",
        }
        local = observed.astimezone(ZoneInfo(zones.get(market, "UTC")))
        effective = local.date()
        if local.hour < 9:
            from datetime import timedelta

            effective -= timedelta(days=1)
            while effective.weekday() >= 5:
                effective -= timedelta(days=1)
        return effective.isoformat()
    except (KeyError, TypeError, ValueError):
        return run_date


def _market_payload_date(payload: Any) -> str:
    """Extract the newest explicit exchange date from provider rows, if present."""

    timestamps = [
        first_timestamp(row, "trade_date", "date", "日期", "datetime", "timestamp")
        for row in _records(payload)
    ]
    dates = [date_part(value, "") for value in timestamps if value]
    return max((value for value in dates if value), default="")


def _timed_call(
    operation: str,
    fn: Callable[[], Any],
    *,
    timeout_seconds: float | None = None,
) -> Tuple[Any, Dict[str, Any]]:
    start = time.time()
    old_handler: Any = None
    armed = bool(
        timeout_seconds
        and threading.current_thread() is threading.main_thread()
        and hasattr(signal, "SIGALRM")
        and hasattr(signal, "setitimer")
    )

    def _raise_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"{operation} timed out after {timeout_seconds:g}s")

    try:
        if armed:
            old_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, _raise_timeout)
            signal.setitimer(signal.ITIMER_REAL, float(timeout_seconds))
        payload = fn()
        return payload, {
            "operation": operation,
            "success": True,
            "latency_ms": int((time.time() - start) * 1000),
            "observed_at": utc_now_iso(),
        }
    except Exception as exc:
        return None, {
            "operation": operation,
            "success": False,
            "latency_ms": int((time.time() - start) * 1000),
            "observed_at": utc_now_iso(),
            "error_type": _error_type(exc),
            "error_message_sanitized": sanitize_diagnostic_text(exc),
        }
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)


def _provider_row_from_quote(symbol: str, quote: Any, run: Mapping[str, Any]) -> Dict[str, Any]:
    provider = "DataFetcherManager"
    if quote is not None:
        raw_source = getattr(getattr(quote, "source", ""), "value", getattr(quote, "source", ""))
        provider = QUOTE_SOURCE_TO_PROVIDER.get(str(raw_source), str(raw_source) or provider)
    return _provider_row(symbol, provider, "price", "realtime_quote", run, record_count=1 if quote is not None else 0)


def _provider_row_from_daily(symbol: str, daily: Any, run: Mapping[str, Any]) -> Dict[str, Any]:
    provider = "DataFetcherManager"
    record_count = 0
    if isinstance(daily, tuple) and daily:
        record_count = _row_count(daily[0])
        provider = _provider_name(daily[1] if len(daily) > 1 else "")
    return _provider_row(symbol, provider, "price", "daily_data", run, record_count=record_count)


def _provider_rows_from_context(symbol: str, domain: str, operation: str, payload: Any, run: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [_provider_row(symbol, "DataFetcherManager", domain, operation, run, record_count=0)]
    rows: List[Dict[str, Any]] = []
    source_chain = payload.get("source_chain") if isinstance(payload.get("source_chain"), list) else []
    if source_chain:
        for item in source_chain:
            if not isinstance(item, Mapping):
                continue
            provider = _provider_name(item.get("provider") or operation)
            result = str(item.get("result") or payload.get("status") or "")
            success = result.lower() in {"ok", "success", "partial", "available", "refreshed"}
            sanitized_result = sanitize_diagnostic_text(result)
            rows.append(
                {
                    "provider": provider,
                    "operation": operation,
                    "data_type": domain,
                    "domain": domain,
                    "symbol": symbol,
                    "success": success,
                    "record_count": 1 if success else 0,
                    "latency_ms": item.get("duration_ms") or run.get("latency_ms"),
                    "observed_at": run.get("observed_at"),
                    "error_type": None if success else _error_type_text(sanitized_result),
                    "error_message_sanitized": "" if success else sanitized_result,
                    "source_scope": "subject_evidence",
                }
            )
    else:
        rows.append(_provider_row(symbol, "DataFetcherManager", domain, operation, run, record_count=1 if _context_success(payload) else 0))
    return rows


def _provider_row(symbol: str, provider: str, domain: str, operation: str, run: Mapping[str, Any], *, record_count: int | None = None) -> Dict[str, Any]:
    success = bool(run.get("success")) and (record_count is None or record_count > 0)
    row = {
        "provider": provider,
        "operation": operation,
        "data_type": domain,
        "domain": domain,
        "symbol": symbol,
        "success": success,
        "record_count": record_count,
        "latency_ms": run.get("latency_ms"),
        "observed_at": run.get("observed_at"),
        "error_type": None if success else run.get("error_type") or "empty",
        "error_message_sanitized": "" if success else run.get("error_message_sanitized") or "empty result",
        "source_scope": "subject_evidence",
    }
    return {key: value for key, value in row.items() if value not in (None, "")}


def _quote_evidence(symbol: str, run_date: str, quote: Any) -> Dict[str, Any]:
    from datetime import datetime

    from src.core.trading_calendar import build_market_phase_context, get_market_for_stock

    provider = QUOTE_SOURCE_TO_PROVIDER.get(str(getattr(getattr(quote, "source", ""), "value", "")), "DataFetcherManager")
    price = getattr(quote, "price", None)
    change_pct = getattr(quote, "change_pct", None)
    fetched_at = first_timestamp(quote, "fetched_at")
    event_time = first_timestamp(quote, "provider_timestamp")
    phase_time = None
    try:
        phase_time = datetime.fromisoformat(str(event_time or fetched_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        pass
    phase = build_market_phase_context(
        market=get_market_for_stock(symbol),
        current_time=phase_time,
        trigger_source="subject_evidence",
    )
    return {
        "id": f"subject:{symbol}:quote:{run_date}",
        "domain": "price",
        "symbol": symbol,
        "subject": symbol,
        "metric": "realtime_quote",
        "measurements": {"price": price, "change_pct": change_pct},
        "value": f"quote session={phase.phase.value} price={price} change_pct={change_pct}",
        "as_of": date_part(event_time or fetched_at, run_date),
        "event_time": event_time,
        "fetched_at": fetched_at,
        "market": phase.market,
        "session_phase": phase.phase.value,
        "is_partial_bar": phase.is_partial_bar,
        "provider": provider,
        "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _dataframe_evidence(
    symbol: str,
    run_date: str,
    domain: str,
    provider: str,
    operation: str,
    payload: Any,
    *,
    fetched_at: str = "",
) -> Dict[str, Any]:
    rows = _records(payload)
    count = len(rows)
    value = _price_series_summary(rows, operation=operation)
    event_time = _latest_row_date(rows)
    return {
        "id": f"subject:{symbol}:{operation}:{run_date}",
        "domain": domain,
        "symbol": symbol,
        "subject": symbol,
        "value": value or f"{operation} returned {count} rows",
        "as_of": date_part(event_time, run_date),
        "event_time": event_time,
        "fetched_at": fetched_at,
        "provider": provider,
        "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _fundamental_evidence(
    symbol: str,
    run_date: str,
    payload: Any,
    *,
    provider: str = "DataFetcherManager",
    fetched_at: str = "",
) -> List[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    facts: List[Dict[str, Any]] = []
    report_date, comparison_period = _fundamental_periods(payload)
    for block in ("valuation", "growth", "earnings", "institution"):
        item = payload.get(block) if isinstance(payload.get(block), Mapping) else {}
        status = str(item.get("status") or "").lower()
        data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
        if status in {"ok", "success", "partial", "available"} and data:
            summary_data = dict(data)
            summary_data.pop("financial_history", None)
            measurements = _fundamental_measurements(block, summary_data)
            as_of = (
                str(data.get("as_of") or "")
                if block == "valuation"
                else report_date
            ) or date_part(fetched_at, run_date)
            fact = {
                    "id": f"subject:{symbol}:fundamental:{block}:{run_date}",
                    "domain": "fundamentals",
                    "symbol": symbol,
                    "subject": symbol,
                    "metric": f"fundamental_{block}",
                    "value": f"{block} available: {_mapping_summary(summary_data, limit=6)}",
                    "measurements": measurements,
                    "as_of": as_of,
                    "fetched_at": fetched_at,
                    "provider": provider,
                    "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
                    "confidence": "medium",
                    "fact_type": "derived_fact",
                    "evidence_scope": "subject_evidence",
                }
            currency = str(data.get("currency") or payload.get("currency") or "").strip().upper()
            if currency:
                fact["currency"] = currency
            if block != "valuation":
                fact["report_period"] = str(data.get("report_date") or report_date or "")
                fact["comparison_period"] = str(data.get("comparison_period") or comparison_period or "")
            facts.append(fact)
    history_fact = _fundamental_history_comparison_evidence(
        symbol,
        run_date,
        payload,
        provider=provider,
        fetched_at=fetched_at,
    )
    if history_fact:
        facts.append(history_fact)
    return facts


def _has_valuation_ratios(facts: Iterable[Mapping[str, Any]]) -> bool:
    """Return whether PE/PB-style valuation, not only market cap, is present."""

    ratio_keys = {"trailing_pe", "forward_pe", "pe_ttm", "pe_ratio", "pe", "price_to_book", "pb_ratio", "pb"}
    for fact in facts:
        if str(fact.get("metric") or "") != "fundamental_valuation":
            continue
        measurements = fact.get("measurements") if isinstance(fact.get("measurements"), Mapping) else {}
        if any(_number(measurements.get(key)) is not None for key in ratio_keys):
            return True
    return False


def _merge_fundamental_facts(
    primary_facts: List[Dict[str, Any]],
    fallback_facts: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge missing fields from a generic fallback without duplicating IDs.

    A primary valuation block may contain only market cap.  Treating that block
    as complete used to discard public PE/PB fallback data.  Existing values
    keep priority; only absent measurements are supplemented.
    """

    by_metric = {str(item.get("metric") or ""): item for item in primary_facts}
    appended: List[Dict[str, Any]] = []
    for raw in fallback_facts:
        incoming = dict(raw)
        metric = str(incoming.get("metric") or "")
        current = by_metric.get(metric)
        if current is None:
            appended.append(incoming)
            by_metric[metric] = incoming
            continue
        current_measurements = current.get("measurements") if isinstance(current.get("measurements"), Mapping) else {}
        incoming_measurements = incoming.get("measurements") if isinstance(incoming.get("measurements"), Mapping) else {}
        if metric == "fundamental_valuation":
            # Cross-provider valuation supplementation is limited to
            # dimensionless PE/PB ratios. Currency-denominated market cap or
            # price fields cannot be combined without a shared currency basis.
            allowed_keys = {
                "trailing_pe", "forward_pe", "pe_ttm", "pe_ratio", "pe",
                "price_to_book", "pb_ratio", "pb",
            }
        elif _fundamental_periods_match(current, incoming):
            allowed_keys = set(str(key) for key in incoming_measurements)
        else:
            continue
        merged = dict(current_measurements)
        added_keys: List[str] = []
        for key, value in incoming_measurements.items():
            if str(key) not in allowed_keys:
                continue
            if key not in merged or merged.get(key) in (None, ""):
                merged[key] = value
                added_keys.append(str(key))
        if not added_keys:
            continue
        current["measurements"] = merged
        providers = [
            *list(current.get("supplemental_providers") or []),
            str(incoming.get("provider") or ""),
        ]
        current["supplemental_providers"] = list(dict.fromkeys(item for item in providers if item))
        supplemental_sources = list(current.get("supplemental_sources") or [])
        supplemental_sources.append({
            "provider": str(incoming.get("provider") or ""),
            "measurement_keys": added_keys,
            "as_of": str(incoming.get("as_of") or ""),
            "report_period": str(incoming.get("report_period") or ""),
            "comparison_period": str(incoming.get("comparison_period") or ""),
            "currency": str(incoming.get("currency") or ""),
        })
        current["supplemental_sources"] = supplemental_sources
        current["value"] = (
            f"{str(current.get('value') or '').rstrip('; ')}; supplemental "
            f"{', '.join(f'{key}={_compact_number(merged[key])}' for key in added_keys[:8])}"
        ).strip("; ")
    return appended


def _fundamental_periods_match(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    """Require an explicit common reporting basis before mixing provider fields."""

    current_period = str(current.get("report_period") or "")
    incoming_period = str(incoming.get("report_period") or "")
    if not current_period or current_period != incoming_period:
        return False
    current_comparison = str(current.get("comparison_period") or "")
    incoming_comparison = str(incoming.get("comparison_period") or "")
    if current_comparison != incoming_comparison:
        return False
    current_currency = str(current.get("currency") or "").upper()
    incoming_currency = str(incoming.get("currency") or "").upper()
    return not (current_currency and incoming_currency and current_currency != incoming_currency)


def _akshare_cn_fundamental_context(symbol: str) -> Dict[str, Any]:
    """Fetch a lightweight mainland financial abstract without Yahoo routing."""

    from data_provider.fundamental_adapter import AkshareFundamentalAdapter

    bundle = AkshareFundamentalAdapter().get_core_financials(symbol)
    if not isinstance(bundle, Mapping):
        return {}
    context: Dict[str, Any] = {
        "status": bundle.get("status") or "not_supported",
        "source_chain": list(bundle.get("source_chain") or []),
        "errors": list(bundle.get("errors") or []),
    }
    for block in ("valuation", "growth", "earnings", "institution"):
        data = bundle.get(block) if isinstance(bundle.get(block), Mapping) else {}
        context[block] = {
            "status": "partial" if data else "not_supported",
            "data": dict(data),
        }
    return context


def _yfinance_public_fundamental_context(symbol: str) -> Dict[str, Any]:
    """Generic free fallback for non-mainland equities, not a ticker special case."""

    from data_provider.yfinance_fundamental_adapter import YfinanceFundamentalAdapter

    bundle = YfinanceFundamentalAdapter().get_fundamental_bundle(symbol)
    if not isinstance(bundle, Mapping):
        return {}
    context: Dict[str, Any] = {
        "status": bundle.get("status") or "not_supported",
        "source_chain": list(bundle.get("source_chain") or []),
        "errors": list(bundle.get("errors") or []),
    }
    for block in ("valuation", "growth", "earnings", "institution"):
        data = bundle.get(block) if isinstance(bundle.get(block), Mapping) else {}
        context[block] = {
            "status": "partial" if data else "not_supported",
            "data": dict(data),
        }
    return context


def _fundamental_budget_seconds(symbol: str) -> int:
    """Offshore public statements need more time than lightweight CN abstracts."""

    return 24 if _is_offshore_equity_symbol(symbol) else 12


def _is_offshore_equity_symbol(symbol: str) -> bool:
    from src.core.trading_calendar import get_market_for_stock

    return get_market_for_stock(str(symbol)) in {"us", "hk", "jp", "kr", "tw"}


def _fundamental_periods(payload: Mapping[str, Any]) -> Tuple[str, str]:
    earnings = payload.get("earnings") if isinstance(payload.get("earnings"), Mapping) else {}
    data = earnings.get("data") if isinstance(earnings.get("data"), Mapping) else earnings
    report = data.get("financial_report") if isinstance(data.get("financial_report"), Mapping) else {}
    return str(report.get("report_date") or ""), str(report.get("comparison_period") or "")


def _fundamental_history_comparison_evidence(
    symbol: str,
    run_date: str,
    payload: Mapping[str, Any],
    *,
    provider: str,
    fetched_at: str,
) -> Dict[str, Any] | None:
    """Fetch history online, compare matching periods locally and deterministically."""

    earnings = payload.get("earnings") if isinstance(payload.get("earnings"), Mapping) else {}
    data = earnings.get("data") if isinstance(earnings.get("data"), Mapping) else earnings
    raw_history = data.get("financial_history") if isinstance(data.get("financial_history"), list) else []
    history = [dict(row) for row in raw_history if isinstance(row, Mapping) and row.get("report_date")]
    history.sort(key=lambda row: str(row.get("report_date") or ""), reverse=True)
    if len(history) < 2:
        return None
    latest = history[0]
    latest_date = str(latest.get("report_date") or "")
    prior_date = ""
    try:
        prior_date = f"{int(latest_date[:4]) - 1:04d}{latest_date[4:]}"
    except (TypeError, ValueError):
        pass
    prior = next((row for row in history[1:] if str(row.get("report_date") or "") == prior_date), None)
    if prior is None:
        return None
    measurements: Dict[str, float] = {"period_count": float(len(history))}
    comparisons: Dict[str, float] = {}
    transitions: Dict[str, str] = {}
    if prior:
        for field, output in (
            ("revenue", "revenue_yoy_pct"),
            ("net_profit_parent", "net_profit_yoy_pct"),
            ("operating_cash_flow", "operating_cash_flow_yoy_pct"),
        ):
            current_value = _number(latest.get(field))
            prior_value = _number(prior.get(field))
            if current_value is None or prior_value is None:
                continue
            if prior_value > 0 and current_value >= 0:
                comparisons[output] = round((current_value / prior_value - 1.0) * 100.0, 4)
            elif prior_value < 0 < current_value:
                transitions[field] = "turned_positive"
            elif prior_value < 0 and current_value < 0:
                transitions[field] = "loss_narrowed" if current_value > prior_value else "loss_widened"
            elif prior_value > 0 > current_value:
                transitions[field] = "turned_negative"
            else:
                transitions[field] = "not_comparable"
    if not comparisons and not transitions:
        return None
    measurements.update(comparisons)
    parts = [
        f"periods={len(history)}",
        f"latest_report={latest_date}",
        f"comparison_report={prior_date}",
    ]
    parts.extend(f"{key}={_compact_number(value)}" for key, value in comparisons.items())
    parts.extend(f"{key}_transition={value}" for key, value in transitions.items())
    return {
        "id": f"subject:{symbol}:fundamental:history_comparison:{run_date}",
        "domain": "fundamentals",
        "symbol": symbol,
        "subject": symbol,
        "metric": "fundamental_history_comparison",
        "value": " ".join(parts),
        "measurements": measurements,
        "transitions": transitions,
        "history": history[:12],
        "as_of": latest_date or run_date,
        "report_period": latest_date,
        "comparison_period": prior_date,
        "comparison_method": "online_history_local_same_period_comparison",
        "fetched_at": fetched_at,
        "provider": provider,
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _fundamental_measurements(block: str, data: Mapping[str, Any]) -> Dict[str, float]:
    raw = _flatten_numeric_measurements(data)
    normalized: Dict[str, float] = {}
    for key, value in raw.items():
        leaf = key.rsplit(".", 1)[-1]
        if block == "growth" and leaf == "revenue_yoy":
            normalized["revenue_yoy_pct"] = value
        elif block == "growth" and leaf == "net_profit_yoy":
            normalized["net_profit_yoy_pct"] = value
        else:
            normalized[key] = value
    return normalized


def _flatten_numeric_measurements(value: Mapping[str, Any], prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            out.update(_flatten_numeric_measurements(item, path))
            continue
        if isinstance(item, bool):
            continue
        number = _number(item)
        if number is not None and math.isfinite(number):
            out[path] = number
    return out


def _is_cn_equity_symbol(symbol: str) -> bool:
    text = str(symbol or "").strip().upper()
    for suffix in (".SH", ".SS", ".SZ", ".BJ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.isdigit() and len(text) == 6


def _context_evidence(
    symbol: str,
    run_date: str,
    domain: str,
    provider: str,
    operation: str,
    payload: Mapping[str, Any],
    *,
    fetched_at: str = "",
) -> Dict[str, Any]:
    return {
        "id": f"subject:{symbol}:{operation}:{run_date}",
        "domain": domain,
        "symbol": symbol,
        "subject": symbol,
        "value": f"{operation} available: {_mapping_summary(payload, limit=8)}",
        "as_of": run_date,
        "fetched_at": fetched_at,
        "provider": provider,
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _context_success(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    status = str(payload.get("status") or "").lower()
    if status in {"failed", "not_supported", "missing"}:
        return False
    if payload.get("errors") and not any(_has_payload(v) for v in payload.values()):
        return False
    return any(_has_payload(v) for key, v in payload.items() if key not in {"errors", "source_chain", "coverage", "market"})


def _has_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        data = value.get("data") if isinstance(value.get("data"), Mapping) else value
        return any(v not in (None, "", [], {}) for v in data.values())
    if isinstance(value, list):
        return bool(value)
    return value not in (None, "")


def _row_count(value: Any) -> int:
    try:
        return int(len(value))
    except Exception:
        return 0


def _market_record_count(value: Any) -> int:
    if isinstance(value, tuple):
        return sum(_market_record_count(item) for item in value)
    if isinstance(value, list):
        return len(value)
    if isinstance(value, Mapping):
        return len(value)
    return 0


def _market_sample_records(value: Any, *, limit: int = 20) -> List[Dict[str, Any]]:
    """Keep a compact normalized sample for local multi-day comparisons."""

    rows: List[Dict[str, Any]] = []
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(item, list) for item in value):
        for side, collection in zip(("top", "bottom"), value):
            for rank, item in enumerate(collection, start=1):
                if isinstance(item, Mapping):
                    row = dict(item)
                    row["rank_side"] = side
                    row["rank"] = rank
                    rows.append(row)
    else:
        rows = _records(value)
    compact: List[Dict[str, Any]] = []
    for row in rows[: max(1, limit)]:
        item = {}
        for key, raw_value in row.items():
            scalar = _json_scalar(raw_value)
            if scalar is not None and scalar != "":
                item[str(key)] = scalar
        if item:
            compact.append(item)
    return compact


def _json_scalar(value: Any) -> Any:
    """Return a JSON-safe scalar without asking arrays for a truth value."""

    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    scalar_item = getattr(value, "item", None)
    if not callable(scalar_item):
        return None
    try:
        scalar = scalar_item()
    except (TypeError, ValueError):
        return None
    return scalar if isinstance(scalar, (str, int, float, bool)) else None


def _records(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, tuple) and value:
        return _records(value[0])
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict("records")
        except TypeError:
            rows = []
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, Mapping)]
    return []


def _price_series_summary(rows: List[Dict[str, Any]], *, operation: str) -> str:
    if not rows:
        return ""
    ordered = _sort_price_rows(rows)
    latest = ordered[-1]
    closes = [_number(_first_present(row, "close", "收盘", "收盘价")) for row in ordered]
    closes = [value for value in closes if value is not None]
    parts = [f"{operation} rows={len(rows)}"]
    latest_date = _first_present(latest, "trade_date", "date", "日期", "datetime")
    if latest_date not in (None, ""):
        parts.append(f"latest_date={latest_date}")
    for label, keys in (
        ("latest_open", ("open", "开盘", "开盘价")),
        ("latest_high", ("high", "最高", "最高价")),
        ("latest_low", ("low", "最低", "最低价")),
        ("latest_close", ("close", "收盘", "收盘价")),
        ("latest_volume", ("volume", "vol", "成交量")),
    ):
        value = _first_present(latest, *keys)
        if value not in (None, ""):
            parts.append(f"{label}={_compact_number(value)}")
    if len(closes) >= 2 and closes[0] not in (None, 0):
        parts.append(f"period_return_pct={round((closes[-1] / closes[0] - 1) * 100, 2)}")
    if closes:
        window5 = closes[-5:]
        parts.append(f"sma5={round(sum(window5) / len(window5), 4)}")
        if len(closes) >= 20:
            window20 = closes[-20:]
            parts.extend(
                [
                    f"sma20={round(sum(window20) / 20, 4)}",
                    f"high20={_compact_number(max(window20))}",
                    f"low20={_compact_number(min(window20))}",
                ]
            )
    volumes = [_number(_first_present(row, "volume", "vol", "成交量")) for row in ordered[-20:]]
    volumes = [value for value in volumes if value is not None]
    latest_volume = _number(_first_present(latest, "volume", "vol", "成交量"))
    if latest_volume is not None and volumes:
        average = sum(volumes) / len(volumes)
        if average:
            parts.append(f"volume_vs_avg20={round(latest_volume / average, 2)}")
    return " ".join(parts)


def _price_comparison_evidence(
    symbol: str,
    run_date: str,
    provider: str,
    payload: Any,
    *,
    fetched_at: str = "",
) -> List[Dict[str, Any]]:
    rows = _sort_price_rows(_records(payload))
    closes = [_number(_first_present(row, "close", "收盘", "收盘价")) for row in rows]
    closes = [value for value in closes if value is not None]
    if len(closes) < 2:
        return []
    latest = closes[-1]
    comparison: Dict[str, Any] = {}
    for sessions in (1, 5, 20, 60, 120, 252):
        if len(closes) <= sessions or closes[-sessions - 1] in (None, 0):
            continue
        comparison[f"return_{sessions}d_pct"] = round((latest / closes[-sessions - 1] - 1) * 100, 2)
    recent = closes[-61:]
    returns = [math.log(current / previous) for previous, current in zip(recent, recent[1:]) if previous > 0 and current > 0]
    if len(returns) >= 2:
        comparison["volatility_60d_annualized_pct"] = round(statistics.stdev(returns) * math.sqrt(252) * 100, 2)
    range_window = closes[-252:]
    range_low = min(range_window)
    range_high = max(range_window)
    if range_high > range_low:
        comparison["range_position_pct"] = round((latest - range_low) / (range_high - range_low) * 100, 2)
    if not comparison:
        return []
    event_time = _latest_row_date(rows)
    value = " ".join(f"{key}={_compact_number(item)}" for key, item in comparison.items())
    return [{
        "id": f"subject:{symbol}:price_history_comparison:{run_date}",
        "domain": "price",
        "symbol": symbol,
        "subject": symbol,
        "metric": "price_history_comparison",
        "value": value,
        "comparison": comparison,
        "as_of": date_part(event_time, run_date),
        "event_time": event_time,
        "fetched_at": fetched_at,
        "provider": provider,
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }]


def _universe_price_comparison_evidence(run_date: str, facts: Iterable[Mapping[str, Any]]) -> Dict[str, Any] | None:
    rows: List[Tuple[str, float]] = []
    fetched_at = ""
    event_time = ""
    for fact in facts:
        if str(fact.get("metric") or "") != "price_history_comparison":
            continue
        comparison = fact.get("comparison") if isinstance(fact.get("comparison"), Mapping) else {}
        return_20d = _number(comparison.get("return_20d_pct"))
        symbol = str(fact.get("symbol") or fact.get("subject") or "").strip()
        if symbol and return_20d is not None:
            rows.append((symbol, return_20d))
        fetched_at = max(fetched_at, str(fact.get("fetched_at") or ""))
        event_time = max(event_time, str(fact.get("event_time") or ""))
    if not rows:
        return None
    ordered = sorted(rows, key=lambda item: item[1], reverse=True)
    leaders = ", ".join(f"{symbol} {value:+.2f}%" for symbol, value in ordered[:5])
    laggards = ", ".join(f"{symbol} {value:+.2f}%" for symbol, value in ordered[-5:])
    breadth = sum(1 for _symbol, value in rows if value > 0) / len(rows) * 100
    return {
        "id": f"subject:market:universe_price_comparison:{run_date}",
        "domain": "price",
        "subject": "market",
        "metric": "universe_price_comparison",
        "value": f"universe={len(rows)} positive_20d_pct={breadth:.1f}; leaders={leaders}; laggards={laggards}",
        "as_of": date_part(event_time, run_date),
        "event_time": event_time,
        "fetched_at": fetched_at,
        "provider": "DataFetcherManager",
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
    }


def _sector_history_evidence(
    docs: Path,
    run_date: str,
    current_facts: Sequence[Mapping[str, Any]],
    *,
    lookback_runs: int = 20,
) -> Dict[str, Any] | None:
    """Build sector persistence from locally retained daily online snapshots."""

    snapshots: List[Tuple[str, List[Dict[str, Any]]]] = []
    current = next(
        (
            row
            for row in current_facts
            if str(row.get("metric") or "") == "sector_rankings"
            and isinstance(row.get("records"), list)
        ),
        None,
    )
    if current:
        snapshots.append((run_date, [dict(row) for row in current.get("records") or [] if isinstance(row, Mapping)]))
    run_root = docs / "run_status"
    if run_root.exists():
        prior_dates = sorted(
            (
                path.name
                for path in run_root.iterdir()
                if path.is_dir() and path.name < run_date
            ),
            reverse=True,
        )[: max(0, lookback_runs - 1)]
        for prior_date in prior_dates:
            prior_rows = _read_jsonl(run_root / prior_date / "subject_evidence.jsonl")
            prior = next(
                (
                    row
                    for row in prior_rows
                    if str(row.get("metric") or "") == "sector_rankings"
                    and isinstance(row.get("records"), list)
                ),
                None,
            )
            if prior:
                snapshots.append(
                    (prior_date, [dict(row) for row in prior.get("records") or [] if isinstance(row, Mapping)])
                )
    if len(snapshots) < 2:
        return None
    counts: Dict[str, Dict[str, int]] = {}
    for _date, rows in snapshots:
        seen: Set[str] = set()
        for row in rows:
            name = str(_first_present(row, "name", "名称", "板块名称", "行业名称") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            bucket = counts.setdefault(name, {"appearances": 0, "top": 0, "bottom": 0})
            bucket["appearances"] += 1
            side = str(row.get("rank_side") or "")
            if side in {"top", "bottom"}:
                bucket[side] += 1
    ranked = sorted(
        (
            {"name": name, **stats}
            for name, stats in counts.items()
            if stats["appearances"] >= 2
        ),
        key=lambda row: (row["appearances"], row["top"] - row["bottom"], row["name"]),
        reverse=True,
    )[:12]
    if not ranked:
        return None
    leaders = [row for row in ranked if row["top"] > row["bottom"]][:5]
    laggards = [row for row in ranked if row["bottom"] > row["top"]][:5]
    value = (
        f"local_sector_history days={len(snapshots)}; "
        f"repeated_leaders={', '.join(row['name'] for row in leaders) or 'none'}; "
        f"repeated_laggards={', '.join(row['name'] for row in laggards) or 'none'}"
    )
    return {
        "id": f"subject:market:sector_history_comparison:{run_date}",
        "domain": "news_sentiment",
        "subject": "market",
        "market": "cn",
        "metric": "sector_history_comparison",
        "value": value,
        "history": ranked,
        "observed_dates": [date for date, _rows in snapshots],
        "as_of": run_date,
        "provider": "LocalResearchHistory",
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
        "comparison_method": "local_snapshot_comparison",
    }


def _market_stats_history_evidence(
    docs: Path,
    run_date: str,
    current_facts: Sequence[Mapping[str, Any]],
    *,
    lookback_runs: int = 60,
) -> Dict[str, Any] | None:
    """Compare locally retained A-share breadth snapshots across daily runs."""

    snapshots: List[Tuple[str, Dict[str, float]]] = []

    def add_snapshot(observed_date: str, facts: Sequence[Mapping[str, Any]]) -> None:
        row = next(
            (
                item for item in facts
                if str(item.get("metric") or "") == "market_stats"
                and str(item.get("subject") or "").lower() in {"market", "market_cn"}
            ),
            None,
        )
        if not row:
            return
        measurements = row.get("measurements") if isinstance(row.get("measurements"), Mapping) else {}
        numeric = {
            key: value
            for key in ("up_count", "down_count", "flat_count", "total_amount_100m_cny")
            if (value := _number(measurements.get(key))) is not None
        }
        up = numeric.get("up_count")
        down = numeric.get("down_count")
        flat = numeric.get("flat_count", 0.0)
        total = (up or 0.0) + (down or 0.0) + flat
        if up is not None and down is not None and total > 0:
            numeric["advancers_pct"] = round(up / total * 100.0, 2)
        if numeric:
            snapshots.append((observed_date, numeric))

    add_snapshot(run_date, current_facts)
    run_root = docs / "run_status"
    if run_root.exists():
        for prior_date in sorted(
            (path.name for path in run_root.iterdir() if path.is_dir() and path.name < run_date),
            reverse=True,
        )[: max(0, lookback_runs - 1)]:
            add_snapshot(prior_date, _read_jsonl(run_root / prior_date / "subject_evidence.jsonl"))
    snapshots = sorted({date: values for date, values in snapshots}.items())
    if len(snapshots) < 2:
        return None

    latest_date, latest = snapshots[-1]
    prior_date, prior = snapshots[-2]
    measurements: Dict[str, float] = {"observation_count": float(len(snapshots))}
    parts = [f"observations={len(snapshots)}", f"latest={latest_date}", f"previous={prior_date}"]
    for metric in ("advancers_pct", "total_amount_100m_cny"):
        current = latest.get(metric)
        previous = prior.get(metric)
        if current is None:
            continue
        measurements[metric] = current
        parts.append(f"{metric}={_compact_number(current)}")
        if previous is not None:
            delta = current - previous
            measurements[f"{metric}_delta_previous"] = round(delta, 4)
            parts.append(f"{metric}_delta_previous={_compact_number(delta)}")
        values = [row.get(metric) for _date, row in snapshots if row.get(metric) is not None]
        if len(values) >= 20:
            percentile = sum(1 for value in values if value <= current) / len(values) * 100.0
            measurements[f"{metric}_local_run_percentile"] = round(percentile, 2)
    return {
        "id": f"subject:market:market_stats_history_comparison:{run_date}",
        "domain": "price",
        "subject": "market",
        "market": "cn",
        "metric": "market_stats_history_comparison",
        "value": " ".join(parts),
        "measurements": measurements,
        "observed_dates": [date for date, _values in snapshots],
        "as_of": run_date,
        "provider": "LocalResearchHistory",
        "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
        "confidence": "medium",
        "fact_type": "derived_fact",
        "evidence_scope": "subject_evidence",
        "comparison_method": "local_snapshot_comparison",
    }


def _valuation_history_evidence(
    docs: Path,
    run_date: str,
    current_facts: Sequence[Mapping[str, Any]],
    *,
    lookback_runs: int = 60,
) -> List[Dict[str, Any]]:
    """Compare generic current valuation snapshots retained by prior runs.

    This is intentionally a local run-history comparison, not a claimed
    multi-year market percentile.  Percentiles are emitted only after at least
    20 dated observations exist for the same symbol and metric.
    """

    snapshots: List[Tuple[str, Sequence[Mapping[str, Any]]]] = [(run_date, current_facts)]
    run_root = docs / "run_status"
    if run_root.exists():
        prior_dates = sorted(
            (
                path.name
                for path in run_root.iterdir()
                if path.is_dir() and path.name < run_date
            ),
            reverse=True,
        )[: max(0, lookback_runs - 1)]
        for prior_date in prior_dates:
            snapshots.append((prior_date, _read_jsonl(run_root / prior_date / "subject_evidence.jsonl")))

    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for observed_date, facts in snapshots:
        seen_symbols: Set[str] = set()
        for fact in facts:
            if str(fact.get("metric") or "") != "fundamental_valuation":
                continue
            symbol = str(fact.get("symbol") or fact.get("subject") or "").strip().upper()
            if not symbol or symbol in seen_symbols:
                continue
            measurements = fact.get("measurements") if isinstance(fact.get("measurements"), Mapping) else {}
            pe = _first_number(measurements, "trailing_pe", "pe_ttm", "pe_ratio", "pe")
            pb = _first_number(measurements, "price_to_book", "pb_ratio", "pb")
            if pe is None and pb is None:
                continue
            by_symbol.setdefault(symbol, []).append({
                "date": observed_date,
                "as_of": str(fact.get("as_of") or observed_date),
                "pe": pe,
                "pb": pb,
            })
            seen_symbols.add(symbol)

    output: List[Dict[str, Any]] = []
    for symbol, observations in by_symbol.items():
        observations.sort(key=lambda row: row["date"])
        if len(observations) < 2:
            continue
        latest = observations[-1]
        previous = observations[-2]
        measurements: Dict[str, float] = {"observation_count": float(len(observations))}
        parts = [f"observations={len(observations)}", f"latest={latest['date']}", f"previous={previous['date']}"]
        eligible_metrics: List[str] = []
        for metric in ("pe", "pb"):
            latest_value = _number(latest.get(metric))
            previous_value = _number(previous.get(metric))
            if latest_value is None:
                continue
            measurements[f"latest_{metric}"] = latest_value
            parts.append(f"latest_{metric}={_compact_number(latest_value)}")
            if previous_value not in (None, 0):
                change_pct = (latest_value / abs(previous_value) - 1.0) * 100.0
                measurements[f"{metric}_change_since_prior_run_pct"] = round(change_pct, 4)
                parts.append(f"{metric}_change_since_prior_run_pct={_compact_number(change_pct)}")
            values = [_number(row.get(metric)) for row in observations]
            clean_values = [value for value in values if value is not None]
            if len(clean_values) >= 20:
                rank = sum(1 for value in clean_values if value <= latest_value) / len(clean_values) * 100.0
                measurements[f"{metric}_local_run_percentile"] = round(rank, 2)
                parts.append(f"{metric}_local_run_percentile={_compact_number(rank)}")
                eligible_metrics.append(metric)
        measurements["valuation_percentile_eligible"] = 1.0 if eligible_metrics else 0.0
        output.append({
            "id": f"subject:{symbol}:fundamental:valuation_history:{run_date}",
            "domain": "fundamentals",
            "symbol": symbol,
            "subject": symbol,
            "metric": "valuation_history_comparison",
            "value": " ".join(parts),
            "measurements": measurements,
            "history": observations,
            "observed_dates": [row["date"] for row in observations],
            "sample_count": len(observations),
            "sample_start": observations[0]["date"],
            "sample_end": observations[-1]["date"],
            "percentile_status": "eligible" if eligible_metrics else "insufficient_sample",
            "eligible_metrics": eligible_metrics,
            "as_of": str(latest.get("as_of") or run_date),
            "provider": "LocalResearchHistory",
            "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
            "confidence": "medium",
            "fact_type": "derived_fact",
            "evidence_scope": "subject_evidence",
            "comparison_method": "local_dated_valuation_snapshots",
        })
    return output


def _first_number(value: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _number(value.get(key))
        if number is not None:
            return number
    return None


def _latest_row_date(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    latest = _sort_price_rows(rows)[-1]
    return first_timestamp(latest, "trade_date", "date", "日期", "datetime")


def _sort_price_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    date_keys = ("trade_date", "date", "日期", "datetime")
    if not any(_first_present(row, *date_keys) not in (None, "") for row in rows):
        return rows
    return sorted(rows, key=lambda row: str(_first_present(row, *date_keys) or ""))


def _market_measurements(operation: str, payload: Any) -> Dict[str, float]:
    rows = _records(payload)
    if not rows:
        return {}
    if operation == "main_indices":
        measurements: Dict[str, float] = {}
        for row in rows:
            code = str(_first_present(row, "code", "代码") or "").strip().lower()
            if not code:
                continue
            for field, aliases in {
                "current": ("current", "close", "最新价", "收盘"),
                "change": ("change", "涨跌额"),
                "change_pct": ("change_pct", "涨跌幅"),
            }.items():
                number = _number(_first_present(row, *aliases))
                if number is not None and math.isfinite(number):
                    measurements[f"index_{code}_{field}"] = number
        return measurements
    if operation != "market_stats":
        return {}
    row = rows[0]
    aliases = {
        "up_count": ("up_count", "up", "上涨家数"),
        "down_count": ("down_count", "down", "下跌家数"),
        "flat_count": ("flat_count", "flat", "平盘家数"),
        "limit_up_count": ("limit_up_count", "limit_up", "涨停家数"),
        "limit_down_count": ("limit_down_count", "limit_down", "跌停家数"),
        "total_amount_100m_cny": ("total_amount", "total_turnover", "成交额", "成交金额"),
    }
    measurements: Dict[str, float] = {}
    for canonical, keys in aliases.items():
        number = _number(_first_present(row, *keys))
        if number is not None and math.isfinite(number):
            measurements[canonical] = number
    return measurements


def _market_evidence_value(
    operation: str,
    payload: Any,
    count: int,
    *,
    measurements: Mapping[str, float] | None = None,
) -> str:
    rows = _records(payload)
    if not rows:
        return f"{operation} returned {count} records"
    if measurements:
        facts = ", ".join(f"{key}={_compact_number(value)}" for key, value in measurements.items())
        return f"{operation} records={count}; {facts}"
    samples = [_mapping_summary(row, limit=5) for row in rows[:8]]
    samples = [item for item in samples if item]
    return f"{operation} records={count}; " + " | ".join(samples)


def _mapping_summary(value: Mapping[str, Any], *, limit: int) -> str:
    parts: List[str] = []
    for key, item in value.items():
        if key in {"source_chain", "errors"} or item in (None, "", [], {}):
            continue
        if isinstance(item, Mapping):
            nested = item.get("data") if isinstance(item.get("data"), Mapping) else item
            text = _mapping_summary(nested, limit=max(1, limit - len(parts)))
            if text:
                parts.append(f"{key}[{text}]")
        elif isinstance(item, list):
            sample = ", ".join(str(row) for row in item[:3])
            if sample:
                parts.append(f"{key}={sample}")
        else:
            parts.append(f"{key}={_compact_number(item)}")
        if len(parts) >= limit:
            break
    return ", ".join(parts)


def _first_present(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value and value.get(key) not in (None, ""):
            return value.get(key)
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return str(value)
    return str(int(number)) if number.is_integer() else str(round(number, 4))


def _provider_name(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "efinance": "EfinanceFetcher",
        "tencent": "TencentFetcher",
        "akshare": "AkshareFetcher",
        "akshare_em": "AkshareFetcher",
        "akshare_sina": "AkshareFetcher",
        "yfinance": "YfinanceFetcher",
        "tushare": "TushareFetcher",
        "baostock": "BaostockFetcher",
        "pytdx": "PytdxFetcher",
        "finnhub": "FinnhubFetcher",
        "alphavantage": "AlphaVantageFetcher",
    }
    return mapping.get(text.lower(), text or "DataFetcherManager")


def _error_type(exc: Exception) -> str:
    return _error_type_text(str(exc))


def _error_type_text(text: Any) -> str:
    lower = str(text or "").lower()
    if "permission" in lower or "权限" in lower or "没有接口" in lower:
        return "permission_limited"
    if "auth" in lower or "token" in lower or "key" in lower or "unauthorized" in lower:
        return "auth_missing"
    if "429" in lower or "quota" in lower or "rate" in lower:
        return "rate_limited"
    if "not_supported" in lower or "unsupported" in lower:
        return "not_supported"
    return "failed"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows
