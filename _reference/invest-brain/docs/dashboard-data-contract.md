# Dashboard 数据契约 v1

> 日期：2026-05-26  
> 目标：Dashboard 只消费用户可读 view-model，不直接读一堆工程原始字段。原始研究文件仍保留为唯一事实源，Dashboard 通过 `source_path/as_of` 追溯。

## 1. 基础字段规则

每个可展示字段必须包含：

| 字段 | 含义 |
|---|---|
| `user_label` | 用户看到的中文标签 |
| `raw_value` | 原始值，保留 enum/数值/结构，供审计 |
| `source_path` | 来源文件或相对路径 |
| `as_of` | 数据时间，不知道就写 `UNKNOWN` |
| `confidence` | `high / medium / low / unknown` |
| `impact_scope` | 影响范围：`portfolio / opportunity / evidence / system / trade_review / market` |

基础对象：

```json
{
  "user_label": "数据降级",
  "raw_value": "DEGRADED_WITH_RECOVERY",
  "source_path": "research/archive/2026-05-26-asia-close-review/13_source_health.json",
  "as_of": "2026-05-26T15:44:31+07:00",
  "confidence": "medium",
  "impact_scope": ["opportunity", "trade_review"]
}
```

## 2. 顶层契约

`dashboard_snapshot.json` 目标顶层结构：

```json
{
  "schema": "dashboard_snapshot_v2",
  "now": "...",
  "executive_investment_brief": {},
  "decision_brief": {},
  "portfolio_monitor": {},
  "market_brief": {},
  "opportunity_brief": {},
  "evidence_brief": {},
  "source_recovery": {},
  "dashboard_governance": {}
}
```

当前兼容字段 `portfolio/source_health/market_strategy/deep_review_queue/pipeline_status/structured_user_summary/ai_digest/cio_reviews` 可以保留，但页面渲染应逐步改为读取上述七类 view-model。

## 3. `executive_investment_brief`

用途：首页第一阅读区，整合 AI 市场总结、持仓影响、重要事项、AI 多维评级、CIO、红蓝、评分卡/仓位/用户确认状态。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `market_summary` | string | Daily AI Summary 或市场策略摘要 |
| `holding_impact` | string | 当前持仓影响和风险缺口 |
| `important_items` | string[] | 今日最该盯 3 件事 |
| `ratings` | object[] | 市场环境/技术位置/催化剂/证据/数据/风险/持仓相关性 |
| `cio_status` | string | CIO 状态摘要 |
| `red_blue_status` | string | 红蓝状态 |
| `red_blue_score` | string | 已有红蓝/评分时引用；无则未评分 |
| `next_step` | string | 今日下一步 |

## 4. `decision_brief`

用途：首页第一卡，回答“今天能不能用、为什么、下一步”。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `verdict` | EvidenceField | 可读 / 降权可读 / 不足以交易 / 阻断 |
| `headline` | EvidenceField | 一句话结论 |
| `can_trade_today` | EvidenceField | 必须为 false，除非红蓝/评分/仓位/用户确认全部完成 |
| `can_enter_red_blue` | EvidenceField | 是否可进入红蓝 |
| `top_reasons` | EvidenceField[] | Top 3 原因 |
| `next_user_action` | EvidenceField | 用户现在该看什么 |
| `next_system_action` | EvidenceField | 系统下一步 |

## 4. `portfolio_monitor`

用途：持仓优先，生成首页持仓摘要和持仓页。

当前实现：`scripts/portfolio_monitoring.py` 生成 `portfolio_monitor_v1`。它只读 `state/portfolio.md`；轻量刷新由 `scripts/portfolio_refresh_now.py` 触发，优先用 `portfolio_quote_adapter.py` 的 Eastmoney push2 获取 A股/深交所 LOF 行情，并补 CNINFO 公告、持仓主题映射和触发状态。价格、公告、板块联动不可得时写 `待刷新/UNKNOWN`，不伪造市值和浮盈亏。每日 AI digest 有持仓时还会输出：

```text
research/archive/YYYY-MM-DD-portfolio-review/
  portfolio_monitor.json
  portfolio_monitor.md
  portfolio_cio_review.json
  portfolio_cio_review.md
  portfolio_trigger_policy.json
  portfolio_red_blue_review.md
```

当前实际字段：

| 字段 | 说明 |
|---|---|
| `account_equity` / `account_size` | 用户账户权益口径，来源 `state/portfolio.md` |
| `positions[]` | 当前持仓，含 `symbol/name/quantity/cost_price/cost_amount/latest_price/market_value/unrealized_pnl/day_change_pct/trigger_status/risk_gaps` |
| `cost_exposure` | 按用户成本和数量可计算时给成本暴露；不能计算则写待确认 |
| `latest_price / market_value / unrealized_pnl` | 行情源缺失时固定 `待刷新` |
| `trigger_status` | `NO_REVIEW_REQUIRED / WATCH / PORTFOLIO_REVIEW_REQUIRED / BLOCKED_NEEDS_EVIDENCE`，不是交易建议 |
| `review_blockers / watch_items` | 缺证据原因与今日最该盯事项 |
| `portfolio_trigger_policy` | 持仓触发策略汇总；只判断是否需要审查，不评分、不交易 |
| `source_status` | portfolio 文件、价格、公告、板块联动状态 |
| `risk_gaps` | 价格源、止损、失效条件、最大亏损等缺口 |
| `protected_writeback / trade_execution` | 永远 false |

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `account_equity` | EvidenceField | 账户权益 |
| `cash_estimate` | EvidenceField | 现金或差额；不知道写 UNKNOWN |
| `positions` | object[] | 当前持仓 |
| `cost_exposure` | EvidenceField | 成本暴露比例 |
| `market_value` | EvidenceField | 市值；行情缺失则 `UNKNOWN` |
| `unrealized_pnl` | EvidenceField | 浮盈亏；价格缺失则 `UNKNOWN` |
| `holding_events` | EvidenceField[] | 公告/新闻/板块事件 |
| `risk_gaps` | EvidenceField[] | 止损、失效条件、最大亏损、价格源缺口 |
| `portfolio_cio_required` | EvidenceField | 有持仓时默认 true |

