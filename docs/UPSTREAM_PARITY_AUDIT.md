# Upstream Parity Audit

> Last verified: 2026-08-12
> Release branch: `codex/reports-v1-release`
> Integration base: `upstream/main@55946536a976`
> Current upstream: `upstream/main@3b98aa1d779a`
> Old online main reference: `origin/main@7a8b4cf83e02`

## 结论

发布候选线在 2026-07-17 从当时的 `upstream/main@55946536` 建立。原项目产品入口保留；Reports 作为新增产品线接入 `/reports` 与 `/api/v1/reports/*`，没有替换原分析、筛选、组合、告警、设置或调度入口。

本轮已完成候选 diff 的人工审查、阻断修复、分包提交和本地回归，但该 parity 只证明与建线基底的兼容，**不证明与最新 upstream 同步**。当前分支 ahead 9 / behind 60；云端发布继续 NO-GO。

## 当前 upstream 漂移

- 最新 upstream：`3b98aa1d779a`。
- 基底后 upstream：60 commits / 394 files changed。
- 当前候选增量与 upstream 重叠 52 个路径；2 个内容已一致，50 个需在集成时按产品语义复核。
- 已知不能遗漏的 provider 修复：
  - `02717771`：裸港股代码路由，当前候选仍可能把 `00700` 等误转为 `.SZ`；
  - `90f62349`：Tencent 日 K 从首选改为最终兜底；
  - `20c399e7`：港股全市场实时快照缓存，避免逐标的重复抓全市场；
  - `7fa29c7e`：Longbridge SDK 参数兼容，避免静默丢失 `volume_ratio`。
- upstream 还包含内建 screening engine、认证、Web/Desktop、Docker、配置和 workflow 变化，不能把“无 Git 冲突”当成功能 parity。
- 处理边界：只在独立干净集成线 merge/rebase/cherry-pick，完成后重跑完整矩阵；禁止回到 dirty tree 机械解冲突。

## P0 产品面

| 功能 | 路径 / 入口 | 当前候选状态 | 本地证据 |
|---|---|---|---|
| Decision Signals | `/decision-signals`, `/api/v1/decision-signals` | PRESERVED | backend/Web regression pass |
| Screening | `/screening`, `/api/v1/alphasift/*` | PRESERVED at base | backend/Web regression pass；最新内建 engine parity 待集成 |
| Intelligence sources | `/api/v1/intelligence/sources` | PRESERVED | backend regression pass |
| Run Flow | `/api/v1/analysis/tasks/{task_id}/flow` | PRESERVED | route/regression pass |
| Usage dashboard | `/usage`, `/api/v1/usage/dashboard` | PRESERVED | payload/auth isolation regression pass |
| Watchlist | `/api/v1/stocks/watchlist` | PRESERVED | backend regression pass |
| Scheduler | `/api/v1/system/scheduler/status`, `/run-now` | PRESERVED | backend regression pass |
| Portfolio position analysis | `/api/v1/portfolio/positions/{symbol}/analysis` | PRESERVED | backend regression pass |
| Web route/nav | `/`, `/chat`, `/portfolio`, `/decision-signals`, `/screening`, `/backtest`, `/alerts`, `/usage`, `/settings` | PRESERVED | lint, Vitest, build pass |

## Reports 接入

| 模块 | 状态 | 说明 |
|---|---|---|
| Reports API | RESTORED | `/api/v1/reports/latest`、`/artifacts`、`/artifacts/{id}`；artifact id 严格限制，非法路径 fail-closed |
| Web Reports | RESTORED | 新增 `/reports`，不替换原页面；公开 URL 客户端再做一层防御 |
| ReportArtifact v1 | RESTORED | API/Web/Pages 共用；ReaderV3 嵌套 schema 和布尔字段严格校验 |
| Reader / Diagnostics | RESTORED | Reader 面向用户；完整 artifact/Diagnostics/ledger/memo 属维护面 |
| SourceHealth / Evidence | RESTORED | 报告链使用，不污染原主分析链；ResearchReliability 独立于 SourceHealth |
| Pages bundle | RESTORED_LOCAL | 公开 staging 仅复制 Reader 首页、汇总和分部门 HTML；未部署 |
| Legacy invest-brain | BOUNDARY RESTORED | `docs/invest-brain/** = 0` |

