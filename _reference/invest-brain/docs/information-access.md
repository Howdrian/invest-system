# Information Access Boundary

## 结论

系统不是“很多信息拿不到”，而是要分清：

1. **免费可稳定自动化**：适合放进每日扫描主流程。
2. **免费但需要专门解析**：可以接，但要单独做脚本和去重。
3. **需要用户授权或 API key**：能接，但不能替用户开通。
4. **付费/闭源/许可限制**：不能假装有完整覆盖，只能用公开线索替代。

## 已经自动化

| 类型 | 当前来源 | 用途 |
|---|---|---|
| 股票/ETF 日线 | Yahoo chart public endpoint；Macro Regime 另有 Nasdaq public historical fallback | 涨跌幅、RSI、均线偏离、量比代理；RSP/SPY/IWM/TLT/SHY/HYG/LQD/XLY/XLP 宏观 ETF 组件 |
| A股/美股热榜 | Eastmoney push2 / Yahoo screener | 成交额、涨跌幅、换手、行业/概念热度 |
| 新闻/催化剂 | GDELT + Google News RSS fallback | 宏观、政策、产业链事件 |
| 公开研报线索 | Google News RSS 中英文查询 | 机构观点、策略展望、白皮书、行业深度 |
| 官方宏观/公告/事实点 | Treasury / NY Fed / BLS / SEC EDGAR / SEC Company Facts | 利率、就业、通胀、美股公告、美股财务事实点 |
| 官方扩展 | BEA / EIA / FRED / FINRA | GDP/PCE、能源价格序列、FINRA short interest；BEA/EIA direct key 可选，FRED fallback 免费跑 |
| 免费源升级探针 | AKShare / efinance / edgartools / SEC Atom / GlobeNewswire / CFTC / EIA / Tradier / Alpha Vantage / Finnhub | 查缺补漏和质量分级；只读，不自动安装，不把需 key 源当已接入 |
| A股公告/政策 | CNINFO + Gov.cn | A股公告、中国政策原文线索 |
| 源健康/观看入口 | `13_source_health.*` + `00_one_screen_brief.html` | 源是否跑通、warning、深评候选一屏查看 |
| 预测市场 | Polymarket Gamma/CLOB/Data | 地缘/宏观概率校准 |
| Crypto | CoinGecko + Binance fallback | 默认 BTC/ETH 风险偏好温度计 |
| 量化模型侧证 | Kronos optional challenger | 不是信息源；只把公开 OHLCV 输入模型后输出独立 `kronos/17_kronos_forecast.*` 供审查 |
| 期权链 | options-long-only lane | 只在 underlying 进入深评或用户指定后扫描 long call/put/protective put 候选；没有稳定链/Greeks 就阻断或降级 |

## 可以接入但还没自动化

| 类型 | 可行来源 | 价值 |
|---|---|---|
| 交易所直连公告 | 上交所、深交所、港交所、Nasdaq/NYSE 公告页 | CNINFO/SEC 已接入；交易所直连可做补充交叉验证 |
| 宏观/能源官方扩展细项 | BEA direct、EIA API、央行/证监会/NDRC 公告 | 主干已通过 `official_extensions_scan.py` 自动化；更细库存、产量、经济日历还可继续扩 |
| 做空/拥挤度扩展 | FINRA 已接入；Nasdaq / 交易所公开页待补 | short interest 已自动化；short volume、borrow rate 仍需扩展 |
| 期权链正式源 | Tradier / Polygon-Massive / Alpaca / IBKR | 已有 probe/scan 脚本；需要用户 key、账号或行情权限后才能稳定输出合约候选 |
| Kronos Phase 2 | 统一周期可选 `--enable-kronos` | 已接可选 lane；真实 pinned-model smoke 已成功；仍不进入评分 |

## 需要用户介入

| 类型 | 为什么 |
|---|---|
| TradingView webhook | 需要用户在 TradingView 里创建 alert，并填系统提供的 webhook URL |
| FMP/Tavily/Finnhub/NewsAPI | 需要用户申请 key 或授权；`FMP_API_KEY` 可让 macro regime 自动刷新，FMP ETF权限不足时会用 Nasdaq public historical fallback |
| BEA/EIA direct key | 免费申请后可提高官方细项覆盖；无 key 时用 FRED fallback |
| Kronos 真实模型运行 | 需要本机 Kronos repo、Python 依赖、Hugging Face 模型下载和 pinned revision；已验证公开 NeoQuasar 模型无需 HF token |
| Broker API / 实盘账户 | 涉及账户、交易和权限，必须由用户授权 |

## 不能稳定免费完整获取

| 类型 | 边界 |
|---|---|
| Wind/iFinD/Choice 全量数据 | 需要付费终端或授权接口 |
| 财联社电报/内参 | 实时速度和完整内容通常需付费 |
| Bloomberg/Reuters/LSEG 终端新闻 | 版权和订阅限制 |
| 完整券商研报库原文 | 多数有登录/版权/付费限制 |
| Level-2 深度行情/逐笔成交 | 交易所许可和行情授权限制 |

## 使用原则

- 免费公开源可以做“发现”和“重评触发”。
- 付费或不完整源不能伪装成完整覆盖。
- 公开研报/新闻只进入证据层，不直接触发交易。
- 所有交易动作仍必须走红蓝对抗、评分门控和仓位风控。
- 缓存层只减少重复请求和弱网耗时；缓存命中不代表数据一定最新，需要时用 `--refresh-cache`。
- Kronos 这类模型输出只能做 challenger；没有样本外验证、baseline 对比、无 lookahead walk-forward 之前，不进入正式评分。

## Kronos 监控

- `scripts/kronos_backtest_monitor.py` 用于 ingest/settle/report：记录预测、等窗口结束后用公开行情后验结算方向命中和误差。
- 该监控不是交易信号，只服务后续 walk-forward / baseline 验证。
