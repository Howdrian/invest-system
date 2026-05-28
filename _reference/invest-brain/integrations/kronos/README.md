# Kronos Integration

## 定位

这是 `投研` 系统的 Kronos 可选量化预测 challenger。它的作用是把 K 线基础模型的方向性输出放到一份独立证据里，供后续人工/红队审查。

它不是信息源，不是行情源，不是评分器，也不是交易信号。

## 外部项目

- 上游代码：[`shiyu-coder/Kronos`](https://github.com/shiyu-coder/Kronos)
- 上游定位：金融 K-line / candlestick foundation model
- 模型族：`NeoQuasar/Kronos-mini`、`NeoQuasar/Kronos-small` 等 Hugging Face 模型
- 许可证：MIT（以当前上游仓库为准）

本项目当前不 vendor Kronos 上游代码；真实模型运行需要本机提供 `KRONOS_REPO_DIR` 或 `--kronos-repo`。
当前已验证：上游 repo 可缓存到 `research/cache/kronos_repo`，依赖可装到 `research/cache/kronos_env`，公开 Hugging Face 模型不需要 HF API token。

## 边界

不得：

- 写 `state/portfolio.md`
- 写 `trades/trade-log.md`
- 改 `agents/scoring-card.md`
- 改 `agents/red-team-protocol.md`
- 把 Kronos 输出写进 `12_preliminary_deep_review.md`
- 让任何标的因为 Kronos 单独跨过 6.0 分交易门槛

必须：

- 输出独立 `17_kronos_forecast.*`
- `scoring_impact=0`
- `protected_writeback=false`
- 标注数据源、模型版本、checksum 状态、device、amount 是否为 proxy
- smoke 成功后仍只进入 Phase 2 规划；进入评分体系前必须做 walk-forward 验证

## 使用方式

默认只跑安全 smoke：抓取公开 OHLCV、检查依赖、输出 degraded/usable 状态；不下载模型。

```bash
python3 integrations/kronos/cli.py forecast \
  --symbol CCJ \
  --analysis-date 2026-05-18 \
  --lookback 256 \
  --pred-len 20 \
  --model mini
```

输出：

```text
research/archive/YYYY-MM-DD-kronos-smoke/
  17_kronos_forecast.json
  17_kronos_forecast.md
  17_kronos_forecast.html
```

真实模型 smoke 需要：

1. 本机有 Kronos 上游 repo。
2. 安装 `torch`、`huggingface_hub`、`safetensors` 等依赖。
3. 使用 pinned Hugging Face model/tokenizer revision；CLI 内置了已验证的 `mini/small` pinned revision，也可手动覆盖。
4. 显式 `--allow-download`。

```bash
python3 integrations/kronos/cli.py forecast \
  --symbol CCJ \
  --analysis-date 2026-05-18 \
  --allow-download \
  --kronos-repo /path/to/Kronos
```

默认推理参数偏向 smoke 可复现性：`--seed 123 --top-k 1 --top-p 1.0 --sample-count 1`。需要抽样探索时再手动调大 sample 或放开 `top-k`。

2026-05-18 已验证真实 smoke：

- `NeoQuasar/Kronos-mini`
- `NeoQuasar/Kronos-Tokenizer-2k`
- 输出：`research/archive/2026-05-18-kronos-real-smoke-fixed/17_kronos_forecast.json`
- 结果：`status=ok`、`model_available=true`、`scoring_impact=0`、`protected_writeback=false`

## 数据限制

当前 smoke 使用 Yahoo chart public endpoint：

- 美股/ETF日线可用，但不是生产级行情源。
- `amount` 不存在时用 `close * volume` 代理，并强制标注 `amount_missing=true`。
- A股要处理停牌、涨跌停、交易日历。
- 港股要处理港股日历、HKD、南向资金/流动性影响。
- Crypto 要处理 24/7 日线切分。
- 回测前必须处理 raw/adjusted close、split/dividend、缺失 bars。

## Phase 门槛

- Phase 0/1：当前文件夹和 CLI；独立 smoke；2026-05-18 真实 pinned-model smoke 已通过。
- Phase 2：已接入 `run_research_cycle.py --enable-kronos` 可选主流程；默认仍关闭，真实模型运行需加 `--kronos-allow-download`。
- Phase 3：后验监控见 `scripts/kronos_backtest_monitor.py`；只有覆盖多市场、多资产、walk-forward、baseline 对比、无 lookahead 的验证通过后，才讨论是否进入正式评分附注。
