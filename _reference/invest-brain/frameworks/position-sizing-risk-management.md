# 仓位管理与风控实战手册

> 调研日期：2026-03-30
> 适用资金规模：$50K - $200K
> 原则：简单可执行的规则，非复杂模型

---

## 一、Kelly 公式实战

### 公式

**简化版（投资适用）：**

```
Kelly fraction (f*) = Edge / Odds = (b × p - q) / b
```

其中：
- b = 预期收益倍数（每 $1 风险的预期回报）
- p = 获胜概率
- q = 失败概率 (1 - p)

**投资版本（连续回报）：**

```
Kelly weight = Expected Return / Variance of Return
```

> 来源：Wikipedia - Kelly criterion; astuteinvestorscalculus.com

### 实际怎么用

1. **评估你的"边际优势"**：你对这笔交易有多大把握？预期回报是多少？
2. **代入公式算出理论最优仓位**
3. **打个折（Half-Kelly 或 Quarter-Kelly）**

**举例**（来源：astuteinvestorscalculus.com）：
- 你发现一只股票 $10，合理估值 $20，上涨空间 100%
- 但它是波动很大的小盘股，标准差 40%
- 经过 Kelly 计算 + 信心折扣 → Half-Kelly 建议仓位约 7%

### Half-Kelly 为什么更实用

| 指标 | Full Kelly | Half Kelly |
|------|-----------|------------|
| 预期增长率 | 100% | ~75% of Full Kelly |
| 波动率 | 100% | ~50% of Full Kelly |
| Sharpe 比率 | 基准 | 更高 |
| 破产风险 | 较高 | 显著降低 |

> "If you bet half the Kelly amount, you get about three-quarters of the return with half the volatility. So it is much more comfortable to trade."
> -- 来源：oldschoolvalue.com, 引述 Edward Thorp

**为什么不用 Full Kelly：**
- Full Kelly 假设你对概率的估计完全准确 —— 实际中不可能
- Full Kelly 的回撤可以非常剧烈，心理上难以承受
- Triple Kelly（3倍 Kelly）在模拟中导致几乎确定的破产（来源：Frontiers in Applied Mathematics, 2020）
- Half Kelly 在高波动和负回报期间表现最好（同上）

### 实操建议（$50K-$200K 资金）

- 用 Half-Kelly 或 Quarter-Kelly
- 永远不要因为"有信心"就增加到 Full Kelly
- 如果 Kelly 算出来是负数 → **不做这笔交易**
- 对自己的概率估计保持保守（"宁可少赚，不可多亏"）

---

## 二、仓位规则

### 单仓风险上限

| 规则 | 百分比 | 适用人群 | 来源 |
|------|--------|---------|------|
| **1% 规则** | 每笔交易最大亏损 = 账户总值的 1% | 专业交易员标准 | chartguys.com, bullsonwallstreet.com |
| **2% 规则** | 每笔交易最大亏损 = 账户总值的 2% | 经验丰富的交易员 | chartguys.com |
| **0.5-1%** | 新手建议 | 初学者 | journalplus.co, LinkedIn (Van Tharp) |

**注意：这是"风险"不是"仓位大小"。**

以 $100,000 账户、1% 风险为例：
- 最大亏损 = $1,000
- 如果止损距离是 $5/股 → 仓位 = 200 股
- 如果止损距离是 $2/股 → 仓位 = 500 股

```
仓位大小 = 风险金额 / 每股风险（入场价 - 止损价）
```

> 来源：chartguys.com, adventuresofgreg.com, journalplus.co

### 总风险上限（Portfolio Heat）

| 热度等级 | 百分比 | 评估 | 来源 |
|---------|--------|------|------|
| **保守** | 1-3% | 大多数市况安全 | journalplus.co |
| **适中** | 3-6% | 非相关持仓可接受 | journalplus.co |
| **激进** | 6-10% | 相关市场危险 | journalplus.co |
| **极端** | 10%+ | 威胁账户安全 | journalplus.co |

**6% 规则**（来源：chartguys.com）：
- 总 portfolio heat 不超过 6%
- 1% 风险/笔 → 最多 6 个持仓
- 2% 风险/笔 → 最多 3 个持仓

**专业标准**：大多数职业交易员将 portfolio heat 控制在 3-6%（来源：journalplus.co）

```
Portfolio Heat = (所有持仓风险之和 / 账户总值) × 100
```

### 机构标准参考

