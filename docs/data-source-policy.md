# 数据源可信度与产品展示策略

> Last verified: 2026-08-12
> 目标：免费/已有源优先；A 股、港股、美股、宏观同权；系统给研究建议，但不自动下单。

## 两层状态

“数据齐”与“结论可靠”必须分开。

| 层 | 回答什么 | 当前实现 |
|---|---|---|
| SourceHealth | 源是否可用、数据是否新鲜、关键域是否覆盖 | `sourceHealthV2` |
| ResearchReliability | 最终 claim 是否被正确证据支持、是否仍是假设 | `researchReliability` + semantic gate |

`FULL_REVIEW` 只表示核心数据覆盖达到完整复盘条件，不表示所有因果判断都已证实。Reader 默认展示 ResearchReliability；provider 明细只进 Diagnostics。

## 数据域

| 域 | 主要输入 | 满足条件 |
|---|---|---|
| price | DataFetcherManager：EFinance/Tencent/AkShare/Pytdx/Baostock/YFinance 等 | OHLCV/实时行情、交易日与时效可用 |
| fundamentals | A 股 AkShare/Eastmoney、境外 YFinance、SEC companyfacts、公告/法披 | 财务、估值、经营指标可追；财务报告期可比 |
| filings_events | CNINFO、SSE/SZSE、HKEX、SEC、公司 IR | 官方原文或可追 URL |
| macro | FRED、官方政策源、本地市场周期计算 | 方法需要的序列齐全且时效达标 |
| news_sentiment | Tavily、GDELT、RSS、SearXNG | 只作 discovery；重大事实回到权威源 |
| portfolio | 持仓/自选/候选池 | 有快照或显式 empty |
| public_pages | 由 ReportArtifact 构建的 Reader 首页、汇总与分部门 HTML allowlist | Pages validator 通过；原始 artifact / Diagnostics / ledger / memo 不进公开包 |

## 证据等级

- `verified_fact`：SEC、FRED、CNINFO、交易所、政府/监管、公司 IR。
- `derived_fact`：原系统行情、技术指标、估值、资金面和本地确定性计算。
- `discovery`：搜索、新闻、Tavily、GDELT、RSS 线索。
- `agent_opinion`：部门 Agent 或原系统 LLM 分析。
- `final_claim`：CIO 经过语义门和情景裁决后的产品结论。

规则：

1. discovery/opinion 不能冒充 verified fact。
2. evidence id 存在不等于支持结论；还要核主体、指标、时间、来源等级和语义。
3. 因果、机制和未来路径没有直接证据时必须条件化。
4. 原系统 LLM 市场/个股分析只作观点输入；原系统确定性数据和计算才可成为 derived fact。
5. 单个 optional provider 失败不拖垮日报；失败原因必须进入 Diagnostics。

## 当前默认覆盖

| 市场/域 | 默认链 | 可选增强 |
|---|---|---|
| A 股行情 | EFinance、Tencent、AkShare、Pytdx、Baostock | Tushare、TickFlow |
| A 股公告 | CNINFO、SSE、SZSE | 商业公告源 |
| 港股行情/公告 | AkShare 宽基指数、YFinance 行情与财务、HKEX | Longbridge |
| 美股行情/法披 | YFinance、SEC | Finnhub、AlphaVantage、FMP |
| 宏观 | FRED 必需序列；AkShare/Eastmoney 中国 GDP/CPI/PMI（二级 derived） | NBS/PBOC 官方直连、FMP 等商业源 |
| 新闻/地缘 | Tavily、GDELT、RSS、ReliefWeb、OFAC/BIS/EU/官方政策页 | ACLED、商业情报源 |

付费源均为 optional，不是本地产品闭环的阻断依赖。

## 历史对比策略

历史原始数据由通用网上源获取，对比由本地确定性代码计算，不让 LLM 自己算趋势。

