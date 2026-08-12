# invest-system 技术债台账

> Last updated: 2026-08-12
> Scope: upstream-based release candidate + Reports product line.
> Branch: `codex/reports-v1-release`
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
| Git history | 分支从 `upstream/main@55946536` 建立；代码收口 HEAD `97c4d035`；最新 upstream 为 `3b98aa1d779a`；当前 ahead 9 / behind 60 |
| backend gate | `4871 passed, 4 deselected, 416 subtests`；syntax、flake8、deterministic、offline 全通过 |
| Web gate | 当前 lock `npm ci` 后 lint、`tsc -b`、Vitest、Vite build 全通过；`977 passed, 2 skipped` |
| dirty entries | `0`；人工 review 后已分包提交；每日运行产物和本地依赖由 `.gitignore` 隔离 |
| diff shortstat | 不在本文固化自引用行数；以 `python scripts/audit_tech_debt.py` 当前输出为准 |
| legacy public files | `0` |
| reader leak files | `{}` |
| import cycles | `4`，均为 upstream 继承链；Reports 未新增已知 cycle |
| large files >= 500 lines | `181`，其中 Reports 重点为 `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` |
| report regression | 测试在临时目录构造最小 artifact/ledger；不保留会过时的完整日报 fixture |
| 真实报告 | `2026-07-17`：`FULL_REVIEW`，SourceHealth `0.93`；研究可靠性“中等可信，含待验证情景”；21 条无支撑说法已移除 |
| Agent | `11/11` LLM success，fallback `0`，`vertex_ai/gemini-3.5-flash` |

## 台账

