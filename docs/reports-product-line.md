# Reports 产品线与运行边界

> Last verified: 2026-09-08

## 定位

Reports 是 DSA 内的原生新增页面（同一 Web app / API），不是 iframe 或另一套网站；不替代原交互面板、原数据源、原个股分析、原筛选和告警能力。

## 入口和类型

- `/reports`：最新部门日报；`/reports/YYYY-MM-DD`：指定日报。
- `/reports/history:ID`：原系统的个股或市场完整分析，复用原生详情组件。历史列表显示名称，不把市场报告塞进个股日报模板。
- `/reports/<同一日期或ID>/diagnostics`：同一报告的工程排障信息。
- 静态 Reader 是同一日报产物的无后端阅读版，不是第二套 AI 分析链。
- 上游新 `structured_report` 保留原分析结构化产物；我们的 `ReportArtifact v1` 承接跨部门汇总/发布。兼容保留两字段，不为两份结构重复调用模型。以后如要合并 schema，应走 adapter 迁移而非本轮强改。

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

### 跨市场行业材料与复用

- 原 `get_sector_rankings()` 仍服务A股，不修改上游fallback。新增只读 `get_sector_performance(market, as_of)` 接入现有SectorAgent，不另起行业Agent或独立报告服务。
- 美股：YFinance取得11个标普500行业ETF及SPY的复权历史；港股：复用AkShare/Sina解码取得6个行业/主题指数及恒指。港股覆盖含科技、内地银行/油气/地产/消费、博彩，不称为港股全行业。
- 1/5/20/60交易日收益与同起止日期的基准比较进入Evidence；缺基准对应日期就不计算相对收益。价格强弱不是资金流入，也不能直接升级为公司盈利改善。
- 行业Agent保留完整行业记录而非截断长字符串；市场指数按三地优先进入对应Context。下游部门摘要先覆盖不同主体，再填剩余要点，避免第四只股票因固定前三条被遗漏。
- 历史行业路由使用 `news_sentiment`，语义判断只对已知的数值型 `derived_fact` 行业指标补充价格域；搜索/新闻不跟随升级。聚合证据只支持其明确列出的指数/ETF，不为无关公司财务背书。
- Reader并列展示“行情观察”和“部门研究”。行情表可展开阶段表现与来源；部门关注方向仍来自真实部门结论，不把涨幅排行榜伪装成AI推荐。
- CIO补数后按实际输入是否变化决定二次生成；复用证据且上下文不变则不再重写一次。新证据确实改变输入时仍重新总结。

### 当前架构判断与优先级

主干合理，不需要重新搭系统。原交互分析、跨部门日报和静态阅读版有不同用途，数据与生成后端共享；不应为了统一页面而强迫个股提问执行全部部门。

仍有需要收口的边界，不以测试数量代替产品价值：

1. 原个股历史稿与后续部门证据可能不同批次。应标清运行/材料时间，必要时按需重跑原分析，不由Reader抹掉原文。
2. 原 `structured_report` 与兼容 `ReportArtifact v1` 暂经adapter并存，不重复生成。大文件、语义校验的规则复杂度和5组静态循环依赖仍是维护债，不宣称架构完全洁净。
3. 没有持仓时，持仓部门仅作观察池说明；后续可显式跳过低价值空持仓生成。是否跳过应有独立状态，不能冒充LLM完成。
4. 渲染/发布验证的两遍收尾不调用模型，成本低；不优先于资料丢失和重复CIO生成治理。原分析默认复用，只有显式需要才重生成。
5. 下一阶段重点是连续多日运行、实际论点复盘及通知可靠性，而不是继续添加Agent、安全门或状态文档。单次报告可读可追源不等于预测有效或无人值守生产已验收。

运行结果与报告持久化也必须一致：缓存或回退得到的大盘复盘文本只有在报告成功落盘后才算成功；常规 one-shot 只要 `analysis_ok=false` 就返回非零。通知发送成功不能替代报告生成成功。YFinance TTM 现金股息按事件时区使用包含边界的 `cutoff <= event <= as_of`，不得把未来股息计入目标日 TTM。

Agent 工具超时按 first-wins 解析：显式 per-run > 单工具声明 > data/search/analysis/action/market 类别默认 > 无限制，剩余总 wall-clock 预算只作不可突破的外层上限。超时结果标记 non-retriable 并阻止同调用重入；后台 handler 只能协作取消，不能把 Python 线程误述为已强制终止。若 5 个已超时的非协作 handler 占满 pool，runner 给 0.5 秒 cooperative grace，随后只取消仍未启动的 future，并返回带 `queued=true` 的 non-retriable timeout；不会谎称运行中线程已被终止。真实外部 provider 的长工具调用仍需 live 验证。

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

### 2026-09-08 直接阅读与完整下钻

