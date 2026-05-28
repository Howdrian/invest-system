# 组合构建框架

> 方法论来源：Bridgewater (Dalio)、AQR、Vanguard (2024)、NBER、Intech
> 适配 invest-brain 的组合配置需求
> 覆盖：All Weather、Risk Parity、Holy Grail、相关性管理、再平衡

---

## 使用方式

invest-brain 在检测到组合构建/配置/分散化意图时自动加载本框架。
组合变更进入红蓝对抗（`agents/red-team-protocol.md`）+ 评分（`agents/scoring-card.md`）。

---

## 一、Bridgewater All Weather 四季模型

### 核心框架: 增长 x 通胀 2x2 矩阵

经济环境只有四种状态，每种状态配置相应受益资产，**每个象限承担等量风险（各25%的风险敞口）**：

| | 通胀上升 | 通胀下降 |
|---|---|---|
| **增长上升** | 大宗商品、黄金、通胀保护债券(TIPS)、新兴市场股票 | 股票、公司债、长期国债 |
| **增长下降** | 大宗商品、黄金、通胀挂钩债券 | 名义国债（长期）、零息债券 |

**关键原则**: 不是25%的资金在每个象限，而是25%的**风险**在每个象限。

### 简化版配置（Tony Robbins 版本）

| 权重 | 资产类别 | ETF |
|------|---------|-----|
| 30% | 美国股票 | VTI |
| 40% | 长期国债(20年+) | TLT |
| 15% | 中期国债(3-7年) | IEI |
| 7.5% | 大宗商品 | DBC |
| 7.5% | 黄金 | GLD |

**汇总**: 30%股票 + 55%固定收益 + 15%实物资产

### 历史表现（1996.3 - 2026.2, 30年）

| 指标 | 数值 |
|------|------|
| 年化收益(CAGR) | 7.43% |
| 标准差 | 7.46% |
| 最大回撤 | -20.58% |
| 恢复期 | 42个月 |
| 累计收益 | 759.15% |

