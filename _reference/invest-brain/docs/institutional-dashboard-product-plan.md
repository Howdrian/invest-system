# Institutional Dashboard Product Plan

> Updated: 2026-05-26  
> Scope: 不接付费 API；用现有免费/公开源和本地归档，把 Dashboard 产品化为“投研首页 + 证据链页 + 系统健康页”。

## 直接结论

机构级 dashboard 的主轴不是“脚本跑了多少组件”，而是：

```text
能不能信 -> 事实是什么 -> 如何推理 -> 结论是什么 -> 组合风险在哪 -> 哪些证据缺口阻断 -> 数据/系统哪里降级
```

本项目不复制 Bloomberg / FactSet / LSEG / Morningstar 的付费数据层，只吸收它们的产品结构：组合、风险、暴露、归因、情景、新闻/研究、报告、可追溯数据。

## 外部对标依据

| 对标产品 | 可吸收的体验/流程 | 免费源下的本地实现 |
|---|---|---|
| Bloomberg Portfolio Analytics / PORT | 组合风险、表现归因、情景压力、可定制 dashboard、报告输出 | `组合风险 / 暴露 / 情景` 卡片 + ETF/指数 proxy；不输出精确 VaR |
| FactSet Advisor Dashboard | 把风险、表现、暴露、新闻、研究、事件和客户/组合关联到同一首页 | `AI 主动简报` + `候选队列` + `事件时间轴` + `source health` |
| LSEG Workspace | 跨资产数据、新闻、分析、搜索/发现、工作流集成 | `市场总览` + `主题热力图` + `机会漏斗` + `自动化/补跑` |
| Morningstar Direct Portfolio Management | 持仓分析、组合构建、压力情景、归因、清晰报告 | `state/portfolio.md` 驱动的持仓/空仓风险层 + 本地 `dashboard_snapshot.json` |

参考链接：

- Bloomberg Portfolio Analytics: https://www.bloomberg.com/professional/products/bloomberg-terminal/portfolio-analytics/
- FactSet Advisor Dashboard: https://www.factset.com/lp/advisor-dashboard
- LSEG Workspace: https://www.lseg.com/en/data-analytics/products/workspace
- LSEG Workspace Data and Content: https://www.lseg.com/en/data-analytics/products/workspace/data-and-content
- Morningstar Direct Portfolio Management: https://www.morningstar.com/business/products/direct/portfolio-management-tool

## 产品信息架构

### 1. 负责人一屏

首屏只回答 5 件事：

1. 今日是否可用于交易判断；
2. 当前组合风险和暴露；
3. 数据新鲜度与源健康；
4. 用户下一步动作；
5. 是否有 AI 预审材料或正式候选。

当前实现：

- `render_decision_summary()`
- `render_data_freshness_bar()`
- `portfolio_snapshot()` + `render_portfolio_risk()`
- `render_action_card()`
- `render_ai_digest()`
- `render_candidates()`

### 2. 分析师工作台

用于解释“为什么留下/为什么筛掉”，不作为首页压迫用户：

- 市场 regime 与策略总控；
- 市场快照；
- 跨资产真实行情；
- 主题热力图；
- 机会漏斗；
- 候选走势图；
- 催化剂时间轴；
- 相对变化。

### 3. 证据链页

独立文件：`dashboard_evidence.html`。

它不做视觉营销，只负责把材料讲清楚：

- 阻断归因矩阵：事实 → 推理 → 结论；
- CIO 总审与子 Agent 状态；
- AI digest / Codex AI review；
- 市场状态总控；
- 深评候选和原始证据入口。

### 4. 系统健康页

独立文件：`dashboard_system.html`。

它只解释技术/数据状态，不混入投资结论：

- source health / 数据源新鲜度；
- primary / fallback / cache / retry / AI diagnostic 恢复计划；
- 数据源探针；
- 自动化/补跑；
- Dashboard 产品审核。

### 5. 风险与数据健康

把数据源、系统问题和覆盖缺口集中放在一个板块：

- 数据源总探针；
- 系统问题诊断；
- 专业金融面板覆盖度；
- 用户阅读路径。

### 6. 工程诊断

默认折叠。只有排错或审计时才看：

- 单 profile 报告卡；
- 内部指标走势；
- 源健康明细；
- LaunchAgent / Codex automation 状态。

## Agent 分工设计

这里的 “agent” 是职责分工，不新增第二套评分/交易系统。

