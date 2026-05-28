# Rule Audit Process

> Purpose: 用 AI 定期审查筛选/深评/源健康/dashboard/AI digest 规则是否符合交易理念。

## 审计对象

- `scripts/screening_funnel.py`
- `scripts/deep_review_candidates.py`
- `scripts/source_health_dashboard.py`
- `scripts/render_dashboard.py`
- `scripts/daily_ai_digest.py`
- `agents/scoring-card.md`
- `agents/red-team-protocol.md`
- `frameworks/*.md`
- 最近 5-10 次 research cycle 输出

## 审计问题

1. 有没有把热榜/价格异动误升级成交易机会？
2. `DEEP_REVIEW_NOW` 是否过松？
3. `source_health=unavailable` 是否被任何层绕过？
4. `evidence_quality` 是否代表“证据覆盖”，而不是“胜率”？
5. 是否符合：不追高、重证据、先红蓝、控亏损？
6. 哪些规则需要回测/前向 ledger 才能采纳？
7. 最近 N 轮是否存在 `usable=0`，是否需要先修数据源稳定性？
8. 每轮 degraded/unavailable 具体来自哪些组件，是否只是可选源异常？

## 输出

```text
research/archive/YYYY-MM-DD-ai-rule-audit/
├── summary.md
├── rule_findings.json
├── ai_prompt.md
├── proposed_changes.md
└── backtest_needed.md
```

`rule_findings.json.stats.cycle_details` 会记录最近轮次的 `usability`、`trade_review_usability`、不可用组件、降级组件、候选数量、过热数量，方便每周 AI 复核不用再二次追查。

## 决策边界

- AI 可以建议修改规则。
- AI 不自动修改评分卡和红蓝协议。
- AI 不把审计结论当作交易结论。
