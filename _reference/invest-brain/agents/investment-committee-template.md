# Investment Committee Template — L2.5 只读投委会审查

> 目的：在真实交易前，把不同投资方法的冲突暴露出来。它不是投票系统，也不是第二套评分卡。

## 定位

- 层级：L2.5，位于 deep review / framework analysis 之后，red-blue protocol 之前。
- 写入范围：只写 `research/archive/YYYY-MM-DD-<topic>/`。
- 决策权：无。最终仍由 `agents/red-team-protocol.md` + `agents/scoring-card.md` 决定。
- 默认状态：不在日常扫描自动启用；只有触发条件满足时才用。

## 触发条件

启用本模板的场景：

1. 用户明确要求“投委会 / 多风格审查 / 交易前再审”。
2. 涉及真实买入、卖出、加仓、减仓、对冲、long call、long put、protective put。
3. 单笔风险较高，或组合暴露已经集中。
4. 深评候选出现明显方法冲突：基本面好但短线过热、技术好但宏观逆风、股票可买但期权 IV 太贵等。
5. 数据源状态 degraded / unavailable，且结论对该数据敏感。
6. 红队发现 `fatal_objection` 后，需要独立复核冲突点。

不启用的场景：

- 日常“扫描 / 有什么机会 / 完整跑一遍”。
- 所有 watchlist 候选批量跑 6 个角色。
- 数据明显不足，连 evidence pack 都无法填满；这种情况先补数据。

## 硬性禁止

1. 不给本地 0-10 交易评分。
2. 不投票决定买卖。
3. 不输出“立刻买 / 立刻卖 / 下单数量”。
4. 不写 `state/portfolio.md`。
5. 不写 `trades/trade-log.md`。
6. 不改 `agents/scoring-card.md`。
7. 不改 `agents/red-team-protocol.md`。
8. 不把 Options/Kronos/TradingAgents/Polymarket 的分数映射成本地交易分。
9. 不使用 evidence pack 之外的事实；缺失就写“缺失，需要补源”。
10. 不用多数意见压掉少数致命反对意见。

## 输入：Evidence Pack

每次投委会审查先生成同一份 evidence pack。独立角色只读这份材料。

```markdown
# Evidence Pack — <symbol/topic>

## 1. 基本信息
- 标的 / 主题：
- 市场：A股 / 港股 / 美股 / ETF / 商品 / Crypto / Macro
- 审查目的：买入 / 卖出 / 加仓 / 减仓 / 对冲 / 期权表达 / 只做重评
- 当前动作是否会写保护文件：否；仅进入后续 red-blue + scoring 后才可能写

## 2. Thesis
- 核心多头 thesis：
- 核心空头 / 反方 thesis：
- 时间框架：短线 / 中线 / 长线
- 关键催化剂：

## 3. 证据摘要
| 类别 | 证据 | 来源/文件 | 新鲜度 | 质量 | 缺口 |
|---|---|---|---|---|---|
| 基本面 |  |  |  | high/medium/low |  |
| 技术面 |  |  |  | high/medium/low |  |
| 宏观 |  |  |  | high/medium/low |  |
| 事件/政策 |  |  |  | high/medium/low |  |
| 研报/机构观点 |  |  |  | high/medium/low |  |
| 官方公告/财报 |  |  |  | high/medium/low |  |
| 期权链 |  |  |  | high/medium/low |  |
| Kronos/量化侧证 |  |  |  | high/medium/low |  |
| Polymarket/概率 |  |  |  | high/medium/low |  |

## 4. 当前风险
- 价格风险 / 是否追高：
- 流动性风险：
- 波动率 / IV 风险：
- 组合集中风险：
- 数据源不可用风险：
- 关键假设失效条件：

## 5. 待回答问题
1.
2.
3.
```

## 角色 memo 模板

每个角色输出同样结构，不互相投票。

```markdown
## <Role Name> Memo

### 立场
- support / oppose / neutral / blocked_by_missing_data

### 关键依据
- 只引用 evidence pack 中已有证据。

### 关键反对点
- 写最强反方，不要给自己找台阶。

### 数据缺口
- 哪些缺失会改变结论？

### 阻断条件
- fatal_objection：是 / 否
- 如果是，阻断原因：

### preferred_expression
- stock / ETF / wait / hedge / long call / long put / protective put / no action
- 说明：这里只表达工具偏好，不是交易指令。
```

## 角色清单

| 角色 | 重点 | 常见阻断 |
|---|---|---|
| Fundamental Investor | 财务质量、估值、护城河、基本面趋势 | 财报质量差、估值过高、现金流不支持 |
| Macro Regime Investor | 利率、美元、通胀、政策、地缘、commodity regime | 宏观逆风、政策窗口错误、尾部风险过高 |
| Catalyst / Event Investor | 近期/未来催化剂、事件链、公告、产业政策 | 催化剂已 price-in、事件证据弱、时间窗口错 |
| Technical / Quant Trader | 趋势、波动、成交量、位置、Kronos side evidence | 追高、趋势衰竭、信号与价格结构冲突 |
| Skeptic / Short Lens | 会计红旗、拥挤、反身性、过度叙事 | thesis 建在叙事上、数据质量差、下行不对称 |
| Risk / Options Manager | 仓位、相关性、止损、IV、流动性、期权结构 | spread 太宽、IV 太贵、组合暴露过大、卖方腿风险 |

## 冲突矩阵模板（conflict matrix）

```markdown
# Investment Committee Conflict Matrix

| 冲突 | 角色 | 严重度 | 处理 |
|---|---|---|---|
| 时间框架冲突 | 长期好 / 短线过热 | high/medium/low | wait / smaller size / alert only |
| 方法冲突 | 基本面支持 / 宏观反对 | high/medium/low | reduce confidence / require trigger |
| 工具冲突 | 股票可买 / 期权 IV 太贵 | high/medium/low | stock/ETF preferred / no option |
| 数据冲突 | 新闻利好 / 官方数据不支持 | high/medium/low | evidence check / no action |
| 风控冲突 | thesis 好 / 组合暴露满 | high/medium/low | no add / hedge / reduce |

## Fatal objections
- [ ] 无
- [ ] 有：

## Missing data before red-blue
1.
2.

## Red-team focus
1.
2.
3.
```

## 输出位置

推荐写入同一研究目录：

```text
research/archive/YYYY-MM-DD-<topic>/investment_committee/
├── evidence_pack.md
├── role_memos.md
└── conflict_matrix.md
```

## 进入下一步的条件

可以进入红蓝对抗：

- 没有 fatal objection；
- 关键数据缺口已补齐，或明确不会影响本次动作；
- 冲突矩阵已列出 red-team focus；
- 仍然承认最终交易评分只来自 `agents/scoring-card.md`。

如果有 fatal objection：停止交易判断，回到补数据或等待触发条件。
