# Upstream Parity Audit

> Last verified: 2026-07-17
> Release branch: `codex/reports-v1-release`
> Base: `upstream/main@55946536`
> Source report-chain reference: `7a8b4cf8`

## 结论

发布候选线直接从当前 `upstream/main@55946536` 建立；旧集成 worktree 的 397 条混杂 dirty 已归档，145 条真实自定义路径已迁移并拆为可审提交。

原项目产品入口保留；报告系统作为新增产品线接入 `/reports` 和 `/api/v1/reports/*`，没有覆盖原分析、筛选、组合、告警或设置入口。

## P0 parity

| 功能 | 路径 / 入口 | 状态 | 验证 |
|---|---|---|---|
| Decision Signals | `/decision-signals`, `/api/v1/decision-signals` | RESTORED | API route present；Web build chunk present |
| AlphaSift screening | `/screening`, `/api/v1/alphasift/status` | RESTORED | smoke 200；backend tests pass |
| Intelligence sources | `/api/v1/intelligence/sources` | RESTORED | smoke 200 |
| Run Flow | `/api/v1/analysis/tasks/{task_id}/flow` | RESTORED | route present；backend tests pass |
| Usage dashboard | `/usage`, `/api/v1/usage/dashboard` | RESTORED | smoke 200；Web build chunk present |
| Watchlist | `/api/v1/stocks/watchlist` | RESTORED | smoke 200 |
| Scheduler status / run-now | `/api/v1/system/scheduler/status`, `/run-now` | RESTORED | status smoke 200；run-now route present |
| Portfolio position analysis | `/api/v1/portfolio/positions/{symbol}/analysis` | RESTORED | route present；backend tests pass |
| Web route/nav | `/`, `/chat`, `/portfolio`, `/decision-signals`, `/screening`, `/backtest`, `/alerts`, `/usage`, `/settings` | RESTORED | preserved from upstream；Web build pass |

## 报告系统接入

| 模块 | 状态 | 说明 |
|---|---|---|
| Reports API | RESTORED | 新增 `/api/v1/reports/latest`、`/artifacts`、`/artifacts/{id}` |
| Web Reports | RESTORED | 新增 `/reports`，不替换 upstream 页面 |
| ReportArtifact v1 | RESTORED | additive 字段；老 API schema 保持兼容 |
| Reader / Diagnostics | RESTORED | Reader 默认干净；Diagnostics 单独入口 |
| SourceHealth / Evidence | RESTORED | 报告链使用，不污染 upstream 主分析链 |
| Pages bundle | RESTORED | 本地/Actions 运行时生成汇总页、artifact、diagnostics、分部门报告和 agent memos；源码分支不长期追踪每日产物 |
| Legacy invest-brain | RESTORED boundary | `docs/invest-brain/** = 0` |

## P1 parity

| 功能 | 状态 | 说明 |
|---|---|---|
| Tencent provider | RESTORED | 来自 upstream；未重排 provider 优先级 |
| Taiwan institutional provider | RESTORED | 来自 upstream；测试覆盖保留 |
| LLM backend registry | RESTORED | 来自 upstream；系统配置测试通过 |
| JP/KR/TW 市场边界 | RESTORED | 来自 upstream；市场/组合/行情测试通过 |
| stock bar / concept / decision signal UI 修复 | RESTORED | 来自 upstream；Web build pass |

## 技术债口径

- 当前最大债从“报告链”变为“upstream 大体量继承债”。
- `audit_tech_debt.py` 当前检出 `importCycles=4`，均属于 upstream 大模块继承链；报告新增模块未引入新的公开入口覆盖或旧 invest-brain 暴露。
- 默认 Reader 未检出工程字段泄露：`readerLeakFiles={}`。
- npm install 暴露 `16 vulnerabilities`，未自动修；属于 upstream 依赖治理，单独立项，不在本地报告闭环里强改。

## 最终本地复核

- upstream 原页面和 P0 API 入口均保留，Reports 只新增 `/reports` 与 `/api/v1/reports/*`。
- 后端：`4684 passed, 1 skipped, 4 deselected, 416 subtests`。
- Web：`971 passed, 2 skipped`；lint 通过；build 通过。
- Reports：11 个 LLM 部门成功、fallback 0；Pages bundle 21 个 required files、48 条链接、0 broken link。
- 语义审计：PASS；0 条结论被拒绝；44 条推断明确标为待验证情景。
- 本地与 Actions 共用 `scripts/run_research_daily_local.sh`；workflow 不再预填派生 memo、漏跑情报 Evidence 或重复渲染。
- 本结论只覆盖本地；GitHub Actions / Pages 云端尚未执行。
- Git 历史收口债已关闭：发布候选线与 `upstream/main@55946536` 同基线，Reports 增量按研究内核、发布链、Web、测试文档拆分。

## 产物治理

- `docs/` 保留长期文档；每日报告 HTML/JSON 是运行产物。
- `docs/reports/`、`docs/run_status/`、`docs/agent_memos/`、`docs/market_cycle/`、`docs/daily/`、`docs/index.html` 已纳入 `.gitignore`。
- 报告契约测试在 pytest 临时目录构造最小 artifact/ledger，避免固定日期完整日报变成陈旧真相源。
- 完整本地验收产物归档到 `.local_archive/`，不入源码 review。
