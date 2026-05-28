from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json
import os
import shutil
import subprocess
import sys

try:
    from generate_challenge import render_challenge
    from parse_report import parse_inputs
    from provider_config import normalize_provider, required_key_for_provider
    from schemas import (
        ADAPTER_CACHE,
        SidecarMetadata,
        archive_dir_for,
        assert_safe_output_path,
        load_env_files,
        validate_ticker,
        write_json_safe,
        write_text_safe,
    )
except ImportError:  # pragma: no cover - package-style import fallback
    from .generate_challenge import render_challenge
    from .parse_report import parse_inputs
    from .provider_config import normalize_provider, required_key_for_provider
    from .schemas import (
        ADAPTER_CACHE,
        SidecarMetadata,
        archive_dir_for,
        assert_safe_output_path,
        load_env_files,
        validate_ticker,
        write_json_safe,
        write_text_safe,
    )


DEFAULT_ANALYSTS = ["market", "news", "fundamentals"]


def list_ollama_models() -> set[str]:
    if shutil.which("ollama") is None:
        return set()
    result = subprocess.run(
        ["ollama", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    models: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


def assert_provider_ready(
    provider: str,
    quick_model: str | None = None,
    deep_model: str | None = None,
) -> None:
    normalized = normalize_provider(provider)
    if normalized == "ollama":
        if shutil.which("ollama") is None:
            raise RuntimeError("Ollama provider requested, but `ollama` is not installed.")
        if not quick_model or not deep_model:
            raise RuntimeError(
                "Ollama execution requires explicit --quick-model and --deep-model. "
                "Example: --quick-model qwen3:latest --deep-model qwen3:latest"
            )
        installed = list_ollama_models()
        missing = sorted({quick_model, deep_model} - installed)
        if missing:
            raise RuntimeError(
                "Missing Ollama model(s): "
                + ", ".join(missing)
                + ". Run `ollama pull <model>` first."
            )
        return

    required_key = required_key_for_provider(provider)
    if required_key and not os.getenv(required_key):
        raise RuntimeError(
            f"Missing {required_key}; refusing real TradingAgents execution. "
            "Run doctor.py or provide a provider key first."
        )


def render_research_plan(ticker: str, analysis_date: str, mode: str) -> str:
    return f"""# TradingAgents Sidecar Run Plan

## Scope

- Ticker: `{ticker}`
- Analysis date: `{analysis_date}`
- Mode: `{mode}`

## Boundary

This run is read-only relative to the core `投研` state. It may write only inside this archive directory and adapter cache.

It must not update:

- `state/portfolio.md`
- `state/market-pulse.md`
- `state/watchlist.md`
- `trades/trade-log.md`
- `agents/`
- `frameworks/`

## Local decision rule

TradingAgents output is external evidence only. The local system must still run red-blue challenge, `scoring-card`, and position sizing before any state writeback.
"""


def render_complete_report_from_state(state: dict[str, Any], ticker: str) -> str:
    sections = [f"# Trading Analysis Report: {ticker}"]
    mapping = [
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Social Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
        ("investment_plan", "Research Manager"),
        ("trader_investment_plan", "Trader"),
        ("final_trade_decision", "Portfolio Manager"),
    ]
    for key, title in mapping:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(f"## {title}\n\n{value.strip()}")

    debate = state.get("investment_debate_state") or {}
    if isinstance(debate, dict):
        if debate.get("bull_history"):
            sections.append(f"## Bull Researcher\n\n{str(debate['bull_history']).strip()}")
        if debate.get("bear_history"):
            sections.append(f"## Bear Researcher\n\n{str(debate['bear_history']).strip()}")

    risk = state.get("risk_debate_state") or {}
    if isinstance(risk, dict):
        for key, title in [
            ("aggressive_history", "Aggressive Analyst"),
            ("conservative_history", "Conservative Analyst"),
            ("neutral_history", "Neutral Analyst"),
        ]:
            value = risk.get(key)
            if isinstance(value, str) and value.strip():
                sections.append(f"## {title}\n\n{value.strip()}")

    return "\n\n".join(sections).strip() + "\n"


def copy_into_archive(source: Path, destination: Path) -> None:
    assert_safe_output_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def run_tradingagents_execute(
    ticker: str,
    analysis_date: str,
    out_dir: Path,
    llm_provider: str,
    analysts: list[str],
    output_language: str,
    checkpoint: bool,
    quick_model: str | None,
    deep_model: str | None,
    backend_url: str | None,
) -> dict[str, Any]:
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ImportError as exc:
        raise RuntimeError(
            "TradingAgents package is not importable. Install it in an isolated environment before --execute."
        ) from exc

    internal_dir = out_dir / "_tradingagents_internal"
    cache_dir = internal_dir / "cache"
    logs_dir = internal_dir / "logs"
    memory_path = internal_dir / "memory" / "trading_memory.md"
    for path in (cache_dir, logs_dir, memory_path.parent):
        assert_safe_output_path(path)
        path.mkdir(parents=True, exist_ok=True)

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider
    config["output_language"] = output_language
    config["checkpoint_enabled"] = checkpoint
    if quick_model:
        config["quick_think_llm"] = quick_model
    if deep_model:
        config["deep_think_llm"] = deep_model
    if backend_url:
        config["backend_url"] = backend_url
    config["data_cache_dir"] = str(cache_dir)
    config["results_dir"] = str(logs_dir)
    config["memory_log_path"] = str(memory_path)

    graph = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
    final_state, decision = graph.propagate(ticker, analysis_date)
    if not isinstance(final_state, dict):
        raise RuntimeError("TradingAgents returned an unexpected final state")
    final_state["_sidecar_decision"] = decision
    return final_state


def main(argv: list[str] | None = None) -> int:
    load_env_files()
    parser = argparse.ArgumentParser(description="Run or ingest TradingAgents as a read-only sidecar.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--from-report", type=Path)
    parser.add_argument("--from-state-json", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--llm-provider", default="openai")
    parser.add_argument("--quick-model")
    parser.add_argument("--deep-model")
    parser.add_argument("--backend-url")
    parser.add_argument("--output-language", default="Chinese")
    parser.add_argument("--analysts", nargs="+", default=DEFAULT_ANALYSTS)
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args(argv)

    ticker = validate_ticker(args.ticker)
    mode_count = sum(bool(x) for x in (args.from_report, args.from_state_json, args.execute, args.dry_run))
    if mode_count == 0:
        args.dry_run = True
    if args.execute and args.dry_run:
        raise SystemExit("--execute and --dry-run cannot be used together")
    if args.execute:
        try:
            assert_provider_ready(args.llm_provider, args.quick_model, args.deep_model)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    out_dir = archive_dir_for(ticker, args.analysis_date, args.archive_root)
    assert_safe_output_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ADAPTER_CACHE.mkdir(parents=True, exist_ok=True)

    mode = "execute" if args.execute else "ingest" if (args.from_report or args.from_state_json) else "dry-run"
    write_text_safe(out_dir / "research_plan.md", render_research_plan(ticker, args.analysis_date, mode))

    notes: list[str] = []
    report_path = out_dir / "tradingagents_complete_report.md"
    state_path = out_dir / "tradingagents_full_state.json"

    if args.from_report:
        copy_into_archive(args.from_report, report_path)
        notes.append("Imported external complete report.")

    if args.from_state_json:
        copy_into_archive(args.from_state_json, state_path)
        notes.append("Imported external full state JSON.")

    if args.execute:
        final_state = run_tradingagents_execute(
            ticker=ticker,
            analysis_date=args.analysis_date,
            out_dir=out_dir,
            llm_provider=args.llm_provider,
            analysts=args.analysts,
            output_language=args.output_language,
            checkpoint=args.checkpoint,
            quick_model=args.quick_model,
            deep_model=args.deep_model,
            backend_url=args.backend_url,
        )
        write_json_safe(state_path, final_state)
        write_text_safe(report_path, render_complete_report_from_state(final_state, ticker))
        notes.append("Executed TradingAgents package in sidecar mode.")

    if report_path.exists() or state_path.exists():
        evidence = parse_inputs(
            ticker=ticker,
            analysis_date=args.analysis_date,
            report=report_path if report_path.exists() else None,
            state_json=state_path if state_path.exists() else None,
        )
        evidence.write_json(out_dir / "tradingagents_extract.json")
        write_text_safe(out_dir / "local_challenge.md", render_challenge(evidence.to_dict()))
        notes.append("Generated local red-team challenge from extracted evidence.")

    metadata = SidecarMetadata(
        source="tradingagents",
        ticker=ticker,
        analysis_date=args.analysis_date,
        mode=mode,
        output_dir=str(out_dir),
        notes=notes,
    )
    metadata.write_json(out_dir / "tradingagents_metadata.json")

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
