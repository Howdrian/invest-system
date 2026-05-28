# Kronos Status

- Status: Phase 0/1 adapter installed; real pinned `Kronos-mini` smoke passed on 2026-05-18.
- Upstream repo cache: `research/cache/kronos_repo`（ignored；不是 vendor 进本项目）。
- Runtime env cache: `research/cache/kronos_env` + `research/cache/kronos_models`（ignored）。
- Hugging Face token: not required for the tested public, non-gated `NeoQuasar` model/tokenizer repos.
- Main-flow integration: optional lane enabled via `scripts/run_research_cycle.py --enable-kronos`.
- Default behavior: dependency/data smoke only, no model download.
- Current promotion gate: Phase 2 optional `--enable-kronos` lane is implemented; still not allowed into scoring before walk-forward / baseline validation.
- Scoring impact: 0.
- Protected writeback: false.

Latest verified smoke:

- Output: `research/archive/2026-05-18-kronos-real-smoke-fixed/17_kronos_forecast.json`
- Result: `status=ok`, `model_available=true`, `device=cpu`
- Model revision: `f4e68697d9d5aed55cef5c96aabc3376bcad9f81`
- Tokenizer revision: `26966d0035065a0cae0ebad7af8ece35bc1fb51c`

Upstream repo regression check:

- Command scope: upstream `tests/test_kronos_regression.py`
- Result: `4 passed, 2 warnings`
- Notes: warnings are `huggingface_hub` / `hf_xet` deprecation warnings, not model failures.

Monitoring:

- Optional lane output can be ingested by `scripts/kronos_backtest_monitor.py`.
- Ledger: `research/kronos_monitor/forecast_ledger.jsonl`.
