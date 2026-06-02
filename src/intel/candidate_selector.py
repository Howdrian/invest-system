# -*- coding: utf-8 -*-
"""Candidate screening funnel and deep-review queue for market-cycle reports."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def build_screening_funnel(
    *,
    run_date: str,
    symbols: Iterable[str],
    market_heat: Optional[Dict[str, Any]],
    macro_review: Optional[Dict[str, Any]],
    prediction_market: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    symbol_list = [str(s).strip() for s in symbols if str(s).strip()]
    heat = market_heat if isinstance(market_heat, dict) else {}
    macro = macro_review if isinstance(macro_review, dict) else {}
    pm = prediction_market if isinstance(prediction_market, dict) else {}
    rows: List[Dict[str, Any]] = []

    seen: set[str] = set()
    for symbol in symbol_list:
        rows.append(_candidate(
            symbol=symbol,
            name="",
            source="watchlist",
            base_score=4.0,
            evidence=["watchlist_member"],
            verdict="WATCH_ONLY",
            price_risk="NORMAL_RECHECK",
            next_action="继续观察；等待公告/研报/市场热度/技术形态触发。",
        ))
        seen.add(symbol)

    for item in heat.get("focus_items") or []:
        symbol = str(item.get("symbol") or item.get("code") or "").strip()
        if not symbol or symbol in seen:
            continue
        bucket = str(item.get("heat_bucket") or "watch").lower()
        score = 6.0 if bucket in {"hot", "breakout", "volume"} else 4.5
        verdict = "DEEP_REVIEW_WAIT_ENTRY" if score >= 6.0 else "WATCH_ONLY"
        rows.append(_candidate(
            symbol=symbol,
            name=str(item.get("name") or ""),
            source="market_heat",
            base_score=score,
            evidence=["market_heat", str(item.get("reason") or bucket)],
            verdict=verdict,
            price_risk="OVERHEATED_WAIT_ENTRY" if bucket in {"hot", "breakout"} else "NORMAL_RECHECK",
            next_action="等待承接/横盘消化；不因热度直接追高。" if verdict != "WATCH_ONLY" else "继续观察。",
        ))
        seen.add(symbol)

    for item in heat.get("hot_stocks") or []:
        symbol = str(item.get("code") or item.get("symbol") or item.get("股票代码") or "").strip()
        if not symbol or symbol in seen:
            continue
        name = str(item.get("name") or item.get("股票简称") or item.get("名称") or "")
        rows.append(_candidate(
            symbol=symbol,
            name=name,
            source="hot_stocks",
            base_score=6.5,
            evidence=["hot_stock_rank"],
            verdict="DEEP_REVIEW_WAIT_ENTRY",
            price_risk="OVERHEATED_WAIT_ENTRY",
            next_action="读公告/研报和技术承接；不追高。",
        ))
        seen.add(symbol)

    red_team = any(s.get("red_team_trigger") for s in pm.get("scenario_fusion") or [])
    macro_state = ((macro.get("six_factor_regime") or {}).get("risk_state") or "unknown")
    for row in rows:
        if red_team:
            row["evidence"].append("prediction_market_red_team_trigger")
            row["macro_overlay"] = "地缘/预测市场差异触发红队复核。"
        elif macro_state:
            row["macro_overlay"] = f"macro_risk_state={macro_state}"
        if row["verdict"] == "DEEP_REVIEW_WAIT_ENTRY" and macro_state == "risk_on" and row.get("price_risk") == "NORMAL_RECHECK":
            row["verdict"] = "DEEP_REVIEW_NOW"
            row["next_action"] = "进入 governed 深评；仍需红蓝、评分、CIO。"

    rows.sort(key=lambda r: (r.get("verdict") == "DEEP_REVIEW_NOW", r.get("priority_score") or 0), reverse=True)
    return {
        "schema": "screening_funnel_v1",
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "available" if rows else "empty",
        "candidate_count": len(rows),
        "candidates": rows[:80],
        "policy": {
            "watchlist_is_universe_not_deep_review_pool": True,
            "market_heat_trade_signal": False,
            "max_governed_deep_reviews": 6,
            "auto_governed_verdict": "DEEP_REVIEW_NOW",
        },
        "protected_writeback": False,
        "trade_execution": "disabled",
    }


def build_deep_review_queue(
    funnel: Dict[str, Any], *, max_candidates: int = 6) -> Dict[str, Any]:
    candidates = list(funnel.get("candidates") or [])
    auto = [c for c in candidates if c.get("verdict") == "DEEP_REVIEW_NOW"][:max_candidates]
    wait = [c for c in candidates if c.get("verdict") == "DEEP_REVIEW_WAIT_ENTRY"][:max_candidates]
    watch = [c for c in candidates if c.get("verdict") == "WATCH_ONLY"][:max_candidates]
    queue = auto + wait[: max(0, max_candidates - len(auto))]
    return {
        "schema": "deep_review_queue_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "available" if queue or watch else "empty",
        "max_candidates": max_candidates,
        "auto_governed_candidates": auto,
        "candidates": queue[:max_candidates],
        "watch_only": watch,
        "policy": {
            "DEEP_REVIEW_NOW": "自动进入 governed 个股分析候选。",
            "DEEP_REVIEW_WAIT_ENTRY": "值得跟踪，但等待承接/证据确认，不追高。",
            "WATCH_ONLY": "只展示，不深跑。",
        },
        "protected_writeback": False,
        "trade_execution": "disabled",
    }


def render_screening_funnel_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Screening Funnel",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Candidate count: `{payload.get('candidate_count')}`",
        "- Boundary: 候选池不是交易建议；热榜不能直接触发交易。",
        "",
        "| Symbol | Source | Score | Verdict | Evidence | Next action |",
        "|---|---|---:|---|---|---|",
    ]
    for row in payload.get("candidates") or []:
        lines.append(
            f"| `{row.get('symbol')}` | `{row.get('source')}` | {float(row.get('priority_score') or 0):.1f} | "
            f"`{row.get('verdict')}` | {', '.join(row.get('evidence') or [])} | {row.get('next_action')} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_deep_review_queue_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Deep Review Queue",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Max candidates: `{payload.get('max_candidates')}`",
        f"- Auto governed candidates: `{len(payload.get('auto_governed_candidates') or [])}`",
        "- Boundary: 深评队列不是交易建议；交易仍需 RedBlue / Scoring / CIO / 人工确认。",
        "",
        "| Symbol | Verdict | Price risk | Evidence | Next action |",
        "|---|---|---|---|---|",
    ]
    for row in payload.get("candidates") or []:
        lines.append(
            f"| `{row.get('symbol')}` | `{row.get('verdict')}` | `{row.get('price_risk')}` | "
            f"{', '.join(row.get('evidence') or [])} | {row.get('next_action')} |"
        )
    if not payload.get("candidates"):
        lines.append("| - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def render_preliminary_deep_review_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Preliminary Deep Review Summary",
        "",
        "- Boundary: 第一轮自动重评摘要，不是买卖建议。",
        "",
        "## 直接结论",
        "",
    ]
    auto = payload.get("auto_governed_candidates") or []
    if auto:
        lines.append(f"- `{len(auto)}` 只候选满足 `DEEP_REVIEW_NOW`，可进入 governed 深评。")
    elif payload.get("candidates"):
        lines.append("- 当前候选多为等待承接/证据确认，不应追高。")
    else:
        lines.append("- 暂无深评候选。")
    lines.extend(["", "## 候选摘要", "", "| Symbol | Bull / why care | Bear / what can go wrong | Next action |", "|---|---|---|---|"])
    for row in payload.get("candidates") or []:
        bull = "有市场/宏观/事件线索，需读原文确认。"
        bear = "若只有热度或数据源降级，不能升级为交易机会。"
        lines.append(f"| `{row.get('symbol')}` | {bull} | {bear} | {row.get('next_action')} |")
    if not payload.get("candidates"):
        lines.append("| - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def render_screening_funnel_html(payload: Dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(row.get('symbol')))}</td><td>{html.escape(str(row.get('source')))}</td>"
        f"<td>{float(row.get('priority_score') or 0):.1f}</td><td>{html.escape(str(row.get('verdict')))}</td>"
        f"<td>{html.escape(str(row.get('next_action')))}</td></tr>"
        for row in payload.get("candidates") or []
    ) or "<tr><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>"
    return f"<section class='hero'><div><span class='label'>Screening Funnel</span><h1>{html.escape(str(payload.get('status')))}</h1><p>候选池不是交易建议。</p></div></section><section class='card'><table><thead><tr><th>Symbol</th><th>Source</th><th>Score</th><th>Verdict</th><th>Next action</th></tr></thead><tbody>{rows}</tbody></table></section>"


def render_deep_review_queue_html(payload: Dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(row.get('symbol')))}</td><td>{html.escape(str(row.get('verdict')))}</td>"
        f"<td>{html.escape(str(row.get('price_risk')))}</td><td>{html.escape(str(row.get('next_action')))}</td></tr>"
        for row in payload.get("candidates") or []
    ) or "<tr><td>-</td><td>-</td><td>-</td><td>-</td></tr>"
    return f"<section class='hero'><div><span class='label'>Deep Review Queue</span><h1>{len(payload.get('candidates') or [])}</h1><p>最多 6 只；先筛选再深评。</p></div></section><section class='card'><table><thead><tr><th>Symbol</th><th>Verdict</th><th>Price risk</th><th>Next action</th></tr></thead><tbody>{rows}</tbody></table></section>"


def _candidate(
    *,
    symbol: str,
    name: str,
    source: str,
    base_score: float,
    evidence: List[str],
    verdict: str,
    price_risk: str,
    next_action: str,
) -> Dict[str, Any]:
    evidence_quality = "HIGH_OFFICIAL_EVIDENCE" if any("official" in e or "announcement" in e for e in evidence) else "MEDIUM_MIXED_EVIDENCE" if source != "watchlist" else "LOW_WATCHLIST_EVIDENCE"
    return {
        "symbol": symbol,
        "name": name,
        "source": source,
        "priority_score": float(base_score),
        "evidence_quality": evidence_quality,
        "evidence": evidence,
        "verdict": verdict,
        "price_risk": price_risk,
        "next_action": next_action,
        "trade_execution": "disabled",
    }
