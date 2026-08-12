# Reports 产品线与运行边界

> Last verified: 2026-08-12

## 定位

Reports 是在原系统旁新增的投研阅读中心，不替代原交互面板、原数据源、原个股分析、原筛选和告警能力。

默认链路：

```text
原系统 DataFetcherManager / 原分析
→ Evidence Pool
→ Department Context Pack
→ LLM Agent 部门
→ Atomic Claim Semantic Gate
→ Risk / RedTeam
→ CIO Scenario Adjudication
→ ReportArtifact v1
→ Reader / Diagnostics
```

内部真相边界是 `src/research_core/` 的纯契约、语义门和可靠性裁决。`ReportArtifact v1` 是兼容发布契约，`readerV3` 是唯一产品文案源，Diagnostics 是原始排障视图。三者不是平行分析系统。

原系统 `DataFetcherManager` 的行情、K 线、基本面、资金、板块和指数进入 Evidence；原系统 LLM 个股/市场分析只作为 `opinion/input`，不能直接升级为 verified fact。最终 Reader claim 必须通过 evidence 主体、指标、时间、来源等级和因果边界校验。

## 运行产物边界

`docs/` 下的每日 HTML/JSON 是运行产物，不作为源码真相源长期追踪：

- `docs/reports/`
- `docs/run_status/`
- `docs/agent_memos/`
- `docs/market_cycle/`
- `docs/official_events/`
- `docs/daily/`
- `docs/index.html`
- `docs/governed_results.json`

这些目录由本地脚本或 GitHub Actions 运行时生成。完整 artifact、Diagnostics、memo、ledger 和 run status 只在维护面生成与验证；公开 Pages 仅从它们构建 Reader HTML allowlist。源码分支只保留长期文档和最小测试 fixture。

## Reader / Diagnostics

Reader 默认只展示：结论、依据、反证、下一步、部门摘要和可展开的人话证据摘要。

Diagnostics 才展示：provider matrix、source health、evidence ledger、agent run、run matrix、raw artifact。

Reader 分开表达两种状态：

- `SourceHealth`：数据覆盖、时效和 provider 可用性。
- `ResearchReliability`：最终结论是否被证据支持、是否仍是待确认情景。

机构级 Reader 的固定层级：

1. CIO 今日判断、行动定位、可信度和研究边界；
2. 三条核心理由、三条最大反证、三条下一步；
3. A 股、港股、美股市场级指数；仅在缺少市场级数据时才降级为明确标注的单股观察样本；
4. 重点标的价格、阶段表现、趋势、基本面、官方事件和观察位；
5. 基准情景、最强竞争情景、CIO 裁决和翻转信号；
6. 部门研究摘要与可展开证据；
7. 数据与方法说明默认折叠，原始工程字段只进入 Diagnostics。

推理表达固定分层：已核验事实可以确定表述；机制解释必须说明证据和竞争解释；情景必须给翻转信号；建议必须说明触发条件。RedTeam 提供最强竞争解释，不机械唱反调；CIO 必须解决部门冲突，不能把相互矛盾的结论并列复述。

2026-07-17 本地样例覆盖 A股/港股/美股市场级指数与 4 个跨市场标的，报告为 `FULL_REVIEW / 0.93`；Evidence 为 verified 37、derived 102、discovery 117、critical missing 0。该模式只描述数据覆盖，不替代结论可靠性；ResearchReliability 仍为“中等可信，含待验证情景”。最终标题另行通过 evidence closure，单日指数截面不直接升级为中期因果判断。

LLM 长运行发生瞬时网络故障时，可在输入未变化的前提下显式续跑：

```bash
.venv311/bin/python scripts/run_daily_department_agents.py \
  --date YYYY-MM-DD --runtime llm --model-policy configured --resume-successful
```

续跑会重新校验已成功 memo；任何失效部门及其依赖下游都会重跑，不把旧成功直接当新成功。

