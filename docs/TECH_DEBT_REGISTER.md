# invest-system 技术债台账

> Last updated: 2026-08-19
> Scope: upstream-based release candidate + Reports product line.
> Branch: `codex/reports-v1-upstream-sync`
> Status vocabulary: `OPEN` / `OPEN_EXTERNAL` / `FIXING` / `VERIFIED_LOCAL` /
> `VERIFIED` / `DEFERRED_WITH_REASON` / `REOPENED`.

## 验收口径

- 本地候选代码 P0 不允许保留 `OPEN`；外部线上 P0 必须明确标记并阻断发布，未经授权不擅自执行云端清理。
- Reports 只能新增产品线，不能覆盖 upstream 原入口。
- 默认 Reader 不暴露工程字段；Diagnostics 可暴露。
- `docs/invest-brain/**` 不公开。
- 不 push，不跑云端，不自动下单。

## 当前基线

| 指标 | 当前值 |
|---|---:|
| Git history | Reports 历史基底为 `upstream/main@55946536`；验收代码 `5de0183a` 基于 `upstream/main@cfd6b0a5`；2026-08-19 fetch 后 ahead 22 / behind 0 |
| backend gate | `6248 passed, 4 deselected, 40 warnings, 501 subtests passed`；syntax、critical flake8、deterministic、offline 全通过 |
| targeted gate | Agent timeout `536 passed / 1 warning / 8.86s`；merge semantic matrix `557 passed`；当前环境 authenticated Playwright `12/12 passed`，Chat/report API 为 hermetic fixture |
| Web gate | 本轮 Web 代码未变；沿用 `npm ci`、lint、Vitest、TypeScript/Vite build、prod/full audit 全通过，`1108 passed, 2 skipped` |
| Desktop gate | Electron `41.10.3` / Node `22.12.0`；`npm ci`、50/50 tests、build、prod/full audit 0；仅 DMG 打包框架通过，缺 backend bundle、Windows、签名和公证验收 |
| dependency gate | 当前工作树 `.venv311` 已新鲜安装；Python `pip check` 通过、`pip-audit --local` 为 0；Web/Desktop prod/full npm audit 0 |
| validated code anchor | `5de0183a`；本文只锚定已验证代码，不预写文档提交后的工作树状态 |
| diff shortstat | 不在本文固化自引用行数；以 `python scripts/audit_tech_debt.py` 当前输出为准 |
| legacy public files | `0` |
| reader leak files | `{}` |
| import cycles | `5`，作为继承型结构债独立治理 |
| large files >= 500 lines | `223`，其中 Reports 重点为 `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` |
| report regression | 测试在临时目录构造最小 artifact/ledger；不保留会过时的完整日报 fixture |
| Pages regression | 当前 validator 重跑 **2026-07-17 历史产物**：source 21/30/0，public staging 11/19/0；没有生成新 LLM 日报 |
| 真实报告 | `2026-07-17`：`FULL_REVIEW`，SourceHealth `0.93`；研究可靠性“中等可信，含待验证情景”；21 条无支撑说法已移除 |
| Agent | `11/11` LLM success，fallback `0`，`vertex_ai/gemini-3.5-flash` |

## 台账

