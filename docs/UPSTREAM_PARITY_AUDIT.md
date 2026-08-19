# Upstream Parity Audit

> Last verified: 2026-08-19 21:11 CST
> Release branch: `codex/reports-v1-upstream-sync`
> Validated code SHA: `5de0183abf2f`
> Current integration base: `upstream/main@cfd6b0a5fb9c`
> Historical Reports base: `upstream/main@55946536a976`
> Old online main reference: `origin/main@7a8b4cf83e02`

## 结论

Reports 最初从 `55946536` 建线，历史增量先重放到 `upstream/main@3b98aa1d`，再合并报告可靠性修复到 `5c964bf2`；本轮继续合并 Agent per-category tool timeout `cfd6b0a5`，并以 `5de0183a` 修复满池 queue stall。冲突、自动合并和高风险语义已人工复核，最终 fetch 后验收代码为 `ahead 22 / behind 0`，本地代码复审 P0/P1 为 0；外部云端门禁仍开放。

这是**点时本地 parity**：证明原产品面与 Reports 增量在该 SHA 上通过本地回归，不证明未来 upstream、云端 CI、Pages 或生产环境已同步。

## 原产品面与 Reports

| 范围 | 状态 | 本地证据 |
|---|---|---|
| Decision Signals / Run Flow / Usage / Watchlist / Scheduler / Portfolio | PRESERVED | full backend gate |
| Built-in Screening / Futu / Tushare / Responses API | PRESERVED | upstream regression + full backend gate |
| Agent tool execution | PRESERVED_AND_EXTENDED | timeout targeted + merge semantic matrix + full gate |
| Reports API | RESTORED | `/api/v1/reports/latest`、`/artifacts`、`/artifacts/{id}`；OpenAPI static/runtime parity |
| Web Reports | RESTORED | `/reports`；Web gate + authenticated Playwright pass |
| ReportArtifact / Reader / Diagnostics | RESTORED | contract、semantic、Pages validators pass |
| Public Pages bundle | RESTORED_LOCAL | 当前 validator 重跑 2026-07-17 历史 Reader allowlist；未部署 |
| Legacy invest-brain public files | CLEAN_LOCAL | `legacyPublicFiles=0` |

Reports 是新增产品线，不替换原分析、筛选、组合、告警、设置或调度入口。完整 artifact、Diagnostics、ledger、memo 属维护面；公开 Pages 只允许 Reader HTML。

## 本轮 upstream 增量

报告可靠性提交均保留：

- `c7ca990b`：股息 TTM 测试日期相对化；
- `29421088`：分析完成但报告未生成的结果语义修复；
- `5159bd72`：YFinance 股息 fixture 稳定化；
- `5c964bf2`：单股报告日期断言稳定化。

Agent timeout `cfd6b0a5` 已进入当前代码：

- 支持 data/search/analysis/action/market 类别默认超时、单工具声明和显式 per-run 覆盖；first-wins 优先级为 per-run > tool > category > unlimited，剩余 wall-clock 预算只作外层硬上限；
- timeout 结果为 non-retriable 并进入同调用缓存，避免 LLM 重试重入；后台 handler 支持协作取消；
- registry 按配置值失效并在热重载时重建，带锁规避并发竞态；过滤后的 registry 保留类别超时；
- 并行批次共用有界 executor，排队调用从 worker 实际启动时计时，避免未执行即超时。
- 当 5 个已超时的非协作 handler 占满 pool 时，给 0.5 秒 cooperative grace；仍不退出则只取消尚未启动的 future，并返回 `timeout + queued + retriable:false`、写入 non-retriable cache。红测复现从约 1.21 秒降至约 0.60 秒，正常第 6 个 fast 场景保留。

本地 `5cf86b7a` 的报告持久化/one-shot/YFinance 上界修复，以及 `0ff9dd5e` 的 authenticated hermetic E2E、`8f619331` 的 Desktop 安全基线均保留。

## Provider parity（点时代码级）

此前纳入的裸港股路由、Tencent 日 K 最终兜底、港股全市场实时快照缓存、Longbridge keyword args、YFinance PE/PB 与 data-quality 修复均保留。HK 指数、5 日历史、权限 permanent circuit 等本地增强也未被本轮 merge 回退。

Longbridge SDK 参数契约由测试覆盖；本轮仍未使用真实凭据执行 live smoke。

## 安全与配置不变量

- 非 loopback bind 必须 auth=true 且已存在有效管理员密码；middleware 运行时再次 fail-closed。
- 公网运行时关闭认证返回 409；专用关闭入口要求 current password；System Config 不得改 `is_editable=false`。
- PR Review 只运行可信默认分支脚本，通过 API 读取不可信 diff，不检出 fork 代码。
- Reports LLM 配置复用 `YAML > Channels > legacy`；Responses alias 保留 Router deployment；无效显式 YAML/channel 阻断降级。
- Daily Reports step 对齐主分析的 LLM、provider、Stock List 与 market region 配置。

## 本地复核

- Backend：`6248 passed, 4 deselected, 40 warnings, 501 subtests passed`；syntax、critical flake8、deterministic、offline PASS。
- Agent timeout targeted：`536 passed / 1 warning / 8.86s`；merge semantic matrix：`557 passed`。
- 当前工作树 `.venv311` 已新鲜安装；Python pip check + pip-audit 0。
- Authenticated Playwright：当前环境 `12/12 passed`；真实本地认证与临时 DB，Chat/report API 使用 hermetic fixture，未调用真实 LLM/provider。
- Web（本轮代码未变）：lint、TypeScript、Vite build、prod/full audit PASS；Vitest `1108 passed / 2 skipped`。
- Desktop（本轮代码未变）：Electron `41.10.3`、Node `22.12.0`；50/50 tests、build、prod/full npm audit 0。仅验证未签名 DMG 框架，未含 backend bundle/Windows/签名/公证。
- OpenAPI：116 paths / 193 schemas，static/runtime 全量相等，2026-08-19 `--check` PASS。
- Pages：当前 validator 重跑 **2026-07-17 历史产物**；source 21/30/0 broken，Reader staging 11/19/0 broken。没有生成新 LLM 日报。
- AI assets：2026-08-19 PASS。
- 结构：958 files / 430516 LOC / 223 large / 614 complex / 246 TODO-like / 5 cycles；legacy 0、Reader leak 0。
- Docker：daemon/compose config PASS；build 卡在解析 `docker/dockerfile:1.7` frontend，未生成镜像，import/health smoke 未验证。

## 云端边界

2026-08-19 20:35 CST 实时只读核验：

- Pages：legacy `main:/docs`，deployed commit `7a8b4cf8`；三条维护 URL 仍 HTTP 200。
- candidate：未 push；PR 总数 0、open PR 0，无 hosted checks。
- CI：Howdrian/invest-system 的 `ci.yml` endpoint 为 `state=deleted`，active workflow 无 CI。
- main：未保护；rulesets=[]；Actions all、sha pin false；secret scanning/push protection/Dependabot security updates 未启用；code scanning 无有效结果。
- Network Smoke：最新 #59 表面 success，但有效网络覆盖和 quick analysis 仍不满足发布门，且只覆盖旧 main；属于 false-green，不是候选验收。

## 发布判断

```text
LOCAL PARITY PASS AGAINST upstream/main@cfd6b0a5
LOCAL PACKAGING PARTIAL
CLOUD RELEASE NO-GO
```
