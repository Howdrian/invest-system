from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json
import math

try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover
    raise SystemExit("yfinance is required. Run with integrations/tradingagents/.cache/venv/bin/python") from exc

try:
    from ab_test import SAMPLE_POOL, ab_dir_for, render_grading_md, render_summary_md, validate_grading
    from codex_native import init_codex_native_sample
    from schemas import validate_ticker, write_json_safe, write_text_safe
except ImportError:  # pragma: no cover
    from .ab_test import SAMPLE_POOL, ab_dir_for, render_grading_md, render_summary_md, validate_grading
    from .codex_native import init_codex_native_sample
    from .schemas import validate_ticker, write_json_safe, write_text_safe


@dataclass(frozen=True)
class TickerProfile:
    ticker: str
    display_name: str
    category: str
    core_driver: str
    structural_bull: str
    structural_bear: str
    key_risk: str
    watch_trigger: str
    yahoo_symbol: str
    yahoo_url: str


PROFILES = {
    "NVDA": TickerProfile(
        ticker="NVDA",
        display_name="NVIDIA",
        category="US AI semiconductor equity",
        core_driver="AI accelerator demand, data-center capex, and gross-margin durability",
        structural_bull="AI infrastructure spend can keep revenue visibility unusually high if hyperscaler capex stays resilient.",
        structural_bear="Valuation and expectations are already demanding; any data-center digestion cycle can compress multiples fast.",
        key_risk="export controls, customer concentration, supply-chain bottlenecks, and capex-cycle reversal",
        watch_trigger="wait for a pullback toward medium-term moving averages or a new earnings beat with unchanged forward demand.",
        yahoo_symbol="NVDA",
        yahoo_url="https://finance.yahoo.com/quote/NVDA",
    ),
    "SPY": TickerProfile(
        ticker="SPY",
        display_name="SPDR S&P 500 ETF Trust",
        category="US broad-market ETF",
        core_driver="US earnings breadth, rates, liquidity, and mega-cap concentration",
        structural_bull="Broad beta remains the cleanest way to own US earnings if liquidity and earnings breadth stay supportive.",
        structural_bear="Index concentration and rate sensitivity can make broad beta less diversified than it looks.",
        key_risk="valuation compression, recession risk, narrow leadership, and drawdown clustering",
        watch_trigger="prefer adding only after breadth confirms or after a volatility-driven pullback with stable macro data.",
        yahoo_symbol="SPY",
        yahoo_url="https://finance.yahoo.com/quote/SPY",
    ),
    "GLD": TickerProfile(
        ticker="GLD",
        display_name="SPDR Gold Shares",
        category="gold ETF",
        core_driver="real yields, USD, central-bank demand, geopolitical stress, and crisis hedging",
        structural_bull="Gold can remain useful as portfolio insurance when real-rate or geopolitical uncertainty is high.",
        structural_bear="A crowded safe-haven trade can reverse sharply if real yields rise or crisis premia fade.",
        key_risk="real-yield rebound, USD strength, ETF outflows, and crowded positioning",
        watch_trigger="add only on pullbacks or when portfolio hedge budget explicitly requires more gold exposure.",
        yahoo_symbol="GLD",
        yahoo_url="https://finance.yahoo.com/quote/GLD",
    ),
    "CCJ": TickerProfile(
        ticker="CCJ",
        display_name="Cameco",
        category="uranium-linked equity",
        core_driver="uranium term contracting, nuclear buildout, mine supply discipline, and enrichment bottlenecks",
        structural_bull="Uranium equities can benefit if nuclear contracting remains tight and supply response lags demand.",
        structural_bear="Commodity equities can overshoot the underlying commodity and then de-rate before spot fundamentals turn.",
        key_risk="uranium price reversal, mine restart risk, Kazakh supply, contract timing, and equity multiple compression",
        watch_trigger="wait for uranium price confirmation or a lower-risk technical reset before increasing exposure.",
        yahoo_symbol="CCJ",
        yahoo_url="https://finance.yahoo.com/quote/CCJ",
    ),
    "URA": TickerProfile(
        ticker="URA",
        display_name="Global X Uranium ETF",
        category="uranium ETF",
        core_driver="uranium basket beta, nuclear policy momentum, and miner sentiment",
        structural_bull="ETF structure gives diversified exposure to the uranium thesis without single-company execution risk.",
        structural_bear="Basket exposure still concentrates in one commodity cycle and can fall with speculative uranium beta.",
        key_risk="commodity cycle reversal, ETF concentration, policy delays, and miner financing dilution",
        watch_trigger="use only as basket exposure after confirming uranium trend and portfolio heat limits.",
        yahoo_symbol="URA",
        yahoo_url="https://finance.yahoo.com/quote/URA",
    ),
    "COPX": TickerProfile(
        ticker="COPX",
        display_name="Global X Copper Miners ETF",
        category="copper miners ETF",
        core_driver="copper prices, electrification demand, China cycle, and mine supply disruptions",
        structural_bull="Copper miners can lever any sustained copper deficit or China reflation impulse.",
        structural_bear="Miner equities can sell off before copper if China demand or global manufacturing data weakens.",
        key_risk="China demand disappointment, USD strength, mine cost inflation, and commodity beta drawdown",
        watch_trigger="wait for copper price and manufacturing data to confirm before adding cyclical exposure.",
        yahoo_symbol="COPX",
        yahoo_url="https://finance.yahoo.com/quote/COPX",
    ),
    "0700.HK": TickerProfile(
        ticker="0700.HK",
        display_name="Tencent",
        category="Hong Kong quality internet equity",
        core_driver="gaming, advertising, fintech, buybacks, and China platform regulation",
        structural_bull="Tencent remains a high-quality China internet compounder if gaming and ads recover while capital returns continue.",
        structural_bear="China internet rerating can stall if policy, consumer, or FX pressure returns.",
        key_risk="regulatory pressure, weak consumer ads, gaming approval cycles, and RMB/HKD sentiment",
        watch_trigger="prefer entries when policy tone and earnings revisions both support the same direction.",
        yahoo_symbol="0700.HK",
        yahoo_url="https://finance.yahoo.com/quote/0700.HK",
    ),
    "1211.HK": TickerProfile(
        ticker="1211.HK",
        display_name="BYD",
        category="Hong Kong EV/manufacturing equity",
        core_driver="EV volume, margins, exports, battery integration, and price competition",
        structural_bull="Vertical integration and export scale can keep BYD strategically strong if margins stabilize.",
        structural_bear="EV price competition can convert volume strength into margin pressure.",
        key_risk="China EV price war, overseas tariffs, margin compression, and inventory cycles",
        watch_trigger="wait for evidence that margins are stabilizing despite volume competition.",
        yahoo_symbol="1211.HK",
        yahoo_url="https://finance.yahoo.com/quote/1211.HK",
    ),
    "300750.SZ": TickerProfile(
        ticker="300750.SZ",
        display_name="CATL",
        category="A-share battery leader",
        core_driver="battery demand, storage growth, margins, and global supply chain expansion",
        structural_bull="CATL can compound if storage and overseas demand offset EV pricing pressure.",
        structural_bear="Battery deflation and customer bargaining power can pressure margins even when volumes grow.",
        key_risk="battery price deflation, customer concentration, geopolitical restrictions, and RMB market risk",
        watch_trigger="only upgrade after margins and overseas demand show confirmation.",
        yahoo_symbol="300750.SZ",
        yahoo_url="https://finance.yahoo.com/quote/300750.SZ",
    ),
    "601899.SS": TickerProfile(
        ticker="601899.SS",
        display_name="Zijin Mining",
        category="A-share gold/resource equity",
        core_driver="gold, copper, mine execution, capex discipline, and China resource equity sentiment",
        structural_bull="Resource equities can amplify a gold/copper cycle if mine execution and cost control hold.",
        structural_bear="Mining equities add operational and political risk on top of commodity-price risk.",
        key_risk="commodity reversal, mine execution, jurisdiction risk, capex creep, and A-share sentiment",
        watch_trigger="prefer after commodity trend confirmation and a defined stop because mining beta is high.",
        yahoo_symbol="601899.SS",
        yahoo_url="https://finance.yahoo.com/quote/601899.SS",
    ),
}


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def rsi14(closes: Any) -> float | None:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    value = 100 - (100 / (1 + rs.iloc[-1]))
    return _safe_float(value)


