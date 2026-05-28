# 免费数据源升级审计

最后更新：2026-05-25

## 结论

免费源可以显著补强现有系统，但必须分层使用：

- **可直接默认只读探测**：SEC Atom、GlobeNewswire RSS、CFTC COT。
- **可接但需用户 key/token**：EIA、Tradier、Alpha Vantage、Finnhub、Tushare。
- **可接但需本机安装包**：AKShare、efinance、BaoStock、edgartools。
- **不应自动化**：Cboe delayed quote table scraping 等条款风险源。

## 质量分层

| 层级 | 来源 | 质量判断 | 默认用途 |
|---|---|---|---|
| 官方公开 | SEC Atom、CFTC COT | 高 | 快讯/持仓官方证据 |
| 官方免费key | EIA | 高 | 能源库存/产量/天然气/PADD |
| 开源聚合包 | AKShare、efinance、BaoStock | 中-高 | A股深度和回测，需交叉验证 |
| 官方/准官方金融API | Tradier、Alpha Vantage、Finnhub | 中-高 | 期权链、新闻、基本面补充，受key/限速影响 |
| 条款阻断 | Cboe delayed page scraping | 不进入 | 记录风险，不自动抓取 |

## 当前落地

- 注册表：`config/free-data-source-registry.json`
- 探针：`scripts/free_data_source_probe.py`
- 研究周期输出：`05c_free_source_upgrade.md`
- 源健康组件：`free_source_upgrade`

## 验收口径

`free_data_source_probe.py` 的状态含义：

- `ready`：当前可读，可进入后续 adapter 评估。
- `needs_key`：用户提供免费 key/token 后再启用，不阻断日报。
- `needs_install`：本机未安装包；不自动安装，避免污染环境。
- `degraded`：当前连通或解析失败，需要修复/降级。
- `blocked_by_terms`：不进入默认自动化。

## 接入边界

- 不写 `state/portfolio.md`。
- 不写 `trades/trade-log.md`。
- 不改变 `agents/scoring-card.md` 和 `agents/red-team-protocol.md`。
- 不把免费聚合源当官方事实；交易前必须交叉验证。
- 期权只生成候选证据，不自动下单。

## 参考来源

- AKShare 文档：https://akshare.akfamily.xyz/
- edgartools：https://www.edgartools.io/
- EIA API v2：https://www.eia.gov/opendata/documentation.php
- CFTC COT Public Reporting：https://publicreporting.cftc.gov/stories/s/r4w3-av2u
- Tradier options chain：https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains
- Alpha Vantage docs：https://www.alphavantage.co/documentation/
- Finnhub docs：https://finnhub.io/docs/api
