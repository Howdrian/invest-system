# SourceReviewAgent — market

- 输出来源：有限证据 Agent 输出
- 当前状态：警告
- 证据等级：LIMITED

## 一句话结论
有限信息结论：本轮可读但需按 source health 降权。

## 我搜了什么
- src.macro.official_sources: source health check: src.macro.official_sources -> 降级（缺 key），返回 0 条
- src.intel.market_heat: source health check: src.intel.market_heat -> 可用，返回 1 条
- src.prediction_market.polymarket: source health check: src.prediction_market.polymarket -> AVAILABLE_NO_MATCHING_MARKET（无匹配市场），返回 0 条
- src.intel.portfolio_holdings: source health check: src.intel.portfolio_holdings -> 可用，返回 1 条
- src.macro.review: source health check: src.macro.review -> 降级（缺 key），返回 0 条
- src.intel.candidate_selector: source health check: src.intel.candidate_selector -> 可用，返回 1 条
- src.intel.candidate_selector: source health check: src.intel.candidate_selector -> 可用，返回 1 条
- reports/report_YYYYMMDD.md: source health check: reports/report_YYYYMMDD.md -> 可用，返回 1 条
- Tavily: source health check: Tavily -> 降级（未知原因），返回 0 条
- SearXNG: source health check: SearXNG -> 降级（限流/额度不足），返回 0 条
- CNINFO: source health check: CNINFO -> 降级（未知原因），返回 0 条
- Eastmoney: source health check: Eastmoney -> 降级（接口异常），返回 0 条
- AKShare: source health check: AKShare -> 降级（未知原因），返回 0 条
- Tushare: source health check: Tushare -> 降级（权限不足），返回 0 条
- Polymarket: source health check: Polymarket -> AVAILABLE_NO_MATCHING_MARKET（无匹配市场），返回 0 条

## 搜到什么
- 主张：source_health=degraded；数据：source_health=degraded；trade_review_usability=usable_limited；source_count=15；来源：market_cycle/2026-06-19/13_source_health.json；推论：critical unavailable 才阻断交易审查；optional/supporting failure 只降权。

## 搜不到什么
- macro_context
- prediction_market
- macro_review
- search_provider
- search_provider
- official_announcements
- a_share_quote
- a_share_quote_fallback
- a_share_financials
- prediction_market

## 有限信息结论
本轮可读但需按 source health 降权。

## 我看了什么
- market_cycle/2026-06-19/13_source_health.json

## 事实
- source_health=degraded
- trade_review_usability=usable_limited
- source_count=15

## 我的推理
- critical unavailable 才阻断交易审查；optional/supporting failure 只降权。

## 我的结论
本轮可读但需按 source health 降权。

## 下一步谁补
查看 sources/01_source_gap_plan，优先修 critical 或 macro 降级源。

## 审计详情
- schema=agent_memo_v1
- origin=真实 Agent
- scope=market
- status=WARN
- fatal=False
- no_trade_execution=True