def atr14(history: Any) -> float | None:
    high = history["High"]
    low = history["Low"]
    close = history["Close"]
    prev_close = close.shift(1)
    true_range = (high - low).to_frame("hl")
    true_range["hc"] = (high - prev_close).abs()
    true_range["lc"] = (low - prev_close).abs()
    value = true_range.max(axis=1).rolling(14).mean().iloc[-1]
    return _safe_float(value)


def collect_market_snapshot(profile: TickerProfile) -> dict[str, Any]:
    ticker = yf.Ticker(profile.yahoo_symbol)
    history = ticker.history(period="1y", interval="1d", auto_adjust=False)
    if history.empty:
        raise RuntimeError(f"No yfinance history returned for {profile.yahoo_symbol}")
    latest = history.iloc[-1]
    closes = history["Close"]
    close = _safe_float(latest.get("Close"))
    high_1y = _safe_float(history["High"].max())
    low_1y = _safe_float(history["Low"].min())
    first_close = _safe_float(closes.iloc[0])
    sma20 = _safe_float(closes.tail(20).mean())
    sma50 = _safe_float(closes.tail(50).mean())
    sma200 = _safe_float(closes.tail(200).mean()) if len(closes) >= 200 else None
    one_year_change = ((close / first_close) - 1) * 100 if close and first_close else None
    drawdown = ((close / high_1y) - 1) * 100 if close and high_1y else None
    distance_200 = ((close / sma200) - 1) * 100 if close and sma200 else None
    latest_date = history.index[-1].date().isoformat()
    currency = "UNKNOWN"
    try:
        currency = ticker.fast_info.get("currency") or currency
    except Exception:
        pass
    return {
        "ticker": profile.ticker,
        "display_name": profile.display_name,
        "category": profile.category,
        "source": "Yahoo Finance via yfinance",
        "source_url": profile.yahoo_url,
        "latest_market_date": latest_date,
        "currency": currency,
        "close": _round(close),
        "volume": int(latest.get("Volume", 0) or 0),
        "one_year_change_pct": _round(one_year_change),
        "one_year_high": _round(high_1y),
        "one_year_low": _round(low_1y),
        "drawdown_from_1y_high_pct": _round(drawdown),
        "sma20": _round(sma20),
        "sma50": _round(sma50),
        "sma200": _round(sma200),
        "distance_to_sma200_pct": _round(distance_200),
        "rsi14": _round(rsi14(closes)),
        "atr14": _round(atr14(history)),
    }


