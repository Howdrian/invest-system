# -*- coding: utf-8 -*-
"""Adapter that turns original-system analysis outputs into research inputs.

v1.3 deliberately keeps this layer bounded.  It does not let agents fetch data.
It reads the already-built daily universe/evidence/provider ledgers and writes a
compact original-analysis manifest that can be fed to department agents and
shown in diagnostics.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from data_provider.stock_code import normalize_stock_code

from src.source_health.run_matrix import sha256_file, upsert_run_matrix_stage

ORIGINAL_ANALYSIS_SCHEMA = "original_analysis_v1"
ORIGINAL_ANALYSIS_REFS_SCHEMA = "original_analysis_ref_v1"
ORIGINAL_ANALYSIS_SNAPSHOT_SCHEMA = "original_analysis_snapshot_v1"


_KIND_TARGETS: dict[str, list[str]] = {
    "market_review": ["MarketAgent", "SectorAgent", "RiskAgent", "CIOAgent"],
    "market_snapshot": ["MarketAgent", "SectorAgent", "RiskAgent", "CIOAgent"],
    "screening": ["SectorAgent", "MarketAgent", "CIOAgent"],
    "stock_analysis_context": ["FundamentalAgent", "TechnicalAgent", "IntelAgent", "RiskAgent"],
    "fundamental_context": ["FundamentalAgent", "RiskAgent", "CIOAgent"],
    "technical_context": ["TechnicalAgent", "RiskAgent", "CIOAgent"],
    "intel_events": ["IntelAgent", "GeoPolicyAgent", "RiskAgent", "CIOAgent"],
    "geo_policy_seed": ["GeoPolicyAgent", "MacroAgent", "RiskAgent", "CIOAgent"],
    "decision_signals": ["RiskAgent", "RedTeamAgent", "CIOAgent"],
    "portfolio_snapshot": ["PortfolioAgent", "RiskAgent", "CIOAgent"],
    "watchlist_snapshot": ["PortfolioAgent", "SectorAgent", "CIOAgent"],
    "history_summary": ["RiskAgent", "CIOAgent"],
    "stock_analysis_output": ["FundamentalAgent", "TechnicalAgent", "IntelAgent", "RiskAgent", "CIOAgent"],
}


def build_original_analysis_bundle(
    docs_dir: str | Path,
    run_date: str,
    *,
    runtime_reports_dir: str | Path = "reports",
) -> Dict[str, Any]:
    """Build and persist original analysis bundle for ``run_date``."""

    docs = Path(docs_dir)
    run_dir = docs / "run_status" / run_date
    run_dir.mkdir(parents=True, exist_ok=True)

    evidence = _load_jsonl(run_dir / "evidence_ledger.jsonl")
    subject_evidence = _load_jsonl(run_dir / "subject_evidence.jsonl")
    provider_runs = _load_jsonl(run_dir / "subject_provider_runs.jsonl") + _load_jsonl(run_dir / "provider_runs.jsonl")
    universe = _read_json(run_dir / "daily_universe.json") or {}
    health = _read_json(run_dir / "source_health_v2.json") or {}
    snapshot = load_original_analysis_snapshot(docs, run_date)

    evidence_rows = evidence or subject_evidence
    refs = _build_refs(run_date, evidence_rows, provider_runs, universe, health)
    refs.extend(
        _analysis_output_refs(
            run_date,
            Path(runtime_reports_dir),
            universe,
            snapshot=snapshot,
        )
    )
    ref_path = run_dir / "original_analysis_refs.jsonl"
    ref_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in refs), encoding="utf-8")

    ref_kinds = {str(row.get("kind") or "") for row in refs if row.get("status") == "available"}
    empty_kinds = {str(row.get("kind") or "") for row in refs if row.get("status") == "empty"}
    stock_context_refs = [row for row in refs if row.get("kind") in {"stock_analysis_context", "fundamental_context", "technical_context"} and row.get("status") == "available"]
    stock_analysis_refs = [row for row in refs if row.get("kind") == "stock_analysis_output" and row.get("status") == "available"]
    decision_refs = [row for row in refs if row.get("kind") == "decision_signals" and row.get("status") == "available"]

    payload: Dict[str, Any] = {
        "schema": ORIGINAL_ANALYSIS_SCHEMA,
        "runDate": run_date,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "marketContextAvailable": "market_snapshot" in ref_kinds,
        "marketReviewAvailable": "market_review" in ref_kinds,
        "stockContextCount": len(stock_context_refs),
        "stockAnalysisCount": len(stock_analysis_refs),
        "decisionSignalCount": len(decision_refs),
        "portfolioSnapshotAvailable": "portfolio_snapshot" in ref_kinds,
        "structuredSnapshotAvailable": bool(snapshot.get("records")),
        "structuredSnapshotPath": f"docs/run_status/{run_date}/original_analysis_snapshot.json",
        "structuredSnapshotSha256": snapshot.get("sha256"),
        "refsPath": f"docs/run_status/{run_date}/original_analysis_refs.jsonl",
        "refCount": len(refs),
        "availableKinds": sorted(ref_kinds),
        "emptyKinds": sorted(empty_kinds),
        "notes": _bundle_notes(universe, refs),
    }
    path = run_dir / "original_analysis.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    upsert_run_matrix_stage(
        docs,
        run_date,
        {
            "name": "original_analysis_adapter",
            "status": "success" if refs else "partial",
            "blocking": False,
            "inputs": [
                f"run_status/{run_date}/daily_universe.json",
                f"run_status/{run_date}/evidence_ledger.jsonl",
                f"run_status/{run_date}/subject_provider_runs.jsonl",
                f"run_status/{run_date}/original_analysis_snapshot.json",
            ],
            "outputs": [
                f"run_status/{run_date}/original_analysis.json",
                f"run_status/{run_date}/original_analysis_refs.jsonl",
            ],
            "sha256": sha256_file(path),
        },
    )
    return payload


def load_original_analysis(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(Path(docs_dir) / "run_status" / run_date / "original_analysis.json")
    return dict(payload) if isinstance(payload, Mapping) and payload.get("schema") == ORIGINAL_ANALYSIS_SCHEMA else {}


def load_original_analysis_refs(docs_dir: str | Path, run_date: str) -> List[Dict[str, Any]]:
    return _load_jsonl(Path(docs_dir) / "run_status" / run_date / "original_analysis_refs.jsonl")


def load_original_analysis_snapshot(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    payload = _read_json(Path(docs_dir) / "run_status" / run_date / "original_analysis_snapshot.json")
    if not isinstance(payload, Mapping) or payload.get("schema") != ORIGINAL_ANALYSIS_SNAPSHOT_SCHEMA:
        return {}
    if str(payload.get("runDate") or "") != run_date:
        return {}
    return dict(payload)


def export_original_analysis_snapshot(
    docs_dir: str | Path,
    run_date: str,
    *,
    symbols: Sequence[str] = (),
    records: Sequence[Any] | None = None,
) -> Dict[str, Any]:
    """Export same-run original analysis rows as bounded analyst opinions.

    The snapshot deliberately excludes raw prompts, raw model responses and
    full context blobs.  It is an opinion input for department agents, never a
    replacement for Evidence facts.
    """

    if records is None:
        from src.storage import DatabaseManager

        records = DatabaseManager.get_instance().get_analysis_history(days=2, limit=500)

    wanted = {normalize_stock_code(str(item)).upper() for item in symbols if str(item).strip()}
    selected: Dict[tuple[str, str], Dict[str, Any]] = {}
    for record in records:
        created_at = getattr(record, "created_at", None)
        created_date = created_at.date().isoformat() if hasattr(created_at, "date") else ""
        if created_date != run_date:
            continue
        code = normalize_stock_code(str(getattr(record, "code", "") or "")).upper()
        report_type = str(getattr(record, "report_type", "") or "")
        is_market_review = report_type == "market_review" or code.lower() == "market_review"
        if not is_market_review and wanted and code not in wanted:
            continue
        raw = _json_mapping(getattr(record, "raw_result", None))
        payload = _structured_history_record(record, raw, code=code, report_type=report_type)
        key = (code, report_type)
        current = selected.get(key)
        if current is None or str(payload.get("createdAt") or "") > str(current.get("createdAt") or ""):
            selected[key] = payload

    rows = sorted(selected.values(), key=lambda row: (str(row.get("reportType") or ""), str(row.get("code") or "")))
    payload: Dict[str, Any] = {
        "schema": ORIGINAL_ANALYSIS_SNAPSHOT_SCHEMA,
        "runDate": run_date,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "analysis_history",
        "recordCount": len(rows),
        "records": rows,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path = Path(docs_dir) / "run_status" / run_date / "original_analysis_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _build_refs(
    run_date: str,
    evidence_rows: Sequence[Mapping[str, Any]],
    provider_runs: Sequence[Mapping[str, Any]],
    universe: Mapping[str, Any],
    health: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    refs.extend(_market_refs(run_date, evidence_rows, provider_runs))
    refs.extend(_stock_refs(run_date, evidence_rows, provider_runs, universe))
    refs.extend(_portfolio_refs(run_date, evidence_rows, universe, health))
    refs.extend(_geo_policy_refs(run_date, evidence_rows))
    refs.extend(_decision_signal_refs(run_date, evidence_rows, provider_runs))
    refs.extend(_history_refs(run_date, universe))
    return refs


def _market_refs(run_date: str, evidence_rows: Sequence[Mapping[str, Any]], provider_runs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    operations = {"main_indices", "market_stats", "sector_rankings", "concept_rankings", "hot_stocks"}
    op_rows = [row for row in provider_runs if str(row.get("operation") or "") in operations]
    evidence_ids = _ids_for(evidence_rows, subject="market")
    market_ops = sorted({str(row.get("operation")) for row in op_rows if row.get("success")})
    refs = [
        _ref(
            run_date,
            kind="market_snapshot",
            status="available" if {"main_indices", "market_stats"} & set(market_ops) else "empty",
            source_kind="original_market_context",
            summary=_summary_from_ops("原系统市场分析层", op_rows, ["main_indices", "market_stats"]),
            evidence_ids=evidence_ids[:10],
            symbols=["market"],
        ),
        _ref(
            run_date,
            kind="screening",
            status="available" if {"sector_rankings", "hot_stocks", "concept_rankings"} & set(market_ops) else "empty",
            source_kind="original_screening_context",
            summary=_summary_from_ops("原系统候选/板块层", op_rows, ["sector_rankings", "concept_rankings", "hot_stocks"]),
            evidence_ids=[item for item in evidence_ids if "sector" in item or "hot_stocks" in item or "concept" in item][:10],
            symbols=["market"],
        ),
    ]
    return refs


def _analysis_output_refs(
    run_date: str,
    runtime_reports: Path,
    universe: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    compact = run_date.replace("-", "")
    market_path = runtime_reports / f"market_review_{compact}.md"
    stock_path = runtime_reports / f"report_{compact}.md"
    symbols = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)]
    records = [row for row in snapshot.get("records") or [] if isinstance(row, Mapping)]
    market_record = next(
        (
            row
            for row in records
            if str(row.get("reportType") or "") == "market_review"
            or str(row.get("code") or "").lower() == "market_review"
        ),
        None,
    )
    market_ref = _ref(
        run_date,
        kind="market_review",
        status="available" if market_record else "empty",
        source_kind="analysis_history_snapshot" if market_record else "legacy_report_file_only",
        summary=(
            _analysis_record_summary(market_record, fallback="原系统市场复盘已生成。")
            if market_record
            else (
                f"只发现旧 Markdown {market_path.name}；未绑定同日结构化记录，不作为 Agent 分析输入。"
                if _nonempty_file(market_path)
                else "原系统市场复盘未生成；市场快照不冒充 AI 复盘。"
            )
        ),
        evidence_ids=[],
        symbols=["market"],
    )
    if market_record:
        market_ref.update(_analysis_record_ref_fields(market_record, snapshot))
    refs = [market_ref]

    records_by_symbol = {
        normalize_stock_code(str(row.get("code") or "")).upper(): row
        for row in records
        if str(row.get("reportType") or "") != "market_review"
    }
    for symbol in symbols:
        normalized = normalize_stock_code(symbol).upper()
        row = records_by_symbol.get(normalized)
        if not row:
            continue
        ref = _ref(
            run_date,
            kind="stock_analysis_output",
            status="available",
            source_kind="analysis_history_snapshot",
            summary=_analysis_record_summary(row, fallback=f"{symbol} 原系统个股分析已生成。"),
            evidence_ids=[],
            symbols=[symbol],
        )
        ref.update(_analysis_record_ref_fields(row, snapshot))
        refs.append(ref)
    if not any(row.get("kind") == "stock_analysis_output" and row.get("status") == "available" for row in refs):
        refs.append(_ref(
            run_date,
            kind="stock_analysis_output",
            status="empty",
            source_kind="legacy_report_file_only" if _nonempty_file(stock_path) else "original_stock_analysis_output",
            summary=(
                f"只发现旧 Markdown {stock_path.name}；未绑定同日结构化记录，不作为 Agent 分析输入。"
                if _nonempty_file(stock_path)
                else "原系统个股分析未生成；行情、K 线和基本面上下文不冒充 AI 个股结论。"
            ),
            evidence_ids=[],
            symbols=symbols,
        ))
    return refs


def _structured_history_record(record: Any, raw: Mapping[str, Any], *, code: str, report_type: str) -> Dict[str, Any]:
    created_at = getattr(record, "created_at", None)
    created_text = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
    dashboard = raw.get("dashboard") if isinstance(raw.get("dashboard"), Mapping) else {}
    core = dashboard.get("core_conclusion") if isinstance(dashboard.get("core_conclusion"), Mapping) else {}
    result = {
        "recordId": getattr(record, "id", None),
        "queryId": str(getattr(record, "query_id", "") or ""),
        "createdAt": created_text,
        "code": code,
        "name": str(raw.get("name") or getattr(record, "name", "") or ""),
        "reportType": report_type,
        "modelUsed": str(raw.get("model_used") or ""),
        "sentimentScore": raw.get("sentiment_score", getattr(record, "sentiment_score", None)),
        "trendPrediction": str(raw.get("trend_prediction") or getattr(record, "trend_prediction", "") or ""),
        "operationAdvice": str(raw.get("operation_advice") or getattr(record, "operation_advice", "") or ""),
        "action": str(raw.get("action") or ""),
        "confidenceLevel": str(raw.get("confidence_level") or ""),
        "coreConclusion": _clip(str(core.get("one_sentence") or raw.get("analysis_summary") or getattr(record, "analysis_summary", "") or ""), 800),
        "analysisSummary": _clip(str(raw.get("analysis_summary") or getattr(record, "analysis_summary", "") or ""), 1200),
        "keyPoints": _clip(str(raw.get("key_points") or ""), 1000),
        "riskWarning": _clip(str(raw.get("risk_warning") or ""), 1000),
        "buyReason": _clip(str(raw.get("buy_reason") or ""), 800),
        "currentPrice": raw.get("current_price"),
        "changePct": raw.get("change_pct"),
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    result["contentSha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def _analysis_record_summary(record: Mapping[str, Any], *, fallback: str) -> str:
    code = str(record.get("code") or "").strip()
    conclusion = str(record.get("coreConclusion") or record.get("analysisSummary") or "").strip()
    action = str(record.get("operationAdvice") or record.get("action") or "").strip()
    score = record.get("sentimentScore")
    parts = [f"{code} 原系统结构化分析" if code and code != "MARKET_REVIEW" else "原系统结构化市场复盘"]
    if conclusion:
        parts.append(_clip(conclusion, 260))
    if action:
        parts.append(f"原建议：{action}")
    if score not in (None, ""):
        parts.append(f"原评分：{score}")
    return "；".join(parts) if len(parts) > 1 else fallback


def _analysis_record_ref_fields(record: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "recordId": record.get("recordId"),
        "queryId": record.get("queryId"),
        "createdAt": record.get("createdAt"),
        "modelUsed": record.get("modelUsed"),
        "contentSha256": record.get("contentSha256"),
        "snapshotSha256": snapshot.get("sha256"),
        "analysis": {
            key: record.get(key)
            for key in (
                "coreConclusion",
                "analysisSummary",
                "keyPoints",
                "riskWarning",
                "buyReason",
                "operationAdvice",
                "action",
                "sentimentScore",
                "confidenceLevel",
                "currentPrice",
                "changePct",
            )
            if record.get(key) not in (None, "")
        },
    }


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _stock_refs(run_date: str, evidence_rows: Sequence[Mapping[str, Any]], provider_runs: Sequence[Mapping[str, Any]], universe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    symbols = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)]
    out: List[Dict[str, Any]] = []
    for symbol in symbols:
        subject_ids = _ids_for(evidence_rows, symbol=symbol) or _ids_for(evidence_rows, subject=symbol)
        symbol_runs = [row for row in provider_runs if str(row.get("symbol") or "").upper() == symbol.upper()]
        ops = {str(row.get("operation") or "") for row in symbol_runs if row.get("success")}
        fundamentals_ids = _ids_for(evidence_rows, symbol=symbol, domain="fundamentals")
        price_ids = _ids_for(evidence_rows, symbol=symbol, domain="price")
        filing_ids = _ids_for(evidence_rows, symbol=symbol, domain="filings_events")
        out.append(
            _ref(
                run_date,
                kind="stock_analysis_context",
                status="available" if subject_ids else "empty",
                source_kind="original_stock_context",
                summary=f"{symbol} 原系统个股上下文：{_ops_text(symbol_runs)}。",
                evidence_ids=subject_ids[:12],
                symbols=[symbol],
            )
        )
        out.append(
            _ref(
                run_date,
                kind="technical_context",
                status="available" if "daily_data" in ops or price_ids else "empty",
                source_kind="original_technical_context",
                summary=f"{symbol} 技术/K线：{_operation_status(symbol_runs, 'daily_data')}；行情：{_operation_status(symbol_runs, 'realtime_quote')}。",
                evidence_ids=price_ids[:10],
                symbols=[symbol],
            )
        )
        out.append(
            _ref(
                run_date,
                kind="fundamental_context",
                status="available" if fundamentals_ids or filing_ids else "empty",
                source_kind="original_fundamental_context",
                summary=f"{symbol} 基本面/公告：fundamental_context {_operation_status(symbol_runs, 'fundamental_context')}；公告/法披 {len(filing_ids)} 条。",
                evidence_ids=(fundamentals_ids + filing_ids)[:10],
                symbols=[symbol],
            )
        )
    return out


def _portfolio_refs(run_date: str, evidence_rows: Sequence[Mapping[str, Any]], universe: Mapping[str, Any], health: Mapping[str, Any]) -> List[Dict[str, Any]]:
    groups = universe.get("groups") if isinstance(universe.get("groups"), list) else []
    portfolio_group = next((row for row in groups if isinstance(row, Mapping) and row.get("name") == "portfolio"), {})
    watchlist_group = next((row for row in groups if isinstance(row, Mapping) and row.get("name") == "watchlist"), {})
    portfolio_symbols = [str(item) for item in portfolio_group.get("symbols") or [] if str(item)] if isinstance(portfolio_group, Mapping) else []
    watchlist_symbols = [str(item) for item in watchlist_group.get("symbols") or [] if str(item)] if isinstance(watchlist_group, Mapping) else []
    domain = (health.get("domains") or {}).get("portfolio") if isinstance(health.get("domains"), Mapping) else {}
    portfolio_ids = _ids_for(evidence_rows, domain="portfolio")
    status = "available" if portfolio_symbols or portfolio_ids or (isinstance(domain, Mapping) and domain.get("status") == "available") else "empty"
    return [
        _ref(run_date, kind="portfolio_snapshot", status=status, source_kind="original_portfolio_context", summary=f"持仓标的 {len(portfolio_symbols)} 个；watchlist {len(watchlist_symbols)} 个。", evidence_ids=portfolio_ids[:8], symbols=portfolio_symbols),
        _ref(run_date, kind="watchlist_snapshot", status="available" if watchlist_symbols else "empty", source_kind="daily_universe_watchlist", summary=f"watchlist 标的：{', '.join(watchlist_symbols[:10]) or '未配置'}。", evidence_ids=[], symbols=watchlist_symbols),
    ]


def _geo_policy_refs(run_date: str, evidence_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    macro_ids = [row for row in evidence_rows if row.get("domain") == "macro"]
    geo_ids = [str(row.get("id")) for row in macro_ids if any(token in str(row.get("id") or row.get("value") or "").upper() for token in ("DCOIL", "VIX", "DXY", "DGS10", "BAML"))]
    news_ids = [str(row.get("id")) for row in evidence_rows if row.get("domain") == "news_sentiment" and row.get("fact_type") == "discovery"]
    return [
        _ref(
            run_date,
            kind="geo_policy_seed",
            status="available" if geo_ids or news_ids else "empty",
            source_kind="geo_policy_default_pack",
            summary="地缘政策包：能源、美元/利率、信用风险和新闻 discovery 进入地缘政策部门；无官方政策事件时只做传导假设。",
            evidence_ids=(geo_ids + news_ids)[:12],
            symbols=["macro", "geo_policy"],
        )
    ]


def _decision_signal_refs(run_date: str, evidence_rows: Sequence[Mapping[str, Any]], provider_runs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ids = [str(row.get("id")) for row in evidence_rows if "decision" in str(row.get("id") or "").lower()]
    runs = [row for row in provider_runs if "decision" in str(row.get("operation") or "").lower()]
    return [
        _ref(
            run_date,
            kind="decision_signals",
            status="available" if ids or runs else "empty",
            source_kind="original_decision_signals",
            summary=_summary_from_ops("原系统决策信号", runs, []),
            evidence_ids=ids[:10],
            symbols=[],
        )
    ]


def _history_refs(run_date: str, universe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    symbols = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)]
    return [
        _ref(
            run_date,
            kind="history_summary",
            status="available" if symbols else "empty",
            source_kind="local_report_history",
            summary=f"历史报告汇总按 Daily Universe 限定，不全市场重跑；本轮标的 {len(symbols)} 个。",
            evidence_ids=[],
            symbols=symbols[:12],
        )
    ]


def _ref(run_date: str, *, kind: str, status: str, source_kind: str, summary: str, evidence_ids: Sequence[str], symbols: Sequence[str]) -> Dict[str, Any]:
    return {
        "schema": ORIGINAL_ANALYSIS_REFS_SCHEMA,
        "runDate": run_date,
        "kind": kind,
        "sourceKind": source_kind,
        "status": status,
        "agentTargets": _KIND_TARGETS.get(kind, []),
        "summary": _clip(summary, 420),
        "evidenceIds": _dedupe([str(item) for item in evidence_ids if str(item)])[:16],
        "symbols": _dedupe([str(item) for item in symbols if str(item)])[:16],
    }


def _summary_from_ops(prefix: str, rows: Sequence[Mapping[str, Any]], expected: Sequence[str]) -> str:
    if not rows and not expected:
        return f"{prefix}：未发现结构化结果。"
    parts: List[str] = []
    for op in expected:
        parts.append(f"{op} {_operation_status(rows, op)}")
    if not parts:
        parts = [f"{str(row.get('operation') or 'operation')}={str(row.get('success'))}" for row in rows[:6]]
    return f"{prefix}：" + "；".join(parts)


def _operation_status(rows: Sequence[Mapping[str, Any]], operation: str) -> str:
    matched = [row for row in rows if str(row.get("operation") or "") == operation]
    if not matched:
        return "missing"
    success = [row for row in matched if row.get("success")]
    if success:
        count = sum(int(row.get("record_count") or 0) for row in success)
        return f"success({count})"
    error = str(matched[0].get("error_type") or matched[0].get("error_message_sanitized") or "failed")
    return error


def _ops_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "无 provider 记录"
    out: List[str] = []
    for row in rows[:8]:
        op = str(row.get("operation") or "operation")
        status = "success" if row.get("success") else str(row.get("error_type") or "failed")
        count = row.get("record_count")
        out.append(f"{op}={status}({count})")
    return "；".join(out)


def _ids_for(rows: Sequence[Mapping[str, Any]], *, domain: str | None = None, symbol: str | None = None, subject: str | None = None) -> List[str]:
    out: List[str] = []
    for row in rows:
        if domain and str(row.get("domain") or "") != domain:
            continue
        if symbol and str(row.get("symbol") or row.get("subject") or "").upper() != symbol.upper():
            continue
        if subject and str(row.get("subject") or row.get("symbol") or "").upper() != subject.upper():
            continue
        value = str(row.get("id") or "").strip()
        if value:
            out.append(value)
    return _dedupe(out)


def _bundle_notes(universe: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> List[str]:
    notes: List[str] = []
    symbols = [str(item) for item in universe.get("subjectSymbols") or [] if str(item)] if isinstance(universe, Mapping) else []
    notes.append(f"本轮只按 Daily Universe 和候选池接入原系统分析，未全市场重跑；标的 {len(symbols)} 个。")
    if any(row.get("kind") == "portfolio_snapshot" and row.get("status") == "empty" for row in refs):
        notes.append("未发现结构化持仓；PortfolioAgent 只能读 watchlist/空持仓说明。")
    if any(row.get("kind") == "decision_signals" and row.get("status") == "empty" for row in refs):
        notes.append("未发现结构化 decision signals；Risk/CIO 按 evidence 和部门输出复核。")
    return notes


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _json_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def _dedupe(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _clip(text: str, limit: int) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
