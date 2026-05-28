# daily_stock_analysis 对标与采纳边界

> Reviewed: 2026-05-28  
> Source: https://github.com/ZhuLinsen/daily_stock_analysis  
> Local inspection target: `/tmp/daily_stock_analysis`

## 直接结论

`daily_stock_analysis` 比本项目更像一个已经产品化的股票分析工作台：它有 Web/桌面端/API/Bot、数据源 provider、真实 Agent pipeline、策略 YAML、持仓、回测、告警和自动推送。

本项目比它覆盖更宽、交易保护边界更明确，但这不能替代“给用户有价值建议”的能力。后续不应继续只堆数据源和 prompt，而应吸收它的产品化和建议闭环。

推荐采用：

```text
本项目继续作为投研 source of truth
+ 吸收 daily_stock_analysis 的产品/数据/持仓/回测架构
+ 保留本项目红蓝、评分、仓位、用户确认作为执行前门控
```

## 不采用“全量替换”的原因

| 项目 | 结论 |
|---|---|
| 直接以 daily_stock_analysis 为主重构 | 不建议。它更偏股票分析产品，宏观/地缘/商品/期权/证据治理不如本项目覆盖宽。 |
| 保留本项目原架构不变 | 不建议。当前本项目太重、太谨慎、建议层和产品层不够直接。 |
| 混合架构 | 推荐。吸收它成熟的 provider、context pack、portfolio、alert、backtest、Web/API 产品层。 |

## 重点吸收模块

### 1. AnalysisContextPack

把当前 source health 从粗粒度：

```text
usable / degraded / unavailable
```

升级为字段级状态：

```text
available / missing / not_supported / fallback / stale / estimated / partial
```

每个数字都要有：

- 来源；
- as_of；
- 新鲜度；
- fallback；
- 是否可用于持仓监控；
- 是否可用于交易预审。

### 2. DataProvider Manager

本项目需要从“很多脚本各自抓数据”升级成统一 provider 层：

```text
QuoteProvider
AnnouncementProvider
NewsProvider
MacroProvider
OptionsProvider
CommodityProvider
ReportProvider
```

统一输出：

```json
{
  "value": "...",
  "status": "available|fallback|partial|stale|missing",
  "source": "...",
  "as_of": "...",
  "fallback_from": "...",
  "impact_scope": ["portfolio_monitor", "research", "trade_review"]
}
```

### 3. Portfolio Ledger / Snapshot

当前本项目有 `state/portfolio.md` 和 `portfolio_monitor`，但还不是完整持仓账本。

应补：

- 账户；
- 交易流水；
- 现金；
- 成本；
- 快照；
- P&L；
- 风险触发；
- 持仓审查记录；
- 建议后验表现。

保护规则不变：自动流程不能写交易流水，除非用户明确授权。

### 4. Alert Center

Dashboard 不应只展示报告，还应有提醒中心：

```text
持仓价格触发
公告触发
板块共振触发
source missing 触发
红蓝材料待看
回测/复盘待更新
```

提醒只推动审查，不自动交易。

### 5. Backtest / Forward Ledger

本项目最缺的是建议质量验证。

必须记录：

- 哪天建议“等待承接”；
- 哪天建议“进入持仓审查”；
- 后续 1/3/5/10/20 日表现；
- 是否跑赢简单 baseline；
- 红蓝评分和结果是否相关；
- 持仓触发是否真的降低风险。

没有这层，系统无法证明自己比普通 AI 总结更有价值。

## 不直接吸收模块

| 模块 | 原因 |
|---|---|
| DecisionAgent 直接买卖结论 | 可以参考表达形式，但不能替代本项目红蓝/评分/仓位/用户确认 |
| buy/hold/sell 作为最终交易动作 | 本项目可以给“建议/审查状态”，但执行动作必须过门控 |
| 直接复制 Web/Desktop runtime | 需要 license 和工程适配审查，先吸收架构 |
| 第二套 portfolio / score | 会造成系统分裂 |

## 目标混合架构

```text
Cloud / Local Scheduler
        ↓
Provider Manager + ContextPack
        ↓
Portfolio Ledger + Market/News/Event Data
        ↓
Research/Opportunity/Portfolio Analysis Agents
        ↓
Recommendation Layer
  观察 / 等承接 / 持仓审查 / 进入红蓝 / 不推进
        ↓
Red-Blue + Scoring + Position Sizing + User Confirmation
        ↓
Dashboard + Alerts + Backtest/Forward Ledger
```

## 云端部署判断

`daily_stock_analysis` 天然更适合云端：

- GitHub Actions；
- Docker；
- API；
- Web app；
- Bot 推送；
- 配置化数据源；
- 较清晰的服务边界。

本项目当前也可以上 Codex/云端跑部分脚本，但不适合直接 GitHub Actions 全量运行：

- 本地路径和状态文件较多；
- Dashboard 仍是本地 HTML 主导；
- 自动化依赖本机定时和本地 archive；
- 保护文件和用户授权边界更复杂；
- AI review 依赖 Codex 环境。

因此推荐：

```text
短期：本地为主 + Codex 自动化
中期：抽出 provider/context/portfolio/alert/backtest 到可云端运行的服务层
长期：Dashboard/API 云端化，但交易保护区仍保留明确授权边界
```

## 下一步优先级

P0:

1. 新增 `Independent System Architecture Reviewer`，定期反审本项目是否只是“更谨慎”而不是“更有用”。
2. 引入 ContextPack 字段级数据质量。
3. 重构 Provider Manager。
4. 补 Portfolio Ledger。
5. 建立 Recommendation Layer，允许明确建议“观察/审查/等待/推进”，但不输出执行指令。

P1:

1. 建 Alert Center。
2. 建 Backtest / Forward Ledger。
3. Dashboard 改为建议优先，不是工程状态优先。
4. 把真实多 Agent 缩减成少数高价值角色：数据、持仓、机会、风控、产品。
5. 评估是否引入 Web/API 服务层。

## 边界

- `daily_stock_analysis` 当前只作为参考和 sidecar candidate。
- 不把它的买卖结论映射成本项目交易评分。
- 不让外部项目写 `state/portfolio.md` / `trades/trade-log.md`。
- 复制代码前必须检查 license。
