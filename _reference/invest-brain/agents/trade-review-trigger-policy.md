# Trade Review Trigger Policy

## 触发目标

自动生成交易审查包，让用户/AI 后续完成红蓝对抗和评分，不自动交易。

## 机器触发条件

```text
source_health != unavailable
AND verdict = DEEP_REVIEW_NOW
AND evidence_quality >= MEDIUM_MIXED_EVIDENCE
AND price_risk != OVERHEATED_WAIT_ENTRY
```

## 保守降级

以下情况可以生成交易审查包，但状态必须是等待入场或预审：

- RSI14 >= 70
- 偏离20日均线 >= 10%
- 5日涨幅 >= 10%
- source_health = degraded
- evidence_quality 不是 HIGH_OFFICIAL_EVIDENCE

## 短期风险偏好偏强时的偏热处理

`OVERHEATED_WAIT_ENTRY` 不等于“没有机会”，但也不能触发即时交易审查。  
主 Agent 必须先读取 `14_market_strategy.json`：

- 如果 regime 是 `TACTICAL_RISK_ON` 或 `TACTICAL_RISK_ON_CROWDED`，且 confidence 不是 `LOW`：偏热候选可进入 `participation_candidates.json`，状态是等待承接确认、横盘消化、ETF/篮子观察或轮动补位。
- 如果 regime 是 `RISK_OFF_DEFENSIVE` / `EVENT_RISK_DOMINANT` / `UNKNOWN_DEGRADED`：偏热候选只保留为观察或情景推演，不推进交易。

这一步只生成观察/预审条件，不生成买卖指令，不绕过红蓝对抗和评分卡。

## 禁止

- 自动买入/卖出
- 自动写 `trades/trade-log.md`
- 自动改 `state/portfolio.md`
- 外部 agent 评分映射成本地 0-10 评分
