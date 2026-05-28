# Market Regime Strategy Governor

> Role: 主 Agent 的市场状态与策略总控层。  
> Boundary: 只输出“市场环境判断、参与策略、触发条件、风险预算建议”，不输出买卖指令，不替代红蓝对抗和评分卡。

## 为什么需要它

深评队列里的 `OVERHEATED_WAIT_ENTRY` 只说明“当前价格位置不适合追高”，不等于“短期风险偏好偏强时完全空仓”。

主 Agent 必须先判断：

1. **市场环境**：risk-on / risk-off / 轮动震荡 / 结构性强趋势 / 事件风险主导。
2. **主线状态**：主题是否有宏观、产业、公告、研报、资金热度多源共振。
3. **价格位置**：强趋势偏热、正常复核、回撤止跌、证据不足。
4. **观察/预审策略**：ETF/篮子观察、等待承接、轮动补位、弱转强确认、防守等待。
5. **交易闸门**：交易前仍需 evidence pack、红蓝对抗、评分卡、仓位风控和用户确认。

## 输入

- `00_macro_regime.md`
- `08_polymarket.md`
- `09_screening_funnel.json`
- `11_deep_review_queue.json`
- `13_source_health.json`
- 跨资产行情代理：SPY / QQQ / SMH / IWM / GLD / TLT / VIX / 10Y / USD / BTC

## 输出

- `14_market_strategy.json`
- `14_market_strategy.md`
- `14_market_strategy.html`

## Regime 桶

| Regime | 含义 | 默认策略 |
|---|---|---|
| `TACTICAL_RISK_ON` | 短期风险资产强、主线证据强、价格未全线极端 | 可准备观察/预审条件；不能认定结构性牛市 |
| `TACTICAL_RISK_ON_CROWDED` | 短期 risk-on 且主题拥挤/短涨过大 | 不追高，也不机械空仓；只记录承接/轮动观察条件 |
| `ROTATION_RANGE` | 大盘不单边，主题轮动明显 | 不追 broad beta；做相对强弱、回踩和轮动补位 |
| `RISK_OFF_DEFENSIVE` | 风险资产弱、波动/美元/利率压力高 | 防守优先；只看保护性 put、对冲或高确定性止跌 |
| `EVENT_RISK_DOMINANT` | 地缘/政策/Fed 等尾部事件决定方向 | 降低仓位，等待事件确认或用可定义亏损工具 |
| `UNKNOWN_DEGRADED` | 关键数据不可用 | 不给策略结论；先修数据源/补跑 |

## 偏热处理

`OVERHEATED_WAIT_ENTRY` 的正确含义：

- 不是“没机会”；
- 是“不能用普通即时入场策略”；
- 在短期风险偏好偏强时可转为 `PARTICIPATION_WAIT_ENTRY`：
  - ETF/篮子替代；
  - 回踩 5/10/20 日均线不破；
  - 缩量回落后放量转强；
  - 高位横盘 2-5 日不破；
  - 同产业链低位高证据分支补位。

## 硬规则

- `<6.0 = 不操作` 保持不变。
- 主线判断只影响“是否继续准备”和“用什么触发条件”，不直接越过评分卡。
- 数据源 `unavailable` 时不允许给正式策略。
- 地缘/Polymarket 只能校准概率和触发红队，不单独触发买卖。

## 证据边界

- 5日跨资产强弱和主题热度只能支持“短期 risk-on/主题拥挤”，不能单独支持“结构性牛市”。
- 宏观 degraded、数据源 degraded、事件风险 elevated 时，脚本置信度最高只能到 MEDIUM。
- `RISK_OFF_DEFENSIVE` / `EVENT_RISK_DOMINANT` / `UNKNOWN_DEGRADED` 下不得生成主动参与候选，只能观察或情景推演。
