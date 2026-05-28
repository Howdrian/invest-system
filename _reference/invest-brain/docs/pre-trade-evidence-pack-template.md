# Pre-trade Evidence Pack Template

> 用途：交易前统一证据口径，供 `agents/investment-committee-template.md`、红蓝对抗和评分门控读取。它不是交易指令。

## 使用时机

- 买入 / 卖出 / 加仓 / 减仓 / 对冲 / long call / long put / protective put 之前。
- 深评候选存在明显冲突，需要投委会模板审查。
- 数据源 degraded，且该数据会影响结论。

日常扫描不需要生成本模板。

## 写入边界

- 只能写入 `research/archive/YYYY-MM-DD-<topic>/`。
- 不写 `state/portfolio.md`。
- 不写 `trades/trade-log.md`。
- 不改 `agents/scoring-card.md`。
- 不改 `agents/red-team-protocol.md`。

## 模板

```markdown
# Evidence Pack — <symbol/topic>

## 1. 审查对象
- 标的 / 主题：
- 市场：
- 动作类型：只读重评 / 买入 / 卖出 / 加仓 / 减仓 / 对冲 / long call / long put / protective put
- 时间框架：短线 / 中线 / 长线
- 本轮是否允许写保护文件：否

## 2. 现有结论
- 当前 thesis：
- 当前反方 thesis：
- 当前 next action：
- 来自哪个研究目录：

## 3. 证据表
| 维度 | 证据 | 来源文件/URL | 时间 | 质量 | 缺口 |
|---|---|---|---|---|---|
| 基本面 |  |  |  | high/medium/low |  |
| 技术面 |  |  |  | high/medium/low |  |
| 宏观 |  |  |  | high/medium/low |  |
| 催化剂/政策 |  |  |  | high/medium/low |  |
| 官方公告/财报 |  |  |  | high/medium/low |  |
| 研报/机构观点 |  |  |  | high/medium/low |  |
| 期权链/IV/Greeks |  |  |  | high/medium/low |  |
| 量化/Kronos侧证 |  |  |  | high/medium/low |  |
| 外部概率/Polymarket |  |  |  | high/medium/low |  |

## 4. 风险和约束
- 当前价格位置：
- 是否追高 / 过热：
- 流动性：
- spread / slippage：
- IV / theta / 到期风险：
- 组合相关性：
- 最大可承受亏损：
- 关键失效条件：

## 5. 待投委会审查的问题
1.
2.
3.

## 6. 禁止事项确认
- [ ] 不给 0-10 交易评分
- [ ] 不投票买卖
- [ ] 不写 portfolio
- [ ] 不写 trade-log
- [ ] 不把 Options/Kronos/外部项目分数映射成本地评分
```
