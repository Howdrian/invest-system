# Source Gap Plan

只列缺口源；优先 critical，再 supporting，optional 只降权。

## 先读结论
宏观只可背景参考，不是满血 regime；critical 源不可用才阻断交易审查，optional 源失败只降权。

## 宏观

| 数据源 | 今天状态 | 失败原因 | 影响哪个分析结论 | 是否阻断交易审查 | fallback 是否启用 | 下一步怎么修 |
|---|---|---|---|---|---|---|
| src.macro.official_sources | DEGRADED | 缺 key 或 key 不可用 | 影响宏观/地缘、六因子 regime 和交易审查置信度 | 不阻断日报，但交易审查降级 | 未启用 | 检查对应 GitHub Secret / 本地 .env 是否配置并有效。 |
| src.macro.review | DEGRADED | 缺 key 或 key 不可用 | 影响宏观/地缘、六因子 regime 和交易审查置信度 | 不阻断日报，但交易审查降级 | 未启用 | 检查对应 GitHub Secret / 本地 .env 是否配置并有效。 |

## 地缘

| 数据源 | 今天状态 | 失败原因 | 影响哪个分析结论 | 是否阻断交易审查 | fallback 是否启用 | 下一步怎么修 |
|---|---|---|---|---|---|---|
| src.prediction_market.polymarket | AVAILABLE_NO_MATCHING_MARKET | API 可用，但未匹配到可用场景市场 | 影响 Polymarket 概率融合；本轮只能用内部场景概率 | 不阻断，只降权 | 未启用 | 补市场关键词映射，确认是否有足够流动性和清晰结算规则 |
| Polymarket | AVAILABLE_NO_MATCHING_MARKET | API 可用，但未匹配到可用场景市场 | 影响 Polymarket 概率融合；本轮只能用内部场景概率 | 不阻断，只降权 | 待确认 | 补市场关键词映射，确认是否有足够流动性和清晰结算规则 |

## A股

| 数据源 | 今天状态 | 失败原因 | 影响哪个分析结论 | 是否阻断交易审查 | fallback 是否启用 | 下一步怎么修 |
|---|---|---|---|---|---|---|
| CNINFO | DEGRADED | 未知 | 影响 A股热榜、公告、候选池和深评队列 | 不阻断，只降权 | 待确认 | 补公告查询 adapter 或检查公告任务输出。 |
| Eastmoney | DEGRADED | 接口变化 | 影响 A股热榜、公告、候选池和深评队列 | 不阻断，只降权 | 待确认 | 保留 AKShare/Sina fallback，记录 Eastmoney 断连。 |
| AKShare | DEGRADED | 未知 | 影响 A股热榜、公告、候选池和深评队列 | 不阻断，只降权 | 待确认 | 确认 AKShare/Sina fallback 成功率和字段覆盖。 |
| Tushare | DEGRADED | 权限/套餐不足 | 影响 A股热榜、公告、候选池和深评队列 | 不阻断，只降权 | 待确认 | 若无权限，不把 Tushare 当 critical；用公开公告/财报 fallback。 |

## 新闻研报

| 数据源 | 今天状态 | 失败原因 | 影响哪个分析结论 | 是否阻断交易审查 | fallback 是否启用 | 下一步怎么修 |
|---|---|---|---|---|---|---|
| Tavily | DEGRADED | 未知 | 影响新闻、研报、公告原文和催化剂判断 | 不阻断，只降权 | 待确认 | 检查 Tavily key/额度；额度耗尽时走 SearXNG/Google News/GDELT fallback。 |
| SearXNG | DEGRADED | 限流 | 影响新闻、研报、公告原文和催化剂判断 | 不阻断，只降权 | 待确认 | 优先配置自建 SearXNG；公共实例 429/403 只作降级 fallback。 |
