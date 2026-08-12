# invest-system 当前状态

> Document status: `CURRENT_TRUTH`
> Last verified: 2026-08-12
> Active repo: `/Users/hac/AI-Studio/投研/invest-system-release-candidate`

## 一句话结论

当前发布候选线已完成全量人工 diff review、阻断修复、分包提交和本地回归，结论为：

```text
LOCAL GATES PASS / CLOUD RELEASE NO-GO
```

本地产品闭环和 Git 快照可审；但线上仍是旧 `main/docs` Pages，维护端原始产物仍公开，候选线尚未 push/跑云端 CI，而且分支落后最新 upstream 60 commits。因此不能称 production ready 或已发布。

## 当前版本与 Git

| 项目 | 当前值 |
|---|---|
| Branch | `codex/reports-v1-release` |
| 代码收口 HEAD | `97c4d035dab9`；本文档提交位于其后 |
| 建线基底 | `upstream/main@55946536a976` |
| 最新 upstream | `upstream/main@3b98aa1d779a` |
| upstream 漂移 | `ahead 9 / behind 60`；基底后 upstream 改动 60 commits / 394 files |
| upstream 重叠 | 当前候选增量与 upstream 重叠 52 个路径；2 个内容已一致，50 个集成时仍需语义复核 |
| origin/main | `7a8b4cf83e02`（旧线上主线，最后 push 2026-06-26） |
| 本地提交 | 8 个代码/产品提交 + 本文档收口提交；未 squash |
| 工作树 | `git status --short` 为空；结构审计 `dirtyEntries=0` |
| 外部动作 | 未 push、未建 PR、未切 Pages source、未触发候选日报或部署 |

## 本轮已完成

### 提交

1. `2e34bbe8` `fix(security): harden public runtime boundaries`
2. `c815c51f` `fix(research): enforce temporal evidence contracts`
3. `a9a1aa89` `fix(reports): harden reader and publication contracts`
4. `97c4d035` `chore(tooling): make debt audit linear`
5. 本文档收口提交

此前 Reports 产品线四个分包提交继续保留：`8a3aca06`、`92fc0617`、`c3d87d97`、`154d69c7`。

### 关键修复

- **公网认证 fail-closed**：`main.py`、`server.py`、`webui.py` 和 middleware 共用 bind guard；非 loopback 必须启用认证且已存在有效管理员密码。
- **认证高风险操作**：关闭认证即使持有有效 session 也必须再次输入当前密码；公网监听时禁止运行时关闭认证。
- **配置旁路**：通用 System Config 不再允许改写 `is_editable=false` 的 `ADMIN_AUTH_ENABLED`。
- **PR workflow**：退役 `pull_request_target + fork head checkout + secrets`；手动流程只运行可信默认分支脚本，通过 GitHub API 把 PR diff 当不可信数据读取。
- **Pages/文件系统边界**：严格日期、路径 containment、symlink、marker 和 source/target 校验，防止路径穿越及越界删除。
- **公开产物收口**：Pages artifact 只含 Reader allowlist；不上传完整 artifact、Diagnostics、memo、ledger 或原始日志。
- **Reader/Artifact 契约**：严格嵌套类型与布尔字段；公开 URL 移除 userinfo、fragment、凭据 query，并拒绝 webhook/token-shaped path。
- **研究可信度**：移除固定 AAPL/腾讯/地缘模板结论；rejected 字段不再回流；各市场保留自身 `asOf`；补齐 JP/KR/TW 映射。
- **Evidence 时效与口径**：不再把当前行情重标为历史回跑日期；跨 provider 财务只在报告期、比较期和币种可比时补齐。
- **诊断脱敏**：整条 Authorization/Cookie/Set-Cookie、结构化 header、webhook 和 token query 统一脱敏。
- **容器健康检查**：API 模式必须真实通过 HTTP health；scheduler-only 仅检查 PID 1。
- **依赖**：当前 lock/环境 `npm audit` 与 `pip-audit` 均为 0 known vulnerabilities。
- **孤儿运行时**：退役无法 import 且活动链零引用的 `src/market_cycle.py`；兼容生成入口仍为 `scripts/build_pages_compat_bundle.py`。

## 本地验证

### 当前代码快照

- Backend gate：`4871 passed, 4 deselected, 416 subtests`；syntax、flake8、deterministic、offline 全通过。
- Web gate：`npm ci`、lint、Vitest、Vite build 全通过；`977 passed / 2 skipped`。
- 依赖：`npm audit --omit=dev`、全量 `npm audit`、`pip check`、`pip-audit` 全部通过，0 known vulnerabilities。
- Pages source bundle：21 个必需文件、30 个链接、0 broken、0 legacy public files。
- Reader-only staging：11 个公开文件、19 个链接、0 broken；未 publish。
- Semantic audit：PASS；历史 2026-07-17 artifact 中 21 条 claim 被拒绝、28 条标为条件情景，最终可靠性为“中等可信，含待验证情景”。
- 文档链接：98 个 Markdown、244 个本地链接、0 broken。
- AI assets、OpenAPI JSON、`git diff --check`：PASS。
- 结构审计：858 files / 363770 LOC / 181 个 500 行以上文件 / 513 个复杂定义 / 180 个 TODO-like hits / 4 个 import cycles；`legacyPublicFiles=0`，`readerLeakFiles={}`。

