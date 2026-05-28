from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json

try:
    from client import PolymarketAPIError, PolymarketClient
    from normalize import is_live_market, market_has_yes_token, normalize_market
    from report import render_markdown
    from schemas import PULSE_PATH, SignalRun, archive_dir_for, utc_now, write_json_safe, write_text_safe
except ImportError:  # pragma: no cover
    from .client import PolymarketAPIError, PolymarketClient
    from .normalize import is_live_market, market_has_yes_token, normalize_market
    from .report import render_markdown
    from .schemas import PULSE_PATH, SignalRun, archive_dir_for, utc_now, write_json_safe, write_text_safe

DEFAULT_KEYWORDS = [
    "iran",
    "hormuz",
    "ukraine",
    "taiwan",
    "china",
    "fed",
    "fomc",
    "interest rates",
    "rate cut",
    "fed funds",
    "recession",
    "oil",
    "crude oil",
    "nuclear",
]


def _event_score(stub: dict[str, Any]) -> float:
    def f(x: Any) -> float:
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0
    return f(stub.get("volume24hr")) * 10 + f(stub.get("volume")) + f(stub.get("liquidity"))


def collect_signals(
    *,
    keywords: list[str],
    search_limit: int,
    max_events: int,
    max_markets: int,
    enrich_limit: int,
    client: PolymarketClient | None = None,
) -> tuple[list[Any], list[dict[str, Any]], list[str], list[str]]:
    client = client or PolymarketClient()
    event_candidates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []

    for keyword in keywords:
        try:
            payload = client.public_search(keyword, limit=search_limit)
        except PolymarketAPIError as exc:
            warnings.append(f"search failed for {keyword}: {exc}")
            continue
        for event in payload.get("events") or []:
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            record = event_candidates.setdefault(
                event_id,
                {"id": event_id, "keywords": set(), "stub": event},
            )
            record["keywords"].add(keyword)

    selected_events = sorted(event_candidates.values(), key=lambda item: _event_score(item["stub"]), reverse=True)[:max_events]
    raw_markets: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    for item in selected_events:
        event_id = item["id"]
        keywords_for_event = sorted(item["keywords"])
        try:
            event = client.event(event_id)
        except PolymarketAPIError as exc:
            warnings.append(f"event fetch failed for {event_id}: {exc}")
            continue
        for market in event.get("markets") or []:
            question = market.get("question")
            if not is_live_market(market):
                rejected.append({"question": question, "event_title": event.get("title"), "reason": "not live accepting"})
                continue
            if not market_has_yes_token(market):
                rejected.append({"question": question, "event_title": event.get("title"), "reason": "no YES token"})
                continue
            raw_markets.append((event, market, keywords_for_event))

    def market_score(item: tuple[dict[str, Any], dict[str, Any], list[str]]) -> float:
        market = item[1]
        try:
            return float(market.get("volume24hr") or 0) * 10 + float(market.get("volume") or 0) + float(market.get("liquidity") or 0)
        except (TypeError, ValueError):
            return 0.0

    raw_markets = sorted(raw_markets, key=market_score, reverse=True)[:max_markets]
    signals = []
    for idx, (event, market, event_keywords) in enumerate(raw_markets):
        token = market_has_yes_token(market)
        book = None
        buy_price = None
        sell_price = None
        trades = []
        if token and idx < enrich_limit:
            try:
                buy_payload = client.price(token, "buy")
                sell_payload = client.price(token, "sell")
                buy_price = buy_payload.get("price") if isinstance(buy_payload, dict) else None
                sell_price = sell_payload.get("price") if isinstance(sell_payload, dict) else None
            except PolymarketAPIError as exc:
                warnings.append(f"price fetch failed for {market.get('question')}: {exc}")
            try:
                book = client.orderbook(token)
            except PolymarketAPIError as exc:
                warnings.append(f"book fetch failed for {market.get('question')}: {exc}")
            condition_id = market.get("conditionId")
            if condition_id:
                try:
                    trades = client.trades(condition_id, limit=5)
                except PolymarketAPIError as exc:
                    warnings.append(f"trades fetch failed for {market.get('question')}: {exc}")
        signal = normalize_market(
            event,
            market,
            keywords=event_keywords,
            book=book,
            buy_price=buy_price,
            sell_price=sell_price,
            recent_trades=trades,
        )
        if signal.quality_score <= 0 or signal.yes_probability is None:
            rejected.append({"question": signal.question, "event_title": signal.event_title, "reason": "; ".join(signal.notes)})
            continue
        signals.append(signal)
    return signals, rejected, warnings, [item["id"] for item in selected_events]


