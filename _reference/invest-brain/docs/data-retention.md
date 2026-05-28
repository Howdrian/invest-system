# Data Retention

> Current observation: `research/archive` 增长较小，`research/cache` 是主要体积来源。

## 建议策略

| 类型 | 目录 | 策略 |
|---|---|---|
| 研究归档 | `research/archive/` | 长期保留，用于规则审计和前向记录 |
| AI digest | `research/archive/YYYY-MM-DD-ai-digest/` | 至少保留 1-2 年 |
| Trade review | `research/archive/YYYY-MM-DD-trade-review-*` | 长期保留，作为决策记录 |
| Rule audit | `research/archive/YYYY-MM-DD-ai-rule-audit/` | 长期保留，用于校准规则 |
| Cache | `research/cache/` | 30-60 天可清理；模型 cache 另行确认 |
| Logs | `logs/` | 30 天可清理 |

## 删除边界

删除默认先进废纸篓；不得自动删除 `archive` 里的研究和交易审查记录。
