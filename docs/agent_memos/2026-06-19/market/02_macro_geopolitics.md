# MacroGeopoliticsAgent — market

- 输出来源：有限证据 Agent 输出
- 当前状态：警告
- 证据等级：LIMITED

## 一句话结论
有限信息结论：宏观降级，维持观察。

## 我搜了什么
- src.macro.official_sources: source health check: src.macro.official_sources -> 降级（缺 key），返回 0 条
- src.prediction_market.polymarket: source health check: src.prediction_market.polymarket -> AVAILABLE_NO_MATCHING_MARKET（无匹配市场），返回 0 条
- src.macro.review: source health check: src.macro.review -> 降级（缺 key），返回 0 条
- Polymarket: source health check: Polymarket -> AVAILABLE_NO_MATCHING_MARKET（无匹配市场），返回 0 条

## 搜到什么
- 主张：macro_status=DEGRADED；数据：macro_status=DEGRADED；confidence=LOW_TO_MEDIUM；headline=宏观中性，等待价格和证据共振；VIX neutral: 16.94；来源：market_cycle/2026-06-19/01_macro_review.json；推论：宏观/地缘只做背景约束；Polymarket 只做概率校准，不能单独触发交易。

## 搜不到什么
- macro_context_not_refreshed
- six_factor_missing:credit_conditions
- six_factor_missing:size_factor
- six_factor_missing:equity_bond
- six_factor_missing:sector_rotation

## 有限信息结论
宏观降级，维持观察。

## 我看了什么
- market_cycle/2026-06-19/01_macro_review.json

## 事实
- macro_status=DEGRADED
- confidence=LOW_TO_MEDIUM
- headline=宏观中性，等待价格和证据共振；VIX neutral: 16.94
- prediction_market_status=available

## 我的推理
- 宏观/地缘只做背景约束；Polymarket 只做概率校准，不能单独触发交易。

## 我的结论
宏观降级，维持观察。

## 下一步谁补
补 FMP/FRED/BEA/EIA 与六因子缺项，再提高宏观置信度。

## 审计详情
- schema=agent_memo_v1
- origin=真实 Agent
- scope=market
- status=WARN
- fatal=False
- no_trade_execution=True