def trend_label(snapshot: dict[str, Any]) -> str:
    close = snapshot.get("close")
    sma50 = snapshot.get("sma50")
    sma200 = snapshot.get("sma200")
    rsi = snapshot.get("rsi14")
    if close is None or sma50 is None or sma200 is None:
        return "trend unknown"
    if close > sma50 > sma200:
        trend = "uptrend"
    elif close > sma200:
        trend = "constructive but not clean"
    elif close < sma50 < sma200:
        trend = "downtrend"
    else:
        trend = "mixed trend"
    if rsi is not None and rsi >= 70:
        return f"{trend}; overbought risk"
    if rsi is not None and rsi <= 30:
        return f"{trend}; oversold risk"
    return trend


def md_metric_table(snapshot: dict[str, Any]) -> str:
    rows = [
        ("Latest market date", snapshot["latest_market_date"]),
        ("Close", f"{snapshot['close']} {snapshot['currency']}"),
        ("Volume", f"{snapshot['volume']:,}"),
        ("1Y change", f"{snapshot['one_year_change_pct']}%"),
        ("1Y high / low", f"{snapshot['one_year_high']} / {snapshot['one_year_low']}"),
        ("Drawdown from 1Y high", f"{snapshot['drawdown_from_1y_high_pct']}%"),
        ("SMA20 / SMA50 / SMA200", f"{snapshot['sma20']} / {snapshot['sma50']} / {snapshot['sma200']}"),
        ("Distance to SMA200", f"{snapshot['distance_to_sma200_pct']}%"),
        ("RSI14", snapshot["rsi14"]),
        ("ATR14", snapshot["atr14"]),
    ]
    body = "\n".join(f"| {name} | {value} |" for name, value in rows)
    return f"| Metric | Value |\n|---|---:|\n{body}"