def run_scan(args: argparse.Namespace) -> int:
    keywords = args.keywords or DEFAULT_KEYWORDS
    signals, rejected, warnings, _event_ids = collect_signals(
        keywords=keywords,
        search_limit=args.search_limit,
        max_events=args.max_events,
        max_markets=args.max_markets,
        enrich_limit=args.enrich_limit,
    )
    run = SignalRun(
        schema="prediction_market_signal_run_v1",
        generated_at=utc_now(),
        analysis_date=args.analysis_date,
        topic=args.topic,
        keywords=keywords,
        signals=signals,
        rejected=rejected,
        sources=["gamma-api.polymarket.com", "clob.polymarket.com", "data-api.polymarket.com"],
        warnings=warnings,
    )
    out_dir = archive_dir_for(args.analysis_date, args.topic)
    write_json_safe(out_dir / "prediction_market_signal.json", run.to_dict())
    markdown = render_markdown(run, limit=args.report_limit)
    write_text_safe(out_dir / "prediction_market_signal.md", markdown)
    write_text_safe(out_dir / "summary.md", render_summary(run))
    if args.update_pulse:
        write_text_safe(PULSE_PATH, render_pulse(run, out_dir), allow_pulse=True)
    print(out_dir)
    print(f"signals={len(signals)} rejected={len(rejected)} warnings={len(warnings)}")
    return 0


def render_summary(run: SignalRun) -> str:
    high = [s for s in run.signals if s.quality_bucket == "high"]
    medium = [s for s in run.signals if s.quality_bucket == "medium"]
    return f"""# Polymarket Signal Scan Summary

- Date: `{run.analysis_date}`
- Generated: `{run.generated_at}`
- Topic: `{run.topic}`
- Keywords: {', '.join(run.keywords)}
- Signals: `{len(run.signals)}`
- High quality: `{len(high)}`
- Medium quality: `{len(medium)}`

结论：本文件只是外部概率信号摘要，不是交易建议。进入交易决策前仍必须走红蓝对抗和 `<6.0 = 不操作` 门槛。
"""


def render_pulse(run: SignalRun, out_dir: Path) -> str:
    top = sorted(run.signals, key=lambda s: (s.quality_score, s.volume_24h), reverse=True)[:10]
    rows = "\n".join(
        f"| {s.question} | {s.yes_probability * 100:.1f}% | {s.quality_score:.1f} | {s.quality_bucket} | {s.recommended_weight:.0%} |"
        for s in top
        if s.yes_probability is not None
    ) or "| 无 | - | - | - | - |"
    return f"""# Prediction Market Pulse

> 只读外部概率信号；不是交易记录，不是持仓状态，不得直接触发买卖。

- Updated: `{run.generated_at}`
- Latest archive: `{out_dir}`
- Keywords: {', '.join(run.keywords)}

| Market | YES probability | Quality | Bucket | Max fusion weight |
|---|---:|---:|---|---:|
{rows}

## 使用边界

- 只用于宏观/地缘/政策事件概率校准。
- 不能单独让交易评分跨过 6.0。
- 低质量市场只做情绪观察。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Polymarket prediction market signal scanner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--analysis-date", default=date.today().isoformat())
    scan.add_argument("--topic", default="polymarket-signal")
    scan.add_argument("--keywords", nargs="+")
    scan.add_argument("--search-limit", type=int, default=8)
    scan.add_argument("--max-events", type=int, default=30)
    scan.add_argument("--max-markets", type=int, default=50)
    scan.add_argument("--enrich-limit", type=int, default=25)
    scan.add_argument("--report-limit", type=int, default=20)
    scan.add_argument("--update-pulse", action="store_true")
    scan.set_defaults(func=run_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
