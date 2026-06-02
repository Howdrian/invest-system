# -*- coding: utf-8 -*-
"""Read-only Polymarket signal adapter for daily market-cycle reports.

The adapter is intentionally optional/fail-open. It converts prediction-market
quotes into auditable probability evidence; it never trades, writes portfolios,
or changes the local scoring gate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_OUTPUT_DIR = "reports/prediction_market"
DEFAULT_KEYWORDS = [
    "iran", "hormuz", "ukraine", "taiwan", "china", "fed", "fomc",
    "interest rates", "rate cut", "oil", "nuclear",
]
QUALITY_HIGH_WEIGHT = 0.25
QUALITY_MEDIUM_WEIGHT = 0.15
QUALITY_LOW_WEIGHT = 0.0
MAX_FUSION_WEIGHT = 0.30
GAMMA_BASE = "https://gamma-api.polymarket.com"


def build_prediction_market_snapshot(
    *,
    keywords: Optional[Iterable[str]] = None,
    live: bool = False,
    events: Optional[List[Dict[str, Any]]] = None,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Build a read-only prediction-market snapshot.

    ``live=False`` is deterministic and emits a degraded optional snapshot. Tests
    can pass ``events`` to exercise normalization without network access.
    """
    keyword_list = [str(k).strip() for k in (keywords or DEFAULT_KEYWORDS) if str(k).strip()]
    warnings: List[str] = []
    raw_events = events
    if raw_events is None and live:
        try:
            raw_events = _fetch_events(keyword_list, timeout_s=timeout_s)
        except Exception as exc:  # pragma: no cover - network-dependent
            raw_events = []
            warnings.append(f"polymarket_live_unavailable: {exc}")
    elif raw_events is None:
        raw_events = []
        warnings.append("polymarket_live_disabled")

    signals = _normalize_events(raw_events, keyword_list)
    high_quality = [s for s in signals if s.get("quality_bucket") == "high"]
    status = "available" if signals else "degraded"
    scenario_fusion = _build_scenario_fusion(signals)
    if any(item.get("red_team_trigger") for item in scenario_fusion):
        warnings.append("prediction_market_probability_gap_red_team_trigger")

    return {
        "schema": "prediction_market_signal_v1",
        "status": status,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "provider": "polymarket_readonly",
        "keywords": keyword_list,
        "signals": signals[:40],
        "high_quality_count": len(high_quality),
        "scenario_fusion": scenario_fusion,
        "usage_policy": {
            "high_quality_weight": QUALITY_HIGH_WEIGHT,
            "medium_quality_weight": QUALITY_MEDIUM_WEIGHT,
            "low_quality_weight": QUALITY_LOW_WEIGHT,
            "max_fusion_weight": MAX_FUSION_WEIGHT,
            "trade_execution": "disabled",
            "score_gate_bypass": False,
            "notes": [
                "Polymarket 只用于外部概率校准、catalyst clarity 和 Red Team 触发。",
                "不能单独触发交易，不能单独让评分越过 6.0。",
            ],
        },
        "warnings": warnings,
    }


def _fetch_events(keywords: List[str], *, timeout_s: float) -> List[Dict[str, Any]]:  # pragma: no cover - network-dependent
    events: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for keyword in keywords[:12]:
        query = urllib.parse.urlencode({"limit": 20, "active": "true", "closed": "false", "search": keyword})
        url = f"{GAMMA_BASE}/events?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "invest-system-polymarket-readonly/0.1"})
        with urllib.request.urlopen(req, timeout=timeout_s) as response:  # nosec - public read-only HTTPS endpoint
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, dict) else []
        for item in rows or []:
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("id") or item.get("slug") or item.get("title") or "")
            if event_id and event_id not in seen:
                seen.add(event_id)
                events.append(item)
    return events


