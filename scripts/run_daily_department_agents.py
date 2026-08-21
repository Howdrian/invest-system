#!/usr/bin/env python3
"""Run evidence-driven daily department agents."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.daily_department_agents import run_daily_department_agents  # noqa: E402
from src.daily_department_llm import run_llm_daily_department_agents  # noqa: E402
from src.original_analysis_adapter import build_original_analysis_bundle  # noqa: E402
from src.safe_diagnostics import sanitize_diagnostic_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run daily research department agents")
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--runtime-reports-dir", default="reports")
    parser.add_argument(
        "--runtime",
        choices=("auto", "llm", "rule"),
        default=os.getenv("RESEARCH_AGENT_RUNTIME", "auto").strip().lower() or "auto",
        help="Agent runtime. auto tries LLM and allows fallback; llm requires LLM success; rule is deterministic.",
    )
    parser.add_argument("--allow-fallback", action="store_true", help="Allow fallback even when --runtime llm")
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("RESEARCH_AGENT_LLM_RETRY", "1") or "1"))
    parser.add_argument("--max-concurrency", type=int, default=int(os.getenv("RESEARCH_AGENT_MAX_CONCURRENCY", "3") or "3"))
    parser.add_argument(
        "--model-policy",
        choices=("best", "configured", "strict"),
        default=os.getenv("RESEARCH_AGENT_MODEL_POLICY", "best").strip().lower() or "best",
        help="best smokes current candidate models; configured only uses AGENT_LITELLM_MODEL/LITELLM_MODEL.",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print per-agent progress")
    parser.add_argument(
        "--resume-successful",
        action="store_true",
        help="Reuse same-date LLM successes and rerun only failed downstream stages; use only when inputs are unchanged.",
    )
    args = parser.parse_args(argv)

    def _print_progress(row):
        if args.quiet:
            return
        print(
            json.dumps(
                {
                    "agent": row.get("agent"),
                    "status": row.get("status"),
                    "model": row.get("model"),
                    "attempt": row.get("attempt"),
                    "durationSeconds": row.get("durationSeconds"),
                    "totalTokens": (row.get("usage") or {}).get("total_tokens"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    try:
        build_original_analysis_bundle(
            Path(args.docs_dir),
            args.date,
            runtime_reports_dir=Path(args.runtime_reports_dir),
        )
        if args.runtime == "rule":
            result = run_daily_department_agents(
                Path(args.docs_dir),
                args.date,
                runtime_reports_dir=Path(args.runtime_reports_dir),
            )
        else:
            result = run_llm_daily_department_agents(
                Path(args.docs_dir),
                args.date,
                runtime_reports_dir=Path(args.runtime_reports_dir),
                max_retries=args.max_retries,
                require_all_llm=args.runtime == "llm" and not args.allow_fallback,
                progress_callback=_print_progress,
                max_concurrency=args.max_concurrency,
                model_policy=args.model_policy,
                resume_successful=args.resume_successful,
            )
    except RuntimeError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": sanitize_diagnostic_text(exc, max_len=500),
                    "runDate": args.date,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
