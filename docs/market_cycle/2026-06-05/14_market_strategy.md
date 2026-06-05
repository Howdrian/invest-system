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
| `600519` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `000858` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `300750` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `002594` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `601318` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `000001` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `600036` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `000333` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `300059` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `600276` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `601899` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `002415` | `watch` | 仅作为关注线索；进入交易前必须经过 governed 个股分析、红蓝、评分和 CIO。 |
| `SZ000725` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
| `SZ300308` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
| `SH688017` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
| `SH601991` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
| `SH600487` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
| `SH600522` | `DEEP_REVIEW_WAIT_ENTRY` | 读公告/研报和技术承接；不追高。 |