> 来源: [LazyPortfolioETF](https://www.lazyportfolioetf.com/allocation/ray-dalio-all-weather/)
> 来源: [Bridgewater - The All Weather Story](https://www.bridgewater.com/research-and-insights/the-all-weather-story)
> 来源: [Optimized Portfolio](https://www.optimizedportfolio.com/all-weather-portfolio/)

---

## 二、Risk Parity 风险平价

### 核心公式: 朴素风险平价（逆波动率加权）

$$w_i = \frac{1/\sigma_i}{\sum_{j=1}^{N} 1/\sigma_j}$$

其中 w_i = 资产i的权重, sigma_i = 资产i的波动率

### 计算示例

**两资产:**
- 资产A波动率 10%, 资产B波动率 20%
- 逆波动率: A = 1/0.10 = 10, B = 1/0.20 = 5
- 权重: A = 10/15 = **66.7%**, B = 5/15 = **33.3%**
- 结果: 两资产对组合的风险贡献相等

**三资产:**
- 波动率分别为 10%, 20%, 30%
- 逆波动率: 10, 5, 3.33 (合计18.33)
- 权重: **54.5%**, **27.3%**, **18.2%**

### 朴素 vs 完全风险平价（ERC）

| 方法 | 年化收益(14年) | 波动率 | 区别 |
|------|---------------|--------|------|
| 朴素风险平价 | 7.16% | 7.33% | 只看波动率，忽略相关性 |
| 等风险贡献(ERC) | 6.93% | 6.12% | 使用完整协方差矩阵，考虑相关性 |

**关键假设**: 朴素风险平价假设所有资产的夏普比率相似。如果夏普比率差异大，应使用完全风险平价。

**ERC的优势**: 波动率更低(6.12% vs 7.33%)，虽然收益略低(6.93% vs 7.16%)，但风险调整后收益更优。

### 完全风险平价公式

边际风险贡献 = (权重向量 x 协方差矩阵) / 组合波动率

目标: 每个资产的风险贡献 = 总风险 / N

> 来源: [QuantPedia - Risk Parity](https://quantpedia.com/risk-parity-asset-allocation/)
> 来源: [QuantInsti - Risk Parity Portfolio](https://blog.quantinsti.com/risk-parity-portfolio/)
> 来源: [Wikipedia - Risk Parity](https://en.wikipedia.org/wiki/Risk_parity)

---

## 三、Holy Grail：15个不相关回报流

### Dalio 原话
> "My mantra of investing is 15 good uncorrelated return streams, risk-balanced... I can keep the same return as any one of those investments with up to an 80% reduction in risk."

### 核心数据: 相关性 vs 风险降低

| 相关性水平 | 资产数量 | 风险降低幅度 |
|-----------|---------|------------|
| 60%相关 | 5个 | 约20% |
| 60%相关 | 1000个 | 仍然只有约15% |
| 10%相关 | 7-8个 | 50%（风险减半） |
| 0%相关 | 15-20个 | **80%** |

### 关键洞察

1. **相关性比数量重要**: 1000只60%相关的股票，分散效果不如5个不相关资产
2. **收益/风险比提升**: 不相关流组合后，收益/风险比提升 **3-5倍**
3. **亏损概率**: 零相关15+资产组合年度亏损概率约 **11%**，而60%相关组合约 **40%**
4. **边际递减**: 超过20个流后，额外分散效果极小
5. **收益/风险比**: 零相关15-20资产组合的收益/风险比约为 **1.25**

### 数学基础

对于N个等权、等波动率、不相关的资产:
- 组合方差 = sigma^2 / N
- 组合标准差 = sigma / sqrt(N)

示例: 单个资产标准差10%, 15个不相关资产:
- 组合标准差 = 10% / sqrt(15) = 10% / 3.87 = **2.58%**
- 风险降低 = (10% - 2.58%) / 10% = **74.2%**（接近80%）

> 来源: [World Top Investors - Dalio's Holy Grail](https://www.worldtopinvestors.com/ray-dalios-holy-grail/)
> 来源: [StatOasis - Holy Grail](https://statoasis.com/post/the-holy-grail-by-ray-dalio)
> 来源: [Macro Ops - Dalio Portfolio Strategy](https://macro-ops.com/ray-dalio-portfolio-allocation-strategy-holy-grail/)
> 来源: [Investors Journal](https://www.investorsjournal.org/post/holy-grail-dalio)

---

## 四、相关性管理

### 危机中相关性飙升的实证数据

| 资产对 | 正常时期 | 危机时期 | 来源 |
|--------|---------|---------|------|
| S&P 500 vs MSCI EAFE | 变化区间 | 1年滚动相关性从 **-0.24 到 +0.96** 波动 | Intech |
| 股票 vs 债券 | 历史上负相关 | 2022年滚动1年相关性升至 **+0.75** | Intech |
| 大宗商品 vs 股票 | 2000年前中位数 **-0.41** | 2000年后中位数 **+0.35**（区间 -0.58 到 +0.95） | Intech |
| 因子间相关性 | 分散 | 1年滚动从 **-0.96 到 +0.90**（1978-2022） | Intech |

### 关键规律

1. **"最需要分散时，分散失效"**: 2008年危机中，原本不相关的资产（股票与信用产品）同向运动
2. **央行政策改变相关性**: 量化宽松将相关性推高，削弱传统分散效果
3. **高通胀环境**: 股债正相关（2022年验证），传统60/40失效
4. **短期相关性剧烈波动**: 配对相关性可在极短时间内从负变正

### 管理策略

1. **动态再平衡**: 非固定配比，根据相关性变化调整
2. **战术对冲**: 危机期间增加尾部风险对冲
3. **另类资产**: 加入管理期货、趋势跟踪等与传统资产低相关的策略
4. **自适应策略**: 使用能"适应短期和长期相关性变化"的策略
5. **压力测试**: 用危机情景（而非正常情景）的相关性矩阵进行组合优化

### 实操规则

- 不要用正常时期相关性做危机模拟
- 资产间相关性是**动态的**，不是固定参数
- 真正的分散来自经济驱动因子的分散（增长/通胀/流动性），不仅是资产类别的分散

> 来源: [Intech - The Correlation Conundrum](https://www.intechinvestments.com/the-correlation-conundrum-how-will-you-fix-portfolio-diversification/)
> 来源: [Swan Global - The Correlation Conundrum](https://www.swanglobalinvestments.com/institutional/the-correlation-conundrum/)
> 来源: [JDACM - Cross-Asset Correlation Shifts in Crisis](https://jdacm.com/index.php/jdacm/article/download/58/47)

---

## 五、再平衡策略：日历 vs 阈值

### 两种方法对比

| 维度 | 日历再平衡 | 阈值再平衡 |
|------|-----------|-----------|
| 触发条件 | 固定日期（月度/季度/年度） | 偏离目标达到阈值时 |
| 优点 | 简单、易执行 | 成本更低、偏离控制更好 |
| 缺点 | 可能不必要交易，或错过急剧偏离 | 需要持续监控 |

### Vanguard 研究数据（2024年12月发布）

**200/175 阈值策略**: 偏离目标200bps时触发，再平衡到距目标175bps（而非完全回到目标）

| 指标 | 阈值(200/175) | 月度日历 | 季度日历 |
|------|--------------|---------|---------|
| 年化交易成本 | ~15bps | ~22bps | 更低但偏离更大 |
| 相比月度再平衡节省 | 7bps/年 | - | - |
| 相比日度再平衡节省 | 15bps/年 | - | - |
| 最大偏离（2020.3） | +/- 2% | 7% | 10% |
| 年化配置偏差改善 vs 月度 | 少43bps | - | - |
| 年化配置偏差改善 vs 季度 | 少135bps | - | - |
| 收益优势 vs 日历（年化） | 5-21bps | - | - |

### 2020年3月压力测试（Vanguard）

- 50/50股债组合在极端波动下:
  - 阈值方法: 偏离始终控制在 **+/- 2%** 以内
  - 月度日历: 偏离高达 **7%**
  - 季度日历: 偏离高达 **10%**

### NBER 研究发现: 再平衡的隐性成本

- 可预测的再平衡交易被市场"前置": 年化成本约 **8bps**，相当于全市场约 **160亿美元**
- 日历再平衡信号每1标准差变化 → 次日股票收益下降 **16-17bps**，债券收益上升 **4bps**

### 综合推荐（12种策略7个周期评估后）

> **至少年度再平衡 + 任何资产类别偏离目标20%时触发**

实操建议:
- 高交易成本/低流动性资产: 用更宽的阈值带
- 高波动率资产: 用更窄的阈值带
- 合理阈值区间: 单资产 +/-5-10%, 组合总偏差 +/-10-20%

> 来源: [Vanguard - Rebalancing Approach](https://workplace.vanguard.com/insights-and-research/perspective/vanguards-approach-to-target-date-fund-rebalancing.html)
> 来源: [Vanguard Research Dec 2024 - The Rebalancing Edge](https://corporate.vanguard.com/content/dam/corp/research/pdf/the_rebalancing_edge_optimizing_target_date_fund_rebalancing_through_threshold_based_strategies.pdf)
> 来源: [NBER - Unintended Consequences of Rebalancing](https://www.nber.org/system/files/working_papers/w33554/w33554.pdf)
> 来源: [CFA Institute - Rebalancing's Hidden Cost](https://blogs.cfainstitute.org/investor/2025/04/10/rebalancings-hidden-cost-how-predictable-trades-cost-pension-funds-billions/)
> 来源: [Resonanz Capital](https://resonanzcapital.com/insights/the-art-and-science-of-portfolio-rebalancing-a-timeless-framework-for-all-market-environments)

---

## 六、组合构建检查清单

1. **确定经济情景框架**: 用增长x通胀2x2矩阵确定需要覆盖的四种经济状态
2. **选择资产类别**: 为每个象限选择受益资产，确保覆盖所有四种状态
3. **风险平价加权**: 用逆波动率公式(w_i = 1/sigma_i / sum)分配权重，而非等额资金
4. **验证不相关性**: 确保组合包含至少15个低相关回报流（相关性<0.3为佳）
5. **压力测试相关性**: 用危机时期（非正常时期）的相关性矩阵重新测试
6. **设定再平衡规则**: 阈值触发(偏离5-10%) + 至少年度检查，避免纯日历方式
7. **监控相关性变化**: 央行政策转向、通胀环境变化时重新评估资产间相关性

---

## 数据可靠性标注

| 数据 | 置信度 | 说明 |
|------|--------|------|
| All Weather 30年回测 7.43% CAGR | 高 | LazyPortfolioETF + Bridgewater官方 |
| Risk Parity公式 | 高 | QuantPedia/Wikipedia/QuantInsti一致 |
| Holy Grail 80%风险降低 | 中高 | Dalio原话+数学推导验证，但完整逐点数据未公开 |
| 危机相关性飙升数据 | 高 | Intech + JDACM学术论文 |
| Vanguard 200/175再平衡 | 高 | Vanguard 2024年12月官方研究 |
| NBER再平衡隐性成本8bps | 高 | NBER Working Paper |
| ERC vs朴素风险平价对比 | 中 | 单一来源(QuantInsti)14年数据 |
