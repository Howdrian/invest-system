# Subagent Review Protocol — 真实子 Agent 预审协议

> Role: 定义投研预审包里多个真实子 Agent 的分工、输入、输出和保护边界。  
> Boundary: 只读 evidence pack 和项目归档；不交易、不评分、不写保护区。

## 触发位置

当 `daily_ai_digest.py --generate-trade-reviews` 生成 `research/archive/YYYY-MM-DD-trade-review-<symbol>/` 后，Codex AI review automation 可以为该包派生真实子 Agent。

如果当前运行环境没有 `multi_agent_v1` 或无法 spawn 子 Agent，必须在输出中写明：`SUBAGENT_UNAVAILABLE`，不能假装已经完成多 Agent 审查。

## 统一输入

每个子 Agent 只能读取同一个交易预审包和相关只读上下文：

- `evidence_pack.md`
- `trigger.json`
- `red_blue_review.md`
- `scoring_card.md`
- `final_decision.md`
- 关联 profile 的 `13_source_health.json/html`
- 关联 profile 的 `14_market_strategy.json/html`
- 关联 profile 的 `11_deep_review_queue.json/md`
- `state/portfolio.md` 只读
- `state/watchlist.md` 只读

不得使用 evidence pack 以外的新事实来强化结论；如果需要补源，写入 `missing_data`。

## 子 Agent 清单

| Agent | 重点 | 输出文件 |
|---|---|---|
| Source Health / Provenance | 源健康、新鲜度、降权原因、source tier | `subagent_memos/source_health.md/json` |
| Macro / Geopolitics | 宏观 regime、利率、美元、商品、地缘/Polymarket 概率边界 | `subagent_memos/macro_geopolitics.md/json` |
| Catalyst / Policy | 新闻、公告、政策、事件窗口、price-in 风险 | `subagent_memos/catalyst_policy.md/json` |
| Fundamentals / Reports | 财报、SEC、Company Facts、公开研报、估值/质量缺口 | `subagent_memos/fundamentals_reports.md/json` |
| Technical / Quant / Options | 技术位置、趋势、Kronos 侧证、long-only 期权表达风险 | `subagent_memos/technical_quant_options.md/json` |
| Risk / Position Lens | 组合暴露、仓位风险、止损/最大亏损、期权最大亏损 | `subagent_memos/risk_position.md/json` |

## Prompt 固定结构

每个子 Agent prompt 必须包含：

```markdown
# Role
你负责哪类证据，不负责什么。

# Inputs
只读 evidence_pack、dashboard snapshot、source health、相关报告。

# Evidence Rules
每个数字必须有来源/文件/日期；缺失写 UNKNOWN；不得模型补脑。

# Output
verdict、key_findings、risks、missing_data、fatal_objection、handoff_to_cio。

# Guardrails
不交易、不评分、不写保护文件、不覆盖 fatal objection。
```

## 输出 JSON schema

```json
{
  "schema": "subagent_memo_v1",
  "agent": "source_health | macro_geopolitics | catalyst_policy | fundamentals_reports | technical_quant_options | risk_position",
  "symbol": "",
  "status": "PASS | WARN | BLOCKED | SUBAGENT_UNAVAILABLE",
  "verdict": "",
  "key_findings": [],
  "risks": [],
  "missing_data": [],
  "fatal_objection": false,
  "fatal_objection_reason": "",
  "handoff_to_cio": "",
  "protected_writeback": false,
  "trade_execution": false,
  "scoring_impact": 0
}
```

## 硬规则

- 子 Agent 不能输出 0-10 本地交易评分。
- 子 Agent 不能写买入、卖出、加仓、减仓、仓位比例、下单数量。
- 子 Agent 不能写 `state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md`。
- 任一 `fatal_objection=true` 必须交给 CIO 阻断或补证，不得被多数意见覆盖。
- `source_health.trade_review_usability=unavailable` 时，所有子 Agent 最多输出 `NEEDS_EVIDENCE` / `BLOCKED`。

## 参考项目口径

- Anthropic financial-services：学 agent/skill/connector 分层、引用来源、人类审批。
- Anthropic Building Effective Agents：采用 orchestrator-workers / evaluator-optimizer，不做开放群聊。
- TradingAgents：学 Analyst -> Bull/Bear -> Risk -> Manager 的冲突暴露。
- FinRobot：学金融研究报告流水线和角色化研究。

以上均为架构参考，不接成第二套评分、组合或交易系统。
