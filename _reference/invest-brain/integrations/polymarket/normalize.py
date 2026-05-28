from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import math

try:
    from schemas import MarketSource, OrderBookSnapshot, PredictionMarketSignal, utc_now
except ImportError:  # pragma: no cover
    from .schemas import MarketSource, OrderBookSnapshot, PredictionMarketSignal, utc_now

CATEGORY_KEYWORDS = {
    "fed": "rates",
    "fomc": "rates",
    "rate": "rates",
    "hormuz": "geopolitics_energy",
    "iran": "geopolitics_energy",
    "ukraine": "geopolitics",
    "russia": "geopolitics",
    "taiwan": "geopolitics_semis",
    "china": "geopolitics_semis",
    "oil": "energy",
    "crude": "energy",
    "wti": "energy",
    "gold": "gold",
    "nuclear": "nuclear_geopolitics",
    "recession": "macro_growth",
}


def parse_array(value: Any) -> list[Any]:
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


def fnum(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def infer_category(question: str, event_title: str | None = None, keywords: list[str] | None = None) -> str:
    text = " ".join([question or "", event_title or "", " ".join(keywords or [])]).lower()
    for key, category in CATEGORY_KEYWORDS.items():
        if key in text:
            return category
    return "other"


def best_level(levels: list[dict[str, Any]], side: str) -> dict[str, Any] | None:
    if not levels:
        return None
    try:
        if side == "bid":
            return max(levels, key=lambda item: float(item.get("price", 0)))
        return min(levels, key=lambda item: float(item.get("price", 1)))
    except Exception:
        return levels[0]


def orderbook_snapshot(book: dict[str, Any] | None = None, buy_price: Any = None, sell_price: Any = None) -> OrderBookSnapshot:
    bid = fnum(sell_price)
    ask = fnum(buy_price)
    bid_size = None
    ask_size = None
    book_hash = None

    if isinstance(book, dict) and book:
        bid_level = best_level(book.get("bids") or [], "bid")
        ask_level = best_level(book.get("asks") or [], "ask")
        if bid_level:
            bid = fnum(bid_level.get("price"), bid)
            bid_size = fnum(bid_level.get("size"))
        if ask_level:
            ask = fnum(ask_level.get("price"), ask)
            ask_size = fnum(ask_level.get("size"))
        book_hash = book.get("hash")

    mid = None
    spread = None
    if bid is not None and ask is not None:
        mid = round((bid + ask) / 2, 6)
        spread = round(max(0.0, ask - bid), 6)

    return OrderBookSnapshot(
        bid=bid,
        ask=ask,
        mid=mid,
        spread=spread,
        bid_size=bid_size,
        ask_size=ask_size,
        book_hash=book_hash,
        retrieved_at=utc_now(),
    )


def yes_probability(outcomes: list[Any], prices: list[Any], book: OrderBookSnapshot | None = None) -> float | None:
    if book and book.mid is not None:
        return book.mid
    normalized_outcomes = [str(item) for item in outcomes]
    if "Yes" in normalized_outcomes:
        idx = normalized_outcomes.index("Yes")
        if idx < len(prices):
            return fnum(prices[idx])
    return None


def days_to_end(end_date: str | None) -> float | None:
    if not end_date:
        return None
    value = end_date.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - datetime.now(timezone.utc)).total_seconds() / 86400


def quality_score(signal: PredictionMarketSignal) -> tuple[float, list[str]]:
    score = 0.0
    notes: list[str] = []

    if signal.liquidity >= 100_000:
        score += 2
    elif signal.liquidity >= 25_000:
        score += 1
    else:
        notes.append("low liquidity")

    if signal.volume_24h >= 100_000:
        score += 2
    elif signal.volume_24h >= 10_000:
        score += 1
    else:
        notes.append("low 24h volume")

    spread = signal.orderbook.spread
    if spread is not None and spread <= 0.02:
        score += 2
    elif spread is not None and spread <= 0.05:
        score += 1
    else:
        notes.append("wide or missing spread")

    if signal.question.endswith("?") and signal.end_date:
        score += 2
    elif signal.end_date:
        score += 1
    else:
        notes.append("unclear or missing end date")

    horizon = days_to_end(signal.end_date)
    if horizon is not None and 0 <= horizon <= 370:
        score += 1
    elif horizon is not None and horizon > 370:
        notes.append("long horizon")
    else:
        notes.append("expired or unknown horizon")

    if signal.event_category in {"rates", "energy", "geopolitics_energy", "geopolitics", "geopolitics_semis", "macro_growth", "nuclear_geopolitics"}:
        score += 1

    return min(score, 10.0), notes


def quality_bucket(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def recommended_weight(score: float) -> float:
    if score >= 8:
        return 0.25
    if score >= 5:
        return 0.15
    if score > 0:
        return 0.05
    return 0.0


def normalize_market(
    event: dict[str, Any],
    market: dict[str, Any],
    *,
    keywords: list[str] | None = None,
    book: dict[str, Any] | None = None,
    buy_price: Any = None,
    sell_price: Any = None,
    recent_trades: list[dict[str, Any]] | None = None,
) -> PredictionMarketSignal:
    outcomes = [str(item) for item in parse_array(market.get("outcomes"))]
    prices = [fnum(item, 0.0) or 0.0 for item in parse_array(market.get("outcomePrices"))]
    snapshot = orderbook_snapshot(book, buy_price=buy_price, sell_price=sell_price)
    question = str(market.get("question") or "")
    event_title = event.get("title")
    source = MarketSource(
        event_id=str(event.get("id")) if event.get("id") is not None else None,
        market_id=str(market.get("id")) if market.get("id") is not None else None,
        condition_id=market.get("conditionId"),
        slug=market.get("slug"),
        url=f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
    )
    signal = PredictionMarketSignal(
        source=source,
        question=question,
        event_title=event_title,
        event_category=infer_category(question, event_title, keywords),
        yes_probability=yes_probability(outcomes, prices, snapshot),
        outcome_prices=prices,
        outcomes=outcomes,
        volume=fnum(market.get("volume"), 0.0) or 0.0,
        volume_24h=fnum(market.get("volume24hr"), 0.0) or 0.0,
        liquidity=fnum(market.get("liquidity"), 0.0) or 0.0,
        end_date=market.get("endDate"),
        updated_at=market.get("updatedAt"),
        active=bool(market.get("active")),
        closed=bool(market.get("closed")),
        accepting_orders=bool(market.get("acceptingOrders")),
        orderbook=snapshot,
        recent_trades=recent_trades or [],
    )
    score, notes = quality_score(signal)
    signal.quality_score = score
    signal.quality_bucket = quality_bucket(score)
    signal.recommended_weight = recommended_weight(score)
    signal.notes.extend(notes)
    if signal.yes_probability is None:
        signal.notes.append("missing yes probability")
    return signal


def market_has_yes_token(market: dict[str, Any]) -> str | None:
    outcomes = [str(item) for item in parse_array(market.get("outcomes"))]
    tokens = [str(item) for item in parse_array(market.get("clobTokenIds"))]
    if "Yes" not in outcomes:
        return None
    idx = outcomes.index("Yes")
    if idx >= len(tokens):
        return None
    return tokens[idx]


def is_live_market(market: dict[str, Any]) -> bool:
    return bool(market.get("active")) and not bool(market.get("closed")) and bool(market.get("acceptingOrders"))
