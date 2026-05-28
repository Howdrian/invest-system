# Catalyst Intelligence Layer

> 目的：先发现市场正在交易什么，再决定哪些标的需要重评。它不是交易信号，不绕过红蓝对抗和 `<6.0 = 不操作`。

## 核心顺序

```text
近期/未来事件发现
  -> 事件分类
  -> 行业/产业链/龙头映射
  -> watchlist thesis 匹配
  -> 是否触发重评
  -> 技术/基本面/红蓝/评分
```

## 每日必须覆盖

1. **近期已发生事件**：过去 24-72 小时新闻、政策、公司公告、卖方动作。
2. **近期将发生事件**：未来 3-14 天财报、宏观数据、政策会议、产业大会、访问/谈判、OPEC/Fed/监管节点。
3. **行业/产业链映射**：事件不能只归到单 ticker，要映射到 sector、chain、leader、watchlist。
4. **龙头股异动解释**：NVDA、TSM、ASML、腾讯、宁德时代、紫金矿业等龙头大幅变动时，必须解释原因，不能只看 RSI。
5. **A 股增强扫描**：A 股行业板块和龙头单独成章，权重高于普通海外扩展观察池。
6. **漏报审计**：如果龙头 5 日大涨/大跌，但此前没有事件触发，记录 missed catalyst。

## 事件分类

| 类别 | 示例 | 影响对象 |
|---|---|---|
| macro_liquidity | Fed、CPI、PPI、NFP、美元、实际利率 | SPY/QQQ/TLT/黄金/A股风险偏好 |
| geopolitics_policy | 中美、台海、关税、出口管制、制裁 | 半导体、港股、A股科技、黄金、军工 |
| ai_semiconductor | H200/B200/Rubin、出口许可、capex、Computex/GTC | NVDA/TSM/ASML/SMH/中芯/寒武纪/海光 |
| china_policy | 政策刺激、地产、消费、资本市场改革 | A股指数、券商、消费、新能源、互联网 |
| commodities_energy | OPEC、EIA、铜、金、铀、油、天然气 | GLD/USO/XLE/COPX/URA/资源股 |
| sector_rotation | ETF flow、breadth、强弱行业轮动 | 行业板块/龙头 |
| company_specific | 财报、订单、产品、管理层、事故 | 单标的 |
| analyst_expectations | upgrade/downgrade、target raise、estimate revision | 估值重定价 |

## 评分门

每个事件打 0-15 分：

- 市场影响 0-3
- 行业影响 0-3
- watchlist 相关性 0-3
- 时间紧迫性 0-3
- 来源质量 0-3

阈值：

- `>=10`：触发重评
- `7-9`：重点观察
- `<7`：记录但不行动

## A 股增强规则

A 股不是附录，单独输出：

- 指数/宽基：沪深300、中证500、创业板、科创50代理
- 行业：AI/半导体、新能源车/电池、黄金/有色、券商、消费、医药、军工、电力设备、地产链、机器人/自动化
- 个股：只作为候选，不直接买入；必须再跑完整分析和红蓝对抗。

## 禁止事项

- 不得把新闻当买入信号。
- 不得因 RSI 过热直接压掉 thesis-changing catalyst；必须重评。
- 不得写入 `state/portfolio.md` 或 `trades/trade-log.md`。
- 不得用低质量传闻提升评分。
