# invest-system 当前状态

> Document status: `CURRENT_TRUTH`
> Last verified: 2026-08-19 21:11 CST
> Active repo: `/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`
> Validated code SHA: `5de0183abf2f`

## 一句话结论

```text
LOCAL APPLICATION GATES PASS
LOCAL RELEASE PACKAGING PARTIAL
CLOUD RELEASE NO-GO
```

Reports 发布候选已完成最新 upstream 同步、人工 diff review、分包提交和最终本地回归。2026-08-19 fetch 后，验收代码相对 `upstream/main@cfd6b0a5fb9c` 为 `ahead 22 / behind 0`。这只证明本地点时 parity，不代表已推送、已通过托管 CI 或已发布。

线上仍是旧 `main:/docs` legacy Pages，三条维护端原始产物仍公开；候选分支未 push、PR 0，云端 CI 仍被删除。因此不能称 production ready 或已发布。

## 当前版本与 Git

| 项目 | 当前值 |
|---|---|
| Branch | `codex/reports-v1-upstream-sync` |
| 验收代码 SHA | `5de0183abf2f` |
| 当前同步基底 | `upstream/main@cfd6b0a5fb9c` |
| Reports 历史建线基底 | `upstream/main@55946536a976` |
| 验收代码点时 upstream parity | `5de0183a` 为 `ahead 22 / behind 0` |
| origin/main | `7a8b4cf83e02`（旧线上主线，最后 push 2026-06-26） |
| 外部动作 | 未 push、未建 PR、未切 Pages source、未触发候选日报或部署 |

## 本轮完成

- 在原 `upstream/main@5c964bf2` 收口基础上合并 Agent per-category tool timeout，当前基底前进到 `cfd6b0a5`；本地代码人工复核与语义矩阵未发现 P0/P1，外部云端门禁仍单列开放。
- Agent 工具支持 data/search/analysis/action/market 类别默认超时、单工具超时和显式 per-run 覆盖；按 first-wins 解析，剩余 wall-clock 只作外层硬上限。
- 工具超时返回结构化 non-retriable 结果，阻止同调用重入；支持协作取消、配置热重载、线程安全 registry 重建，并让排队调用从 worker 实际启动时计时。
- 修复满池停滞：5 个已超时且不响应协作取消的 handler 占满 worker 时，先给 0.5 秒退出宽限；仍未退出则只取消尚未启动的 future，返回 `timeout + queued + retriable:false` 并写入 non-retriable cache。原 1.21 秒复现降至约 0.60 秒，正常第 6 个 fast 调用场景保持不变。
- 保留上游内建 Screening、Responses API、Futu/Tushare、Desktop 分享图及通知能力，以及本地 Reports/Evidence/Agent/Reader 产品线。
- 报告结果 fail-closed：缓存/回退大盘复盘也必须持久化报告；常规 one-shot 只要 `analysis_ok=false` 即非零退出。
- YFinance TTM 现金股息窗口使用 `cutoff <= event <= as_of`，按事件时区执行包含边界判断，未来股息不计入 TTM。
- Web authenticated Playwright 使用真实本地登录/后端与临时 DB，报告和聊天接口使用 hermetic fixture，不调用真实或付费 LLM/provider。
- Desktop 安全基线为 Electron `41.10.3`、electron-builder `26.15.3`、electron-updater `6.8.9`，Desktop CI/Release Node 为 `22.12.0`。
- 公网 bind/auth 继续 fail-closed；Reports LLM 配置继续复用 `YAML > Channels > legacy`；OpenAPI 继续由 runtime 确定性生成。

## 本地验证

- Backend gate（验收代码 `5de0183a`）：syntax、critical flake8、deterministic、offline 全通过；`6248 passed, 4 deselected, 40 warnings, 501 subtests passed`。
- Agent timeout 目标回归：`536 passed / 1 warning / 8.86s`；合并语义矩阵：`557 passed`。
- 当前工作树 `.venv311` 已新鲜安装依赖；`pip check` 通过，`pip-audit --local` 为 0 known vulnerabilities。
- Authenticated Playwright：当前环境 `12/12 passed`；覆盖真实本地认证入口，但 Chat SSE、报告历史/API 为隔离 fixture，不是外部 provider、真实 LLM 或生产端到端证明。
- Web（本轮无 Web 代码变更，沿用已验证证据）：lint、TypeScript、Vite build、prod/full audit 通过；Vitest `1108 passed / 2 skipped`。
- Desktop（本轮无 Desktop 代码变更，沿用已验证证据）：50/50 tests、build、prod/full `npm audit` 0；仅为未签名 DMG 打包框架，未包含可交付 backend bundle，未验证 Windows、签名或公证。
- OpenAPI：2026-08-19 生成器 `--check` PASS；runtime/static 全量相等，116 paths / 193 schemas。
- Pages：2026-08-19 用当前 validator 重跑 **2026-07-17 历史产物**，source bundle 21 required / 30 links / 0 broken，Reader-only staging 11 files / 19 links / 0 broken；未生成新日报、未 publish。
- AI assets：2026-08-19 PASS。
- 结构审计：958 files / 430516 LOC / 223 个 500 行以上文件 / 614 个复杂定义 / 246 个 TODO-like hits / 5 个 import cycles；`legacyPublicFiles=0`，`readerLeakFiles={}`。扫描时仅 6 份本轮真相文档处于编辑态。
- Docker：daemon 与 compose config PASS；build 仍卡在 `resolve image config for docker-image://docker.io/docker/dockerfile:1.7`。没有生成镜像，关键模块 import 与 health smoke 未验证。