| ID | 等级 | 范围 | 债项 | 当前证据 | 策略 | 状态 |
|---|---|---|---|---|---|---|
| TD-P0-001 | P0 | upstream parity | 旧集成 worktree 基于过期 HEAD 且有 `397` 条 dirty | 已从 `upstream/main@55946536` 建立干净发布候选线；只迁移 145 条真实自定义路径并按逻辑拆分提交；旧 worktree 全量差异已归档 | 以发布候选线为唯一活跃集成入口；旧 worktree 只读保留 | VERIFIED |
| TD-P0-002 | P0 | routing | 报告系统可能覆盖原面板 | upstream routes 保留，新增 `/reports` | Reports 作为新增产品线 | VERIFIED |
| TD-P0-003 | P0 | API | 原 P0 API 可能缺失 | smoke 覆盖 AlphaSift / intelligence / usage / watchlist / scheduler；decision-signal/run-flow/position-analysis route present | 保留 upstream router，新增 reports router | VERIFIED |
| TD-P0-004 | P0 | pages/legacy | 旧 invest-brain 公开暴露 | Pages validator: `legacy_public_files=[]` | 不带 `docs/invest-brain/**` | VERIFIED |
| TD-P0-005 | P0 | tests/env | 真实 `.env` 污染测试 | LiteLLM 从旧 `.venv` 位置自动 load dotenv | pytest 默认 `LITELLM_MODE=PROD` | VERIFIED |
| TD-P0-006 | P0 | report artifact | Reports API/Web/Pages contract 分裂 | API smoke + Pages validator + Web tests | 三面只读 ReportArtifact v1 | VERIFIED |
| TD-P0-007 | P0 | Actions/PR | `pull_request_target` 检出 fork PR head 并运行 Python，同时注入 token/LLM secrets | 本地 workflow 已改为手动，只检出可信默认分支脚本并通过 GitHub API 读取 diff；安全回归覆盖 | 保持不执行 PR 代码；形成提交并云端复核后才关闭发布门 | VERIFIED_LOCAL |
| TD-P0-008 | P0 | live Pages | legacy `main/docs` 线上仍公开完整 artifact、RAW_AGENT memo、source-health JSON | 2026-08-12 三条抽检 URL 均 HTTP 200；公开内容扫描未发现 credential 实值，但维护原文已公开 | 用户授权后切 Actions allowlist、部署、验证旧 URL 404；必要时再决定 history purge/rotation | OPEN_EXTERNAL |
| TD-P0-009 | P0 | Docker/API bind | Docker compose 通过 `main.py --serve-only --host 0.0.0.0` 暴露端口，旧实现仅 warning；同时 auth runtime 只读磁盘 `.env`，compose 进程环境无法启用认证 | `main.py` 现对所有非 loopback 且 auth=false 的 bind fail-closed；`src/auth.py` 在持久化文件无显式键时回退进程环境；认证/入口/System Config 目标回归及最终 backend gate 通过 | 保持 Docker 公网入口必须显式启用 auth；实际镜像构建与部署 smoke 后再转 VERIFIED | VERIFIED_LOCAL |
| TD-P0-010 | P0 | auth settings | 有效 session cookie 曾可在不重新输入当前密码时关闭认证 | 已同步关闭认证二次确认契约：关闭认证必须 currentPassword；真实 ASGI 覆盖缺失 400、错误 401、限流 429、成功后清 cookie；前端回归通过；Web lint/build PASS | 集成 upstream 后保留同一契约并在云 CI 复核 | VERIFIED_LOCAL |
| TD-P1-001 | P1 | report UI | Reader 工程字段泄露 | audit: `readerLeakFiles={}` | Reader / Diagnostics 分层 | VERIFIED |
| TD-P1-002 | P1 | macro/source | source smoke 与 subject evidence 混用会误升 FULL | v1.1 已引入 true daily universe；subject evidence 由 DataFetcherManager 真实写入 | smoke 只证明源可连；FULL/LIMITED 只看 subject evidence | VERIFIED |
| TD-P1-003 | P1 | generated artifacts | report/docs 产物混审 | cleanup 前 `docs/` 生成产物淹没 status | 运行产物移入 `.local_archive/`，`.gitignore` 忽略每日产物；测试在临时目录构造最小 artifact/ledger | VERIFIED |
| TD-P1-004 | P1 | import cycles | audit `importCycles=4` | cycles 属 upstream 继承大链 | 不在报告接入中强拆；后续独立降债 | DEFERRED_WITH_REASON |
| TD-P1-005 | P1 | dependency security | npm / Python 依赖曾存在已知漏洞 | 当前 lock/环境 `npm audit --omit=dev`、全量 `npm audit` 与 `pip-audit` 均为 0 known vulnerabilities；`pip check` 无 broken requirements | 合并 upstream 后重跑云端/镜像审计；不把本地环境结果外推为所有部署环境 | VERIFIED_LOCAL |
| TD-P1-006 | P1 | agent/report | Agent 部门输出缺 reader contract | 多标的日报曾被 `600519` 单股 memo 污染 | Reader 只展示 market/portfolio/daily 部门；单股结论进个股下钻 | VERIFIED |
| TD-P1-007 | P1 | data/evidence | 原系统 DataFetcherManager 未进入 Evidence | 已新增 Subject Evidence Collector；2026-06-29 真实产出 `providerRuns=61`、`evidenceFacts=20` | 继续扩更多原系统 source 到 evidence；失败明确进 Diagnostics | VERIFIED |
| TD-P1-008 | P1 | ci | full gate 需要重跑验证 | 历史曾卡在 AlphaSift/SSL | 本轮已重跑全量 gate | VERIFIED |
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
| TD-P1-029 | P1 | upstream parity | 发布候选线不等于最新 upstream | 2026-08-12：`upstream/main=3b98aa1d779a`；当前 ahead 9 / behind 60；上游增量 394 files；候选增量重叠 52 paths，其中 2 已一致、50 待语义复核 | 在独立干净集成线合并 upstream；重跑认证、screening、P0 API、Web、Desktop、Reports、Pages、Docker 和 provider parity | DEFERRED_WITH_REASON |
| TD-P1-030 | P1 | release hygiene | 已验证的产品增量曾未形成可交付 Git 快照 | 104+ dirty 状态项已人工 review，并拆为安全、研究、Reports、tooling 与文档提交；`git status --short` 为空，结构审计 `dirtyEntries=0` | 保持生成产物隔离；后续集成 upstream 继续使用独立分支/工作树 | VERIFIED |
| TD-P1-031 | P1 | reader URL security | evidence `sourceUrl` 可把 userinfo、API key、signature 原样写入公开 Reader | canary 已复现；当前 sanitizer 移除敏感 query/fragment/userinfo并拒绝 webhook/token path，回归通过 | 所有公开链接只走同一 sanitizer；Pages staging 做 secret canary | VERIFIED |
| TD-P1-032 | P1 | API bind/auth | 文档入口 `server.py` 曾硬编码 `0.0.0.0:8000 + reload`，Docker 的 `main.py` 路径也曾只 warning | 当前默认 loopback；`server.py` 与 `main.py` 非 loopback 且无 auth 均直接拒绝；Docker 进程环境 auth 回归覆盖 | Docker/反代公开部署必须启用 admin auth；后续拆 public Reader API 与 private raw API | VERIFIED_LOCAL |
| TD-P1-033 | P1 | architecture | `src/market_cycle.py` 引用不存在模块且不在活动 runner | 原文件无法 import；活动链使用 `build_pages_compat_bundle.py`；删除后缺失 absolute import 为 0 | 退役孤儿平行运行时，不恢复 legacy 模块 | VERIFIED |
| TD-P1-034 | P1 | Docker health | API healthcheck 最后无条件 `exit(0)`，服务挂掉仍可 healthy | 新 healthcheck 对 API 模式强制 HTTP 探测，scheduler-only 仅检查 PID 1 | 保持 fail-closed 并在镜像构建 smoke 复核 | VERIFIED_LOCAL |
| TD-P1-035 | P1 | diagnostics/logs | 部门错误和公开 Actions raw log tail 可能绕过 sanitizer | 部门 runtime / CLI 已接统一 sanitizer；workflow 不再回显原始日志尾部；回归覆盖 | 公开日志只显示受控摘要，raw log 留本地维护面 | VERIFIED |
| TD-P1-036 | P1 | GitHub governance | public repo main 无 branch protection/ruleset；云端 CI workflow 为 `state=deleted`；Actions `allowed_actions=all` 且未强制 SHA pin；secret scanning、push protection、Dependabot security updates 关闭 | 2026-08-12 GitHub API 实时复核；rulesets=[]，main protection 404，active workflow 列表无 CI/required checks | 用户授权后恢复并验证 CI，保护 main、配置 required checks、限制 Actions 并固定三方 action SHA，启用可用的安全扫描与 push protection | OPEN_EXTERNAL |
| TD-P1-037 | P1 | provider parity | 裸港股路由、Tencent priority、港股全市场快照缓存和 Longbridge SDK 参数修复尚未集成 | 当前候选实测裸 `00700` 可误转 `.SZ`；对应 upstream commits 为 `02717771`、`90f62349`、`20c399e7`、`7fa29c7e` | 随 upstream 集成统一移植并跑 provider/market regression；不对当前代码伪称已修 | DEFERRED_WITH_REASON |
| TD-P2-001 | P2 | large files | 大文件/大服务多 | 2026-08-12 audit：858 files / 363770 LOC / largeFilesGe500=181 / complexDefs=513 / todoHits=180 / importCycles=4 | upstream 继承债；不阻塞本地报告闭环 | DEFERRED_WITH_REASON |
| TD-P2-002 | P2 | tests | 测试文件超大 | 多个 tests > 1000 行 | 保留回归价值，后续按模块拆 | DEFERRED_WITH_REASON |
| TD-P2-003 | P2 | report modules | `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` 仍偏大 | 2026-07-18 扫描分别为 5109/3241/2433 行；当前契约、测试与入口稳定 | 发布前不再为降行数做风险重构；后续按 contract/adapter/renderer 独立立项 | DEFERRED_WITH_REASON |

