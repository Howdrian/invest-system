# -*- coding: utf-8 -*-
"""Lightweight cloud market-cycle runtime for governed daily reports.

This module intentionally does not import or mirror the legacy 投研 dashboard.
It builds a compact daily market view from invest-system runtime artifacts:
macro context, market heat, governed report files, source health, strategy, and
one-screen HTML outputs.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.intel.market_heat import DEFAULT_OUTPUT_DIR as DEFAULT_MARKET_HEAT_DIR
from src.intel.market_heat import build_market_heat_snapshot, load_latest_market_heat
from src.macro.official_sources import MacroContextService

DEFAULT_OUTPUT_ROOT = "reports/market_cycle"
CRITICAL_COMPONENTS = {"macro_context"}
UNAVAILABLE_STATES = {"UNAVAILABLE", "ERROR", "FAILED", "MISSING"}
DEGRADED_STATES = {"DEGRADED", "DISABLED", "EMPTY", "EMPTY_WATCHLIST", "MISSING_OR_STALE"}
USABLE_STATES = {"REFRESHED", "AVAILABLE", "USABLE", "OK"}


def build_market_cycle_payload(
    *,
    run_date: str,
    symbols: Iterable[str],
    macro_context: Optional[Dict[str, Any]],
    market_heat: Optional[Dict[str, Any]],
    report_files: Iterable[Path],
) -> Dict[str, Any]:
    """Build deterministic market-cycle view-model from runtime artifacts."""
    symbol_list = [str(s).strip() for s in symbols if str(s).strip()]
    macro = macro_context if isinstance(macro_context, dict) else {}
    heat = market_heat if isinstance(market_heat, dict) else {}
    reports = [Path(p) for p in report_files if Path(p).exists()]

    macro_status = str(macro.get("status") or "UNAVAILABLE").upper()
    heat_status = str(heat.get("status") or "UNAVAILABLE").upper()
    source_health = build_source_health(macro, heat, reports)
    market_strategy = build_market_strategy(macro, heat, source_health)

    return {
        "schema": "market_cycle_v1",
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbol_list,
        "macro_status": macro_status,
        "macro_context": macro,
        "market_heat_status": heat_status,
        "market_heat": heat,
        "report_files": [str(p) for p in reports],
        "source_health": source_health,
        "market_strategy": market_strategy,
        "protected_writeback": False,
        "trade_execution": "disabled",
    }


def build_source_health(
    macro_context: Dict[str, Any],
    market_heat: Dict[str, Any],
    report_files: List[Path],
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    rows.append(_component_row(
        component="macro_context",
        status=str(macro_context.get("status") or "UNAVAILABLE"),
        criticality="critical",
        warnings=list(macro_context.get("warnings") or []),
        source="src.macro.official_sources",
    ))
    rows.append(_component_row(
        component="market_heat",
        status=str(market_heat.get("status") or "UNAVAILABLE"),
        criticality="optional",
        warnings=list(market_heat.get("warnings") or []),
        source="src.intel.market_heat",
    ))
    rows.append(_component_row(
        component="governed_reports",
        status="available" if report_files else "degraded",
        criticality="optional",
        warnings=[] if report_files else ["report_file_missing_for_today"],
        source="reports/report_YYYYMMDD.md",
        extra={"count": len(report_files)},
    ))

    usability = _global_usability(rows)
    trade_review_usability = _trade_review_usability(rows)
    return {
        "schema": "source_health_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_status": str(macro_context.get("status") or "UNAVAILABLE").upper(),
        "usability_verdict": usability,
        "trade_review_usability": trade_review_usability,
        "rows": rows,
        "blocking_summary": {
            "critical_unavailable_components": [
                r["component"] for r in rows
                if r.get("criticality") == "critical" and r.get("usability") == "unavailable"
            ],
            "optional_unavailable_components": [
                r["component"] for r in rows
                if r.get("criticality") == "optional" and r.get("usability") == "unavailable"
            ],
            "optional_degraded_components": [
                r["component"] for r in rows
                if r.get("criticality") == "optional" and r.get("usability") == "degraded"
            ],
        },
    }


def build_market_strategy(
    macro_context: Dict[str, Any],
    market_heat: Dict[str, Any],
    source_health: Dict[str, Any],
) -> Dict[str, Any]:
    trade_usability = source_health.get("trade_review_usability")
    if trade_usability == "unavailable":
        regime = "UNKNOWN_DEGRADED"
        confidence = "LOW"
        participation_allowed = False
        gate_reason = "critical_source_unavailable"
        headline = "关键数据源不可用；只生成看盘摘要，不进入交易审查。"
    else:
        macro_regime = macro_context.get("regime") if isinstance(macro_context.get("regime"), dict) else {}
        risk_state = str(macro_regime.get("risk_state") or "unknown").lower()
        confidence = str(macro_regime.get("confidence") or "medium").upper()
        if risk_state == "risk_on":
            regime = "STRUCTURAL_RISK_ON"
            headline = "宏观风险偏好偏强；候选可进入人工预审，但不得跳过红蓝和评分。"
            participation_allowed = True
        elif risk_state == "risk_off":
            regime = "RISK_OFF_DEFENSIVE"
            headline = "宏观风险偏好偏弱；优先防守和等待确认。"
            participation_allowed = False
        elif risk_state == "neutral":
            regime = "NEUTRAL_WATCH"
            headline = "宏观中性；维持观察，等待价格和证据共振。"
            participation_allowed = True
        else:
            regime = "UNKNOWN_DEGRADED"
            headline = "宏观上下文降级；日报可读但交易审查降权。"
            participation_allowed = trade_usability != "unavailable"
        gate_reason = "allowed" if participation_allowed else "macro_or_source_gate"

    focus_items = list(market_heat.get("focus_items") or [])[:12]
    candidate_routing = [
        {
            "symbol": item.get("symbol") or item.get("code"),
            "bucket": item.get("heat_bucket") or "watch",
            "rule": "仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。",
            "ordinary_participation": bool(participation_allowed),
        }
        for item in focus_items
        if item.get("symbol") or item.get("code")
    ]
    return {
        "schema": "market_strategy_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "confidence": confidence,
        "strategy": {
            "headline": headline,
            "stance": "watch_conditions_ready" if participation_allowed else "wait_or_defensive",
            "actions": [
                "把热度和宏观作为候选发现，不直接触发交易",
                "NORMAL_RECHECK 候选必须进入 governed 个股分析",
                "任何买卖前仍需红蓝、评分、CIO 和人工确认",
            ],
            "avoid": ["只因热度高就追买", "跳过评分卡", "把降级数据当满血信号"],
        },
        "participation_allowed": participation_allowed,
        "participation_gate_reason": gate_reason,
        "candidate_routing": candidate_routing,
        "scoring_impact": 0,
        "trade_execution": "disabled",
    }


def write_market_cycle_outputs(payload: Dict[str, Any], output_dir: Path | str) -> Dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "one_screen_html": out / "00_one_screen_brief.html",
        "source_health_html": out / "13_source_health.html",
        "source_health_md": out / "13_source_health.md",
        "source_health_json": out / "13_source_health.json",
        "market_strategy_html": out / "14_market_strategy.html",
        "market_strategy_md": out / "14_market_strategy.md",
        "market_strategy_json": out / "14_market_strategy.json",
        "summary_md": out / "summary.md",
    }
    paths["source_health_json"].write_text(
        json.dumps(payload["source_health"], ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    paths["market_strategy_json"].write_text(
        json.dumps(payload["market_strategy"], ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    paths["source_health_md"].write_text(_render_source_health_md(payload), encoding="utf-8")
    paths["market_strategy_md"].write_text(_render_market_strategy_md(payload), encoding="utf-8")
    paths["source_health_html"].write_text(_html_page("数据源健康", _render_source_health_body(payload)), encoding="utf-8")
    paths["market_strategy_html"].write_text(_html_page("市场策略总控", _render_market_strategy_body(payload)), encoding="utf-8")
    paths["one_screen_html"].write_text(_html_page("统一看盘一屏总览", _render_one_screen_body(payload)), encoding="utf-8")
    paths["summary_md"].write_text(_render_summary_md(payload), encoding="utf-8")
    return paths


def _component_row(
    *,
    component: str,
    status: str,
    criticality: str,
    warnings: List[str],
    source: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status_upper = str(status or "UNAVAILABLE").upper()
    if status_upper in USABLE_STATES and not warnings:
        usability = "usable"
    elif status_upper in UNAVAILABLE_STATES:
        usability = "unavailable"
    else:
        usability = "degraded" if warnings or status_upper in DEGRADED_STATES else "usable"
    blocking_level = "critical" if criticality == "critical" and usability == "unavailable" else "none"
    row = {
        "component": component,
        "status": status_upper,
        "usability": usability,
        "criticality": criticality,
        "blocking_level": blocking_level,
        "warnings": warnings,
        "source": source,
    }
    if extra:
        row.update(extra)
    return row


def _global_usability(rows: List[Dict[str, Any]]) -> str:
    if any(r.get("usability") == "unavailable" for r in rows):
        return "unavailable"
    if any(r.get("usability") == "degraded" for r in rows):
        return "degraded"
    return "usable"


def _trade_review_usability(rows: List[Dict[str, Any]]) -> str:
    critical = [r for r in rows if r.get("criticality") == "critical"]
    if any(r.get("usability") == "unavailable" for r in critical):
        return "unavailable"
    if any(r.get("usability") == "degraded" for r in critical):
        return "usable_limited"
    return "usable"


def _render_summary_md(payload: Dict[str, Any]) -> str:
    strategy = payload["market_strategy"]
    health = payload["source_health"]
    return "\n".join([
        f"# 投研日报运行摘要 — {payload.get('run_date')}",
        "",
        f"- Macro status: `{payload.get('macro_status')}`",
        f"- Source health: `{health.get('usability_verdict')}`",
        f"- Trade review usability: `{health.get('trade_review_usability')}`",
        f"- Regime: `{strategy.get('regime')}`",
        f"- Participation allowed: `{strategy.get('participation_allowed')}`",
        "- Boundary: review-only; no trade execution; no protected writeback.",
        "",
    ])


def _render_source_health_md(payload: Dict[str, Any]) -> str:
    health = payload["source_health"]
    lines = [
        "# Source Health",
        "",
        f"- Usability: `{health.get('usability_verdict')}`",
        f"- Trade review usability: `{health.get('trade_review_usability')}`",
        "",
        "| Component | Status | Usability | Criticality | Warnings |",
        "|---|---|---|---|---|",
    ]
    for row in health.get("rows") or []:
        warnings = "; ".join(str(w) for w in row.get("warnings") or []) or "-"
        lines.append(
            f"| `{row.get('component')}` | `{row.get('status')}` | `{row.get('usability')}` | "
            f"`{row.get('criticality')}` | {warnings} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_market_strategy_md(payload: Dict[str, Any]) -> str:
    strategy = payload["market_strategy"]
    s = strategy.get("strategy") or {}
    lines = [
        "# Market Regime Strategy",
        "",
        f"- Regime: `{strategy.get('regime')}`",
        f"- Confidence: `{strategy.get('confidence')}`",
        f"- Stance: `{s.get('stance')}`",
        f"- Participation allowed: `{strategy.get('participation_allowed')}`",
        "- Boundary: review-only; no trade execution; scoring_impact=0.",
        "",
        "## 主结论",
        "",
        str(s.get("headline") or ""),
        "",
        "## 应该做",
        "",
    ]
    lines.extend(f"- {item}" for item in s.get("actions") or [])
    lines.extend(["", "## 禁止/避免", ""])
    lines.extend(f"- {item}" for item in s.get("avoid") or [])
    if strategy.get("candidate_routing"):
        lines.extend(["", "## 候选处理", "", "| Symbol | Bucket | Rule |", "|---|---|---|"])
        for item in strategy.get("candidate_routing") or []:
            lines.append(f"| `{item.get('symbol')}` | `{item.get('bucket')}` | {item.get('rule')} |")
    lines.append("")
    return "\n".join(lines)


def _render_one_screen_body(payload: Dict[str, Any]) -> str:
    strategy = payload["market_strategy"]
    health = payload["source_health"]
    macro = payload.get("macro_context") or {}
    reason = ""
    if isinstance(macro.get("regime"), dict):
        reason = macro["regime"].get("reason") or ""
    return f"""