- 首屏列CIO总判断及A/H/US三地具体选择；研究范围、组合说明、方法后置折叠，不在首屏重复大段规则。三地要点仍来自同轮CIO，缺少某市场意见时不制造推荐。
- 公司“综合研究”在当前日报展开同轮CIO、基本面、技术、情报、风险和红队的相关完整观点及证据摘要；按公司主体精确匹配，不纳入其他公司或已经撤回的论点。
- 原历史入口明确标为“原 DSA 短线分析”，保留独立时点/策略的原文。它不是当前CIO评级的完整论证，二者允许因期限或材料差异得出不同建议。
- 静态独立部门页保留全部已保留论点、反证和行动条件，不截取前5条或180字。摘要可以精简，但展开后不能丢失后排港美观点或句末改判条件。
- 行业判断默认简洁展开；行情观察提供20交易日同日期基准相对收益图和完整阶段表。图表不另算研究评级，正负数值与文字同时呈现。手机和桌面使用同一Reader内容。
- 本轮没有改变原DSA入口、数据源路由或增加门控。本期已在9/8真实11部门日报上完成复审，结论见[当前状态](CURRENT_STATE.md)；不以预览、Prompt变更或UI测试代替LLM质量。

- 价格/财务快照表不再展示原规则型stance定位，避免与CIO研究评级竞争；原API字段兼容保留。系统候选名称来自同轮universe discovery，不因缺原DSA单股历史而退化为纯代码。

### 2026-09-06 关注清单与逐条论据

- `readerV3.focusList` 索引同轮现有部门结论，不新调用模型、不生成另一套投资排序。板块分强势跟踪/承压观察；个股分优先研究/跟踪观察，保留理由、观察条件和原分析入口。未建立行业归属不硬连板块与个股。
- `readerV3.departmentCards[].claimAssessment` 区分有据支持、部分支持、推演待验证、存在争议。单条推演或已删除的草稿不再把整个部门压成中等；未来触发条件不混入当前结论统计。
- 保留旧 `confidence` 兼容字段，但不把它包装成统计胜率；历史被程序改写过的自评分不追溯伪造。新运行不再因含一条推演就覆盖模型自评。
- 已有红队有效反证仍逐条关联争议结论，不因新关注清单/新标签恢复已撤回说法。它不是对整个部门或系统新增限制。
- Web 和静态 HTML（含部门子页）消费同一 Reader 数据；仅重渲染时不意味着重新采集市场行情或重跑 Agent。


Reader 默认只展示：结论、依据、反证、下一步、部门摘要和可展开的人话证据摘要。

Diagnostics 才展示：provider matrix、source health、evidence ledger、agent run、run matrix、raw artifact。

Reader 分开表达两种状态：

- `SourceHealth`：数据覆盖、时效和 provider 可用性。
- `ResearchReliability`：最终结论是否被证据支持、是否仍是待确认情景。

机构级 Reader 的固定层级：

1. CIO 今日判断、行动定位、论据评估和研究边界，以及分级板块/个股关注清单；
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

当前工作树 `.venv311` 已新鲜安装依赖；本地启动使用当前代码和当前解释器：

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

本地必须通过：后端 gate、Pages validator、API smoke、Web test/lint/build、semantic quality audit、AI asset check、`git diff --check` 和运行产物 secret scan。2026-08-19 验收代码 `5de0183a`：后端 `6248 passed, 4 deselected, 40 warnings, 501 subtests passed`，Agent timeout targeted `536 passed / 1 warning / 8.86s`，merge semantic matrix `557 passed`，当前环境 authenticated Playwright `12/12 passed`；当前工作树 Python dependency audit 为 0。Playwright 使用真实本地 login/backend 与临时 DB，但 Chat/report API 为 hermetic fixture，不调用真实 LLM/provider。Web 代码本轮未变，沿用 `1108 passed / 2 skipped`、lint/TypeScript/build/audit 0；Desktop 代码本轮未变，沿用 Electron `41.10.3` / Node `22.12.0` 下 50 tests、build 和 audit 0，但仍只是未签名 DMG 框架。Pages 的 21 required / 30 links 与公开 staging 11 files / 19 links 是当前 validator 对 **2026-07-17 历史产物**的重跑，不是 `5de0183a` 新生成日报。验收不包含新 LLM 日报、完整 Desktop backend bundle/Windows/签名公证、成功 Docker image 或云端发布。

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

截至 2026-08-19 20:35 CST，GitHub Pages 仍为 `build_type=legacy`、
source=`main:/docs`，线上 `origin/main@7a8b4cf8` 不是当前发布候选线。
实时抽检完整 artifact、RAW_AGENT memo 与 source-health JSON 仍为 HTTP 200，
说明旧维护产物正在公开；候选 allowlist 不会自动清理旧站或 Git 历史。首次发布必须
在用户授权下切换 Actions、部署 allowlist，并逐项验证旧 raw URL 已 404。以上本地验收
不能表述为云端已发布。候选分支仍未 push、PR 为 0，CI workflow 为 `state=deleted`；
2026-08-19 Network Smoke #59 虽显示 success，但有效网络覆盖和 quick analysis 仍不满足
发布门且仅覆盖旧 main，属于 false-green，不能作为候选发布证据。