def _normalize_events(events: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    for event in events:
        markets = event.get("markets") if isinstance(event.get("markets"), list) else []
        if not markets and _looks_like_market(event):
            markets = [event]
        for market in markets:
            if not isinstance(market, dict) or not _is_live_market(market):
                continue
            signal = _normalize_market(event, market, keywords)
            if signal.get("yes_probability") is not None:
                signals.append(signal)
    signals.sort(key=lambda item: (item.get("quality_score") or 0, item.get("volume_24h") or 0), reverse=True)
    return signals


def _looks_like_market(item: Dict[str, Any]) -> bool:
    return "outcomes" in item or "outcomePrices" in item or "question" in item


def _is_live_market(market: Dict[str, Any]) -> bool:
    if market.get("closed") is True:
        return False
    if market.get("active") is False:
        return False
    if market.get("acceptingOrders") is False:
        return False
    return True


def _normalize_market(event: Dict[str, Any], market: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
    outcomes = _parse_array(market.get("outcomes"))
    prices = [_to_float(x, 0.0) or 0.0 for x in _parse_array(market.get("outcomePrices"))]
    yes_prob = _yes_probability(outcomes, prices, market)
    question = str(market.get("question") or event.get("title") or "")
    spread = _spread(market)
    volume = _to_float(market.get("volume"), 0.0) or 0.0
    volume_24h = _to_float(market.get("volume24hr") or market.get("volume24h"), 0.0) or 0.0
    liquidity = _to_float(market.get("liquidity"), 0.0) or 0.0
    category = _infer_category(question, str(event.get("title") or ""), keywords)
    score, notes = _quality_score(
        active=_is_live_market(market),
        yes_probability=yes_prob,
        volume_24h=volume_24h,
        liquidity=liquidity,
        spread=spread,
        end_date=market.get("endDate"),
        category=category,
    )
    bucket = _quality_bucket(score)
    weight = _recommended_weight(score)
    return {
        "question": question,
        "event_title": event.get("title"),
        "event_category": category,
        "yes_probability": yes_prob,
        "outcomes": outcomes,
        "outcome_prices": prices,
        "spread": spread,
        "volume": volume,
        "volume_24h": volume_24h,
        "liquidity": liquidity,
        "end_date": market.get("endDate"),
        "url": _event_url(event),
        "quality_score": score,
        "quality_bucket": bucket,
        "recommended_weight": weight,
        "notes": notes,
    }


def _parse_array(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _yes_probability(outcomes: List[Any], prices: List[float], market: Dict[str, Any]) -> Optional[float]:
    for i, outcome in enumerate(outcomes):
        if str(outcome).lower() == "yes" and i < len(prices):
            return _clamp_probability(prices[i])
    for key in ("lastTradePrice", "bestAsk", "bestBid"):
        val = _to_float(market.get(key))
        if val is not None:
            return _clamp_probability(val)
    return None


def _spread(market: Dict[str, Any]) -> Optional[float]:
    bid = _to_float(market.get("bestBid") or market.get("sellPrice"))
    ask = _to_float(market.get("bestAsk") or market.get("buyPrice"))
    if bid is None or ask is None:
        return None
    return max(0.0, round(ask - bid, 6))


def _quality_score(
    *,
    active: bool,
    yes_probability: Optional[float],
    volume_24h: float,
    liquidity: float,
    spread: Optional[float],
    end_date: Any,
    category: str,
) -> tuple[float, List[str]]:
    score = 0.0
    notes: List[str] = []
    if active:
        score += 2
    else:
        notes.append("not live accepting")
    if yes_probability is not None:
        score += 1
    else:
        notes.append("missing yes probability")
    if liquidity >= 100_000:
        score += 2
    elif liquidity >= 10_000:
        score += 1
    else:
        notes.append("low liquidity")
    if volume_24h >= 100_000:
        score += 2
    elif volume_24h >= 10_000:
        score += 1
    else:
        notes.append("low 24h volume")
    if spread is not None and spread <= 0.02:
        score += 2
    elif spread is not None and spread <= 0.05:
        score += 1
    else:
        notes.append("wide or missing spread")
    if end_date:
        score += 1
    else:
        notes.append("unclear or missing end date")
    if category in {"rates", "energy", "geopolitics_energy", "geopolitics", "geopolitics_semis", "macro_growth", "nuclear_geopolitics"}:
        score += 1
    return min(score, 10.0), notes


def _quality_bucket(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _recommended_weight(score: float) -> float:
    if score >= 8:
        return QUALITY_HIGH_WEIGHT
    if score >= 5:
        return QUALITY_MEDIUM_WEIGHT
    return QUALITY_LOW_WEIGHT


def _infer_category(question: str, event_title: str, keywords: List[str]) -> str:
    text = " ".join([question, event_title, " ".join(keywords)]).lower()
    mapping = {
        "fed": "rates", "fomc": "rates", "rate": "rates",
        "hormuz": "geopolitics_energy", "iran": "geopolitics_energy",
        "ukraine": "geopolitics", "russia": "geopolitics",
        "taiwan": "geopolitics_semis", "china": "geopolitics_semis",
        "oil": "energy", "crude": "energy", "wti": "energy",
        "nuclear": "nuclear_geopolitics", "recession": "macro_growth",
    }
    for token, category in mapping.items():
        if token in text:
            return category
    return "other"


def _build_scenario_fusion(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scenarios = [
        {"id": "geopolitics_energy", "label": "地缘能源缓和/升级", "internal_probability": 0.35},
        {"id": "geopolitics_semis", "label": "台海/半导体地缘尾部", "internal_probability": 0.15},
        {"id": "rates", "label": "Fed 利率路径", "internal_probability": 0.50},
        {"id": "energy", "label": "油价尾部风险", "internal_probability": 0.20},
    ]
    output: List[Dict[str, Any]] = []
    for scenario in scenarios:
        candidates = [s for s in signals if s.get("event_category") == scenario["id"]]
        if not candidates:
            output.append({
                "scenario_id": scenario["id"],
                "label": scenario["label"],
                "status": "missing_market",
                "internal_probability": scenario["internal_probability"],
                "market_probability": None,
                "fusion_weight": 0.0,
                "fused_probability": scenario["internal_probability"],
                "red_team_trigger": False,
            })
            continue
        signal = candidates[0]
        p_market = signal.get("yes_probability")
        weight = min(MAX_FUSION_WEIGHT, float(signal.get("recommended_weight") or 0.0))
        fused = log_odds_fusion(scenario["internal_probability"], p_market, weight) if p_market is not None and weight > 0 else scenario["internal_probability"]
        gap = abs(float(p_market or 0) - scenario["internal_probability"]) if p_market is not None else 0.0
        output.append({
            "scenario_id": scenario["id"],
            "label": scenario["label"],
            "status": "fused" if weight > 0 else "observed_only",
            "question": signal.get("question"),
            "internal_probability": round(scenario["internal_probability"], 6),
            "market_probability": round(float(p_market), 6) if p_market is not None else None,
            "fusion_weight": round(weight, 6),
            "fused_probability": round(fused, 6),
            "red_team_trigger": gap >= 0.25 and weight > 0,
        })
    return output


def log_odds_fusion(p_internal: float, p_market: float, weight: float) -> float:
    w = min(MAX_FUSION_WEIGHT, max(0.0, float(weight)))
    return _sigmoid((1.0 - w) * _logit(p_internal) + w * _logit(p_market))


def _clamp_probability(value: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, float(value)))


def _logit(p: float) -> float:
    p = _clamp_probability(p)
    return math.log(p / (1.0 - p))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _event_url(event: Dict[str, Any]) -> Optional[str]:
    slug = event.get("slug")
    return f"https://polymarket.com/event/{slug}" if slug else None


def write_prediction_market_snapshot(payload: Dict[str, Any], output_dir: str = DEFAULT_OUTPUT_DIR) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "latest_prediction_market_signal.json"
    md_path = out / "latest_prediction_market_signal.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_prediction_market_md(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def load_latest_prediction_market(output_dir: str = DEFAULT_OUTPUT_DIR) -> Optional[Dict[str, Any]]:
    path = Path(output_dir) / "latest_prediction_market_signal.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _render_prediction_market_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Prediction Market Signal",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Provider: `{payload.get('provider')}`",
        "- Boundary: 只读概率校准；不交易；不能单独越过 6.0。",
        "",
        "## 高质量市场",
        "",
        "| Market | YES | Quality | Bucket | Weight |",
        "|---|---:|---:|---|---:|",
    ]
    for item in payload.get("signals") or []:
        if item.get("quality_bucket") != "high":
            continue
        prob = item.get("yes_probability")
        prob_text = "-" if prob is None else f"{float(prob) * 100:.1f}%"
        lines.append(
            f"| {item.get('question') or '-'} | {prob_text} | `{item.get('quality_score')}` | "
            f"`{item.get('quality_bucket')}` | `{item.get('recommended_weight')}` |"
        )
    if not any((item.get("quality_bucket") == "high") for item in payload.get("signals") or []):
        lines.append("| - | - | - | - | - |")
    lines.extend(["", "## 融合场景", "", "| Scenario | Internal | Market | Weight | Final | Red Team |", "|---|---:|---:|---:|---:|---|"])
    for item in payload.get("scenario_fusion") or []:
        mp = item.get("market_probability")
        lines.append(
            f"| {item.get('label')} | {float(item.get('internal_probability') or 0) * 100:.1f}% | "
            f"{('-' if mp is None else f'{float(mp) * 100:.1f}%')} | {float(item.get('fusion_weight') or 0) * 100:.0f}% | "
            f"{float(item.get('fused_probability') or 0) * 100:.1f}% | `{item.get('red_team_trigger')}` |"
        )
    if payload.get("warnings"):
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {w}" for w in payload.get("warnings") or [])
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only Polymarket prediction-market snapshot")
    parser.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS), help="Comma-separated keywords")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--live", action="store_true", help="Fetch public Polymarket APIs")
    args = parser.parse_args(argv)
    keywords = [s.strip() for s in args.keywords.split(",") if s.strip()]
    payload = build_prediction_market_snapshot(keywords=keywords, live=args.live)
    paths = write_prediction_market_snapshot(payload, args.output_dir)
    print(json.dumps({"status": payload.get("status"), "warnings": payload.get("warnings"), "paths": paths}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