| ID | 等级 | 范围 | 债项 | 当前证据 | 策略 | 状态 |
|---|---|---|---|---|---|---|
| TD-P0-001 | P0 | upstream parity | 旧集成 worktree 基于过期 HEAD 且有 `397` 条 dirty | 历史 Reports 提交已重放，报告可靠性与 Agent timeout upstream 增量均已合并；2026-08-19 fetch 后验收代码相对 `upstream/main@cfd6b0a5` 为 ahead 22 / behind 0 | 以 upstream-sync 分支为当前本地代码入口；旧线只读保留 | VERIFIED_LOCAL |
| TD-P0-002 | P0 | routing | 报告系统可能覆盖原面板 | upstream routes 保留，新增 `/reports` | Reports 作为新增产品线 | VERIFIED |
| TD-P0-003 | P0 | API | 原 P0 API 可能缺失 | smoke 覆盖 AlphaSift / intelligence / usage / watchlist / scheduler；decision-signal/run-flow/position-analysis route present | 保留 upstream router，新增 reports router | VERIFIED |
| TD-P0-004 | P0 | pages/legacy | 旧 invest-brain 公开暴露 | Pages validator: `legacy_public_files=[]` | 不带 `docs/invest-brain/**` | VERIFIED |
| TD-P0-005 | P0 | tests/env | 真实 `.env` 污染测试 | LiteLLM 从旧 `.venv` 位置自动 load dotenv | pytest 默认 `LITELLM_MODE=PROD` | VERIFIED |
| TD-P0-006 | P0 | report artifact | Reports API/Web/Pages contract 分裂 | API smoke + Pages validator + Web tests | 三面只读 ReportArtifact v1 | VERIFIED |
| TD-P0-007 | P0 | Actions/PR | `pull_request_target` 检出 fork PR head 并运行 Python，同时注入 token/LLM secrets | 本地 workflow 已改为手动，只检出可信默认分支脚本并通过 GitHub API 读取 diff；安全回归覆盖 | 保持不执行 PR 代码；形成提交并云端复核后才关闭发布门 | VERIFIED_LOCAL |
| TD-P0-008 | P0 | live Pages | legacy `main:/docs` 线上仍公开完整 artifact、RAW_AGENT memo、source-health JSON | 2026-08-19 三条抽检 URL 均 HTTP 200（12,325 / 6,317 / 5,877 bytes）；公开内容扫描未发现 credential 实值，但维护原文已公开 | 用户授权后切 Actions allowlist、部署、验证旧 URL 404；必要时再决定 history purge/rotation | OPEN_EXTERNAL |
| TD-P0-009 | P0 | Docker/API bind | Docker compose 通过 `main.py --serve-only --host 0.0.0.0` 暴露端口，旧实现仅 warning；同时 auth runtime 只读磁盘 `.env`，compose 进程环境无法启用认证 | `main.py` 现对非 loopback 且 auth=false/未初始化密码的 bind fail-closed；`src/auth.py` 在持久化文件无显式键时回退进程环境；认证/入口/System Config 回归及 full gate 通过。daemon/compose config 通过；image build 卡在解析 `docker/dockerfile:1.7` frontend，未生成镜像 | 保持公网入口必须显式 auth；取得镜像、import 和 health smoke 证据后再转 VERIFIED | VERIFIED_LOCAL |
| TD-P0-010 | P0 | auth settings | 有效 session cookie 曾可在不重新输入当前密码时关闭认证 | 关闭认证必须 currentPassword；真实 ASGI 覆盖缺失 400、错误 401、限流 429、成功后清 cookie；公网运行时返回 409；前端和 full gate 通过 | 云 CI 继续复核同一契约 | VERIFIED_LOCAL |
| TD-P1-001 | P1 | report UI | Reader 工程字段泄露 | audit: `readerLeakFiles={}` | Reader / Diagnostics 分层 | VERIFIED |
| TD-P1-002 | P1 | macro/source | source smoke 与 subject evidence 混用会误升 FULL | v1.1 已引入 true daily universe；subject evidence 由 DataFetcherManager 真实写入 | smoke 只证明源可连；FULL/LIMITED 只看 subject evidence | VERIFIED |
| TD-P1-003 | P1 | generated artifacts | report/docs 产物混审 | cleanup 前 `docs/` 生成产物淹没 status | 运行产物移入 `.local_archive/`，`.gitignore` 忽略每日产物；测试在临时目录构造最小 artifact/ledger | VERIFIED |
| TD-P1-004 | P1 | import cycles | audit `importCycles=5` | cycles 为继承型大链 | 不在报告接入中强拆；后续独立降债 | DEFERRED_WITH_REASON |
| TD-P1-005 | P1 | dependency security | npm / Python 依赖曾存在已知漏洞 | Web/Desktop production 与 full npm audit 均为 0；Desktop 已升 Electron `41.10.3` / Node `22.12.0`；Python `pip check` 无 broken requirements，`pip-audit --local` 为 0 | 云端和镜像仍须用 fresh environment 复核；不把本地环境外推到所有部署环境 | VERIFIED_LOCAL |
| TD-P1-006 | P1 | agent/report | Agent 部门输出缺 reader contract | 多标的日报曾被 `600519` 单股 memo 污染 | Reader 只展示 market/portfolio/daily 部门；单股结论进个股下钻 | VERIFIED |
| TD-P1-007 | P1 | data/evidence | 原系统 DataFetcherManager 未进入 Evidence | 已新增 Subject Evidence Collector；2026-06-29 真实产出 `providerRuns=61`、`evidenceFacts=20` | 继续扩更多原系统 source 到 evidence；失败明确进 Diagnostics | VERIFIED |
| TD-P1-008 | P1 | ci | full gate 需要重跑验证 | 历史曾卡在 AlphaSift/SSL；当前代码锚点 full gate 为 6248 passed / 4 deselected | 本轮已在当前新鲜 `.venv311` 重跑全量 gate | VERIFIED_LOCAL |
| TD-P1-009 | P1 | report policy | artifact/Reader 状态口径可能漂移 | 2026-07-10 真实 artifact 为 `LIMITED_REVIEW/0.9545`；`missingFacts=0`，但 000001 只有浅层估值、缺财务质量与增长数据 | SourceHealth、artifact、Reader、Pages validator 同源校验；不再用 provider 成功冒充基本面深度 | VERIFIED |
| TD-P1-010 | P1 | report UI | 板块表仍是旧模板文案 | 默认页“各板块结论”曾显示旧 market_cycle 模板 | ReaderV3 固定产品主线 + 分部门下钻，表格和下钻页改读 `departmentReports` | VERIFIED |
| TD-P1-011 | P1 | diagnostics/security | provider/API 异常可能把 token query 带进日志或诊断 | subagent 复审指出 `str(exc)` 直写风险；旧本地日志曾含 query token | 新增 `src/safe_diagnostics.py`，Finnhub/AlphaVantage/official/source-health 路径统一脱敏；旧本地日志移入废纸篓；测试覆盖 | VERIFIED |
| TD-P1-012 | P1 | reader/public pages | 首页和 one-screen brief 曾泄露 `SCREEN_ONLY` / `governed` / `agent_reported_data_gap` | subagent 复审 FAIL；Pages validator 当时未覆盖首页/one-screen | homepage/market_cycle/compat bundle 全部 reader 化；validator 纳入首页/one-screen和禁词；当前扫描 clean | VERIFIED |
| TD-P1-013 | P1 | macro methodology | LLM 曾用 DGS10 对比联邦基金利率判断收益率曲线，并用单点数据声称“历史低位” | 2026-07-10 RedTeam 识别到方法错误 | Prompt 明确可比期限；语义门拒绝错误比较；运行时剔除无支撑比较结论并保留 Diagnostics warning | VERIFIED |
| TD-P1-014 | P1 | agent runtime | 11 部门长运行遇到瞬时 DNS/凭据刷新失败时只能全量重跑 | 2026-07-10 后三阶段因 `oauth2.googleapis.com` DNS 失败 | 新增显式 `--resume-successful`；只复用同日成功 LLM memo，并重新验证语义和依赖；失效部门及其下游重跑 | VERIFIED |
| TD-P1-015 | P1 | architecture | `src/research_core/` 曾有未接入真实日报的平行 ResearchRun/Gate/Artifact 与仓位许可原型 | `gates.py` 及 ResearchRun/ResearchArtifact 只被自测调用；真实日报走 semantic gate、reliability 和 `report_artifact.py` | 退役平行 gates、无引用 contract 和手动 wrapper；`research_core` 只保留 Evidence/AtomicClaim、语义核验和可靠性裁决 | VERIFIED |
| TD-P1-016 | P1 | reader semantics | CIO/部门输出含工程 token、伪缺口、煽动性措辞和重复下一步 | 旧 Reader 依赖多层文本替换，`无/暂无` 被计为缺口 | ReaderV3 成为产品文案源；过滤伪缺口；下一步收口为“不做/看什么/下次复核”；Diagnostics 保留原文 | VERIFIED |
| TD-P1-017 | P1 | API cold start | API 启动无论是否使用飞书都会顶层加载完整 `lark_oapi` SDK | 冷启动 trace 确认通知 sender 是放大器；修后 `server` import 不再加载 `lark_oapi`，Reports/原 API smoke 全 200 | 飞书 App Bot SDK 改为使用时加载；Webhook/缺凭据路径不加载；SDK domain 在加载后解析 | VERIFIED |
| TD-P1-018 | P1 | model routing | Vertex 3.5 Flash 曾在错误项目/地区上下文中返回 404 | 另一项目证明同机 ADC + `global` 可用；Reports 子进程此前未透传 LiteLLM 使用的 `VERTEXAI_*` 变量 | 补齐 runtime env，配置同一 GCP project/global；真实 smoke `vertex_ai/gemini-3.5-flash` 成功 | VERIFIED |
| TD-P1-019 | P1 | evidence semantics | evidence id 存在不等于能支持对应结论，可能出现标的、指标、时间或因果错配 | 新增 17 组 semantic gate 回归，覆盖多标的、收益率曲线、Sahm、SEC、诉讼、资金流和地缘事件 | 原子 claim 逐条做存在性、主体、指标、时间、来源等级和因果边界校验；不支持则移除，推断则条件化 | VERIFIED |
| TD-P1-020 | P1 | macro data | FRED 缓存缺少期限利差、Sahm 等方法所需序列，旧缓存可被误当完整 | 真实刷新取得 DGS10/DGS2/T10Y2Y/T10Y3M/SAHMREALTIME 等 12 组序列 | required series 缺失即刷新；日报先 `--fred-only` 刷新，再建 Evidence | VERIFIED |
| TD-P1-021 | P1 | trust semantics | SourceHealth 覆盖分与最终结论可靠性曾混成一个“可信度” | 2026-07-12 数据覆盖为 FULL/0.895，但 46 条推断仍需条件化 | SourceHealth 只描述数据覆盖；ResearchReliability 独立描述结论审计；Reader 展示后者 | VERIFIED |
| TD-P1-022 | P1 | original analysis | 原系统 LLM 市场/个股分析可能被二次报告链误当事实 | 原始市场文本抽查出现不可靠叙事；当前部门上下文明确标为 opinion/input | 原系统分析只作观点输入；只有 Evidence 通过 semantic gate 后可支持 Reader 核心结论 | VERIFIED |
| TD-P1-023 | P1 | generated docs | 根 `docs/report_*.md/html` 曾漏出运行产物治理范围 | git status/audit 曾将 2 个根报告识别为 generated artifacts | `.gitignore` 增加 `/docs/report_*.md`、`/docs/report_*.html` | VERIFIED |
| TD-P1-024 | P1 | ignore/fixtures | 未锚定的 `reports/` 规则误伤任意层级同名目录，且本地完整日报 fixture 无测试引用 | `git check-ignore` 指向根规则；静态引用扫描为 0 | 改为 `/reports/`；退役无引用完整 fixture，契约测试继续使用临时目录 | VERIFIED |
| TD-P1-025 | P1 | local/cloud runner | 本地日报与 Actions 曾各自维护整套阶段顺序，云端漏情报 Evidence、预填派生 memo 且重复渲染 | workflow 与本地 runner 逐步漂移；静态报告步骤存在两次 `render_report_html.py` | Actions 只调用 `run_research_daily_local.sh`，再执行 publish；单一编排入口覆盖情报、Evidence、Agent、Reader 和 validator | VERIFIED |
| TD-P1-026 | P1 | report compatibility | ReaderV3 在没有部门 memo 的旧报告上丢失个股总结 | 全量 gate 首轮仅 `test_render_report_html...` 失败，旧 artifact 的 `301013` 未进入中心页 | 无部门卡时把 legacy `readerBrief.finalConclusion` 注入“重点个股”区；目标测试及全量 gate 通过 | VERIFIED |
| TD-P1-027 | P1 | pages/public boundary | 公开 Pages 曾可能随 `docs/` 上传 artifact、Diagnostics 和运行 ledger | workflow 改为上传每次清空重建的 `.pages_staging/site`；实际 staging 仅 11 个 Reader HTML，维护资产与工程字段扫描为 0 | 公开 Pages 只复制 Reader allowlist；完整诊断只留维护工作区 | VERIFIED |
| TD-P1-028 | P1 | reader/evidence binding | Reader curation 改写部门结论后仍可能沿用改写前的 evidence sample | 市场页曾用 AAPL/腾讯单股样本支撑市场级结论，地缘页曾显示 FRED 宏观样例 | curation 后按可见结论重新绑定：市场→A/H/US main indices，地缘→ReliefWeb 事件；回归测试覆盖 | VERIFIED |
| TD-P1-029 | P1 | upstream parity | 发布候选线不等于最新 upstream | 2026-08-19 fetch 后，验收代码相对 `upstream/main@cfd6b0a5` 为 ahead 22 / behind 0；Agent timeout merge、queue stall 修复与高风险语义已人工复核，目标、语义矩阵和 full gate 通过 | 发布前重新 fetch；若 upstream 再前进则重跑 parity matrix，不把点时同步写成永久状态 | VERIFIED_LOCAL |
| TD-P1-030 | P1 | release hygiene | 已验证的产品增量曾未形成可交付 Git 快照 | 历史 dirty 已人工 review 并拆为研究、Reports、Web、安全、配置、API、Desktop、tooling 提交；当前验证代码锚点为 `5de0183a` | 保持生成产物隔离；文档独立提交，最终再次核 `git status` | VERIFIED_LOCAL |
| TD-P1-031 | P1 | reader URL security | evidence `sourceUrl` 可把 userinfo、API key、signature 原样写入公开 Reader | canary 已复现；当前 sanitizer 移除敏感 query/fragment/userinfo并拒绝 webhook/token path，回归通过 | 所有公开链接只走同一 sanitizer；Pages staging 做 secret canary | VERIFIED |
| TD-P1-032 | P1 | API bind/auth | 文档入口 `server.py` 曾硬编码 `0.0.0.0:8000 + reload`，Docker 的 `main.py` 路径也曾只 warning | 当前默认 loopback；`server.py`、`main.py`、`webui.py` 与 middleware 共享非 loopback guard；auth 与 full gate 通过 | Docker/反代公开部署必须启用 admin auth；后续拆 public Reader API 与 private raw API | VERIFIED_LOCAL |
| TD-P1-033 | P1 | architecture | `src/market_cycle.py` 引用不存在模块且不在活动 runner | 原文件无法 import；活动链使用 `build_pages_compat_bundle.py`；删除后缺失 absolute import 为 0 | 退役孤儿平行运行时，不恢复 legacy 模块 | VERIFIED |
| TD-P1-034 | P1 | Docker health | API healthcheck 最后无条件 `exit(0)`，服务挂掉仍可 healthy | 新 healthcheck 对 API 模式强制 HTTP 探测，scheduler-only 仅检查 PID 1；本地契约回归通过，但 image build 未完成 | 保持 fail-closed；成功 image/import/health smoke 后关闭环境验证缺口 | VERIFIED_LOCAL |
| TD-P1-035 | P1 | diagnostics/logs | 部门错误和公开 Actions raw log tail 可能绕过 sanitizer | 部门 runtime / CLI 已接统一 sanitizer；workflow 不再回显原始日志尾部；回归覆盖 | 公开日志只显示受控摘要，raw log 留本地维护面 | VERIFIED |
| TD-P1-036 | P1 | GitHub governance | public repo main 无 branch protection/ruleset；云端 CI workflow 为 `state=deleted`；Actions `allowed_actions=all` 且未强制 SHA pin；secret scanning、push protection、Dependabot security updates 未启用 | 2026-08-19 GitHub API 实时复核；rulesets=[]，main protection 404，active workflow 列表无 CI/required checks，code scanning 无有效结果 | 用户授权后恢复并验证 CI，保护 main、配置 required checks、限制 Actions 并固定三方 action SHA，启用可用的安全扫描与 push protection | OPEN_EXTERNAL |
| TD-P1-037 | P1 | provider parity | 裸港股路由、Tencent priority、港股全市场快照缓存和 Longbridge SDK 参数修复曾缺失 | `02717771`、`90f62349`、`20c399e7`、`7fa29c7e` 与 YFinance PE/PB 修复均保留；full backend gate 通过 | 保持 provider/market regression；Longbridge 真凭据 live smoke 仍按需只读执行 | VERIFIED_LOCAL |
| TD-P1-038 | P1 | runtime/report outcome | 缓存/回退大盘复盘可能返回文本却未落盘；常规 one-shot 曾对部分 `analysis_ok=false` 返回 0；YFinance TTM 可能计入 `as_of` 后的未来股息 | 缓存/回退报告保存失败现在 fail-closed，常规 one-shot 任意失败返回非零，TTM 使用包含边界的 `cutoff <= event <= as_of`；当前 full backend 6248 通过 | 持续覆盖报告持久化、退出码和可注入时钟边界；不把通知成功替代报告成功 | VERIFIED_LOCAL |
| TD-P1-039 | P1 | cloud smoke | Network Smoke workflow 显示 success，但有效网络覆盖/quick analysis 不满足发布门 | 2026-08-19 #59 仍为 false-green，且运行在旧 main | 将无有效网络用例或 quick failure 设为非零；候选分支云端重跑前不作为发布证据 | OPEN_EXTERNAL |
| TD-P1-040 | P1 | agent/tool timeout | 类别/单工具/显式超时优先级、后台线程取消、registry 热重载与并行排队可能造成错误超时、无限 queue wait 或重复副作用 | `cfd6b0a5` 实现 first-wins/wall cap/non-retriable/协作取消/带锁 registry/worker-start deadline；`5de0183a` 在 5 个非协作超时 handler 满池时给 0.5s grace，随后只取消未启动 future 并返回 queued/non-retriable timeout，红测约 1.21s→0.60s；targeted 536、matrix 557、full 6248，复审 P0/P1=0 | 保持配置/并发/side-effect 回归；真实外部 provider 长工具调用仍不冒充已验证 | VERIFIED_LOCAL |
| TD-P2-001 | P2 | large files | 大文件/大服务多 | 2026-08-19 audit：958 files / 430516 LOC / largeFilesGe500=223 / complexDefs=614 / todoHits=246 / importCycles=5 | 继承型结构债；不阻塞本地报告闭环 | DEFERRED_WITH_REASON |
| TD-P2-002 | P2 | tests | 测试文件超大 | 多个 tests > 1000 行 | 保留回归价值，后续按模块拆 | DEFERRED_WITH_REASON |
| TD-P2-003 | P2 | report modules | `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` 仍偏大 | 2026-08-19 扫描分别为 5513/3325/2430 行；当前契约、测试与入口稳定 | 发布前不再为降行数做风险重构；后续按 contract/adapter/renderer 独立立项 | DEFERRED_WITH_REASON |

