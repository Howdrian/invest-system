# invest-system 技术债台账

> Last updated: 2026-07-17
> Scope: upstream-based release candidate + Reports product line.
> Branch: `codex/reports-v1-release`
> Status vocabulary: `OPEN` / `FIXING` / `VERIFIED` / `DEFERRED_WITH_REASON` / `REOPENED`.

## 验收口径

- P0 不允许保留 `OPEN`。
- Reports 只能新增产品线，不能覆盖 upstream 原入口。
- 默认 Reader 不暴露工程字段；Diagnostics 可暴露。
- `docs/invest-brain/**` 不公开。
- 不 push，不跑云端，不自动下单。

## 当前基线

| 指标 | 当前值 |
|---|---:|
| Git history | 分支从 `upstream/main@55946536` 建立；Reports 真正增量已按研究内核、发布链、Web、测试文档拆分为可审提交 |
| backend gate | `4684 passed, 1 skipped, 4 deselected, 416 subtests`；Python 3.11 全量 gate 通过 |
| Web gate | `971 passed, 2 skipped`；lint 通过；build 通过 |
| dirty entries | 发布候选线目标为 `0`；每日运行产物、验收材料和本地依赖由 `.gitignore` 隔离 |
| diff shortstat | 不在本文固化自引用行数；以 `python scripts/audit_tech_debt.py` 当前输出为准 |
| legacy public files | `0` |
| reader leak files | `{}` |
| import cycles | `4`，均为 upstream 继承链；Reports 未新增已知 cycle |
| large files >= 500 lines | `178`，其中 Reports 重点为 `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` |
| report regression | 测试在临时目录构造最小 artifact/ledger；不保留会过时的完整日报 fixture |
| 真实报告 | `2026-07-16`：`LIMITED_REVIEW`，SourceHealth `0.84`；研究可靠性“可用，含待确认情景” |
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
| TD-P1-001 | P1 | report UI | Reader 工程字段泄露 | audit: `readerLeakFiles={}` | Reader / Diagnostics 分层 | VERIFIED |
| TD-P1-002 | P1 | macro/source | source smoke 与 subject evidence 混用会误升 FULL | v1.1 已引入 true daily universe；subject evidence 由 DataFetcherManager 真实写入 | smoke 只证明源可连；FULL/LIMITED 只看 subject evidence | VERIFIED |
| TD-P1-003 | P1 | generated artifacts | report/docs 产物混审 | cleanup 前 `docs/` 生成产物淹没 status | 运行产物移入 `.local_archive/`，`.gitignore` 忽略每日产物；测试在临时目录构造最小 artifact/ledger | VERIFIED |
| TD-P1-004 | P1 | import cycles | audit `importCycles=4` | cycles 属 upstream 继承大链 | 不在报告接入中强拆；后续独立降债 | DEFERRED_WITH_REASON |
| TD-P1-005 | P1 | dependency security | npm audit `16 vulnerabilities` | npm install 输出 | 不自动 audit fix；后续安全升级计划 | DEFERRED_WITH_REASON |
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
| TD-P2-001 | P2 | large files | 大文件/大服务多 | audit largeFilesGe500=178 | upstream 继承债；不阻塞本地报告闭环 | DEFERRED_WITH_REASON |
| TD-P2-002 | P2 | tests | 测试文件超大 | 多个 tests > 1000 行 | 保留回归价值，后续按模块拆 | DEFERRED_WITH_REASON |
| TD-P2-003 | P2 | report modules | `report_artifact.py`、`daily_department_llm.py`、`render_report_html.py` 仍偏大 | 分别约 2944/2966/2116 行；当前契约、测试与入口稳定 | 发布前不再为降行数做风险重构；后续按 contract/adapter/renderer 独立立项 | DEFERRED_WITH_REASON |

## 已完成提交分包

1. `8a3aca06 feat(research): add evidence-led department workflow`
   - Evidence、SourceHealth、部门 Context Pack、LLM runtime、GeoPolicy、RedTeam/CIO、语义与可靠性门。
2. `92fc0617 feat(reports): add artifact API and pages publication`
   - Reports API、ReportArtifact、Reader/Diagnostics、Pages bundle、统一本地/Actions 编排。
3. `c3d87d97 feat(web): add reports reader workspace`
   - `/reports` 产品 Reader、历史报告、部门下钻和 Diagnostics Web 入口。
4. `test(docs): close reports integration`
   - 契约/回归测试、Agent SOP、数据源政策、技术债、parity 和本地工作区真相源。

每日 HTML/JSON、日志、DB、缓存、真实 `.env` 和 `.local_archive/` 均不进入提交。

## 复审文件

- `docs/UPSTREAM_PARITY_AUDIT.md`
- `docs/reports-product-line.md`
- 报告契约测试使用 pytest 临时目录构造最小 artifact/ledger，不依赖固定日期完整日报。
- 运行时验收报告：`docs/local_acceptance/{run_date}/final_acceptance.md`（被 `.gitignore` 忽略，按需生成）
- 原 2026-07-02 完整本地产物归档：`.local_archive/generated_runs/20260709-cleanup/`（被 `.gitignore` 忽略）
