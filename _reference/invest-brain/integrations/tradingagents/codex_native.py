from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json

try:
    from ab_test import SAMPLE_POOL, ab_dir_for, init_sample
    from schemas import assert_safe_output_path, validate_ticker, write_json_safe, write_text_safe
except ImportError:  # pragma: no cover
    from .ab_test import SAMPLE_POOL, ab_dir_for, init_sample
    from .schemas import assert_safe_output_path, validate_ticker, write_json_safe, write_text_safe


IMPORTED_PATTERNS = [
    "analyst role separation",
    "bull-vs-bear research debate",
    "risk manager review",
    "portfolio manager synthesis",
    "complete report artifact",
    "structured decision log",
]

PRESERVED_LOCAL_DESIGN = [
    "local red-blue protocol is mandatory",
    "local 0-10 scoring-card remains the only score",
    "score below 6.0 means no action",
    "portfolio.md remains the only real portfolio source",
    "trade-log.md remains the only real trade attribution log",
    "frameworks remain the local method source of truth",
]

FORBIDDEN_DUPLICATION = [
    "no second portfolio state",
    "no second scoring system",
    "no TradingAgents rating to local score mapping",
    "no writeback to protected state during A/B",
    "no new report tree outside research/archive",
]


def codex_native_paths(ticker: str, analysis_date: str, archive_root: Path | None = None) -> dict[str, Path]:
    out_dir = ab_dir_for(ticker, analysis_date, archive_root)
    return {
        "directory": out_dir,
        "plan": out_dir / "codex_native_plan.json",
        "prompt": out_dir / "codex_native_prompt.md",
        "b_variant": out_dir / "b_with_tradingagents.md",
    }


def codex_native_plan(ticker: str, analysis_date: str) -> dict[str, Any]:
    safe_ticker = validate_ticker(ticker)
    return {
        "schema": "codex_native_tradingagents_plan_v1",
        "ticker": safe_ticker,
        "analysis_date": analysis_date,
        "mode": "codex_native",
        "source_project": "TauricResearch/TradingAgents",
        "intent": (
            "Absorb TradingAgents multi-agent research structure into the local invest-brain "
            "workflow without calling the TradingAgents runtime."
        ),
        "imported_patterns": IMPORTED_PATTERNS,
        "preserved_local_design": PRESERVED_LOCAL_DESIGN,
        "forbidden_duplication": FORBIDDEN_DUPLICATION,
        "required_output_sections": [
            "source log and unknowns",
            "market analyst",
            "news analyst",
            "fundamentals analyst",
            "bull case",
            "bear case",
            "risk manager review",
            "portfolio manager synthesis",
            "local red-blue challenge",
            "local scoring-card gate",
            "A/B grading notes",
        ],
        "ab_evidence_markers": [
            "codex_native_plan.json",
            "codex_native_prompt.md",
        ],
        "writeback_allowed": False,
    }


def render_codex_native_prompt(ticker: str, analysis_date: str) -> str:
    safe_ticker = validate_ticker(ticker)
    return f"""# Codex-Native TradingAgents-Inspired Flow

- Ticker: `{safe_ticker}`
- Analysis date: `{analysis_date}`
- Mode: `codex_native`

## Purpose

Run the local `invest-brain` process with TradingAgents' useful architecture imported as a role structure, not as a second runtime. Do not call the TradingAgents Python package for this variant.

## Local Source Of Truth

- `agents/red-team-protocol.md`
- `agents/scoring-card.md`
- `frameworks/`
- `state/portfolio.md` as read-only context
- `state/market-pulse.md` as read-only context
- `state/watchlist.md` as read-only context
- `trades/trade-log.md` as read-only context

## Imported From TradingAgents

{chr(10).join(f"- {item}" for item in IMPORTED_PATTERNS)}

## Must Preserve

{chr(10).join(f"- {item}" for item in PRESERVED_LOCAL_DESIGN)}

## Must Not Do

{chr(10).join(f"- {item}" for item in FORBIDDEN_DUPLICATION)}

## Required Output

1. Source log: list every real data source used. Mark missing or stale facts as unknown.
2. Analyst pass: market, news, and fundamentals each give claims, evidence, and uncertainties.
3. Debate pass: bull case and bear case attack each other directly.
4. Risk pass: identify fatal risks, weak assumptions, sizing risks, and time-horizon mismatch.
5. Portfolio pass: state whether this belongs in the current portfolio context, but do not write state.
6. Local red-blue challenge: apply `agents/red-team-protocol.md`.
7. Local score gate: apply `agents/scoring-card.md`; score below 6.0 means no action.
8. A/B note: explain what this B variant added over A, and cite `codex_native_plan.json` plus `codex_native_prompt.md`.

## Output Boundary

The result is research evidence for A/B evaluation only. It is not a trade instruction and must not update protected project files.
"""


def render_b_variant_template(ticker: str, analysis_date: str) -> str:
    safe_ticker = validate_ticker(ticker)
    return f"""# B With TradingAgents-Derived Codex-Native Flow

- Ticker: `{safe_ticker}`
- Analysis date: `{analysis_date}`
- Evidence mode: `codex_native`
- Required local artifacts: `codex_native_plan.json`, `codex_native_prompt.md`

TODO: run the Codex-native multi-role flow, then replace this template with the final B analysis.

The final B analysis must explicitly explain how `codex_native_plan.json` and `codex_native_prompt.md` changed the process, then record whether the local `<6.0 = no action` gate was preserved.
"""


def init_codex_native_sample(
    ticker: str,
    analysis_date: str,
    archive_root: Path | None = None,
    force: bool = False,
) -> Path:
    safe_ticker = validate_ticker(ticker)
    init_sample(safe_ticker, analysis_date, archive_root=archive_root, force=force)
    paths = codex_native_paths(safe_ticker, analysis_date, archive_root)
    out_dir = paths["directory"]
    assert_safe_output_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if force or not paths["plan"].exists():
        write_json_safe(paths["plan"], codex_native_plan(safe_ticker, analysis_date))
    if force or not paths["prompt"].exists():
        write_text_safe(paths["prompt"], render_codex_native_prompt(safe_ticker, analysis_date))
    b_variant_needs_template = force or not paths["b_variant"].exists()
    if not b_variant_needs_template and paths["b_variant"].exists():
        existing_b = paths["b_variant"].read_text(encoding="utf-8")
        has_codex_markers = "codex_native_plan.json" in existing_b and "codex_native_prompt.md" in existing_b
        is_placeholder = "TODO" in existing_b or "paste or generate" in existing_b
        b_variant_needs_template = is_placeholder and not has_codex_markers
    if b_variant_needs_template:
        write_text_safe(paths["b_variant"], render_b_variant_template(safe_ticker, analysis_date))
    return out_dir


def init_codex_native_pool(analysis_date: str, force: bool = False) -> list[Path]:
    return [init_codex_native_sample(sample["ticker"], analysis_date, force=force) for sample in SAMPLE_POOL]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create Codex-native TradingAgents-inspired A/B artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-sample")
    init_parser.add_argument("--ticker", required=True)
    init_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_parser.add_argument("--force", action="store_true")

    init_pool_parser = subparsers.add_parser("init-pool")
    init_pool_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_pool_parser.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "init-sample":
        print(init_codex_native_sample(args.ticker, args.analysis_date, force=args.force))
        return 0

    if args.command == "init-pool":
        for path in init_codex_native_pool(args.analysis_date, force=args.force):
            print(path)
        return 0

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
