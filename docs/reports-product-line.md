# Reports 产品线与运行边界

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

这些目录由本地脚本或 GitHub Actions 运行时生成，并通过 Pages artifact 发布。源码分支只保留长期文档和最小测试 fixture。

## Reader / Diagnostics

Reader 默认只展示：结论、依据、反证、下一步、部门摘要和可展开的人话证据摘要。

Diagnostics 才展示：provider matrix、source health、evidence ledger、agent run、run matrix、raw artifact。

Reader 分开表达两种状态：

- `SourceHealth`：数据覆盖、时效和 provider 可用性。
- `ResearchReliability`：最终结论是否被证据支持、是否仍是待确认情景。

2026-07-16 真实样例数据覆盖为 `LIMITED_REVIEW / 0.84`，结论层显示“可用，含待确认情景”；数据覆盖与结论可靠性仍分别表达，不把 provider 可用误写成结论确定。

LLM 长运行发生瞬时网络故障时，可在输入未变化的前提下显式续跑：

```bash
.venv311/bin/python scripts/run_daily_department_agents.py \
  --date YYYY-MM-DD --runtime llm --model-policy configured --resume-successful
```

续跑会重新校验已成功 memo；任何失效部门及其依赖下游都会重跑，不把旧成功直接当新成功。

## 本地生成

```bash
cd /Users/hac/AI-Studio/投研/invest-system-release-candidate
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

## 验收

本地必须通过：后端 gate、Pages validator、API smoke、Web test/lint/build、semantic quality audit、AI asset check、`git diff --check` 和运行产物 secret scan。2026-07-17 在 2026-07-16 报告样例上完成发布候选线验收：后端 `4684 passed, 1 skipped, 4 deselected, 416 subtests`，Web `971 passed / 2 skipped`。

## 云端发布边界

GitHub Actions 的 Reports 步骤必须显式获得 Daily Universe、数据源和 LLM 配置；step 之间不会自动继承上一 step 的 `env`。

本地与 Actions 使用同一个 `scripts/run_research_daily_local.sh` 编排入口。Actions 只在该入口完成后执行 Pages staging/publish，禁止再复制一套 Evidence、Agent、渲染和 validator 顺序。

发布门：

- `RESEARCH_AGENT_RUNTIME=llm`；
- 11 个 LLM Agent 全部成功；
- fallback 为 0；
- semantic quality audit 通过；
- Pages bundle validator 通过；
- 失败时上传 logs/artifacts，但不得部署 Pages。

本机 Vertex ADC 不会自动存在于 GitHub-hosted runner。当前云端先使用 Repository Secret `GEMINI_API_KEY`，模型策略 `best` 会优先 smoke Gemini 3.5 Flash，再回退到已配置的 Gemini 模型；规则 Agent 不作为云端成功 fallback。

首次发布前还要把仓库 Pages build source 从 legacy `main/docs` 切换成 `GitHub Actions`。该设置属于云端状态，必须在代码提交后再切换并手动触发验证。