| Agent | 输入 | 输出 | 边界 |
|---|---|---|---|
| Source Health Agent | `13_source_health.json`、`run_metadata.json` | 可用/降级/不可用、失败原因 | 不改候选评分 |
| Market Regime Agent | `14_market_strategy.json`、跨资产 proxy | risk-on / crowded / rotation / risk-off / event risk | 不直接给买卖 |
| Portfolio Risk Agent | `state/portfolio.md` | 持仓/空仓、Portfolio Heat、暴露、情景 proxy | 无价格时写未知，不造 P&L |
| Candidate Funnel Agent | `11_deep_review_queue.json` | Top 候选、证据质量、价格风险、下一步 | 不把等待承接显示成买点 |
| AI Digest Agent | `digest.json`、交易预审包 | 是否提醒、是否生成 evidence pack | 不交易、不写保护区 |
| Subagent Review Agents | 同一份 `evidence_pack.md`、source health、market strategy、portfolio 只读 | Source/Macro/Catalyst/Fundamental/Technical/Risk 六类独立 memo | 不评分、不交易、不写保护区 |
| CIO Review Agent | `subagent_memos/*.json/md` + evidence pack | 是否进入红蓝、fatal objection、缺失证据、用户下一步 | 不投票、不输出 0-10 分、不下单 |
| Dashboard Product Agent | 上述 snapshot | 负责人一屏和可读 UI | 隐藏工程字段，保留追溯链接 |
| Dashboard Financial Product Reviewer | `dashboard.html`、`dashboard_snapshot.json`、AI review、CIO review | 产品审核：信息架构、图表误导、数据质量、交易安全边界 | 不给买卖建议 |
| Architecture / Rule Audit Agent | 源码、测试、dashboard 输出 | 契约漂移、保护区、执行语言检查 | 只提/执行工程修复，不改交易规则 |

## 数据契约

新增/强化：

- `scripts/contracts.py`：统一 digest verdict、交易预审层级、保护文件等展示契约；
- `dashboard_snapshot.json`：sanitised view-model，只保留首页/前端需要的摘要字段；原始研究数据仍以 `research/archive/...` 为唯一真相源；
- `13_source_health.json.recovery_plan`：源恢复契约，写明每个组件的可靠性、备用源/缓存、影响范围、补跑和 Codex AI 诊断条件；
- `cio_review.json`：CIO 总审 view-model，只允许 `READY_FOR_RED_BLUE / WAIT_ENTRY / NEEDS_EVIDENCE / BLOCKED_BY_FATAL`；
- `dashboard_product_review.json`：Dashboard 产品审核 view-model，只允许 `PASS / PASS_WITH_WARNINGS / BLOCKED / UNKNOWN`；
- `dashboard_governance_audit.json`：Dashboard Governance Agent 复评结果，包含 `composite_score`、10秒/30秒阅读线、截图级审核状态、数据契约缺口和链路断点；目标综合分 `>4.5`，只代表产品可用性，不代表可交易；
- `scripts/test_render_dashboard.py`：验证枚举中文化、链接不暴露本机绝对路径、空仓不伪造风险；
- `architecture_audit.py`：验证产品化 section、无裸枚举、无 `/Users/hac/` 本机路径泄漏。

## v1 验收标准

- 非付费源即可生成 dashboard；
- 首页有 `负责人一屏 / 分析师工作台 / 风险与数据健康 / 工程诊断`；
- 同时生成 `dashboard_evidence.html` 和 `dashboard_system.html`，把证据链与技术健康从首页拆出去；
- source degraded 时，首页和系统健康页必须说明备用源/缓存、影响范围、系统下一步和 AI 介入条件；
- 首屏 KPI 是投资 KPI，不是组件 KPI；
- 空仓显示空仓，不伪造组合 VaR / P&L；
- 有持仓时风险来自 `state/portfolio.md`，缺价格显示未知；
- 交易预审材料显示为“预审/等待确认”，不是买卖信号；
- `dashboard.html` 不暴露 `/Users/hac/` 绝对路径；
- `dashboard.html` 不显示 `REVIEW_PACK_READY`、`TRADE_REVIEW_PREP_WAIT_EVENT` 等裸枚举；
- 保护文件无 diff；
- 单测、架构审计、dashboard 生成均通过。

## v1.1 专业调研标准层（2026-05-26）

本计划已拆出三份可执行标准文档，作为后续 Dashboard 重构的验收基准：

- `docs/dashboard-product-standard.md`：定义首页 10 秒/30 秒阅读线、持仓优先、图表规则、数据降权和误导交易防护。
- `docs/dashboard-information-architecture.md`：定义首页、持仓页、机会页、证据链页、系统健康页的目标信息架构。
- `docs/dashboard-data-contract.md`：定义 `decision_brief / portfolio_monitor / market_brief / opportunity_brief / evidence_brief / source_recovery / dashboard_governance` 七类 view-model。

当前差距审计见：

- `research/archive/2026-05-26-dashboard-research-audit/dashboard_gap_audit.md`

新增硬规则：只要首页信息过载、持仓未首屏一级展示、CIO 今日焦点偏离持仓、source recovery 缺连续失败/新鲜度/下一次重试，Dashboard 产品审核就不能给 `PASS 5.0`。
