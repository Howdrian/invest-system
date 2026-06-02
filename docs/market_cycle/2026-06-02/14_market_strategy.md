# Market Regime Strategy

- Regime: `NEUTRAL_WATCH`
- Confidence: `MEDIUM`
- Stance: `watch_conditions_ready`
- Participation allowed: `True`
- Boundary: review-only; no trade execution; scoring_impact=0.

## 主结论

宏观中性；维持观察，等待价格和证据共振。

## 应该做

- 把热度和宏观作为候选发现，不直接触发交易
- NORMAL_RECHECK 候选必须进入 governed 个股分析
- 任何买卖前仍需红蓝、评分、CIO 和人工确认

## 禁止/避免

- 只因热度高就追买
- 跳过评分卡
- 把降级数据当满血信号

## 候选处理

| Symbol | Bucket | Rule |
|---|---|---|
| `301013` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `160644` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