- 对冲基金普遍使用持仓集中度限制和行业集中度限制（来源：thehedgefundjournal.com）
- 不使用持仓和行业集中度限制被认为是"灾难等待发生"（同上）
- 55% 的对冲基金用 VaR 分析个别持仓风险，69% 用 VaR 分析组合风险（同上）
- 单一名义集中度如果达到总组合的 10%，一次冲击就影响至少 10% 的组合（来源：moodys.com）

### 做多 + 做空组合管理

- 多头和空头分别计算 portfolio heat
- 对冲仓位可以部分抵消风险，但在极端市况下相关性可能剧变
- 统计套利基金经验：如果 30 个持仓中 15 个相关性超过 0.70，应减仓 40-50%（来源：breakingalpha.io）

---

## 三、止损方法对比

### 三种主流方法

| 方法 | 原理 | 优点 | 缺点 | 来源 |
|------|------|------|------|------|
| **固定百分比** | 入场价下跌 X% 止损 | 简单直接 | 不考虑波动性，容易被震出 | tradefundrr.com |
| **ATR 倍数** | 止损 = 入场价 - N × ATR | 自动适应波动性 | 隐含正态分布假设 | breakingalpha.io, tradefundrr.com |
| **支撑位/技术位** | 在关键支撑位下方止损 | 符合市场结构 | 主观判断，可能被市场假突破利用 | tradefundrr.com |

### ATR 倍数详细参考

| 市况 | ATR 倍数 | 示例（ATR=10时止损距离） | 来源 |
|------|---------|------------------------|------|
| 低波动 | 1.5x | 15 点 | tradefundrr.com |
| 中波动 | 2x | 20 点 | tradefundrr.com, goatfundedtrader.com |
| 高波动 | 3x | 30 点 | tradefundrr.com |

> "常见操作规则使用 2 倍 ATR 给交易呼吸空间，同时维持可预测的亏损上限。"
> -- 来源：goatfundedtrader.com

### 数据支撑哪种更好？

- **ATR 优于固定百分比**：固定止损不考虑市场波动，在高波动期被频繁触发，在低波动期保护不够（来源：blog.traderspost.io）
- **百分位法优于 ATR**：ATR 隐含正态分布假设，但实际价格分布有肥尾和偏态。百分位方法捕捉实际分布特征，在尾部风险主导的策略中更准确（来源：breakingalpha.io）
- **自适应止损最优**：机构使用分类模型（随机森林等）动态调整 ATR 倍数，在高相关高波动环境用 2.8x ATR，低相关低波动用 1.6x ATR，Sharpe 比率提升 8-15%（来源：breakingalpha.io）

**实操推荐（不用机器学习的简化版）：**
- 默认用 **2x ATR (14日)**
- 结合技术支撑位做微调
- 不要把止损设在明显的整数位或常见支撑位正好的位置

---

## 四、VaR（Value at Risk）

### 是什么

"在 X% 置信度下，未来 N 天内最大可能亏损是多少"

**举例**（来源：thefinanalytics.com）：
- 1日 VaR = $10,000 @ 99% 置信度
- 意思是：99% 的概率下，一天内亏损不超过 $10,000
- 一年约 252 个交易日，1% 意味着约 2-3 天可能超过这个数

### 三种计算方法

| 方法 | 复杂度 | 优点 | 缺点 | 来源 |
|------|--------|------|------|------|
| **方差-协方差法** | 低 | 只需均值和标准差 | 假设正态分布 | quantstart.com, agiboo.com |
| **历史模拟法** | 中 | 不假设分布形态 | 依赖历史数据 | investopedia.com |
| **蒙特卡洛模拟** | 高 | 最灵活 | 计算量大 | agiboo.com |

### 简化计算（方差-协方差法）

```
日 VaR (95%) ≈ 组合价值 × 日标准差 × 1.65
日 VaR (99%) ≈ 组合价值 × 日标准差 × 2.33
```

### 局限性（重要！）

1. **不告诉你超过 VaR 时会亏多少** —— 只知道阈值在哪，不知道最坏有多坏（来源：thefinanalytics.com）
2. **正态分布假设低估极端事件**（黑天鹅）（来源：investopedia.com）
3. **低波动期的数据会低估未来风险**（来源：investopedia.com）
4. **不满足次可加性**（非一致性风险度量）—— 两个组合的 VaR 之和可能小于合并后的 VaR（来源：thefinanalytics.com）
5. **补救方法**：Expected Shortfall (CVaR) —— 计算超过 VaR 阈值后的平均亏损，弥补 VaR 的尾部盲区

### 实操建议

- VaR 适合做"日常体检"，不适合做"极端情况的保险"
- 搭配 Expected Shortfall 使用
- 对我们 $50K-$200K 的规模，用简化的历史模拟法足够