## 已完成提交分包

1. `e839427f` / `b46e202f` / `560d086d` / `a2cce1b4`
   - Evidence/Agent/Reports/Web 产品线、契约测试与基础文档。
2. `cd31bced` / `bad4f723` / `d220a390` / `db9072d8`
   - 公网安全、时间与 evidence 契约、Reader/Pages 加固、技术债扫描性能。
3. `368a3d5f`
   - 同步前发布候选状态快照。
4. `eb7c8cf7`
   - upstream 集成冲突收口，保留 Screening、provider、CI、Desktop 与配置运行时契约。
5. `d235728e` / `0894a625` / `309b89e1`
   - Reports LLM/workflow 配置、OpenAPI 可复现产物、时间敏感回归稳定化。
6. `81bbec6b` / `4f12aac5` / `dca827b0`
   - 首轮 Desktop 安全依赖、OpenAPI schema toolchain 与 2026-08-12 同步验收文档收口。
7. `c6894771`
   - 合并 upstream 4 个报告可靠性提交，基底前进到 `5c964bf2`。
8. `0ff9dd5e` / `5cf86b7a` / `8f619331`
   - 认证态 hermetic Playwright、报告持久化/one-shot/YFinance 时间边界，以及 Electron 41 / Node 22 Desktop 安全基线。
9. `98b15a99`（合并 `upstream/main@cfd6b0a5`）
   - Agent per-category/tool/per-run timeout、协作取消、registry 热重载与并发 deadline 语义。
10. `5de0183a`
   - 满池非协作超时 handler 的 queue stall fail-closed，保留正常排队后 fast 调用语义。
11. 本文档收口提交
   - CURRENT_STATE、parity、技术债、工作区路由、Reports 边界和 Changelog 对齐 2026-08-19 代码锚点与云端点时状态。

每日 HTML/JSON、日志、DB、缓存、真实 `.env` 和 `.local_archive/` 均不进入提交。

## 复审文件

- `docs/UPSTREAM_PARITY_AUDIT.md`
- `docs/reports-product-line.md`
- 报告契约测试使用 pytest 临时目录构造最小 artifact/ledger，不依赖固定日期完整日报。
- 运行时验收报告：`docs/local_acceptance/{run_date}/final_acceptance.md`（被 `.gitignore` 忽略，按需生成）
- 原 2026-07-02 完整本地产物归档：`.local_archive/generated_runs/20260709-cleanup/`（被 `.gitignore` 忽略）