<section class="hero">
  <div><span class="label">统一看盘 · 一屏总览</span><h1>{html.escape(str(strategy.get('regime')))}</h1><p>{html.escape(str((strategy.get('strategy') or {}).get('headline') or ''))}</p></div>
  <div class="kpi"><small>Macro</small><b>{html.escape(str(payload.get('macro_status')))}</b><span>{html.escape(str(reason))}</span></div>
  <div class="kpi"><small>Source</small><b>{html.escape(str(health.get('usability_verdict')))}</b><span>trade: {html.escape(str(health.get('trade_review_usability')))}</span></div>
</section>
<section class="card"><h2>今日边界</h2><ul><li>只读看盘，不自动交易。</li><li>个股交易前必须经过 governed 分析、红蓝、评分、CIO 和人工确认。</li><li>可选源失败只降权；关键源不可用才阻断交易审查。</li></ul></section>
<section class="card"><h2>关注列表</h2>{_render_candidates_html(strategy.get('candidate_routing') or [])}</section>
"""


def _render_source_health_body(payload: Dict[str, Any]) -> str:
    health = payload["source_health"]
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('component')))}</td>"
        f"<td>{html.escape(str(row.get('status')))}</td>"
        f"<td>{html.escape(str(row.get('usability')))}</td>"
        f"<td>{html.escape(str(row.get('criticality')))}</td>"
        f"<td>{html.escape('; '.join(str(w) for w in row.get('warnings') or []) or '-')}</td>"
        "</tr>"
        for row in health.get("rows") or []
    )
    return f"""
