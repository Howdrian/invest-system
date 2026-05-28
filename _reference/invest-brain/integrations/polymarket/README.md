# Polymarket Integration

## 定位

这是 `投研` 系统的 Polymarket 只读预测市场信号层。它负责把外部市场隐含概率、流动性、价差和近期成交整理成 `Prediction Market Signal`，供现有 invest-brain 做宏观/地缘概率校准。

它不是交易 bot，不接钱包，不下单，不写 portfolio，不写 trade-log。

## 使用方式

```bash
python3 integrations/polymarket/cli.py scan \
  --analysis-date 2026-05-10 \
  --topic polymarket-signal \
  --keywords iran hormuz ukraine taiwan china fed fomc "interest rates" "rate cut" "fed funds" oil "crude oil" nuclear \
  --update-pulse
```

输出：

```text
research/archive/YYYY-MM-DD-polymarket-signal/
  prediction_market_signal.json
  prediction_market_signal.md
  summary.md
```

可选更新：

```text
state/prediction-market-pulse.md
```

这个 state 文件只是外部概率摘要，不是交易状态。

## A/B 测试入口

用于比较：

- A：旧流程，不使用预测市场信号
- B：加入 Polymarket 外部概率、价差、流动性、成交和质量分

```bash
python3 integrations/polymarket/ab_test.py run \
  --analysis-date 2026-05-10 \
  --topic polymarket-abtest-v2 \
  --keywords iran hormuz ukraine taiwan china fed fomc "interest rates" "rate cut" "fed funds" recession oil "crude oil" nuclear
```

输出：

```text
research/archive/YYYY-MM-DD-polymarket-abtest-v2/
  prediction_market_signal.json
  prediction_market_signal.md
  a_old_flow.md
  b_with_polymarket.md
  ab_grading.json
  ab_grading.md
  protected_audit.json
  summary.md
```

A/B 结论只证明“报告质量、证据增量、纪律性、可审计性”是否改善；不直接证明预测准确率更高。预测准确率要等事件结算后做 Brier score / log loss 回测。

## 融合规则

- 高质量市场：可作为外部概率校准，初始权重 20%-30%。
- 中质量市场：低权重参考，通常 10%-15%。
- 低质量市场：只观察情绪，不进入概率融合。

预测市场信号只能影响：

- scenario probability
- catalyst clarity
- red-team trigger
- confidence note

不得：

- 单独触发买卖
- 单独让评分跨过 6.0
- 写入 `state/portfolio.md` 或 `trades/trade-log.md`

## 代码边界

- `client.py`：Gamma/CLOB/Data API 只读客户端
- `normalize.py`：原始 event/market 转标准信号
- `scoring.py` 功能目前在 `normalize.py` 内，以后可拆出
- `fusion.py`：线性融合与 log-odds 融合
- `report.py`：markdown 输出
- `cli.py`：扫描入口
- `ab_test.py`：报告质量 A/B 测试入口
