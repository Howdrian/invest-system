# Holding Review Lens — 持仓审查口径

> 目的：在不改动 `red-team-protocol.md` 核心门控的前提下，把“已有持仓”审查说清楚。  
> 边界：只读；不评分；不下单；不写 `state/portfolio.md` / `trades/trade-log.md` / `agents/scoring-card.md` / `agents/red-team-protocol.md`。

## 使用位置

当用户要求审查已有持仓，或 Dashboard / Portfolio CIO 发现持仓风险触发时，先做证据就绪检查：

- 当前价 / 成本距离；
- 市值 / 浮盈亏；
- 公告 / 事件；
- 板块 / 主题联动；
- source health；
- 止损 / 失效条件 / 最大亏损。

若关键证据缺失，结论只能是 `NEEDS_EVIDENCE`，不得启动完整交易结论。

## 表达方式

持仓审查不写成“买/卖二选一”，而写成：

```text
继续持有理由
vs
降风险理由
vs
必须补的证据
vs
是否进入正式红蓝
```

## 进入红蓝条件

满足以下任一项时，才进入现有 `red-team-protocol.md`：

- 用户明确询问买入 / 卖出 / 加仓 / 减仓；
- 持仓价格、公告、板块联动、source health 已足够支持审查；
- 重大事件、异常波动或风险边界被触发；
- Portfolio CIO 明确输出需要红蓝。

红蓝仍按现有顺序执行：

```text
蓝队论点 → 红队攻击 → 仲裁 → scoring-card → 仓位风控 → 用户确认
```

不升级成 TradingAgents 式开放群聊辩论。