<section class="hero"><div><span class="label">数据源健康</span><h1>{html.escape(str(health.get('usability_verdict')))}</h1><p>trade_review_usability={html.escape(str(health.get('trade_review_usability')))}</p></div></section>
<section class="card"><table><thead><tr><th>Component</th><th>Status</th><th>Usability</th><th>Criticality</th><th>Warnings</th></tr></thead><tbody>{rows}</tbody></table></section>
"""


def _render_market_strategy_body(payload: Dict[str, Any]) -> str:
    strategy = payload["market_strategy"]
    s = strategy.get("strategy") or {}
    return f"""
<section class="hero"><div><span class="label">市场策略总控</span><h1>{html.escape(str(strategy.get('regime')))}</h1><p>{html.escape(str(s.get('headline') or ''))}</p></div><div class="kpi"><small>参与</small><b>{html.escape(str(strategy.get('participation_allowed')))}</b><span>{html.escape(str(strategy.get('participation_gate_reason')))}</span></div></section>
<section class="card"><h2>应该做</h2><ul>{''.join(f'<li>{html.escape(str(x))}</li>' for x in s.get('actions') or [])}</ul></section>
<section class="card"><h2>禁止/避免</h2><ul>{''.join(f'<li>{html.escape(str(x))}</li>' for x in s.get('avoid') or [])}</ul></section>
<section class="card"><h2>候选处理</h2>{_render_candidates_html(strategy.get('candidate_routing') or [])}</section>
"""


def _render_candidates_html(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "<p class='muted'>暂无候选；等待下一轮市场热度或个股报告。</p>"
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('symbol') or '-'))}</td>"
        f"<td>{html.escape(str(item.get('bucket') or '-'))}</td>"
        f"<td>{html.escape(str(item.get('rule') or '-'))}</td>"
        "</tr>"
        for item in items
    )
    return f"<table><thead><tr><th>Symbol</th><th>Bucket</th><th>Rule</th></tr></thead><tbody>{rows}</tbody></table>"


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#0b1020;--card:#121a2b;--line:#26344f;--text:#edf2ff;--muted:#9aa8c7;--accent:#7dd3fc}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(135deg,#08101f,#111827);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}} main{{max-width:1180px;margin:0 auto;padding:28px}} .hero{{display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:16px;border:1px solid var(--line);background:rgba(18,26,43,.92);border-radius:24px;padding:22px;margin-bottom:16px}} .card{{border:1px solid var(--line);background:var(--card);border-radius:20px;padding:18px;margin:16px 0}} h1{{margin:.2em 0;font-size:30px}} h2{{margin:0 0 12px;color:#cfe0ff}} .label,.muted,small{{color:var(--muted)}} .kpi{{border-left:1px solid var(--line);padding-left:16px}} .kpi b{{display:block;font-size:24px;color:var(--accent)}} table{{width:100%;border-collapse:collapse}} th,td{{border-bottom:1px solid #23304a;padding:9px;text-align:left;vertical-align:top}} th{{color:#9db2d5;font-size:12px;text-transform:uppercase}} @media(max-width:900px){{.hero{{grid-template-columns:1fr}}.kpi{{border-left:0;padding-left:0}}}}
</style></head><body><main>{body}<p class="muted">Generated by invest-system market_cycle_v1 · review-only · no trade execution</p></main></body></html>
"""