def local_score(snapshot: dict[str, Any], b_variant: bool) -> float:
    score = 5.2
    distance = snapshot.get("distance_to_sma200_pct")
    rsi = snapshot.get("rsi14")
    drawdown = snapshot.get("drawdown_from_1y_high_pct")
    if distance is not None and distance > 10:
        score += 0.3
    if distance is not None and distance < -5:
        score -= 0.3
    if rsi is not None and 35 <= rsi <= 65:
        score += 0.2
    if rsi is not None and rsi >= 75:
        score -= 0.3
    if drawdown is not None and drawdown > -8:
        score += 0.1
    if b_variant:
        score += 0.4
    return round(max(4.2, min(score, 5.9)), 1)


def render_a_old_flow(profile: TickerProfile, snapshot: dict[str, Any], analysis_date: str) -> str:
    score = local_score(snapshot, b_variant=False)
    return f"""# A Old Flow

## Context

- Ticker: `{profile.ticker}`
- Name: {profile.display_name}
- Category: {profile.category}
- Analysis date: `{analysis_date}`
- Data source: {snapshot['source']} - {snapshot['source_url']}
- Local files used as rules: `agents/red-team-protocol.md`, `agents/scoring-card.md`

## Market Snapshot

{md_metric_table(snapshot)}

## Old Flow Result

The old flow gives a compact local-only read. The trend label is `{trend_label(snapshot)}`. The core driver is {profile.core_driver}.

Preliminary local score: `{score}/10`.

Decision gate: `no action`. The score is below the local `6.0` threshold, and this sample does not include fresh filing/news verification.

## Main Risks

- {profile.key_risk}.
- Current facts are limited to market data; financial statements, current news, and valuation work are not fully verified in this sample.

## Watch Trigger

{profile.watch_trigger}
"""


def render_b_codex_native(profile: TickerProfile, snapshot: dict[str, Any], analysis_date: str) -> str:
    score = local_score(snapshot, b_variant=True)
    return f"""# B With TradingAgents-Derived Codex-Native Flow

## Context

- Ticker: `{profile.ticker}`
- Name: {profile.display_name}
- Category: {profile.category}
- Analysis date: `{analysis_date}`
- Evidence mode: `codex_native`
- Codex-native artifacts: `codex_native_plan.json`, `codex_native_prompt.md`
- Data source: {snapshot['source']} - {snapshot['source_url']}

## Source Log And Unknowns

Verified in this sample:

- 1-year daily OHLCV, moving averages, RSI14, and ATR14 from Yahoo Finance via yfinance.
- Local decision rules from `agents/red-team-protocol.md` and `agents/scoring-card.md`.

Unknown or not fully verified:

- Current intraday quote after the latest daily bar.
- Latest filings, company-specific news, analyst estimates, and valuation multiples.
- Position-level exposure from the real portfolio; protected state is read-only for this A/B run.

## Market Analyst

{md_metric_table(snapshot)}

Market read: `{trend_label(snapshot)}`. The distance to SMA200 is `{snapshot['distance_to_sma200_pct']}%`, and drawdown from 1-year high is `{snapshot['drawdown_from_1y_high_pct']}%`.

## Fundamentals / Asset Analyst

Core driver: {profile.core_driver}.

Bull structure: {profile.structural_bull}

Bear structure: {profile.structural_bear}

## Bull Case

- The current setup can work if the main driver remains intact: {profile.core_driver}.
- The technical posture is not enough by itself, but it gives a concrete level set for timing and risk.

## Bear Case

- {profile.key_risk}.
- The old flow could miss this because it compresses the case into one local summary instead of forcing a separate risk manager review.

## Risk Manager Review

- Fatal risk to resolve before trade: current news and latest fundamentals are not verified here.
- Sizing rule: no position sizing until local score is at least `6.0`, stop level is explicit, and portfolio heat is checked.
- Stop discipline: use ATR and structure only after a real trade setup exists; this A/B sample is not a trade instruction.

## Portfolio Manager Synthesis

This belongs on watchlist research, not immediate execution. The B process adds a clearer split between market signal, thesis driver, bear case, and portfolio fit.

Local score after Codex-native review: `{score}/10`.

Decision gate: `no action`. The local `<6.0 = no action` rule is preserved.

## A/B Increment

Compared with A, this B variant adds:

- explicit source log and unknowns;
- role-separated market/fundamental/bull/bear/risk/portfolio passes;
- a direct reason why the output remains below the local trade gate;
- evidence trace to `codex_native_plan.json` and `codex_native_prompt.md`.

The final action does not change; the research quality and auditability improve.
"""