`positions[]` 字段：

```json
{
  "symbol": "160644",
  "name": "港美互联网LOF",
  "market": "SZSE",
  "quantity": {"user_label":"39手", "raw_value":3900, "source_path":"state/portfolio.md", "as_of":"2026-05-26", "confidence":"high", "impact_scope":["portfolio"]},
  "cost_price": {},
  "cost_amount": {},
  "latest_price": {},
  "market_value": {},
  "unrealized_pnl": {},
  "trigger_status": "WATCH",
  "review_blockers": [],
  "watch_items": [],
  "source_status": {}
}
```

## 5. `market_brief`

用途：市场一句话和机会页背景。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `regime_label` | EvidenceField | 市场状态中文 |
| `risk_on_off` | EvidenceField | risk-on/risk-off/rotation/event-risk |
| `crowding_level` | EvidenceField | 拥挤度 |
| `event_risk` | EvidenceField | 事件风险 |
| `cross_asset_snapshot` | EvidenceField[] | 指数、利率、美元、商品、crypto 代理 |
| `strategy_implication` | EvidenceField | 策略含义，不含买卖词 |

## 6. `opportunity_brief`

用途：机会摘要和机会页。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_counts` | EvidenceField | 可读/等承接/缺证据/阻断数量 |
| `top_watch_items` | EvidenceField[] | 今日最该盯 3 件事 |
| `theme_heat` | EvidenceField[] | 主题/行业热度 |
| `catalysts` | EvidenceField[] | 催化剂时间轴 |
| `charts` | EvidenceField[] | 可展示图表数据入口 |
| `red_blue_ready` | EvidenceField[] | 可进入红蓝候选；通常为空 |
| `blocked_candidates` | EvidenceField[] | 阻断候选和原因 |

## 7. `evidence_brief`

用途：证据链页，供 CIO/子 Agent/红蓝预审追溯。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `cio_reviews` | EvidenceField[] | CIO 总审列表 |
| `subagent_status` | EvidenceField | 子 Agent 完成数 |
| `fatal_objections` | EvidenceField[] | fatal objection |
| `missing_evidence` | EvidenceField[] | 缺证据 |
| `reasoning_chain` | EvidenceField[] | 事实 → 推理 → 结论 |
| `red_blue_status` | EvidenceField | 红蓝状态 |
| `evidence_pack_links` | EvidenceField[] | 证据包链接 |

## 8. `source_recovery`

用途：系统健康页和首页数据可信度摘要。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `overall` | EvidenceField | FULL / DEGRADED_WITH_RECOVERY / AI_DIAGNOSTIC_REQUIRED / UNAVAILABLE |
| `summary` | EvidenceField | 用户语言总结 |
| `components` | object[] | 每个组件恢复状态 |
| `ai_intervention_required` | EvidenceField | 是否需要 AI 诊断 |
| `next_retry_at` | EvidenceField | 下一次重试 |
| `trade_review_impact` | EvidenceField | 对交易预审影响 |

`components[]` 必备字段：

```json
{
  "component": "a_share",
  "component_label": "A股增强",
  "primary_source": {},
  "fallback_source": {},
  "fallback_quality_tier": {},
  "failure_streak": {},
  "last_success_at": {},
  "last_failure_at": {},
  "freshness_age_seconds": {},
  "next_retry_at": {},
  "impact_scope": {},
  "next_system_action": {}
}
```

## 9. `dashboard_governance`

用途：产品审核和误导风险控制。

必备字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `verdict` | EvidenceField | PASS / PASS_WITH_WARNINGS / BLOCKED |
| `composite_score` | EvidenceField | 0-5 |
| `homepage_card_count` | EvidenceField | 首页卡片数 |
| `portfolio_first_screen` | EvidenceField | 持仓是否首屏 |
| `source_degraded_explained` | EvidenceField | 降级是否说清楚 |
| `reasoning_chain_visible` | EvidenceField | 事实推理结论是否可见 |
| `misleading_trade_risk` | EvidenceField | 是否有误导风险 |
| `top_issues` | EvidenceField[] | P0/P1/P2/P3 问题 |

## 10. 写入边界

- 数据契约写入：`dashboard_snapshot.json` 和 `research/archive/.../dashboard_*`。
- 禁止自动写：`state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md`。
- `state/portfolio.md` 只有用户明确授权持仓更新时才写。
- 所有合同字段缺失时写 `UNKNOWN`，不得用模型补数据。