### 未执行

- Docker image build：Docker daemon 未运行。
- Desktop 打包/安装、Playwright、Windows/macOS 签名与更新链。
- network live、真实外部 provider 全链、全新 LLM 日报。
- 候选分支 GitHub Actions、Pages 部署和线上 canary。

## 历史真实日报

最新完整日报仍是 `2026-07-17`，本轮没有重新生成：

| 指标 | 结果 |
|---|---|
| analysisMode | `FULL_REVIEW` |
| SourceHealth | `0.93` |
| Evidence | verified 37 / derived 102 / discovery 117 / missing 0 / critical missing 0 |
| Agent | 11/11 LLM success；fallback 0；`vertex_ai/gemini-3.5-flash` |
| ResearchReliability | 中等可信，含待验证情景 |

入口：

- `docs/reports/2026-07-17.html`
- `docs/reports/2026-07-17.artifact.json`
- `docs/reports/2026-07-17.diagnostics.html`
- `docs/local_acceptance/2026-07-17/final_acceptance.md`

这些是历史本地产物，不证明当前代码已生成新日报，也不代表云端已发布。

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

本地 allowlist 不会自动清除旧站或 Git 历史。当前只确认维护原文公开，未发现 credential 实值；不能升级表述为“密钥已泄漏”。

## 仍未收口

1. **线上 raw Pages exposure（P0 external）**：旧维护产物仍公开。
2. **upstream parity（P1）**：behind 60；至少缺少裸港股代码路由、Tencent provider 优先级、港股全市场快照缓存、Longbridge SDK 参数兼容等上游修复，不能机械 cherry-pick 后跳过产品回归。
3. **云端 CI/发布（P1）**：候选分支未 push；云端 `CI` workflow 当前为 `state=deleted`，active workflow 列表无 CI，也无 required checks。最新 Daily workflow 仍是旧 `main` 的 2026-06-26 failure；2026-08-12 的 Network Smoke success 仍只覆盖旧 main。
4. **GitHub 治理（P1 external）**：main 无 branch protection/ruleset；Actions 允许全部且不强制 SHA pin；secret scanning、push protection、Dependabot security updates 均关闭。
5. **Docker/Desktop/live（P1）**：镜像、跨平台桌面包、网络数据源和新 LLM 日报尚未验。
6. **API 权限分层（P1）**：完整 Reports artifact 仍依赖全局 admin auth；公开 Reader DTO 与私有维护 DTO 尚未拆开。
7. **继承型技术债（P2）**：181 个大文件、513 个复杂定义、4 个 import cycles 暂缓独立治理，不在发布前强拆。

## 下一步顺序

1. 在独立干净集成线合并/移植 upstream 60 commits，先处理 provider、认证、screening、Desktop 和 workflow 重叠。
2. 重跑 backend/Web/Reports/Pages/认证/P0 API；Docker daemon 可用后补 image smoke，并补 Desktop/Playwright。
3. 经用户授权后 push 候选分支并跑云端 required checks。
4. 启用仓库保护和安全扫描，固定第三方 Action SHA。
5. 将 Pages source 切到 GitHub Actions，部署 Reader allowlist，逐条确认旧 raw URL 为 404。
6. 最后再恢复日报 schedule；不在云验前自动触发模型、通知或发布。

## 架构真相

```text
原系统 DataFetcherManager / 原分析
→ Daily Universe
→ Evidence Pool / SourceHealth
→ Department Context Pack
→ 11 个 LLM Agent
→ Atomic Claim Semantic Gate
→ Risk / RedTeam
→ CIO Scenario Adjudication
→ ReportArtifact v1
→ ReaderV3 / Diagnostics / API / Pages
```

- Reports 是新增产品线，不是第二套独立系统。
- `readerV3` 面向公开阅读；完整 artifact、Diagnostics、ledger、memo 和日志属于维护面。
- SourceHealth 描述数据覆盖；ResearchReliability 描述结论可靠性。
- 搜索/新闻/LLM raw output 只作 discovery/opinion；进入 Reader 前必须回到 verified/derived evidence 或明确标为待验证情景。
- 不自动下单，不自动修改交易记录。

## 维护规则

- 当前代码、当次命令和线上实时状态优先于历史报告与计划。
- 本地测试、Git 可交付状态、云端发布状态必须分开汇报。
- `.env`、DB、logs、cache、每日生成产物不进入源码提交。
- 未经明确授权不 push、不切 Pages、不触发付费模型/通知/部署。
