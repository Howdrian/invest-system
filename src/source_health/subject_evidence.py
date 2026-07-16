"""Collect subject evidence from the upstream data-provider stack."""

from __future__ import annotations

import json
import math
import signal
import statistics
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Mapping, Tuple

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
    manager: DataFetcherManager | None = None,
) -> Dict[str, Any]:
    """Collect current-run provider/evidence rows for the daily universe."""

    docs = Path(docs_dir)
    universe = load_daily_universe(docs, run_date)
    subject_symbols = list(symbols or universe.get("subjectSymbols") or [])
    if max_symbols is not None and max_symbols >= 0:
        subject_symbols = subject_symbols[:max_symbols]
    region = market or str(universe.get("market") or "cn")
    if manager is None:
        from data_provider import DataFetcherManager

        mgr = DataFetcherManager()
    else:
        mgr = manager

    provider_rows: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []

    provider_rows.extend(_collect_market_scope(mgr, run_date, region, evidence_rows))
    for symbol in subject_symbols:
        provider_rows.extend(_collect_symbol_scope(mgr, run_date, str(symbol), evidence_rows))
    universe_comparison = _universe_price_comparison_evidence(run_date, evidence_rows)
    if universe_comparison:
        evidence_rows.append(universe_comparison)

    out_dir = docs / "run_status" / run_date
    provider_path = out_dir / "subject_provider_runs.jsonl"
    evidence_path = out_dir / "subject_evidence.jsonl"
    write_provider_ledger(provider_path, provider_rows)
    write_evidence_ledger(evidence_path, evidence_rows)
    summary = {
        "schema": "subject_evidence_collection_v1",
        "runDate": run_date,
        "market": region,
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

    fundamental, fund_run = _timed_call(
        "fundamental_context",
        lambda: mgr.get_fundamental_context(symbol, budget_seconds=8),
        timeout_seconds=12,
    )
    rows.extend(_provider_rows_from_context(symbol, "fundamentals", "fundamental_context", fundamental, fund_run))
    fundamental_facts = _fundamental_evidence(
        symbol,
        run_date,
        fundamental,
        fetched_at=str(fund_run.get("observed_at") or ""),
    )
    evidence_rows.extend(fundamental_facts)
    if not fundamental_facts and _is_cn_equity_symbol(symbol):
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
        evidence_rows.extend(fallback_facts)

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
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for operation, domain, fn in [
        ("main_indices", "price", lambda: mgr.get_main_indices(market)),
        ("market_stats", "price", lambda: mgr.get_market_stats(purpose="daily_universe")),
        ("sector_rankings", "news_sentiment", lambda: mgr.get_sector_rankings(n=8)),
        ("concept_rankings", "news_sentiment", lambda: mgr.get_concept_rankings(n=8)),
        ("hot_stocks", "news_sentiment", lambda: mgr.get_hot_stocks(n=10)),
    ]:
        payload, run = _timed_call(operation, fn, timeout_seconds=30)
        count = _market_record_count(payload)
        rows.append(_provider_row("market", "DataFetcherManager", domain, operation, run, record_count=count))
        if count > 0:
            measurements = _market_measurements(operation, payload)
            evidence_rows.append(
                {
                    "id": f"subject:market:{operation}:{run_date}",
                    "domain": domain,
                    "subject": "market",
                    "metric": operation,
                    "value": _market_evidence_value(operation, payload, count, measurements=measurements),
                    "measurements": measurements,
                    "as_of": run_date,
                    "fetched_at": run.get("observed_at"),
                    "provider": "DataFetcherManager",
                    "raw_path": f"run_status/{run_date}/subject_provider_runs.jsonl",
                    "confidence": "medium",
                    "fact_type": "derived_fact",
                    "evidence_scope": "subject_evidence",
                }
            )
    return rows


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
    for block in ("valuation", "growth", "earnings", "institution"):
        item = payload.get(block) if isinstance(payload.get(block), Mapping) else {}
        status = str(item.get("status") or "").lower()
        data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
        if status in {"ok", "success", "partial", "available"} and data:
            measurements = _fundamental_measurements(block, data)
            facts.append(
                {
                    "id": f"subject:{symbol}:fundamental:{block}:{run_date}",
                    "domain": "fundamentals",
                    "symbol": symbol,
                    "subject": symbol,
                    "metric": f"fundamental_{block}",
                    "value": f"{block} available: {_mapping_summary(data, limit=6)}",
                    "measurements": measurements,
                    "as_of": run_date,
                    "fetched_at": fetched_at,
                    "provider": provider,
                    "raw_path": f"run_status/{run_date}/subject_evidence.jsonl",
                    "confidence": "medium",
                    "fact_type": "derived_fact",
                    "evidence_scope": "subject_evidence",
                }
            )
    return facts


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
    for block in ("growth", "earnings", "institution"):
        data = bundle.get(block) if isinstance(bundle.get(block), Mapping) else {}
        context[block] = {
            "status": "partial" if data else "not_supported",
            "data": dict(data),
        }
    return context


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
