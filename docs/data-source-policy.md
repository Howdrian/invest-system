# 数据源可信度与产品展示策略

> Last verified: 2026-07-13
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
| fundamentals | 原系统 fundamental context、SEC companyfacts、公告/法披 | 财务、估值、经营指标可追 |
| filings_events | CNINFO、SSE/SZSE、HKEX、SEC、公司 IR | 官方原文或可追 URL |
| macro | FRED、官方政策源、本地市场周期计算 | 方法需要的序列齐全且时效达标 |
| news_sentiment | Tavily、GDELT、RSS、SearXNG | 只作 discovery；重大事实回到权威源 |
| portfolio | 持仓/自选/候选池 | 有快照或显式 empty |
| publish_bundle | Artifact、Reader、Diagnostics、分部门报告 | Pages validator 通过 |

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
| 港股行情/公告 | AkShare、YFinance、HKEX | Longbridge |
| 美股行情/法披 | YFinance、SEC | Finnhub、AlphaVantage、FMP |
| 宏观 | FRED 必需序列、官方政策源 | FMP 等商业源 |
| 新闻/地缘 | Tavily、GDELT、RSS、ReliefWeb、OFAC/BIS/EU/官方政策页 | ACLED、商业情报源 |

付费源均为 optional，不是本地产品闭环的阻断依赖。

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

Web、API、静态 Pages 读取同一份 `ReportArtifact v1`；`readerV3` 是唯一产品文案源。

## 当前真实样例

2026-07-12 本地运行：

- SourceHealth：`FULL_REVIEW / 0.895`
- Evidence：verified 37、derived 66、discovery 10、missing critical 0
- ResearchReliability：`可用，含待确认情景`
- 11/11 LLM Agent success，fallback 0
- 46 条推断已条件化；semantic quality audit PASS

## 运行产物

- `docs/run_status/{run_date}/provider_runs.jsonl`
- `docs/run_status/{run_date}/evidence_ledger.jsonl`
- `docs/run_status/{run_date}/source_health_v2.json`
- `docs/reports/{run_date}.artifact.json`
- `docs/reports/{run_date}.html`
- `docs/reports/{run_date}.diagnostics.html`

这些是运行时产物，由本地脚本或 Actions 生成，不作为源码长期追踪。
