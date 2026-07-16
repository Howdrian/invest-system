# -*- coding: utf-8 -*-
"""Macro/geopolitical review builder for daily market-cycle reports."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def build_macro_review(
    *,
    run_date: str,
    macro_context: Optional[Dict[str, Any]],
    market_heat: Optional[Dict[str, Any]] = None,
    prediction_market: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    macro = macro_context if isinstance(macro_context, dict) else {}
    heat = market_heat if isinstance(market_heat, dict) else {}
    pm = prediction_market if isinstance(prediction_market, dict) else {}
    warnings = list(macro.get("warnings") or [])
    if pm and str(pm.get("status") or "").lower() != "available":
        warnings.append("prediction_market_optional_degraded")
    elif not pm:
        warnings.append("prediction_market_missing")

    regime = _build_regime(macro)
    dimensions = _build_dimensions(macro, heat)
    geopolitical = _build_geopolitical_scenarios(pm)
    data_gaps = _data_gaps(macro, pm)
    status = "REFRESHED" if str(macro.get("status") or "").upper() == "REFRESHED" else "DEGRADED"
    confidence = _confidence(regime, data_gaps)
    headline = _headline(regime)
    asset_implications = _asset_implications(regime, geopolitical)
    red_team_flags = [
        f"{item.get('label')}: prediction_market_gap"
        for item in geopolitical
        if item.get("red_team_trigger")
    ]

    return {
        "schema": "macro_review_v1",
        "run_date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "headline": headline,
        "confidence": confidence,
        "macro_dimensions": dimensions,
        "six_factor_regime": regime,
        "geopolitical_scenarios": geopolitical,
        "prediction_market_status": pm.get("status") or "MISSING",
        "prediction_market_policy": {
            "high_quality_weight": 0.25,
            "medium_quality_weight": 0.15,
            "max_weight": 0.30,
            "low_quality": "observe_only",
            "score_gate_bypass": False,
            "trade_execution": "disabled",
        },
        "asset_implications": asset_implications,
        "portfolio_and_candidate_implications": [
            "持仓每日轻量复核；只有公告、价格、宏观或风险触发时进入 governed 深评。",
            "宏观和地缘只能调整风险预算、候选优先级和红队问题，不能直接触发交易。",
        ],
        "red_team_flags": red_team_flags,
        "data_gaps": data_gaps,
        "warnings": warnings,
        "protected_writeback": False,
        "trade_execution": "disabled",
    }


def build_event_context(
    *,
    macro_review: Optional[Dict[str, Any]] = None,
    market_heat: Optional[Dict[str, Any]] = None,
    prediction_market: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    heat = market_heat if isinstance(market_heat, dict) else {}
    pm = prediction_market if isinstance(prediction_market, dict) else {}
    macro = macro_review if isinstance(macro_review, dict) else {}
    events: List[Dict[str, Any]] = []
    for item in heat.get("focus_items") or []:
        symbol = item.get("symbol") or item.get("code")
        if symbol:
            events.append({
                "source": "market_heat",
                "symbol": symbol,
                "event_type": item.get("heat_bucket") or "watch",
                "summary": item.get("reason") or "watchlist_member",
                "severity_hint": "low",
            })
    for item in pm.get("scenario_fusion") or []:
        events.append({
            "source": "prediction_market",
            "event_type": item.get("scenario_id"),
            "summary": item.get("label"),
            "market_probability": item.get("market_probability"),
            "fused_probability": item.get("fused_probability"),
            "red_team_trigger": bool(item.get("red_team_trigger")),
            "severity_hint": "medium" if item.get("red_team_trigger") else "low",
        })
    return {
        "schema": "event_context_v1",
        "status": "available" if events else "degraded",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_headline": macro.get("headline"),
        "events": events[:80],
        "policy": "共享事件包；Risk 可独立评估严重度，不依赖 Intel 结论。",
    }


def _build_regime(macro: Dict[str, Any]) -> Dict[str, Any]:
    compact_regime = macro.get("regime") if isinstance(macro.get("regime"), dict) else {}
    risk_state = str(compact_regime.get("risk_state") or "unknown").lower()
    confidence = str(compact_regime.get("confidence") or "low").lower()
    reason = compact_regime.get("reason") or "macro data degraded"
    components = macro.get("components") if isinstance(macro.get("components"), dict) else {}
    fmp = components.get("fmp") if isinstance(components.get("fmp"), dict) else {}
    data = fmp.get("data") if isinstance(fmp.get("data"), list) else []
    price_map = {str(row.get("symbol") or row.get("name") or "").upper(): row for row in data if isinstance(row, dict)}
    market_proxy_factors = {
        "market_concentration": _factor_from_index(price_map, "^GSPC"),
        "credit_conditions": _factor_from_pair(price_map, "HYG", "LQD", "high_yield_vs_ig_credit_proxy"),
        "size_factor": _factor_from_pair(price_map, "IWM", "SPY", "small_vs_large_cap_proxy"),
        "equity_bond": _factor_from_pair(price_map, "SPY", "TLT", "equity_vs_long_duration_bond_proxy"),
        "sector_rotation": _factor_from_pair(price_map, "XLY", "XLP", "cyclical_vs_defensive_proxy"),
        "volatility": _factor_from_index(price_map, "^VIX"),
    }

    fred = components.get("fred") if isinstance(components.get("fred"), dict) else {}
    fred_by_factor = _fred_by_factor(fred)
    official_macro_factors = {
        "growth": _factor_from_fred(fred_by_factor, "growth", "增长"),
        "inflation": _factor_from_fred(fred_by_factor, "inflation", "通胀"),
        "liquidity_rates": _factor_from_fred(fred_by_factor, "liquidity_rates", "利率与流动性"),
        "credit": _factor_from_fred(fred_by_factor, "credit", "信用条件"),
        "risk_appetite": _factor_from_fred(fred_by_factor, "risk_appetite", "风险偏好"),
        "energy_geo": _factor_from_fred(fred_by_factor, "energy_geo", "能源与地缘"),
    }

    official_missing = [k for k, v in official_macro_factors.items() if v.get("status") == "missing"]
    proxy_missing = [k for k, v in market_proxy_factors.items() if v.get("status") == "missing"]
    if len(official_missing) < len(proxy_missing):
        factor_set = "official_macro_factors"
        six_factors = official_macro_factors
        missing = official_missing
        boundary = "FRED 官方六类宏观因子优先；FMP/ETF 代理因子仅作可选增强。"
    else:
        factor_set = "market_proxy_six_factors"
        six_factors = market_proxy_factors
        missing = proxy_missing
        boundary = "FMP/ETF 代理因子可用时展示；缺项不代表 FRED 官方宏观缺失。"

    return {
        "risk_state": risk_state,
        "confidence": confidence,
        "reason": reason,
        "classification": _classification(risk_state),
        "factor_set": factor_set,
        "six_factor_status": "DEGRADED" if missing else "REFRESHED",
        "factors": six_factors,
        "missing_factors": missing,
        "boundary": boundary,
    }


def _factor_from_index(price_map: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any]:
    row = price_map.get(key)
    if not row:
        return {"status": "missing", "note": f"{key} missing"}
    return {
        "status": "available",
        "symbol": row.get("symbol"),
        "price": row.get("price"),
        "change_percentage": row.get("changePercentage"),
        "price_avg_50": row.get("priceAvg50"),
        "price_avg_200": row.get("priceAvg200"),
    }


def _factor_from_pair(price_map: Dict[str, Dict[str, Any]], numerator: str, denominator: str, label: str) -> Dict[str, Any]:
    left = price_map.get(numerator)
    right = price_map.get(denominator)
    if not left or not right:
        missing = numerator if not left else denominator
        return {"status": "missing", "note": f"{missing} missing for {label}"}
    left_price = _to_float(left.get("price"))
    right_price = _to_float(right.get("price"))
    left_change = _to_float(left.get("changePercentage"))
    right_change = _to_float(right.get("changePercentage"))
    ratio = (left_price / right_price) if left_price is not None and right_price not in {None, 0} else None
    spread = (left_change - right_change) if left_change is not None and right_change is not None else None
    return {
        "status": "available",
        "proxy": label,
        "numerator": numerator,
        "denominator": denominator,
        "ratio": ratio,
        "change_spread": spread,
    }


def _factor_from_fred(fred_by_factor: Dict[str, List[Dict[str, Any]]], factor: str, label: str) -> Dict[str, Any]:
    rows = fred_by_factor.get(factor) or []
    if not rows:
        return {"status": "missing", "note": f"FRED {factor} missing"}
    evidence = _fred_evidence(rows)
    return {
        "status": "available",
        "source": "FRED",
        "label": label,
        "series": rows,
        "evidence": evidence,
    }


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classification(risk_state: str) -> str:
    if risk_state == "risk_on":
        return "risk_on_watch"
    if risk_state == "risk_off":
        return "defensive"
    if risk_state == "neutral":
        return "neutral_watch"
    return "unknown_degraded"


def _build_dimensions(macro: Dict[str, Any], heat: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    components = macro.get("components") if isinstance(macro.get("components"), dict) else {}
    fmp = components.get("fmp") if isinstance(components.get("fmp"), dict) else {}
    official = components.get("official_calendar") if isinstance(components.get("official_calendar"), dict) else {}
    fred = components.get("fred") if isinstance(components.get("fred"), dict) else {}
    fred_by_factor = _fred_by_factor(fred)
    return {
        "growth": {
            "status": "available_limited" if fred_by_factor.get("growth") else "degraded",
            "signal": "official_series" if fred_by_factor.get("growth") else "unknown",
            "evidence": _fred_evidence(fred_by_factor.get("growth")) or "GDP/PMI/employment official extensions not yet fully wired in invest-system.",
        },
        "inflation": {
            "status": "available_limited" if fred_by_factor.get("inflation") else "degraded",
            "signal": "official_series" if fred_by_factor.get("inflation") else "unknown",
            "evidence": _fred_evidence(fred_by_factor.get("inflation")) or "CPI/PCE/EIA/FRED extension points pending; use original 投研 source as migration reference.",
        },
        "rates_liquidity": {
            "status": "available_limited" if fred_by_factor.get("liquidity_rates") or official else "degraded",
            "signal": "neutral_or_unknown",
            "evidence": _fred_evidence(fred_by_factor.get("liquidity_rates")) or official.get("note") or "Treasury/Fed/BLS details pending.",
        },
        "energy_commodities": {
            "status": "available_limited" if fred_by_factor.get("energy_geo") else "degraded",
            "signal": "watch",
            "evidence": _fred_evidence(fred_by_factor.get("energy_geo")) or "WTI/EIA/FRED not fully wired; Polymarket energy scenarios can only be optional hints.",
        },
        "usd_fx": {
            "status": "missing",
            "signal": "unknown",
            "evidence": "DXY/USD/CNH not wired in v1.",
        },
        "risk_appetite": {
            "status": fmp.get("status") or "degraded",
            "signal": (macro.get("regime") or {}).get("risk_state") if isinstance(macro.get("regime"), dict) else "unknown",
            "evidence": (macro.get("regime") or {}).get("reason") if isinstance(macro.get("regime"), dict) else "macro data degraded",
        },
        "market_heat": {
            "status": heat.get("status") or "unavailable",
            "signal": "watchlist_or_hotspot",
            "evidence": f"focus_items={len(heat.get('focus_items') or [])}",
        },
    }


def _fred_by_factor(fred: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    series = fred.get("series") if isinstance(fred.get("series"), list) else []
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in series:
        if not isinstance(row, dict):
            continue
        factor = str(row.get("factor") or "")
        if not factor:
            continue
        out.setdefault(factor, []).append(row)
    return out


def _fred_evidence(rows: Optional[List[Dict[str, Any]]]) -> str:
    if not rows:
        return ""
    parts = []
    for row in rows[:3]:
        parts.append(f"{row.get('series_id')}={row.get('value')}@{row.get('date')}")
    return "FRED " + ", ".join(parts)


def _build_geopolitical_scenarios(pm: Dict[str, Any]) -> List[Dict[str, Any]]:
    fusion = pm.get("scenario_fusion") if isinstance(pm.get("scenario_fusion"), list) else []
    by_id = {item.get("scenario_id"): item for item in fusion if isinstance(item, dict)}
    defaults = [
        ("A_controlled_deescalation", "A 管控下降", 0.30, "冲突可控、缓慢修复；避险资产逐步降权。"),
        ("B_crisis_cascade", "B 危机级联", 0.40, "多点冲突或供应链断裂；商品、黄金、能源风险预算上升。"),
        ("C_great_power_conflict", "C 大国冲突", 0.20, "直接军事对抗；全面 risk-off。"),
        ("D_nuclear_tail", "D 核武尾部", 0.10, "极端尾部；现金、实物黄金和流动性优先。"),
    ]
    output: List[Dict[str, Any]] = []
    geo_energy = by_id.get("geopolitics_energy") or {}
    geo_semis = by_id.get("geopolitics_semis") or {}
    nuclear = by_id.get("nuclear_geopolitics") or {}
    adjustments = {
        "A_controlled_deescalation": geo_energy,
        "B_crisis_cascade": geo_energy,
        "C_great_power_conflict": geo_semis,
        "D_nuclear_tail": nuclear,
    }
    for scenario_id, label, p_internal, implication in defaults:
        pm_item = adjustments.get(scenario_id) or {}
        output.append({
            "scenario_id": scenario_id,
            "label": label,
            "internal_probability": p_internal,
            "market_probability": pm_item.get("market_probability"),
            "fusion_weight": pm_item.get("fusion_weight", 0.0),
            "fused_probability": pm_item.get("fused_probability", p_internal),
            "red_team_trigger": bool(pm_item.get("red_team_trigger")),
            "implication": implication,
            "probability_note": "主观估计精度不超过 ±15pp；排序比数字更重要。",
        })
    return output


def _data_gaps(macro: Dict[str, Any], pm: Dict[str, Any]) -> List[str]:
    gaps: List[str] = []
    if not macro or str(macro.get("status") or "").upper() != "REFRESHED":
        gaps.append("macro_context_not_refreshed")
    regime = _build_regime(macro)
    for item in regime.get("missing_factors") or []:
        gaps.append(f"six_factor_missing:{item}")
    pm_status = str(pm.get("status") or "").lower()
    if pm_status == "available_no_matching_market" or pm.get("scenario_coverage_status") == "available_no_matching_market":
        gaps.append("prediction_market_available_no_matching_market")
    if not pm or pm_status != "available":
        gaps.append("prediction_market_optional_missing_or_degraded")
    return gaps


def _confidence(regime: Dict[str, Any], gaps: List[str]) -> str:
    if str(regime.get("confidence") or "").lower() == "medium" and len(gaps) <= 2:
        return "MEDIUM"
    if len(gaps) > 5:
        return "LOW"
    return "LOW_TO_MEDIUM"


def _headline(regime: Dict[str, Any]) -> str:
    state = regime.get("risk_state")
    reason = regime.get("reason") or ""
    if state == "risk_on":
        return f"风险偏好偏强，但仍需候选证据确认；{reason}"
    if state == "risk_off":
        return f"风险偏好偏弱，优先防守和等待确认；{reason}"
    if state == "neutral":
        return f"宏观中性，等待价格和证据共振；{reason}"
    return f"宏观降级，不能作为满血 Regime；{reason}"


def _asset_implications(regime: Dict[str, Any], geopolitical: List[Dict[str, Any]]) -> List[str]:
    implications = []
    state = regime.get("risk_state")
    if state == "risk_on":
        implications.append("可观察高质量成长/科技候选，但不得追高或跳过评分。")
    elif state == "risk_off":
        implications.append("降低高 beta 暴露，优先现金、低波动和防御资产。")
    else:
        implications.append("维持观察，等待宏观、板块和个股证据共振。")
    if any(item.get("red_team_trigger") for item in geopolitical):
        implications.append("地缘/预测市场概率差异触发红队复核，相关板块进入风险清单。")
    implications.append("Polymarket 和宏观只影响候选优先级、风险预算和红队问题，不直接交易。")
    return implications


def render_macro_review_md(payload: Dict[str, Any]) -> str:
    lines = [
        f"# Macro Review — {payload.get('run_date')}",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Confidence: `{payload.get('confidence')}`",
        f"- Prediction market: `{payload.get('prediction_market_status')}`",
        "- Boundary: review-only; no trade execution; no scoring gate bypass.",
        "",
        "## 主结论",
        "",
        str(payload.get("headline") or ""),
        "",
        "## 宏观四维度 / 风险温度",
        "",
        "| Dimension | Status | Signal | Evidence |",
        "|---|---|---|---|",
    ]
    for name, item in (payload.get("macro_dimensions") or {}).items():
        lines.append(f"| `{name}` | `{item.get('status')}` | `{item.get('signal')}` | {item.get('evidence')} |")
    regime = payload.get("six_factor_regime") or {}
    lines.extend([
        "",
        "## 6 因子 Regime",
        "",
        f"- Risk state: `{regime.get('risk_state')}`",
        f"- Six-factor status: `{regime.get('six_factor_status')}`",
        f"- Reason: {regime.get('reason')}",
        f"- Boundary: {regime.get('boundary')}",
        "",
        "## 地缘四场景 / Polymarket 融合",
        "",
        "| Scenario | Internal | Market | Weight | Fused | Red Team |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for item in payload.get("geopolitical_scenarios") or []:
        mp = item.get("market_probability")
        lines.append(
            f"| {item.get('label')} | {float(item.get('internal_probability') or 0) * 100:.1f}% | "
            f"{('-' if mp is None else f'{float(mp) * 100:.1f}%')} | {float(item.get('fusion_weight') or 0) * 100:.0f}% | "
            f"{float(item.get('fused_probability') or 0) * 100:.1f}% | `{item.get('red_team_trigger')}` |"
        )
    lines.extend(["", "## 对资产/候选池影响", ""])
    lines.extend(f"- {item}" for item in payload.get("asset_implications") or [])
    if payload.get("data_gaps"):
        lines.extend(["", "## Data gaps", ""])
        lines.extend(f"- `{gap}`" for gap in payload.get("data_gaps") or [])
    lines.append("")
    return "\n".join(lines)


def render_macro_review_html(payload: Dict[str, Any]) -> str:
    body = [
        "<section class='hero'><div><span class='label'>Macro Review</span>",
        f"<h1>{html.escape(str(payload.get('status')))}</h1>",
        f"<p>{html.escape(str(payload.get('headline') or ''))}</p></div>",
        f"<div class='kpi'><small>Confidence</small><b>{html.escape(str(payload.get('confidence')))}</b></div>",
        f"<div class='kpi'><small>Polymarket</small><b>{html.escape(str(payload.get('prediction_market_status')))}</b></div></section>",
        "<section class='card'><h2>宏观四维度 / 风险温度</h2><table><thead><tr><th>Dimension</th><th>Status</th><th>Signal</th><th>Evidence</th></tr></thead><tbody>",
    ]
    for name, item in (payload.get("macro_dimensions") or {}).items():
        body.append(
            f"<tr><td>{html.escape(str(name))}</td><td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{html.escape(str(item.get('signal')))}</td><td>{html.escape(str(item.get('evidence')))}</td></tr>"
        )
    body.append("</tbody></table></section>")
    body.append("<section class='card'><h2>地缘四场景 / Polymarket 融合</h2><table><thead><tr><th>Scenario</th><th>Internal</th><th>Market</th><th>Weight</th><th>Fused</th><th>Red Team</th></tr></thead><tbody>")
    for item in payload.get("geopolitical_scenarios") or []:
        mp = item.get("market_probability")
        body.append(
            f"<tr><td>{html.escape(str(item.get('label')))}</td>"
            f"<td>{float(item.get('internal_probability') or 0) * 100:.1f}%</td>"
            f"<td>{html.escape('-' if mp is None else f'{float(mp) * 100:.1f}%')}</td>"
            f"<td>{float(item.get('fusion_weight') or 0) * 100:.0f}%</td>"
            f"<td>{float(item.get('fused_probability') or 0) * 100:.1f}%</td>"
            f"<td>{html.escape(str(item.get('red_team_trigger')))}</td></tr>"
        )
    body.append("</tbody></table></section>")
    body.append("<section class='card'><h2>边界</h2><ul><li>只读宏观/地缘分析。</li><li>不能单独触发交易。</li><li>不能单独让评分越过 6.0。</li></ul></section>")
    return "".join(body)
