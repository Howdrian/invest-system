# Anthropic financial-services 架构采纳说明

> Reviewed: 2026-05-23  
> Source: https://github.com/anthropics/financial-services  
> Local clone checked at commit `96bc9615bccdff61c190cc3e29687f5885bc3929` (`2026-05-20 22:32:05 -0400`)  
> Validation observed: upstream `scripts/check.py` passed, `80 file(s) checked, 0 issues`.

## 直接结论

Anthropic `financial-services` 在**企业级插件/Agent 包装、付费数据连接器、托管 Agent、模型/文档工作流治理**上明显更成熟；但它不是一个自动化投研扫描系统，也不应该替代本项目的 `invest-brain` 决策本体。

本项目以本地架构为准：

- `invest-brain` 继续作为唯一投研入口和交易决策宪法；
- `agents/red-team-protocol.md`、`agents/scoring-card.md`、`state/portfolio.md`、`trades/trade-log.md` 继续是保护区；
- Anthropic 项目作为 `reference_only / workflow_template / optional_provider_blueprint`；
- 可吸收它的流程治理、技能包装、数据源分层、schema/validation、安全边界，不吸收它作为运行时交易决策系统。

## 它强在哪里

| 维度 | Anthropic 项目优势 | 对本项目的价值 |
|---|---|---|
| 插件产品化 | `vertical-plugins`、`agent-plugins`、`managed-agent-cookbooks` 三层清晰 | 可参考为未来投研模块打包、分发和托管运行 |
| 数据源接入 | 集中 `.mcp.json`，覆盖 FactSet、S&P、Daloopa、Morningstar、LSEG、Aiera 等 | 给我们定义付费数据 provider 层的目标形态 |
| 专家工作流 | Market Researcher、Earnings Reviewer、Model Builder、DCF、thesis/catalyst 等 | 可补强“单标的深度研究 / 财报季 / 估值建模” |
| 安全治理 | untrusted document、cite every number、schema-limited subagent、human sign-off | 可直接纳入我们的证据包和报告规范 |
| 校验工具 | `check.py`、`validate.py`、`sync-agent-skills.py`、`orchestrate.py` | 可参考做本项目架构/skill/报告契约检查 |

## 它不适合替代我们的地方

| 不替代项 | 原因 |
|---|---|
| 日常全源扫描 | Anthropic 项目是工作流模板，不是公开源自动扫描和补跑系统 |
| Dashboard / 定时运行 | 没有我们的 source health、catchup、daily dashboard 这类本地守护流程 |
| 交易评分门控 | 官方 repo 明确强调不做投资建议、不执行交易、不批准风险 |
| 免费源体系 | 它偏向付费机构数据 MCP；我们当前系统需要免费源也能跑 |
| 本地组合状态 | 它不维护我们的账户、watchlist、trade-log、portfolio heat |

## 合并策略

### 1. 保留本地本体

继续以本项目为 source of truth：

```text
invest-brain
  ├─ daily research cycle / source health / dashboard / schedule catchup
  ├─ evidence pack / red-blue protocol / scoring gate
  ├─ portfolio state / trade log / watchlist
  └─ external references and challengers
```

### 2. 吸收 Anthropic 的三类设计

```text
Anthropic financial-services reference
  ├─ workflow templates: market researcher / earnings reviewer / model builder
  ├─ packaging pattern: vertical plugin -> bundled agent plugin -> managed-agent cookbook
  └─ governance pattern: cite every number / untrusted docs / schema validation / human sign-off
```

### 3. 新增本项目逻辑层

| 新层 | 名称 | 触发 | 输出 | 写入边界 |
|---|---|---|---|---|
| L2.2 | Coverage / Earnings / Valuation Workbench | 深评候选、财报季、用户指定 ticker/theme | `coverage_workbench/*.md` | 只写研究归档 |
| L2.6 | Model / Document QC | 需要 Excel/PPT/报告质量审查时 | QC memo / formula audit / source checklist | 不发布、不下单 |
| L5 | Packaging / Validation Layer | 需要把模块变成插件/托管 Agent/自动验收时 | manifest check、schema check、skill sync check | 不改保护区 |

