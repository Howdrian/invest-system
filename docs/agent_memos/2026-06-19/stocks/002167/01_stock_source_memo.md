# StockSourceAgent — 002167

- 输出来源：有限证据 Agent 输出
- 当前状态：警告
- 证据等级：LIMITED

## 一句话结论
有限信息结论：可审计最终门控；需补单股原始源引用。

## 我搜了什么
- CNINFO: 东方锆业 002167 公告/监管原文 -> 降级（未知原因），返回 0 条
- Eastmoney: 东方锆业 002167 行情/估值/热度 -> 降级（未知原因），返回 0 条
- AKShare: 东方锆业 002167 行情 fallback -> 降级（未知原因），返回 0 条
- Tushare: 东方锆业 002167 财务字段 -> 降级（权限不足），返回 0 条
- Tavily: 东方锆业 002167 新闻/研报搜索 -> 降级（未知原因），返回 0 条
- SearXNG: 东方锆业 002167 搜索 fallback -> 降级（未知原因），返回 0 条

## 搜到什么
- 主张：symbol=002167；数据：symbol=002167；name=东方锆业；source=governed_results summary；来源：governed_results.json#002167；推论：当前公开 Pages 只有最终 governed 摘要；原始逐 Agent transcript 尚未完全持久化。

## 搜不到什么
- raw_stock_source_refs
- agent_tool_trace_memos

## 有限信息结论
可审计最终门控；需补单股原始源引用。

## 我看了什么
- governed_results.json#002167
- report_20260619.md

## 事实
- symbol=002167
- name=东方锆业
- source=governed_results summary

## 我的推理
- 当前公开 Pages 只有最终 governed 摘要；原始逐 Agent transcript 尚未完全持久化。

## 我的结论
可审计最终门控；需补单股原始源引用。

## 下一步谁补
后续从 pipeline ctx.opinions/stage_results 直接持久化。

## 审计详情
- schema=agent_memo_v1
- origin=真实 Agent
- scope=stock
- status=WARN
- fatal=False
- no_trade_execution=True