---

## 五、R-Multiple 和期望值

### R-Multiple 是什么

R = 每笔交易的初始风险金额。所有交易结果都用 R 的倍数来表达。

> 概念由 Dr. Van K. Tharp（《Trade Your Way to Financial Freedom》作者）提出

**举例**（来源：trademetria.com）：
- 买入 $50，止损 $48，风险（1R）= $2
- 卖出 $56，盈利 $6
- R-multiple = $6 / $2 = **+3R**（赚了 3 倍风险）

- 做空 $120，止损 $123，风险（1R）= $3
- 被止损出局，亏损 $3
- R-multiple = -$3 / $3 = **-1R**

### 期望值（Expectancy）

```
期望值 (R) = 胜率 × 平均盈利R + (1 - 胜率) × 平均亏损R
```

> 来源：pnlledger.com

**举例**（来源：LinkedIn, Van Tharp 方法）：
- 胜率 40%，平均盈利 +2R，平均亏损 -1R
- 期望值 = 0.4 × 2 + 0.6 × (-1) = 0.8 - 0.6 = **+0.2R**
- 意思是每笔交易平均赚 0.2 倍风险

### 怎么用来评估交易系统

1. **记录至少 30-50 笔交易的 R-multiple**
2. **计算期望值**：正数 = 系统有效，负数 = 系统亏钱
3. **关注分布**：如果亏损经常超过 -1R，说明止损纪律有问题
4. **系统比较**：

> "我的日内通道交易期望值约 0.20R，但一天可以做 30-50 笔；波段交易期望值超过 3.00R，但频率低得多。"
> -- 来源：elitetrader.com (RTharp)

5. **总收益 = 期望值 × 交易频率**

### R-Multiple 的核心价值

- **标准化**：不同品种、不同仓位的交易可以直接比较（来源：pnlledger.com）
- **纪律**：如果经常出现 > -1R 的亏损，说明没有执行止损（来源：thetraderisk.com）
- **去情绪化**：关注 R 而非金额，减少心理偏差（来源：trademetria.com）

---

## 六、压力测试简化版

### 怎么做（不需要复杂模型）

**步骤**（来源：luxalgo.com）：

1. **创建场景**：
   - 历史崩盘重演（2008金融危机、2020新冠、2022加息）
   - 假设性挑战（VIX > 40、流动性枯竭、单日暴跌 10%）
   - 极端罕见事件（黑天鹅）

2. **测试指标**：
   - 最大回撤：亏多少、持续多久？
   - VaR 和 Expected Shortfall
   - 是否触发 margin call？

3. **调整参数**：

| 参数类型 | 正常设置 | 压力测试设置 | 目的 |
|---------|---------|-------------|------|
| 波动率带 | 14日 ATR | 50日 ATR | 检测加大的波动 |
| 动量阈值 | RSI 70/30 | RSI 80/20 | 评估极端条件 |
| 均线 | 标准周期 | 15 & 200 日测试 | 识别趋势失败 |

> 来源：luxalgo.com

### 简化压力测试（适合我们规模）

**手动操作法：**

1. 列出所有持仓，假设每个持仓同时亏损到止损位
   - 这就是你的 portfolio heat —— 能承受吗？

2. 假设止损被击穿，滑点导致实际亏损 = 2× 止损距离
   - 还能承受吗？

3. 查找历史上相关品种的最大单日跌幅
   - 把这个数字应用到你的持仓上

4. **相关性检查**：
   - 如果你的多头仓位都是科技股 → 它们会一起跌
   - 检查你的持仓在 2020.03 或 2022.09 会怎样

5. **流动性检查**：
   - 你的持仓能否在 1 天内平仓？
   - 小盘股在恐慌时流动性可能消失

### 关键经验（来源：breakingalpha.io）

- **组合层面的相关性监控比个别持仓止损更重要**
- 2008 年教训：用个别持仓止损的统计套利基金持续亏损；用组合相关性监控的基金在 2007 年就减仓了
- 如果你的持仓开始同向运动（相关性升高），先减仓再说

---

## 七、推荐：最简可行的风控规则集

### 适用于 $50K-$200K 账户，可同时管理做多和做空

#### 入场前规则

| # | 规则 | 具体标准 | 来源 |
|---|------|---------|------|
| 1 | **单仓风险上限** | 每笔交易最大亏损 ≤ 账户总值的 **1%** | chartguys.com, bullsonwallstreet.com |
| 2 | **仓位计算公式** | 仓位大小 = 风险金额 / (入场价 - 止损价) | chartguys.com |
| 3 | **止损方法** | 默认 **2x ATR(14)** 设止损，参考技术支撑/阻力位微调 | tradefundrr.com, goatfundedtrader.com |
| 4 | **Kelly 校验** | 对高信心交易用 Half-Kelly 校验仓位是否合理 | proficient-project.eu |

