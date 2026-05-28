# System Architecture

## 设计原则

1. **单入口**：用户只需要记 `invest-brain`。
2. **本体在项目内**：扫描器、审计器、协议和方法论放在 `/Users/hac/AI-Studio/投研`，避免把几十个项目模块全加载到用户级 skill。
3. **外部项目分层吸收**：数据适配器可直接接入；TradingAgents、Kronos 等只作为 challenger；Anthropic financial-services 这类官方金融工作流项目作为架构/流程参考，不替代本地评分、组合和交易记录。
4. **只读优先**：完整扫描只写研究归档，不改持仓和交易记录。
5. **门控后置**：发现机会不等于买卖；交易前必须红蓝对抗和评分门控。

## 分层

| 层 | 组件 | 职责 |
|---|---|---|
| L0 | `scripts/daily_intelligence.py`、`market_heat_scan.py`、`report_intelligence.py`、`official_*`、`crypto_scan.py` | 公开源扫描和证据采集 |
| L0.7 | `screening_funnel.py`、`deep_review_candidates.py` | 多证据汇总、候选排序、深评排队 |
| L0.82 | `frameworks/options-long-only.md` + `scripts/options_data_probe.py` + `scripts/options_chain_scan.py` | 可选 long-only 期权候选，只输出 `options/18_options_candidates.*` |
| L0.85 | `integrations/kronos/` + `scripts/kronos_lane.py` | 可选量化预测侧证，只输出 `kronos/17_kronos_forecast.*` |
| L1 | `macro_regime_refresh.py`、`integrations/polymarket/` | 宏观 regime 和外部概率校准 |
| Scheduler | `scripts/scheduled_research.py`、`scripts/schedule_catchup.py`、macOS LaunchAgent | 本机定时和漏跑补检；只调用研究周期，不做交易、不写保护区 |
| Dashboard | `scripts/render_dashboard.py`、`dashboard.html`、`dashboard_snapshot.json` | 机构化每日控制台；负责人一屏、组合风险/暴露/情景、数据新鲜度、AI Digest、候选队列、分析师工作台、风险与数据健康、折叠工程诊断 |
| AI Digest | `scripts/daily_ai_digest.py` | 每个固定 profile/补跑后读取报告并生成 AI prompt、提醒状态和可选交易审查包；不交易、不写保护区 |
| Codex AI Review | Codex automation | 工作日收盘/盘前后读取 AI digest、dashboard 和深评队列，输出 AI review；只复核，不自动交易 |
| Rule Audit | `scripts/weekly_rule_audit.py` | 每周审计筛选/深评/source-health/dashboard/AI触发规则是否符合交易理念；只输出建议 |
| L2 | `frameworks/` | 个股、商品、宏观、做空、对冲、组合方法论 |
| L2.2 | `docs/anthropic-financial-services-adoption.md` + future `coverage_workbench/` | 单标的/主题进入深评后的 coverage、earnings、valuation、thesis、catalyst 工作台；参考 Anthropic market-researcher / earnings-reviewer / model-builder，但只写研究归档 |
| L2.5 | `agents/investment-committee-template.md` + `docs/pre-trade-evidence-pack-template.md` | 交易前只读投委会审查：统一证据包、角色 memo、冲突矩阵；不投票、不评分、不写保护区 |
| L2.7 | `scripts/daily_ai_digest.py` generated `trade-review-*` | 强候选自动生成交易审查包；只到 evidence pack / role memos / red-blue scaffold / scoring scaffold，不自动给交易结论 |
| L2.8 | `agents/subagent-review-protocol.md` + `agents/chief-investment-officer.md` + `scripts/cio_review_pack.py` | 真实 Subagent memo + CIO 总审：判断是否进入红蓝、缺什么证据、是否 fatal 阻断；不评分、不投票、不写保护区 |
| L2.6 | future model/document QC templates | Excel/模型/报告质量审查：公式、硬编码、来源、图表、结论一致性；不发布、不下单 |
| L3 | `agents/red-team-protocol.md`、`quality-reviewer.md` | 红蓝对抗和质量审查 |
| L3.1 | `agents/holding-review-lens.md` | 持仓审查口径：继续持有理由 vs 降风险理由；证据不足时先补证据，不改红蓝核心协议 |
| L4 | `agents/scoring-card.md`、position sizing skill | 评分门控和仓位风控 |
| L5 | future packaging / validation checks | 参考 Anthropic plugin + managed-agent cookbook 的打包和校验层；只做 manifest/schema/路径/保护区检查，不改变投资决策权 |
| State | `state/`、`trades/` | 持仓、市场状态、关注列表、交易记录；默认保护 |

## 外部项目吸收边界

### Institutional dashboard benchmark

吸收的是 Bloomberg PORT、FactSet Advisor Dashboard、LSEG Workspace、Morningstar Direct 这类机构终端的产品结构，不吸收其付费数据源。

- 本地说明：`docs/institutional-dashboard-product-plan.md`
- 已用位置：`scripts/render_dashboard.py`、`scripts/dashboard_product_review.py`、`scripts/dashboard_governance_audit.py`、`dashboard.html`、`dashboard_snapshot.json`
- 可吸收位置：组合风险、暴露、情景 proxy、新闻/研究/事件关联、源健康、报告输出。
- 保留边界：不输出精确 VaR，不伪造 P&L/持仓归因，不把 dashboard 变成第二套评分器或交易系统。

### Subagent / CIO Review

吸收的是 Anthropic orchestrator-workers、TradingAgents 多角色审查和 FinRobot 报告流水线的“分工 + 汇总”结构，不吸收自动交易。

