# Source Health Dashboard

- Generated: `2026-06-01T13:33:47+00:00`
- Cycle dir: `invest-brain/2026-06-01/research-cycle`
- Verdict: **WARN**
- Usability: **unavailable**
- Trade review usability: **usable**
- Trade review reason: 仅可选源异常，不阻断交易审查，但需在 AI 复核中提示。
- Recovery: **AI_DIAGNOSTIC_REQUIRED** — 存在关键源失败或备用说明不足；自动化应补跑，并由 Codex AI 写清根因、影响范围、下一步。
- Quality: freshness=`过期/待补` coverage=`缺失` tier=`官方/行情/RSS/缓存混合` impact=不可用于交易门控

| Status | Usability | Criticality | Blocking | Component | RC | Data | Counts | Warnings | Detail |
|---|---|---|---|---|---:|---|---|---|---|
| OK | usable | macro_regime | supporting | `macro_regime` | 0 | True | stale:1, refreshed:1 | - | - |
| OK | usable | catalyst_news | supporting | `intelligence` | 0 | True | snapshots:103, events:22, triggers:103, cache_hits:112 | - | optional source skipped with fallback |
| OK | usable | core_market_data | core | `market_heat` | 0 | True | items:270, candidates:40, cache_hits:9 | - | - |
| OK | usable | core_market_data | core | `a_share` | 0 | True | snapshots:55, events:22, triggers:55, cache_hits:64 | - | optional source skipped with fallback |
| OK | usable | research_opinion | supporting | `reports` | 0 | True | reports_scanned:53, usable_reports:34, high_value_reports:7, report_triggers:43, cache_hits:14 | - | - |
| OK | usable | official_filings_or_announcements | core | `official` | 0 | True | macro_points:6, sec_filings:34, sec_company_facts:69, cache_hits:30 | - | - |
| OK | usable | research_opinion | supporting | `official_ext` | 0 | True | extension_points:4, finra_short_interest:8, cache_hits:12 | - | optional source skipped with fallback |
| OK | usable | source_quality_upgrade | supporting | `free_source_upgrade` | 0 | True | providers_total:13, ready_providers:3, needs_key_providers:5, needs_install_providers:4, degraded_providers:0, blocked_by_terms_providers:1, high_quality_ready:2, phase1_ready:3, cache_hits:3 | - | - |
| OK | usable | official_filings_or_announcements | core | `announcements` | 0 | True | cninfo_announcements:32, gov_policy_items:60, announcement_triggers:13, cache_hits:15 | - | - |
| OK | usable | crypto_risk_proxy | optional | `crypto` | 0 | True | snapshots:2, candidates:2 | - | - |
| WARN | unavailable | optional_prediction_market | optional | `polymarket` | 0 | False | signals:0, rejected:0 | search failed for iran: URL error for https://gamma-api.polymarket.com/public-search?q=iran&limit=5: [Errno 54] Connection reset by peer; search failed for hormuz: URL error for https://gamma-api.polymarket.com/public-search?q=hormuz&limit=5: [Errno 54] Connection reset by peer; search failed for ukraine: URL error for https://gamma-api.polymarket.com/public-search?q=ukraine&limit=5: [Errno 54] Connection reset by peer | - |
| OK | usable | research_synthesis | core | `deep_review` | 0 | True | candidates:6 | - | - |

## Recovery Plan

| Component | Reliability | Fallback | Failure streak | Last success | Last failure | Next retry | Fallback quality | Impact | Next system action | AI |
|---|---|---|---:|---|---|---|---|---|---|---|
| `polymarket` | UNAVAILABLE | 未使用备用源 | 6 | 2026-05-29T12:56:20+00:00 | 2026-06-01T13:33:47+00:00 | 2026-06-02T13:33:47+00:00 | none | 关键数据缺失；相关候选只能观察或补源，不能触发交易审查。 | 补跑检查；若代码源和备用源都失败，Codex AI 必须写 source diagnostic，不允许只显示“失败”。 | True |

## Boundary

- 这个面板只看数据源是否跑通、是否有 warning、是否有可用数据；不评价投资结论。
- `usable/degraded/unavailable` 是操作可用性分级：degraded 表示可用但要降权或复核。
