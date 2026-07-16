# Local Workspace Placement

> Last verified: 2026-07-17

## Current local path

`/Users/hac/AI-Studio/投研/invest-system-release-candidate`

This repo is the clean release-candidate line for the investment research system. It starts from `upstream/main@55946536`, keeps upstream product capabilities and adds the Reports product line in reviewable commits.

The former integration worktree at `/Users/hac/AI-Studio/投研/invest-system-upstream-integration` is retained only as a local archive/reference. Do not use it as the active source or publish from it.

## Boundary

- Runtime source: current repo code plus generated local artifacts.
- Reports product line: `/reports`, `/api/v1/reports/*`, `src/source_health/`, `src/research_core/`, department Agent runtime, Reader and Diagnostics.
- Original system product lines remain active: chat, portfolio, screening, decision signals, alerts, usage, settings, scheduler and data providers.
- Daily report outputs under `docs/reports/`, `docs/run_status/`, `docs/agent_memos/`, `docs/market_cycle/`, `docs/daily/` and `docs/index.html` are generated artifacts. They are ignored in source review and regenerated locally or in Actions.
- Local and GitHub Actions report generation both enter through `scripts/run_research_daily_local.sh`; Pages publication is a separate final step.
- Long-term docs remain under `docs/*.md`.
- Old `invest-brain` stays reference-only outside public docs; `docs/invest-brain/**` must not be exposed.

## Git

Use this repo's git status for code/doc changes:

```bash
git -C /Users/hac/AI-Studio/投研/invest-system-release-candidate status
```

Do not commit `.env`, DB, logs, caches, or generated daily report bundles.
