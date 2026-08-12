# invest-system 当前状态

> Document status: `CURRENT_TRUTH`
> Last verified: 2026-08-12
> Active repo: `/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`
> Validated code SHA: `4f12aac5ebae`

## 一句话结论

```text
LOCAL APPLICATION GATES PASS
LOCAL RELEASE PACKAGING PARTIAL
CLOUD RELEASE NO-GO
```

Reports 发布候选已在独立分支完成 upstream 同步、人工 diff review、安全与配置收口、分包提交和本地回归。对本轮 fetch 的 `upstream/main@3b98aa1d779a` 为 `ahead 15 / behind 0`。这只证明本地点时 parity，不代表已推送、已通过托管 CI 或已发布。

线上仍是旧 `main/docs` legacy Pages，三条维护端原始产物仍公开；候选分支尚未 push、无 PR、未跑云端 CI。因此不能称 production ready 或已发布。

## 当前版本与 Git

| 项目 | 当前值 |
|---|---|
| Branch | `codex/reports-v1-upstream-sync` |
| 验收代码 SHA | `4f12aac5ebae` |
| 当前同步基底 | `upstream/main@3b98aa1d779a` |
| Reports 历史建线基底 | `upstream/main@55946536a976` |
| 验收代码点时 upstream parity | `4f12aac5` 为 `ahead 15 / behind 0` |
| origin/main | `7a8b4cf83e02`（旧线上主线，最后 push 2026-06-26） |
| 工作树 | 不固化文档编辑态；最终提交后以 `git status` 回执为准 |
| 外部动作 | 未 push、未建 PR、未切 Pages source、未触发候选日报或部署 |

## 本轮完成

- 把 9 个 Reports/安全/研究/文档提交重放到最新 upstream，并逐项人工审查冲突和无冲突自动合并。
- 保留上游内建 Screening、Responses API、Futu/Tushare、CI 三分片、Desktop 分享图及通知能力。
- 集成并验证裸港股路由、Tencent 最终兜底、港股全市场缓存、Longbridge kwargs、YFinance PE/PB 等 provider 修复。
- 公网 bind/auth 继续 fail-closed：非 loopback 必须启用认证且预先初始化管理员密码；关闭认证需二次密码，公网运行时禁止关闭；通用 System Config 不能旁路只读开关。
- Reports lightweight LLM 配置与主 Config 共享同一解析语义：`YAML > Channels > legacy`；Responses alias 保留 wire route/API surface/base/key/header，显式无效 YAML/channel fail-closed，不污染 `os.environ`。
- Daily workflow 的 Reports step 与主分析对齐 LLM、Stock List、Realtime、Tushare、TickFlow、Longbridge 配置；`LITELLM_CONFIG_YAML` 独立原子落盘。
- OpenAPI 产物从 runtime 确定性生成，覆盖 116 paths、193 schemas 和三条 Reports API；FastAPI/Pydantic/Starlette schema toolchain 已固定。
- Desktop 依赖升级到 Electron `39.8.10`、electron-builder `26.15.3`、electron-updater `6.8.9`；漏洞补丁按兼容 major 收窄 override，Release Node 固定 `20.17.0`。
- YFinance 股息窗口统一使用可注入 UTC 时钟；Web 异步断言去除历史时间/调度型 flaky。

## 本地验证

- Backend gate：syntax、flake8、deterministic、offline 全通过；`6174 passed, 4 deselected, 501 subtests`。
- Web：`npm ci`、lint、TypeScript/Vite build 通过；最终 Vitest `1108 passed / 2 skipped`。并行满载首轮出现 3 个既有时序 flaky，三个用例单独复跑全通过，随后全量复跑 0 fail。
- Provider parity：109 个裸港股/Tencent/HK cache/Longbridge/YFinance 目标测试通过；相关能力也包含在全量 backend gate。
- Desktop：`npm ci`、50/50 tests、prod/full `npm audit` 0；DMG packaging framework 通过。仍缺真实 Windows NSIS、签名/公证，且本机未提供 `dist/backend/stock_analysis`，所以不是完整可安装交付包。
- 依赖：Web 与 Desktop production/full audit 均为 0；Python `pip check` 通过，`pip-audit --local` 为 0 known vulnerabilities。
- OpenAPI：生成器 `--check` PASS；runtime/static 全量相等，116 paths / 193 schemas。
- Pages：历史 2026-07-17 source bundle 21 required / 30 links / 0 broken；Reader-only staging 11 files / 19 links / 0 broken，未 publish。
- Semantic：PASS；11 个部门、blocking 0；历史 artifact 有 rejected claims 21、conditional claims 28，可靠性“中等可信，含待验证情景”。
- AI assets、workflow YAML/shell、`git diff --check`：PASS。
- 结构审计：957 files / 427962 LOC / 220 个 500 行以上文件 / 613 个复杂定义 / 235 个 TODO-like hits / 5 个 import cycles；`legacyPublicFiles=0`，`readerLeakFiles={}`。
- Docker：daemon 与 compose config 可用；image build 首次在 `files.pythonhosted.org` 下载超时，第二次在同一慢速点中止，均未完成；未取得镜像/import/health smoke 成功证据。

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

2026-08-12 实时核验：

```text
build_type=legacy
status=built
source=main/docs
url=https://howdrian.github.io/invest-system/
```

以下维护端路径仍为 HTTP 200：

- `reports/2026-06-19.artifact.json`：12,325 bytes
- `agent_memos/2026-06-19/market/02_macro_geopolitics.json`：6,317 bytes
- `market_cycle/2026-06-19/13_source_health.json`：5,877 bytes

本地 allowlist 不会自动清除旧站或 Git 历史。当前只确认维护原文公开，不能把它夸大为已确认密钥泄漏。

## 仍未收口

1. **线上 raw Pages exposure（P0 external）**：旧维护产物仍公开；必须经授权部署 Reader allowlist 并逐条验证旧 URL 404。
2. **云端 CI/发布（P1 external）**：候选分支未 push、无 PR；云端 `CI` workflow endpoint 为 `state=deleted`，active workflow 无 CI/required checks。最新 Daily 是旧 main 的 2026-06-26 failure；2026-08-12 Network Smoke success 也只覆盖旧 main。
3. **GitHub 治理（P1 external）**：main 无 branch protection/ruleset；Actions 允许全部且不强制 SHA pin；secret scanning、push protection、Dependabot security updates 关闭。
4. **Docker/Desktop/live（P1）**：Docker image 未因网络超时完成；Windows/签名/公证/完整 backend bundle、真实外部 provider、Playwright 和新 LLM 日报未验。
5. **API 权限分层（P1）**：完整 Reports artifact 仍依赖全局 admin auth；公开 Reader DTO 与私有维护 DTO 尚未拆开。
6. **继承型技术债（P2）**：220 个大文件、613 个复杂定义、5 个 import cycles 后续独立治理，不在本轮强拆。

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
