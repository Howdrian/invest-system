from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json

try:
    from schemas import assert_safe_output_path, write_text_safe
except ImportError:  # pragma: no cover
    from .schemas import assert_safe_output_path, write_text_safe


def _items(items: list[dict[str, Any]], empty: str) -> str:
    if not items:
        return f"- {empty}\n"
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        claim = str(item.get("claim") or "").strip()
        section = str(item.get("source_section") or "unknown").strip()
        evidence = str(item.get("evidence") or "").strip()
        lines.append(f"{index}. Source section: `{section}`")
        lines.append(f"   - External claim: {claim}")
        if evidence and evidence != claim:
            lines.append(f"   - Evidence snippet: {evidence}")
        lines.append("   - Local fact check: TODO")
        lines.append("   - Red-team attack: TODO")
        lines.append("   - Accepted / rejected / unknown: TODO")
    return "\n".join(lines) + "\n"


def render_challenge(evidence: dict[str, Any]) -> str:
    ticker = evidence.get("ticker", "UNKNOWN")
    analysis_date = evidence.get("analysis_date", "UNKNOWN")
    rating = evidence.get("rating") or "None"
    claims = evidence.get("claims") or []
    risks = evidence.get("risks") or []
    catalysts = evidence.get("catalysts") or []
    unknowns = evidence.get("unknowns") or []

    unknown_lines = "\n".join(f"- {u}" for u in unknowns) if unknowns else "- None extracted"

    return f"""# Local Challenge for TradingAgents Evidence

## Context

- Ticker: `{ticker}`
- Analysis date: `{analysis_date}`
- TradingAgents rating: `{rating}`
- Source: `tradingagents_extract.json`

## Rule

TradingAgents is external evidence only. This file is not a trade decision.

Before any action:

1. Verify facts against local data skills or web sources.
2. Run local red-blue challenge.
3. Apply local `scoring-card`.
4. Use local `position-sizer` if and only if score is `>= 6.0`.
5. Do not write `portfolio.md` or `trade-log.md` from this file.

## External Bull Claims To Attack

{_items(claims, "No bull claims extracted. Red team should treat this as weak external support.")}

## External Risks To Verify

{_items(risks, "No risks extracted. Red team should check whether TradingAgents missed obvious downside.")}

## External Catalysts To Verify

{_items(catalysts, "No catalysts extracted. Catalyst score should remain low unless local research finds one.")}

## Extracted Unknowns

{unknown_lines}

## Local Decision Gate

- Local score: TODO / 10
- Score gate passed: TODO (`yes` only if score >= 6.0)
- Fatal unresolved risk: TODO
- Position sizing complete: TODO
- Final local action: TODO

## Conflict Review

- If TradingAgents is bullish but local score < 6.0: `no action`; record why.
- If TradingAgents is bearish but local score >= 6.0: reduce confidence or require stronger local evidence.
- If both agree: still apply local score and position rules.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate local red-team challenge template from TradingAgents evidence JSON.")
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    evidence = json.loads(args.extract.read_text(encoding="utf-8"))
    assert_safe_output_path(args.out)
    write_text_safe(args.out, render_challenge(evidence))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

