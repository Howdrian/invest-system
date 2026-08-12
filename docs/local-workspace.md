# Local Workspace Placement

> Last verified: 2026-08-12

## Current local path

`/Users/hac/AI-Studio/投研/invest-system-release-candidate`

This repo is the active release-candidate line for the investment research system. It starts from `upstream/main@55946536`, preserves the original product surface, and adds the Reports product line in reviewable commits.

The product diff has completed manual review and was split into local commits. The code snapshot before the documentation commit is `97c4d035dab9`; the committed worktree is clean and the final structural audit reports `dirtyEntries=0`. Generated daily artifacts and local dependencies remain ignored and are not part of the source snapshot.

The current upstream tip is `3b98aa1d779a`. The branch is 9 commits ahead and 60 commits behind upstream; the upstream delta since the integration base spans 394 files. Do not describe the candidate as matching latest upstream until a clean integration and parity rerun complete. See [CURRENT_STATE](CURRENT_STATE.md) and [Upstream Parity Audit](UPSTREAM_PARITY_AUDIT.md).

The live GitHub Pages site is still legacy `main/docs`. On 2026-08-12, sampled raw artifact, RAW_AGENT memo, and source-health JSON URLs were still HTTP 200. Local Reader-only staging is therefore not evidence that the public site has been cleaned.

The former implementation and integration worktrees were compacted into `/Users/hac/AI-Studio/投研/_legacy/invest-system-worktree-archives/20260717` and removed from the live workspace. This repo has a standalone `.git` directory and does not depend on the retired worktrees.

## Boundary

- Runtime source: current repo code plus generated local artifacts.
- Reports product line: `/reports`, `/api/v1/reports/*`, `src/source_health/`, `src/research_core/`, department Agent runtime, Reader and Diagnostics.
- Original product lines remain active: chat, portfolio, screening, decision signals, alerts, usage, settings, scheduler and data providers.
- Daily outputs under `docs/reports/`, `docs/run_status/`, `docs/agent_memos/`, `docs/market_cycle/`, `docs/daily/` and `docs/index.html` are generated artifacts. They are ignored in source review and regenerated locally or in Actions.
- Local and GitHub Actions report generation both enter through `scripts/run_research_daily_local.sh`; Pages publication is a separate final step.
- Long-term docs remain under `docs/*.md`.
- Old `invest-brain` stays reference-only outside public docs; `docs/invest-brain/**` must not be exposed.

## Git

Use this repo's Git state:

```bash
git -C /Users/hac/AI-Studio/投研/invest-system-release-candidate status --short
git -C /Users/hac/AI-Studio/投研/invest-system-release-candidate rev-list --left-right --count HEAD...upstream/main
```

Do not commit `.env`, DB, logs, caches, or generated daily report bundles.

Before a cloud release, integrate upstream in a separate clean branch/worktree and rerun the full parity matrix. Do not merge the 60-commit drift into a dirty tree, and do not treat old-main CI or local Pages staging as candidate cloud acceptance.
