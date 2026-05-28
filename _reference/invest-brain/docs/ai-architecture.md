# AI Architecture — Digest / Trade Review / Rule Audit

> Updated: 2026-05-25  
> Boundary: AI 层只做解读、审查、触发和证据包生成；不自动交易、不自动写保护文件。

## 直接结论

本项目采用“脚本扫全市场 + AI 做解读/审计/交易审查”的分层架构。

```text
LaunchAgent 定时数据扫描 run_research_cycle.py
  -> dashboard snapshot / source health / market regime strategy / deep-review queue
  -> daily_ai_digest.py 机器预筛 + AI prompt + 交易审查包
  -> Codex automation 定时读取 ai_prompt/dashboard 做 AI 复核
  -> 需要交易判断时进入红蓝对抗、评分卡、仓位风控
  -> 用户确认后才可能进入仓位/交易记录
```

## 三层 AI

| 层 | 频率 | 入口 | 作用 | 写入 |
|---|---:|---|---|---|
| Daily AI Digest | 每个固定 profile 跑完后 + catchup 后 | `scripts/daily_ai_digest.py` | 读取当天报告，判断是否需要提醒、是否触发交易审查 | `research/archive/YYYY-MM-DD-ai-digest/` |
| Codex AI Review | 工作日 16:45 / 20:45 / 17:15 / 21:15 | Codex automation | 读取 digest、dashboard、深评队列，输出 AI 洞察、用户提醒，并刷新 dashboard 的 AI 洞察卡片 | `asia_close_ai_review.md` / `us_premarket_ai_review.md` / `catchup_ai_review.md` |
| Trade Review Package | 有强候选时自动生成 | `daily_ai_digest.py --generate-trade-reviews` | 生成 evidence pack、角色 memo、红蓝/评分/执行脚手架 | `research/archive/YYYY-MM-DD-trade-review-<symbol>/` |
| Subagent + CIO Review | 有交易预审包后 | Codex automation + `agents/subagent-review-protocol.md` + `agents/chief-investment-officer.md` | 真实子 Agent 独立审同一 evidence pack，CIO 汇总是否进入红蓝 | `subagent_memos/`、`cio_review.md/json` |
| Dashboard Governance Review | Dashboard 刷新后/每周产品审 | `agents/dashboard-financial-product-reviewer.md` + `scripts/dashboard_product_review.py` + `scripts/dashboard_governance_audit.py` | 审 10秒/30秒阅读线、截图级可读性、数据契约、链路断点、图表误导和交易安全边界；目标综合分 >4.5 | `YYYY-MM-DD-dashboard-product-review/` + `YYYY-MM-DD-dashboard-governance-audit/` |
| Weekly Rule Audit | 每周一次本地审计 + Codex 复核 | `scripts/weekly_rule_audit.py` + Codex automation | 审核代码规则是否符合交易理念和筛选需求 | `research/archive/YYYY-MM-DD-ai-rule-audit/` |

## Dashboard Product Agent

Dashboard 不是新的交易 Agent，而是展示层 Agent：

```text
profiles + AI digest + source health + portfolio.md + market strategy
  + Codex AI review markdown
  -> dashboard_snapshot.json
  -> 负责人一屏 / 30秒阅读路径 / 红蓝对抗工作台 / AI 洞察 / 分析师工作台 / 风险与数据健康 / 工程诊断
```

它负责把裸枚举、工程路径和脚本诊断翻译为用户可读信息：

- `REVIEW_PACK_READY` -> 已生成交易预审材料；
- `WATCH_CONDITIONS_READY` -> 有观察条件候选；
- 绝对路径 -> 项目相对链接；
- 空仓 -> 明确“当前空仓，不伪造组合风险”；
- 源降级 -> 首屏标注“可读但降权”。
- Codex AI review -> 展示“关注什么、为什么、缺什么、下一步”，不只展示程序预筛。
- 红蓝对抗工作台 -> 只要有交易预审包，就直接展示 red_blue_review / evidence_pack / final_decision 入口；仍不自动交易、不自动评分。

Dashboard Product Agent 不重算评分、不维护第二套组合、不自动交易。

## Subagent Review / CIO Review

真实多子 Agent 不接成第二套交易系统，只在 `trade-review-*` 包内做只读预审：

```text
evidence_pack.md
  -> Source / Macro / Catalyst / Fundamentals / Technical / Risk 六类真实子 Agent
  -> subagent_memos/*.md/json
  -> CIO 总审 cio_review.md/json
  -> Dashboard CIO 总审卡片
  -> 如可继续，再进入 red_blue_review.md / scoring_card.md
```

脚本层会先生成 `SUBAGENT_UNAVAILABLE` 占位，防止自动化缺工具时假装多 Agent 已审。Codex automation 有 `multi_agent_v1` 时必须 spawn 真实子 Agent 覆盖占位 memo。

CIO 只允许输出：