> **线上例外：**2026-08-12 实时核验仍为 legacy `main/docs`。完整 artifact、RAW_AGENT memo 和 source-health JSON 三条抽检 URL 均为 HTTP 200；这是外部 P0 release blocker。本地 `legacyPublicFiles=0` 不能关闭该项。

## P1 parity

| 功能 | 状态 | 说明 |
|---|---|---|
| 公网认证与 bind | LOCAL HARDENED / UPSTREAM REVIEW | 当前候选比建线基底更严格；集成 upstream 时必须保留 stored-password、runtime-disable、System Config 旁路回归 |
| Tencent provider | PARITY PENDING | 当前候选尚未集成 upstream 最终兜底优先级修复 |
| 港股代码与实时行情 | PARITY PENDING | 裸港股路由及全市场快照缓存修复尚未集成 |
| Longbridge | PARITY PENDING | SDK 参数兼容修复尚未集成 |
| Taiwan institutional provider | PRESERVED at base | 当前测试保留；仍需在最新 upstream 集成后复跑 |
| LLM backend registry | PRESERVED at base | 当前系统配置测试通过；最新 upstream 集成后复跑 |
| JP/KR/TW 市场边界 | LOCAL HARDENED | Reader/market mapping 已补齐；provider parity 仍需随 upstream 复核 |
| Desktop / release | UNVERIFIED | 本轮未做跨平台打包、安装、签名、公证或更新链 |

## 本地复核

- Backend：`4871 passed, 4 deselected, 416 subtests`；syntax、flake8、deterministic、offline PASS。
- Web：`npm ci`、lint、Vitest、Vite build PASS；`977 passed / 2 skipped`。
- Dependency audit：npm production/all 与 pip-audit 均为 0 known vulnerabilities。
- Pages source：21 required files / 30 links / 0 broken；Reader staging：11 files / 19 links / 0 broken。
- Semantic audit：PASS；2026-07-17 artifact 为 11/11 LLM、fallback 0，最终可靠性“中等可信，含待验证情景”。
- AI assets、OpenAPI JSON、Markdown links、`git diff --check`：PASS。
- 结构审计：858 files / 363770 LOC / 181 large files / 513 complex definitions / 180 TODO-like hits / 4 import cycles；Reader leak 0。
- 未执行：Docker image、Desktop/Playwright、network live、新 LLM 日报、候选 Actions/Pages。

## 云端边界

- Pages：legacy `main/docs`，不是 Actions deployment。
- origin/main：`7a8b4cf83e02`，最后 push 2026-06-26。
- CI workflow：云端 endpoint 当前为 `state=deleted`，active workflow 列表无 CI，main 也无 required checks。
- Daily workflow：最新仍为 2026-06-26 failure。
- Network Smoke：2026-08-12 旧 main success，只证明旧主线定时 smoke，不是候选验收。
- 候选分支：未 push、无 PR、无云端 required checks、无 Pages canary。

## 产物治理

- `docs/` 保留长期文档；每日报告 HTML/JSON 是运行产物。
- `docs/reports/`、`docs/run_status/`、`docs/agent_memos/`、`docs/market_cycle/`、`docs/daily/`、`docs/index.html` 由 `.gitignore` 管理。
- 契约测试在 pytest 临时目录构造最小 artifact/ledger，避免固定日期完整日报变成陈旧 fixture。
- 完整本地验收产物留在 `.local_archive/` 或被忽略的运行目录，不进入源码 review。