def _resolve_date(value: Optional[str]) -> str:
    if value:
        return value
    return datetime.now().strftime("%Y-%m-%d")


def _split_symbols(raw: Optional[str]) -> List[str]:
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return [s.strip() for s in os.getenv("STOCK_LIST", "").split(",") if s.strip()]


def _find_report_files(run_date: str, report_glob: str) -> List[Path]:
    compact = run_date.replace("-", "")
    candidates = [Path(p) for p in sorted(Path().glob(report_glob))]
    today = [p for p in candidates if compact in p.name]
    return today or candidates


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build daily market-cycle outputs for GitHub reports")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols; defaults to STOCK_LIST")
    parser.add_argument("--output-dir", default="", help="Output dir; default reports/market_cycle/YYYY-MM-DD")
    parser.add_argument("--date", default="", help="Run date YYYY-MM-DD")
    parser.add_argument("--market-heat-output-dir", default=DEFAULT_MARKET_HEAT_DIR)
    parser.add_argument("--report-glob", default="reports/report_*.md")
    parser.add_argument("--refresh-macro", action="store_true", help="Allow network macro refresh")
    args = parser.parse_args(argv)

    run_date = _resolve_date(args.date)
    output_dir = Path(args.output_dir or Path(DEFAULT_OUTPUT_ROOT) / run_date)
    symbols = _split_symbols(args.symbols)

    macro_context = MacroContextService().get_context(
        allow_network=args.refresh_macro,
        force_refresh=args.refresh_macro,
    )
    market_heat = load_latest_market_heat(args.market_heat_output_dir)
    if market_heat is None:
        market_heat = build_market_heat_snapshot(symbols, live=False)
    report_files = _find_report_files(run_date, args.report_glob)
    payload = build_market_cycle_payload(
        run_date=run_date,
        symbols=symbols,
        macro_context=macro_context,
        market_heat=market_heat,
        report_files=report_files,
    )
    paths = write_market_cycle_outputs(payload, output_dir)
    print(
        "market_cycle "
        f"macro status={payload.get('macro_status')} "
        f"source_health={payload['source_health'].get('usability_verdict')} "
        f"trade_review_usability={payload['source_health'].get('trade_review_usability')} "
        f"output_dir={output_dir}"
    )
    print(json.dumps({"paths": {k: str(v) for k, v in paths.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