- `READY_FOR_RED_BLUE`
- `WAIT_ENTRY`
- `NEEDS_EVIDENCE`
- `BLOCKED_BY_FATAL`

CIO 不输出 0-10 分、不投票、不下单、不写 `state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md`。

## Daily AI Digest 输入

- `dashboard.html`
- `research/archive/YYYY-MM-DD-*/13_source_health.json`
- `research/archive/YYYY-MM-DD-*/14_market_strategy.json`
- `research/archive/YYYY-MM-DD-*/11_deep_review_queue.json`
- `research/archive/YYYY-MM-DD-*/12_preliminary_deep_review.md`
- `state/watchlist.md`
- `state/portfolio.md`

## 自动交易审查触发条件

允许触发交易审查包，但不允许触发交易：

```text
source_health.trade_review_usability != unavailable
AND candidate.verdict = DEEP_REVIEW_NOW
AND evidence_quality >= MEDIUM_MIXED_EVIDENCE
AND price_risk != OVERHEATED_WAIT_ENTRY
```

`source_health.usability_verdict` 仍保留全局健康口径；`trade_review_usability` 是分层后的交易审查口径。核心行情/官方公告/深评队列不可用会阻断；Polymarket、Crypto 风险温度计等可选源异常只降权提示，不单独阻断。

保守降级：即使 `price_risk=NORMAL_RECHECK`，如果理由里出现 RSI>=70、偏离20日均线>=10%、5日涨幅>=10%，也降级成 `TRADE_REVIEW_PREP_WAIT_ENTRY`。

未触发候选会写入 `blocked_candidates.json`，区分 source unavailable、证据不足、非 deep-review-now 等；短期风险偏好偏强时的过热候选还会进入 `participation_candidates.json`，避免把“等待入场”误读成“没有机会”。

## Market Regime Strategy Governor

`scripts/market_regime_strategy.py` 是主 Agent 的上层判断：

```text
macro regime + cross-asset + sector heat + candidates + source health + event risk
  -> TACTICAL_RISK_ON / TACTICAL_RISK_ON_CROWDED / ROTATION_RANGE / RISK_OFF_DEFENSIVE / EVENT_RISK_DOMINANT / UNKNOWN_DEGRADED
  -> strategy stance
  -> participation plan
```

它不直接触发买卖，只决定下一步是哪种参与准备：

- `RED_BLUE_NOW`：可进入红蓝重评；
- `PARTICIPATION_WAIT_ENTRY`：强趋势偏热，等待承接/回踩/横盘消化；
- `CORE_BASKET_CANDIDATE`：短期 risk-on 时可用 ETF/篮子降低单股追高风险；
- `WEAK_TO_STRONG_CONFIRMATION`：回撤候选只等止跌确认。

## 交易审查包输出

```text
research/archive/YYYY-MM-DD-trade-review-<symbol>/
├── trigger.json
├── evidence_pack.md
├── subagent_memos/
├── cio_review.md
├── cio_review.json
├── role_memos.md
├── red_blue_review.md
├── scoring_card.md
├── position_or_options_plan.md
└── final_decision.md
```

每日 AI digest 输出：

```text
research/archive/YYYY-MM-DD-ai-digest/
├── digest.json
├── trade_review_triggers.json
├── participation_candidates.json
├── blocked_candidates.json
├── summary.md
└── ai_prompt.md
```

默认状态只能是：

- `USER_CONFIRM_REQUIRED`
- `WAIT_ENTRY`
- `NOT_READY`
- `UNSCORED`

## 保护区

AI 和脚本默认不得写：

- `state/portfolio.md`
- `trades/trade-log.md`
- `agents/scoring-card.md`
- `agents/red-team-protocol.md`

修改交易规则必须先进入 `proposed_changes.md`，再由用户确认。

## 当前 Codex automation

- `asia-close-review`：工作日 16:45，`gpt-5.5 / xhigh`，输出 `asia_close_ai_review.md` 并刷新 dashboard。
- `us-premarket-review`：工作日 20:45，`gpt-5.5 / xhigh`，输出 `us_premarket_ai_review.md` 并刷新 dashboard。
- `missed-run-catch-up-check`：工作日 17:15、21:15，`gpt-5.5 / xhigh`，输出 `catchup_ai_review.md` 并刷新 dashboard。
- `weekly-rule-ai-review`：周一 11:00，`gpt-5.5 / xhigh`，输出 `ai_review.md`。

这些 automation 可以运行 AI，但仍禁止自动交易和保护区写回。

Fallback 规则：

- 报告缺失或 `source_health=unavailable`：先调用 `scripts/schedule_catchup.py`，让本地脚本决定是否补跑。
- profile 报告已存在但 AI digest 缺失：只调用 `scripts/daily_ai_digest.py --generate-trade-reviews` 补齐 AI 输入。
- 不允许 Codex automation 手工重复执行 `run_research_cycle.py` 重型扫描。