## 本地生成

```bash
cd /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812
scripts/run_research_daily_local.sh --date YYYY-MM-DD --runtime llm --symbols "600519,000001,AAPL,HK00700"
```

需要重新生成原系统市场与个股分析时，加：

```bash
scripts/run_research_daily_local.sh --date YYYY-MM-DD --runtime llm \
  --symbols "600519,000001,AAPL,HK00700" --with-original-analysis
```

## 打开

```bash
.venv311/bin/python server.py
```

然后访问：

```text
http://localhost:8000/reports
```

`server.py` 读取 `WEBUI_HOST` / `WEBUI_PORT`，默认只绑定
`127.0.0.1:8000`。非 loopback 绑定必须先启用 `ADMIN_AUTH_ENABLED=true`，
并在 loopback/离线 CLI 初始化有效管理员密码，否则直接拒绝启动；不要用手写 `uvicorn --host 0.0.0.0` 绕过此边界。

## 验收

本地必须通过：后端 gate、Pages validator、API smoke、Web test/lint/build、semantic quality audit、AI asset check、`git diff --check` 和运行产物 secret scan。2026-08-12 最终代码快照验收：后端 `6174 passed, 4 deselected, 501 subtests`，Web 最终 `1108 passed / 2 skipped`；Pages source 为 21 个必需文件 / 30 个链接 / 0 broken，公开 staging 只含 11 个 Reader HTML / 19 个链接，工程字段与维护路径扫描为 0。Desktop 50 tests、DMG 打包框架和依赖审计已通过；该验收仍不包含新 LLM 日报、完整 Desktop backend bundle/跨平台签名、成功 Docker image 或云端发布。

## 云端发布边界

GitHub Actions 的 Reports 步骤必须显式获得 Daily Universe、数据源和 LLM 配置；step 之间不会自动继承上一 step 的 `env`。

本地与 Actions 使用同一个 `scripts/run_research_daily_local.sh` 编排入口。Actions 只在该入口完成后执行 Pages staging/publish，禁止再复制一套 Evidence、Agent、渲染和 validator 顺序。

Pages staging 只复制公开 Reader 资产：`index.html`、汇总报告和分部门 HTML。完整 artifact、Diagnostics、Agent memo、provider/evidence ledger、run status 与原始日志只留在本地维护工作区，不进入公开 Pages artifact，也不上传到公开仓库的通用 Actions artifact。

发布门：

- `RESEARCH_AGENT_RUNTIME=llm`；
- 11 个 LLM Agent 全部成功；
- fallback 为 0；
- semantic quality audit 通过；
- Pages bundle validator 通过；
- 失败时只在 Actions job log 输出已脱敏摘要，不上传完整 logs/artifacts，也不得部署 Pages；若未来需要远程诊断包，必须先迁移到访问受限的私有存储。

本机 Vertex ADC 不会自动存在于 GitHub-hosted runner。candidate workflow 支持通过 Repository Secret `GEMINI_API_KEY` 运行；模型策略 `best` 会优先 smoke Gemini 3.5 Flash，再回退到已配置的 Gemini 模型，规则 Agent 不作为云端成功 fallback。实际云端 provider 尚未验证。

首次发布前还要把仓库 Pages build source 从 legacy `main/docs` 切换成 `GitHub Actions`。该设置属于云端状态，必须在代码提交后再切换并手动触发验证。

截至 2026-08-12，GitHub Pages 仍为 `build_type=legacy`、
source=`main/docs`，线上 `origin/main@7a8b4cf8` 不是当前发布候选线。
实时抽检完整 artifact、RAW_AGENT memo 与 source-health JSON 仍为 HTTP 200，
说明旧维护产物正在公开；候选 allowlist 不会自动清理旧站或 Git 历史。首次发布必须
在用户授权下切换 Actions、部署 allowlist，并逐项验证旧 raw URL 已 404。以上本地验收
不能表述为云端已发布。
