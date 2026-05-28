# Free Data Source Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, quality-scored free-data-source upgrade lane covering A-share depth, US fundamentals, fast news, options quality, and commodity fundamentals.

**Architecture:** Keep the existing `invest-brain` single-entry architecture. Add a separate provider registry and a single probe script that classifies providers by quality, authorization, latency, and trading usability; then wire the probe into `run_research_cycle.py` and `source_health_dashboard.py` as a supporting component. Nothing writes portfolio/trade logs or changes scoring gates.

**Tech Stack:** Python stdlib HTTP/JSON/CSV, optional local packages (`akshare`, `efinance`, `edgar`, etc.) detected by import only, existing `source_cache.py`, existing source-health dashboard.

---

## File Structure

- Create `config/free-data-source-registry.json`: provider registry with tier, quality, access mode, scope, and integration recommendation.
- Create `scripts/free_data_source_probe.py`: read-only provider probe; outputs JSON/MD/HTML and `run_metadata.json`.
- Create `scripts/test_free_data_source_probe.py`: unit tests for scoring and provider result parsing.
- Modify `scripts/source_health_dashboard.py`: display `free_source_upgrade` component and count provider statuses.
- Modify `scripts/run_research_cycle.py`: optional/default run of `free_data_source_probe.py` as supporting source-quality component.
- Modify `config/data-sources.md`, `docs/information-access.md`, `docs/research-cycle.md`, `AGENTS.md`, `README.md`: update source architecture and boundaries.

## Tasks

### Task 1: Registry
- [x] Create provider registry with fields: `id`, `name`, `domain`, `tier`, `access_mode`, `quality_score`, `role`, `recommended_action`, `trade_use`, `source_url`.
- [x] Mark free/public vs free-keyed vs optional package vs forbidden scraping.

### Task 2: Probe
- [x] Implement `free_data_source_probe.py` with safe archive writes.
- [x] Probe optional package availability without installing.
- [x] Probe official/public HTTP endpoints where safe: EIA v2 metadata, CFTC Socrata, SEC Atom/current submissions, Alpha Vantage demo docs endpoint, Tradier token presence only.
- [x] Output `free_data_source_probe.json`, `.md`, `.html`, and `run_metadata.json`.

### Task 3: Source Health Integration
- [x] Add component labels/counts for `free_source_upgrade`.
- [x] Treat this lane as supporting: unavailable should degrade source quality, not block core trading review if current core sources are OK.

### Task 4: Cycle Integration
- [x] Run the probe during the research cycle unless explicitly skipped.
- [x] Copy summary into cycle output.

### Task 5: Tests and Audit
- [x] Unit tests for scoring and no-key behavior.
- [x] Run scripts tests, integration tests, py_compile, architecture audit, protected diff check.

## Quality Gates

- Probe must distinguish: `ready`, `needs_key`, `needs_install`, `degraded`, `blocked_by_terms`.
- `blocked_by_terms` providers cannot be promoted into the default run.
- Free keyed providers can be registered but must not fail the full cycle if keys are absent.
- Official sources get higher confidence than scraped aggregators.
- Outputs must include evidence URLs and clear trade-use boundaries.
