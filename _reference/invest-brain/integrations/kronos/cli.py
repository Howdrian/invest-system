#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date

try:
    from .adapter import run_forecast
    from .schemas import KronosForecastRequest
except ImportError:  # pragma: no cover
    from adapter import run_forecast
    from schemas import KronosForecastRequest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run Kronos optional forecast challenger smoke. Review-only; no scoring/writeback.")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("forecast", help="fetch OHLCV and optionally run pinned Kronos model")
    f.add_argument("--symbol", required=True)
    f.add_argument("--analysis-date", default=date.today().isoformat())
    f.add_argument("--topic", default="kronos-smoke")
    f.add_argument("--lookback", type=int, default=256)
    f.add_argument("--pred-len", type=int, default=20)
    f.add_argument("--model", choices=["mini", "small"], default="mini")
    f.add_argument("--interval", default="1d")
    f.add_argument("--range", dest="range_", default="2y")
    f.add_argument("--seed", type=int, default=123, help="deterministic seed for smoke-level reproducibility")
    f.add_argument("--temperature", type=float, default=1.0)
    f.add_argument("--top-k", type=int, default=1, help="default 1 makes smoke deterministic; use 0 for sampling")
    f.add_argument("--top-p", type=float, default=1.0)
    f.add_argument("--sample-count", type=int, default=1)
    f.add_argument("--allow-download", action="store_true", help="allow real Hugging Face model download/run; still requires local Kronos repo and pinned revisions")
    f.add_argument("--kronos-repo", default=os.environ.get("KRONOS_REPO_DIR"), help="local upstream Kronos repo path; project does not vendor it")
    f.add_argument("--revision", default=None, help="pinned Hugging Face model revision/commit; built-in pinned default is used when omitted")
    f.add_argument("--tokenizer-revision", default=None, help="pinned Hugging Face tokenizer revision/commit; optional when built-in pinned default is valid")
    args = p.parse_args(argv)
    if args.cmd == "forecast":
        req = KronosForecastRequest(
            symbol=args.symbol,
            analysis_date=args.analysis_date,
            lookback=args.lookback,
            pred_len=args.pred_len,
            model=args.model,
            interval=args.interval,
            range_=args.range_,
            seed=args.seed,
            temperature=args.temperature,
            top_k=args.top_k,
            top_p=args.top_p,
            sample_count=args.sample_count,
            allow_download=args.allow_download,
            kronos_repo=args.kronos_repo,
            model_revision=args.revision,
            tokenizer_revision=args.tokenizer_revision,
        )
        result = run_forecast(req, topic=args.topic)
        print(result.output_files.get("json"))
        print(json.dumps({"status": result.status, "usability": result.usability, "model_available": result.model_available, "scoring_impact": result.scoring_impact, "protected_writeback": result.protected_writeback}, ensure_ascii=False))
        return 0 if result.status in {"ok", "degraded"} else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