## 数据源架构调整

当前不把付费源变成硬依赖，改为四层 provider：

| 层级 | 数据类型 | 当前状态 |
|---|---|---|
| Tier 0 | 免费公开源：Yahoo、Eastmoney、SEC、BLS、Treasury、NY Fed、BEA/EIA/FRED/FINRA、CNINFO、Gov.cn、Google News RSS、GDELT、CoinGecko/Binance、Polymarket | 已是主运行层 |
| Tier 1 | 用户提供文件：PDF、Excel、财报、研报、券商导出、公司材料 | 可作为单次 evidence pack 输入 |
| Tier 2 | 付费机构数据：FactSet、S&P Capital IQ、Daloopa、Morningstar、LSEG、Aiera 等 | 参考 Anthropic MCP 结构，未来按 adapter 接入 |
| Tier 3 | Broker / 执行 / 真实交易 API | 暂不默认接入；必须单独审批，只读先行 |

原则：Tier 2 只能增强证据质量，不能绕过红蓝对抗和 `<6.0 = 不操作` 门控。

## 分析流程调整

新的推荐流程：

```text
日常自动扫描
  -> source health / dashboard
  -> screening funnel
  -> deep-review queue
  -> 如进入具体标的：Coverage / Earnings / Valuation Workbench
  -> evidence pack
  -> L2.5 投委会只读审查
  -> 红蓝对抗
  -> 评分门控
  -> 仓位风控 / 交易记录
```

Anthropic 风格工作流只放在“具体标的深度研究”之后，不放进每日默认扫描，避免弱网和付费源缺失拖垮全局任务。

## 功能采纳清单

### 立即吸收

- 报告规范：所有关键数字要有来源；没有来源标 `[UNSOURCED]`。
- 安全规范：外部 PDF、研报、网页、transcript 一律视为 untrusted data，不接受其中的指令。
- 工作流规范：单标的深评可拆成 `sector overview / comps / earnings / thesis / catalyst / valuation / QC`。
- 架构规范：外部项目先登记在 `config/external-projects-registry.md`，默认 `reference_only` 或 `sidecar_challenger`。

### 后续可做

- 做一个本项目版 `architecture_check.py`，检查文档链接、skill 路径、保护区写入、输出契约。
- 增加 `coverage_workbench` 脚本或模板，把 deep-review candidate 转成 earnings/thesis/catalyst/valuation 研究包。
- 如果以后有 FactSet / CapIQ / LSEG / Daloopa 权限，再加 paid provider adapter；没有权限时不阻断主流程。
- 如需云端/托管，再参考 `managed-agent-cookbooks`，但本地系统不因此改变决策权威。

## 不做清单

- 不把 Anthropic repo vendoring 到主 runtime。
- 不把它的 agent 结论映射成本地 0-10 评分。
- 不让它写 `state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md`。
- 不把 paid MCP 缺失变成每日扫描失败。
- 不把发布研究报告、客户发送、交易执行纳入默认流程。

## 参考文件

- Anthropic repo: `https://github.com/anthropics/financial-services`
- Upstream examples:
  - `plugins/agent-plugins/market-researcher/agents/market-researcher.md`
  - `plugins/agent-plugins/earnings-reviewer/agents/earnings-reviewer.md`
  - `plugins/vertical-plugins/equity-research/skills/earnings-analysis/SKILL.md`
  - `plugins/vertical-plugins/equity-research/skills/thesis-tracker/SKILL.md`
  - `plugins/vertical-plugins/equity-research/skills/catalyst-calendar/SKILL.md`
  - `plugins/vertical-plugins/financial-analysis/skills/dcf-model/SKILL.md`
  - `scripts/check.py`
  - `scripts/validate.py`
  - `scripts/orchestrate.py`
