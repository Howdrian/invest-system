# Market Regime Strategy

- Regime: `STRUCTURAL_UPTREND_CONFIRMED`
- Confidence: `HIGH`
- Confidence caps: `-`
- Stance: `watch_conditions_ready`
- Participation allowed: `True`
- Boundary: review-only; no trade execution; no protected writeback; scoring_impact=0.

## 主结论

结构性上行需多周期趋势、宽度和信用共同确认；本层只生成观察与预审条件。

## 证据

- 权益/高beta篮子5日均值 +3.7%
- 权益/高beta篮子20日均值 +10.2%
- 趋势确认比例 100%（50/200日均线代理）
- ASIA 最热主题5日均值 +9.4%
- 深评候选 6 个，其中偏热 0 个，高证据 4 个
- 跨资产价格为当前 live/cache 快照；重跑旧周期时不能当 point-in-time 历史结论

## 应该做

- ETF/篮子或龙头组合列为观察对象
- NORMAL_RECHECK 候选可进入红蓝预审
- 偏热个股等待承接确认

## 禁止/避免

- 一次性追满仓
- 只因热度高就买
- 跳过评分卡

## 候选处理方式

| Symbol | Bucket | 普通参与 | Price risk | Evidence | Rule |
|---|---|---|---|---|---|
| `600111.SS` 北方稀土 | WEAK_TO_STRONG_CONFIRMATION | True | PULLBACK_OR_WEAK_CONFIRM_FIRST | HIGH_OFFICIAL_EVIDENCE | 等止跌、收复短均线、反弹有量且不再新低。 |
| `002466.SZ` 天齐锂业 | WEAK_TO_STRONG_CONFIRMATION | True | PULLBACK_OR_WEAK_CONFIRM_FIRST | HIGH_OFFICIAL_EVIDENCE | 等止跌、收复短均线、反弹有量且不再新低。 |
| `002460.SZ` 赣锋锂业 | WEAK_TO_STRONG_CONFIRMATION | True | PULLBACK_OR_WEAK_CONFIRM_FIRST | HIGH_OFFICIAL_EVIDENCE | 等止跌、收复短均线、反弹有量且不再新低。 |
| `600893.SS` 航发动力 | WEAK_TO_STRONG_CONFIRMATION | True | PULLBACK_OR_WEAK_CONFIRM_FIRST | HIGH_OFFICIAL_EVIDENCE | 等止跌、收复短均线、反弹有量且不再新低。 |
| `XLK` Technology Select Sector SPDR | CORE_BASKET_CANDIDATE | True | NORMAL_RECHECK | MEDIUM_MIXED_EVIDENCE | 风险偏好允许时的篮子观察对象；进入交易前仍需红蓝、评分和仓位工具。 |
| `SMH` VanEck Semiconductor ETF | CORE_BASKET_CANDIDATE | True | NORMAL_RECHECK | MEDIUM_MIXED_EVIDENCE | 风险偏好允许时的篮子观察对象；进入交易前仍需红蓝、评分和仓位工具。 |
