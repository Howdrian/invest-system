# CandidateReviewAgent — market

- 输出来源：有限证据 Agent 输出
- 当前状态：通过
- 证据等级：LIMITED

## 一句话结论
有限信息结论：本轮候选多数处于观察或等待承接。

## 我搜了什么
- screening_funnel: candidate evidence cross-check -> 降级（未知原因），返回 6 条

## 搜到什么
- 主张：candidate_count=6；数据：candidate_count=6；auto_governed_count=0；top_candidates=太极实业:DEEP_REVIEW_WAIT_ENTRY；中际旭创:DEEP_REVIEW_WAIT_ENTRY；东方锆业:DEEP_REVIEW_WAIT_ENTRY；工业富联:DEEP_REVIEW_WAIT_ENTRY；盛和资源:DEEP_REVIEW_WAIT_ENTRY；中钨高新:DEEP_REVIEW_WAIT_ENTRY；来源：market_cycle/2026-06-19/11_deep_review_queue.json；推论：候选池用于筛选，不等于交易池；热榜证据必须经公告/研报/基本面/技术承接复核。

## 搜不到什么
- no_auto_governed_candidates

## 有限信息结论
本轮候选多数处于观察或等待承接。

## 我看了什么
- market_cycle/2026-06-19/11_deep_review_queue.json

## 事实
- candidate_count=6
- auto_governed_count=0
- top_candidates=太极实业:DEEP_REVIEW_WAIT_ENTRY；中际旭创:DEEP_REVIEW_WAIT_ENTRY；东方锆业:DEEP_REVIEW_WAIT_ENTRY；工业富联:DEEP_REVIEW_WAIT_ENTRY；盛和资源:DEEP_REVIEW_WAIT_ENTRY；中钨高新:DEEP_REVIEW_WAIT_ENTRY

## 我的推理
- 候选池用于筛选，不等于交易池；热榜证据必须经公告/研报/基本面/技术承接复核。

## 我的结论
本轮候选多数处于观察或等待承接。

## 下一步谁补
只让 DEEP_REVIEW_NOW 或持仓异常进入个股 governed 深评。

## 审计详情
- schema=agent_memo_v1
- origin=真实 Agent
- scope=market
- status=PASS
- fatal=False
- no_trade_execution=True