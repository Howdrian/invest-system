# FundamentalReportsAgent — 600667

- 输出来源：有限证据 Agent 输出
- 当前状态：警告
- 证据等级：LIMITED

## 一句话结论
有限信息结论：先按最终评分和报告摘要审计；需要补财报/公告/研报原文链。

## 我搜了什么
- CNINFO: 太极实业 600667 公告/监管原文 -> 降级（未知原因），返回 0 条
- Eastmoney: 太极实业 600667 行情/估值/热度 -> 降级（未知原因），返回 0 条
- AKShare: 太极实业 600667 行情 fallback -> 降级（未知原因），返回 0 条
- Tushare: 太极实业 600667 财务字段 -> 降级（权限不足），返回 0 条
- Tavily: 太极实业 600667 新闻/研报搜索 -> 降级（未知原因），返回 0 条
- SearXNG: 太极实业 600667 搜索 fallback -> 降级（未知原因），返回 0 条

## 搜到什么
- 主张：score=2.0；数据：score=2.0；headline=太极实业短期风险过高，估值偏离严重，不建议操作；来源：governed_results.json#600667；推论：基本面/估值缺口是当前个股 governed 的关键输入，但尚未独立成 Agent memo。

## 搜不到什么
- financial_statement_refs
- valuation_peer_refs
- report_refs

## 有限信息结论
先按最终评分和报告摘要审计；需要补财报/公告/研报原文链。

## 我看了什么
- governed_results.json#600667
- report_20260619.md

## 事实
- score=2.0
- headline=太极实业短期风险过高，估值偏离严重，不建议操作

## 我的推理
- 基本面/估值缺口是当前个股 governed 的关键输入，但尚未独立成 Agent memo。

## 我的结论
先按最终评分和报告摘要审计；需要补财报/公告/研报原文链。

## 下一步谁补
新增 FundamentalReportsAgent 或持久化现有基本面上下文。

## 审计详情
- schema=agent_memo_v1
- origin=真实 Agent
- scope=stock
- status=WARN
- fatal=False
- no_trade_execution=True