# Kronos Phase 2 / Monitoring Design

## 结论

Kronos 上游有 `examples/run_backtest_kronos.py`，但那只是上游项目的单独回测示例；它没有接入本项目的候选队列、源健康面板、红蓝边界、forecast ledger 和后验监控。

所以本项目采用：**Phase 2 可选 lane + 持续 forecast ledger + 后续 walk-forward 验证**。

## 当前接入位置

```text
统一扫描 / 多源候选
  ↓
11_deep_review_queue.json
  ↓  --enable-kronos
kronos/17_kronos_forecast.*
  ↓
红队/人工重评参考
  ↓
评分卡仍独立控制
```

Kronos 输出只做侧证：

- `scoring_impact=0`
- `protected_writeback=false`
- 不写 `12_preliminary_deep_review.md`
- 不写 `state/portfolio.md`
- 不写 `trades/trade-log.md`

## Phase 2 运行方式

默认不跑 Kronos，避免弱网、模型下载和 CPU 时间拖慢统一周期。

安全侧证 smoke：

```bash
python3 scripts/run_research_cycle.py \
  --topic research-cycle \
  --enable-kronos \
  --kronos-top-n 3
```

真实模型侧证：

```bash
python3 scripts/run_research_cycle.py \
  --topic research-cycle \
  --enable-kronos \
  --kronos-top-n 3 \
  --kronos-allow-download
```

如果本机存在 `research/cache/kronos_env/bin/python` 和 `research/cache/kronos_repo`，统一周期会默认优先用它们。

## 持续监控系统

新增脚本：`scripts/kronos_backtest_monitor.py`

它做三件事：

1. **ingest**：把每次 Kronos 预测写入本地 ledger。
2. **settle**：等预测窗口结束后，用 Yahoo 后验价格结算方向和误差。
3. **report**：输出 HTML/MD/JSON 监控报告。

一键运行：

```bash
python3 scripts/kronos_backtest_monitor.py run \
  --source-dir research/archive/YYYY-MM-DD-research-cycle/kronos \
  --analysis-date YYYY-MM-DD \
  --topic kronos-monitor
```

输出：

- ledger：`research/kronos_monitor/forecast_ledger.jsonl`
- 快照：`research/kronos_monitor/ledger_snapshot.json`
- 报告：`research/archive/YYYY-MM-DD-kronos-monitor/kronos_monitor.md/html/json`

## 它和正式回测的区别

持续监控是“从今天开始的真实前向记录”：

- 优点：不会 lookahead，记录真实模型当时的输出。
- 缺点：样本积累慢。

正式回测 / walk-forward 是“历史切片重跑”：

- 用历史某天以前的数据做输入。
- 预测后面 N 天。
- 和真实未来价格比较。
- 与 baseline 比较。

Kronos 上游已有 backtest 示例，可作为参考；本项目还需要单独做适配，避免数据泄漏。

## 后续进入评分前的门槛

Kronos 进入评分前至少要满足：

1. 样本：跨美股/ETF/A股/港股/商品 proxy，至少 50-100 个预测窗口。
2. Baseline：必须对比随机游走、简单趋势、均线/动量。
3. No lookahead：历史切片不得读取预测日之后的数据。
4. 成本：至少估算交易成本、滑点、调仓频率。
5. 稳定性：按市场、资产、波动率、趋势/震荡状态拆分。
6. 结论：只有明显优于 baseline，才考虑极低权重的 `technical_model_alignment` 附注。

## 当前判断

- 可以进入 Phase 2 可选 lane。
- 可以开始持续监控。
- 还不能进入主评分。
- 还不能触发交易。