#### 组合管理规则

| # | 规则 | 具体标准 | 来源 |
|---|------|---------|------|
| 5 | **Portfolio Heat 上限** | 所有持仓总风险 ≤ **6%** | chartguys.com, journalplus.co |
| 6 | **实际目标** | 保守期 3%，正常期 5%，最大不超过 6% | journalplus.co |
| 7 | **单一行业/板块** | 同一板块的持仓不超过总风险的 **50%** | thehedgefundjournal.com (对冲基金最佳实践) |
| 8 | **做多/做空分开算** | 多头 heat 和空头 heat 分别追踪 | — |

#### 持仓中规则

| # | 规则 | 具体标准 | 来源 |
|---|------|---------|------|
| 9 | **止损必须执行** | 被止损 = -1R，不移动止损让亏损扩大 | thetraderisk.com |
| 10 | **相关性警报** | 如果多数持仓开始同向运动，主动减仓 30-50% | breakingalpha.io |
| 11 | **每周压力测试** | "如果所有止损同时触发，我亏多少？" 答案必须 ≤ 6% | journalplus.co |

#### 记录规则

| # | 规则 | 具体标准 | 来源 |
|---|------|---------|------|
| 12 | **记录 R-multiple** | 每笔平仓交易记录实际 R-multiple | pnlledger.com, trademetria.com |
| 13 | **月度期望值** | 每月计算系统期望值，正数才继续 | pnlledger.com |
| 14 | **亏损超 -1R 审查** | 如果出现 > -1R 的亏损，复盘为什么止损没执行 | thetraderisk.com |

---

### 速查卡（$100,000 账户示例）

```
单仓最大风险：$1,000 (1%)
Portfolio Heat 上限：$6,000 (6%)
目标持仓数：3-6 个（每个 1% 风险）
止损方法：2x ATR(14)

买入某股 $50
→ ATR(14) = $3
→ 止损 = $50 - $6 = $44
→ 每股风险 = $6
→ 仓位 = $1,000 / $6 = 166 股
→ 仓位金额 = 166 × $50 = $8,300 (占账户 8.3%)
→ 最大亏损 = $1,000 (占账户 1%) ✓
```

---

## 信息来源汇总

| 来源 | URL | 主要贡献 |
|------|-----|---------|
| ChartGuys | chartguys.com/articles/position-sizing | 1%/2% 规则、6% portfolio heat |
| JournalPlus | journalplus.co/tools/portfolio-heat-calculator | Portfolio heat 等级标准 |
| BullsOnWallStreet | bullsonwallstreet.com | 1% 规则实战 |
| AdventuresOfGreg | adventuresofgreg.com/blog | 仓位计算三种方法、60%贡献研究 |
| OldSchoolValue | oldschoolvalue.com | Kelly + Half-Kelly 投资应用 |
| Frontiers in Applied Math | frontiersin.org (2020论文) | Half-Kelly vs Full Kelly 实证 |
| AstutInvestorsCalculus | astuteinvestorscalculus.com | Kelly 实操案例 |
| Proficient Project | proficient-project.eu | Half/Quarter Kelly 波动率数据 |
| QuantStart | quantstart.com | VaR 方差-协方差法 |
| Investopedia | investopedia.com/terms/v/var | VaR 局限性 |
| TheFinAnalytics | thefinanalytics.com | VaR 完整框架+局限分析 |
| QuantInsti | blog.quantinsti.com/value-at-risk | VaR 实操 |
| P&L Ledger | pnlledger.com | R-multiple + 期望值公式 |
| Trademetria | trademetria.com/blog | R-multiple 案例 |
| TheTradeRisk | thetraderisk.com | R-multiple 纪律 |
| EliteTrader (RTharp) | elitetrader.com | 期望值 + 频率实战 |
| BreakingAlpha | breakingalpha.io | ATR止损、相关性监控、自适应止损 |
| GoatFundedTrader | goatfundedtrader.com | 2x ATR 标准 |
| TradeFundrr | tradefundrr.com | ATR 倍数表 |
| TradersPost | blog.traderspost.io | ATR vs 固定止损比较 |
| LuxAlgo | luxalgo.com | 压力测试方法 |
| HedgeFundJournal | thehedgefundjournal.com | 对冲基金风控最佳实践 |
| Moody's | moodys.com | 名义集中度风险 |