| 对比 | 原始数据 | 计算/留存 |
|---|---|---|
| 价格趋势 | 原 DataFetcherManager 多源 OHLCV，默认 260 交易日 | 本地计算 1/5/20/60/120/252 日收益、60 日波动率、区间位置 |
| 财务趋势 | A 股 AkShare/Eastmoney；美/港/日/韩/台 YFinance；美股 SEC 补强 | 本地按相同报告期对比收入、净利、经营现金流；保留最多 12 期 |
| 行业持续性 | 每日 sector rankings 在线快照 | 本地跨 run 统计重复领涨/领跌；只有两个以上快照才产出持续性证据 |
| 市场宽度 | A 股每日上涨/下跌家数与成交快照 | 本地跨 run 比较上涨占比、成交变化；20 个以上样本才计算本地分位 |
| 估值 | A 股原 provider quote + AkShare 公共 PE/PB 近三年序列；港美 YFinance fundamentals | 在线历史序列可直接计算公开样本分位；同时按日留存 PE/PB，至少 2 个本地样本才比较变化、至少 20 个样本才计算本地运行分位 |
| 宏观趋势 | FRED 历史序列 | 本地计算前值、12 期变化、历史位置 |

不做标的特例。基本面按缺失 block 补全，而不是“主源返回任意一个字段就停止 fallback”。单一源超时时可按市场路由到通用免费 fallback；失败进 Diagnostics，不伪造数据。

本地网络路由同样属于数据源合同：macOS 系统代理存在时，Eastmoney、Sina、Tencent、AkShare 上游、交易所与公告域名默认进入 `NO_PROXY`，避免国内免费源被本地代理误路由。明确的权限/认证错误按“数据源 + 市场”立即熔断本轮请求；例如 Tushare 免费账户无 `daily` 权限时跳过后续同市场标的，但不影响 Tencent/AkShare/Baostock 等免费 fallback。

中国 GDP/CPI/PMI 当前来自公开的 Eastmoney 数据集并由 AkShare 适配，统一标记为 `derived_fact / public_secondary_derived`，不冒充国家统计局直连。港股宽基指数优先尝试 AkShare 免费入口，失败后继续走原 provider fallback；单条历史不足时不再伪造 `0.00%` 涨跌。

基本面 fallback 按字段补齐，不再按整块覆盖：主源只有市值时，通用免费源仍可补入 PE/PB；主源已有的报告期、财务和估值值保持优先。A 股公开估值序列属于二级派生数据，不冒充交易所或公司法披。

## FRED 方法边界

日报在 Evidence 构建前执行 FRED 刷新。必需序列包括 GDP、失业率及历史、Sahm、CPI、政策利率、10Y/2Y、10Y-2Y、10Y-3M、信用利差、WTI、VIX。

- 收益率曲线只使用可比期限利差。
- 单点不能支撑“历史高/低位”。
- required series 缺失时刷新缓存；仍失败则明确降级。

## 产品展示

Reader 只展示：

- 今日判断
- 核心依据
- 正反情景及 CIO 裁决
- 分部门结论
- 风险、触发器、下一步
- 人话数据可信度

Diagnostics 才展示：

- provider matrix
- source health raw data
- evidence ledger
- Agent/model/run ledger
- raw artifact

Web 与管理面 API 读取完整 `ReportArtifact v1`；静态 Pages 只发布由它构建的 Reader HTML allowlist，不提供原始 artifact 或 Diagnostics。`readerV3` 是唯一产品文案源。

## 当前真实样例

2026-07-17 最新完整本地运行（本轮未重跑 LLM 日报）：

- SourceHealth：`FULL_REVIEW / 0.93`
- Evidence：verified 37、derived 102、discovery 117、missing critical 0
- ResearchReliability：`中等可信，含待验证情景`
- 11/11 LLM Agent success，fallback 0
- 21 条无支撑 claim 已移除，28 条推断已条件化；semantic quality audit PASS

## 运行产物

- `docs/run_status/{run_date}/provider_runs.jsonl`
- `docs/run_status/{run_date}/evidence_ledger.jsonl`
- `docs/run_status/{run_date}/source_health_v2.json`
- `docs/reports/{run_date}.artifact.json`
- `docs/reports/{run_date}.html`
- `docs/reports/{run_date}.diagnostics.html`

这些是运行时产物，由本地脚本或 Actions 生成，不作为源码长期追踪。