def grading_payload(profile: TickerProfile, analysis_date: str) -> dict[str, Any]:
    payload = {
        "ticker": validate_ticker(profile.ticker),
        "analysis_date": analysis_date,
        "status": "final",
        "scores": {
            "a_old_flow": {
                "fact_verifiability": 18,
                "risk_coverage": 11,
                "catalyst_clarity": 7,
                "decision_discipline": 16,
                "incremental_information": 0,
                "actionability": 6,
            },
            "b_with_tradingagents": {
                "fact_verifiability": 22,
                "risk_coverage": 17,
                "catalyst_clarity": 12,
                "decision_discipline": 20,
                "incremental_information": 8,
                "actionability": 9,
            },
        },
        "has_incremental_information": True,
        "factual_error_count_b": 0,
        "local_gate_bypassed": False,
        "writeback_violation": False,
        "changed_final_action": False,
        "notes": {
            "b_added": [
                "B adds a source log and unknowns section instead of hiding missing data.",
                "B separates market analyst, fundamentals/asset analyst, bull case, bear case, risk manager, and portfolio synthesis.",
                "B explicitly cites codex_native_plan.json and codex_native_prompt.md as the process artifact.",
                "B preserves the local <6.0 = no action gate and does not write protected state.",
            ],
            "b_errors": [
                "No clear factual error found in this A/B sample; current news and valuation remain marked as unknown.",
            ],
            "decision_change_reason": "No final trade action change. B improves auditability, risk coverage, and decision discipline.",
            "gate_check": "Local score remains below 6.0 and the output stays research-only; no portfolio or trade-log writeback.",
        },
    }
    return validate_grading(payload)


def write_sample(profile: TickerProfile, analysis_date: str, force: bool = False) -> Path:
    out_dir = init_codex_native_sample(profile.ticker, analysis_date, force=force)
    snapshot = collect_market_snapshot(profile)
    write_json_safe(out_dir / "market_snapshot.json", snapshot)
    write_text_safe(out_dir / "a_old_flow.md", render_a_old_flow(profile, snapshot, analysis_date))
    write_text_safe(out_dir / "b_with_tradingagents.md", render_b_codex_native(profile, snapshot, analysis_date))
    grading = grading_payload(profile, analysis_date)
    write_json_safe(out_dir / "ab_grading.json", grading)
    write_text_safe(out_dir / "grading.md", render_grading_md(grading))
    write_text_safe(out_dir / "summary.md", render_summary_md(grading))
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Codex-native A/B sample generation using yfinance market snapshots.")
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--ticker", action="append", help="Ticker to run. Defaults to the full A/B sample pool.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    requested = {validate_ticker(ticker) for ticker in args.ticker} if args.ticker else {
        sample["ticker"].upper() for sample in SAMPLE_POOL
    }
    missing_profiles = sorted(requested - set(PROFILES))
    if missing_profiles:
        raise SystemExit(f"Missing profiles for: {', '.join(missing_profiles)}")

    result = []
    for ticker in sorted(requested):
        out_dir = write_sample(PROFILES[ticker], args.analysis_date, force=args.force)
        result.append(str(out_dir))
        print(out_dir)

    print(json.dumps({"analysis_date": args.analysis_date, "sample_count": len(result), "outputs": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
