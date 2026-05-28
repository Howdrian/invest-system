# TradingView Integration Plan

## 定位

TradingView 当前只作为“人工图表 + 云端 alert + webhook 信号输入”。不要把 TradingView 当作官方免费行情 API。

官方可用能力：

- Alerts
- Webhook URL
- Pine Script alertcondition / alert()

官方边界：

- Webhook 是 TradingView 在 alert 触发后向外部 URL 发送 HTTP POST。
- Alert message 如果是合法 JSON，会按 `application/json` 发出。
- Webhook 需要 HTTPS 更稳；只接受 80/443 端口；接收端超过 3 秒会被取消。
- TradingView 的公开 REST 文档主要是 Broker Integration，不等于个人会员可直接拉全市场行情的消费者 API。

边界：

- Webhook 只接收 alert，不自动交易。
- Alert 进入系统后只触发 `REVIEW`，仍需红蓝对抗和 `<6.0 = 不操作`。
- 如果没有 webhook endpoint，就先人工查看 TradingView alert log，并把关键信号告诉系统。

## 建议 Alert JSON

```json
{
  "source": "tradingview",
  "symbol": "{{ticker}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "price": "{{close}}",
  "time": "{{time}}",
  "signal": "breakout_or_reversal",
  "strategy": "manual_or_pine_name",
  "note": "why this alert matters"
}
```

## 建议先设置的 Alert 类别

- A股/港股/美股龙头突破 20D high / 52W high
- RSI 从超卖区回升
- 放量突破
- 关键均线重新站上
- NVDA/SMH/AI链条、A股 AI 芯片、光模块、新能源、黄金有色、券商板块代理

## 后续可做

- 本地 webhook receiver：接收 TradingView POST，写入 `research/archive/YYYY-MM-DD-tradingview-alerts/`。
- 与 `run_research_cycle.py` 聚合：TradingView alert 只作为额外触发源。