- 已用位置：`agents/subagent-review-protocol.md`、`agents/chief-investment-officer.md`、`scripts/cio_review_pack.py`、`scripts/render_dashboard.py`
- 输入：同一份 `evidence_pack.md` 和项目只读上下文。
- 输出：`subagent_memos/*.md/json`、`cio_review.md/json`。
- 保留边界：真实 Subagent 不能评分、不能交易、不能写保护区；CIO 只判断 `READY_FOR_RED_BLUE / WAIT_ENTRY / NEEDS_EVIDENCE / BLOCKED_BY_FATAL`，不替代红蓝和评分卡。

### Anthropic financial-services

吸收的是“企业级金融 Agent/Skill/数据连接器/托管 Agent 的架构模板”，不是交易决策系统。

- 参考项目：`https://github.com/anthropics/financial-services`
- 本地采纳说明：`docs/anthropic-financial-services-adoption.md`
- 已确认形态：官方 Claude for Financial Services 模板，包含 `vertical-plugins/`、`agent-plugins/`、`managed-agent-cookbooks/`、partner data connectors 和校验脚本。
- 可吸收位置：
  - L2.2：coverage / earnings / valuation / thesis / catalyst workbench；
  - L2.6：model / report / deck QC；
  - L5：plugin packaging、schema validation、skill sync、untrusted-document guardrails；
  - Tier 2 paid provider blueprint：FactSet、S&P Capital IQ、Daloopa、Morningstar、LSEG、Aiera 等以后按 adapter 接入。
- 保留边界：不 vendoring 到主 runtime；不替代 `invest-brain`；不把外部 agent 结论映射为本地 0-10 评分；不写 `state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md`；付费 MCP 缺失不阻断每日免费源扫描。

### Investment Committee / L2.5

吸收的是“交易前多风格冲突审查”，不是投资经理投票制。

- 已用位置：`agents/investment-committee-template.md`、`docs/pre-trade-evidence-pack-template.md`
- 触发：真实买/卖/加/减/对冲/long call/long put/protective put 前，或用户明确要求投委会审查。
- 输入：同一份 evidence pack。
- 输出：role memos + conflict matrix + fatal objections + missing data。
- 保留边界：不投票、不输出本地 0-10 交易评分、不写 `state/portfolio.md` 或 `trades/trade-log.md`；最终仍进入 `agents/red-team-protocol.md` 和 `agents/scoring-card.md`。

### TradingAgents

吸收的是“多角色审查/挑战结构”，不是它的 portfolio 或买卖结论。

- 已用位置：`integrations/tradingagents/`
- 用途：sidecar report、local challenge、A/B 质量验证。
- 保留边界：本地 `agents/scoring-card.md` 和 `agents/red-team-protocol.md` 是唯一评分/红蓝源。

### Options long-only

吸收的是“买方期权作为有限风险表达/保护工具”的规则，不吸收卖方期权或自动交易。

- 已用位置：`frameworks/options-long-only.md`、`scripts/options_data_probe.py`、`scripts/options_chain_scan.py`
- 输出：`options/18_options_candidates.json/md/html`
- 当前状态：Phase 1 可选 lane 已接入；没有 Tradier/Polygon/Alpaca/IBKR 等稳定数据源时会降级/阻断。
- 保留边界：只允许 long call / long put / protective put；不卖腿、不自动下单、不写 `trades/trade-log.md`；`options_candidate_score` 不是本地交易评分。

### Kronos

吸收的是“K线基础模型作为技术侧 challenger”的思想，不吸收它作为交易系统本体。

- 已用位置：`integrations/kronos/`
- 参考项目：`https://github.com/shiyu-coder/Kronos`
- 输出：`kronos/17_kronos_forecast.json/md/html`
- 当前状态：Phase 2 可选 lane 已接入；2026-05-18 真实 `Kronos-mini` pinned-model smoke 已通过；默认仍不进入评分。
- 保留边界：不写 `12_preliminary_deep_review.md`、不影响 0-10 评分、不触发交易；后验监控由 `scripts/kronos_backtest_monitor.py` 记录。

### Polymarket

吸收的是外部事件概率，不吸收预测市场交易。

- 已用位置：`integrations/polymarket/`
- 用途：scenario probability、catalyst clarity、red-team trigger。
- 保留边界：不得单独越过 6.0。

### TradingView

吸收的是用户设置的图表/告警入口，不把 TradingView 当官方行情 API。

- 已用位置：`integrations/tradingview/`
- 当前状态：alert/webhook 规划。

## 冗余处理策略

| 类型 | 当前判断 | 处理 |
|---|---|---|
| `AGENTS.md` 与 `CLAUDE.md` 重复 | 有意重复，服务不同入口 | 保持同步，不合并 |
| `_archive/`、`_reference/` | 非运行时资料 | 保留，不参与主流程 |
| `architecture_audit.py` 与 `completion_audit.py` | 有交叉但目标不同 | 保留：前者看架构/接线，后者看一次运行完成度 |
| commodity lane 与 commodity fundamentals | 一个筛候选，一个看基本面覆盖 | 保留 |
| TradingAgents 与 Kronos | 都是 challenger，但证据类型不同 | 保留独立，不进主评分 |

## 验收标准

- 统一周期可跑完，组件 `rc=0`；同时 `13_source_health.json.usability_verdict` 不能是 `unavailable`。
- 每日 AI Digest 可生成，且 `protected_writeback=false`、`trade_execution=false`。
- 必要报告和 HTML 视图存在。
- 深评候选含 evidence quality / price risk / next action。
- `paid_api_required=false`，`protected_writeback=false`。
- 保护文件无 diff。
- 可选 challenger/期权 lane 输出独立文件，且 `scoring_impact=0` 或仅候选评分，不写保护区。
- L2.5 投委会审查只读 evidence pack，输出冲突矩阵，不投票、不评分、不写保护区。