## 历史真实日报

最新完整日报仍是 `2026-07-17`，本轮没有调用付费模型重新生成：

| 指标 | 结果 |
|---|---|
| analysisMode | `FULL_REVIEW` |
| SourceHealth | `0.93` |
| Evidence | verified 37 / derived 102 / discovery 117 / missing 0 |
| Agent | 11/11 LLM success；fallback 0；`vertex_ai/gemini-3.5-flash` |
| ResearchReliability | 中等可信，含待验证情景 |

入口位于同步前参考线的被忽略历史运行目录：

- `/Users/hac/AI-Studio/投研/invest-system-release-candidate/docs/reports/2026-07-17.html`
- `/Users/hac/AI-Studio/投研/invest-system-release-candidate/docs/reports/2026-07-17.artifact.json`

这些是历史本地产物，不证明当前代码生成了新日报，也不代表云端已发布。

## 线上 Pages：当前 P0

2026-08-19 20:35 CST 实时只读核验：

```text
build_type=legacy
status=built
source=main:/docs
deployed_commit=7a8b4cf83e02
url=https://howdrian.github.io/invest-system/
```

以下维护端路径仍为 HTTP 200：

- `reports/2026-06-19.artifact.json`：12,325 bytes
- `agent_memos/2026-06-19/market/02_macro_geopolitics.json`：6,317 bytes
- `market_cycle/2026-06-19/13_source_health.json`：5,877 bytes

本地 allowlist 不会自动清除旧站或 Git 历史。当前只确认维护原文公开，不能把它夸大为已确认密钥泄漏。

## 仍未收口

1. **线上 raw Pages exposure（P0 external）**：旧维护产物仍公开；必须经授权部署 Reader allowlist 并逐条验证旧 URL 404。
2. **云端 CI/发布（P1 external）**：候选分支未 push、PR 0；`CI` workflow endpoint 为 `state=deleted`，active workflow 无 CI/required checks。
3. **云端 false-green（P1 external）**：2026-08-19 Network Smoke #59 仍显示 success，但有效网络覆盖和 quick analysis 结果仍不满足发布门，而且只覆盖旧 main，不能作为候选验收。
4. **GitHub 治理（P1 external）**：main 无 branch protection/ruleset；Actions 允许全部且不强制 SHA pin；secret scanning、push protection、Dependabot security updates 仍未启用，code scanning 无有效结果。
5. **Docker/Desktop/live（P1）**：Docker 无成功 image/import/health；Desktop 无完整 backend bundle、Windows、签名或公证；真实外部 provider、新 LLM 日报与云端浏览器链未验。
6. **API 权限分层（P1）**：完整 Reports artifact 仍依赖全局 admin auth；公开 Reader DTO 与私有维护 DTO 尚未拆开。
7. **继承型技术债（P2）**：223 个大文件、614 个复杂定义、5 个 import cycles 后续独立治理，不在本轮强拆。

## 下一步顺序

1. 用户授权后 push `codex/reports-v1-upstream-sync` 并建立 PR。
2. 恢复/启用云端 CI，跑 backend shards、Web、Docker、Desktop/Futu packaging、AI governance。
3. 配置 main 保护、required checks、安全扫描和 Action SHA 策略。
4. 将 Pages source 切到 GitHub Actions，部署 Reader allowlist，确认三条旧维护 URL 为 404。
5. 云端验收后再恢复 Daily schedule；不在此前自动触发模型、通知或发布。

## 维护规则

- 当前代码、当次命令和线上实时状态优先于历史计划。
- 本地测试、Git 可交付状态、云端发布状态必须分开汇报。
- `.env`、DB、logs、cache、每日生成产物不进入源码提交。
- 未经明确授权不 push、不切 Pages、不触发付费模型/通知/部署。