## 已完成提交分包

1. `8a3aca06 feat(research): add evidence-led department workflow`
   - Evidence、SourceHealth、部门 Context Pack、LLM runtime、GeoPolicy、RedTeam/CIO、语义与可靠性门。
2. `92fc0617 feat(reports): add artifact API and pages publication`
   - Reports API、ReportArtifact、Reader/Diagnostics、Pages bundle、统一本地/Actions 编排。
3. `c3d87d97 feat(web): add reports reader workspace`
   - `/reports` 产品 Reader、历史报告、部门下钻和 Diagnostics Web 入口。
4. `154d69c7 test(docs): close reports integration`
   - 契约/回归测试、Agent SOP、数据源政策、技术债、parity 和本地工作区真相源。
5. `2e34bbe8 fix(security): harden public runtime boundaries`
   - 公网 bind/auth、配置旁路、PR workflow、Docker health、诊断脱敏和依赖审计。
6. `c815c51f fix(research): enforce temporal evidence contracts`
   - Evidence 时间、主体、指标、来源、跨 provider 财务和跨市场语义约束。
7. `a9a1aa89 fix(reports): harden reader and publication contracts`
   - Reader schema/URL、Pages 路径安全、公开 allowlist、动态 curation 和孤儿 runtime 退役。
8. `97c4d035 chore(tooling): make debt audit linear`
   - 技术债扫描按定义线性计数，避免嵌套 AST 重复遍历。
9. 本文档收口提交
   - CURRENT_STATE、parity、技术债、部署/auth 文档和 Changelog 对齐 2026-08-12 实际状态。

每日 HTML/JSON、日志、DB、缓存、真实 `.env` 和 `.local_archive/` 均不进入提交。

## 复审文件

- `docs/UPSTREAM_PARITY_AUDIT.md`
- `docs/reports-product-line.md`
- 报告契约测试使用 pytest 临时目录构造最小 artifact/ledger，不依赖固定日期完整日报。
- 运行时验收报告：`docs/local_acceptance/{run_date}/final_acceptance.md`（被 `.gitignore` 忽略，按需生成）
- 原 2026-07-02 完整本地产物归档：`.local_archive/generated_runs/20260709-cleanup/`（被 `.gitignore` 忽略）
