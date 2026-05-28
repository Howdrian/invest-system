# TradingAgents 接入 A/B 测试 Rubric

## 目的

判断 TradingAgents sidecar 是否真实提升 `投研` 系统输出质量。测试通过前，不允许进入深度合并或 runtime 化。

## A/B 定义

- A 组：旧流程，只用本地 `invest-brain` 数据技能、frameworks、红蓝对抗、scoring-card。
- B 组：新流程，在 A 组基础上加入 TradingAgents-derived evidence，再由本地红队攻击和评分。

最终裁判仍然只看本地评分与风控。TradingAgents rating 不直接算分。

当前支持两种 evidence mode：

- `sidecar`：B 组引用同标的 `tradingagents_extract.json` 和 `local_challenge.md`。
- `codex-native`：B 组引用同标的 `codex_native_plan.json` 和 `codex_native_prompt.md`。

2026-05-05 当前主线是 `codex-native`，原生 sidecar 保留为可选证据源。

## 样本池

第一轮 10 个标的：

| 标的 | 类型 | 目的 |
|---|---|---|
| NVDA | 美股个股 | 高关注科技成长股 |
| SPY | 大盘 ETF | broad beta |
| GLD | 黄金 ETF | 避险/宏观 |
| CCJ | 商品类个股 | 铀主线 |
| URA | 商品 ETF | 铀 basket |
| COPX | 商品 ETF | 铜主线 |
| 0700.HK | 港股个股 | 港股质量资产 |
| 1211.HK | 港股个股 | 港股强势制造/新能源 |
| 300750.SZ | A 股个股 | A 股强势成长 |
| 601899.SS | A 股个股 | 黄金/资源股 |

## 评分维度

每个标的对 A/B 两组分别打分，满分 100。

| 维度 | 权重 | 评分问题 |
|---|---:|---|
| 事实可核验性 | 25 | 数字、新闻、财务、技术数据是否能追溯；是否有编造 |
| 风险覆盖 | 20 | 是否识别了真正能改变决策的风险 |
| 催化剂清晰度 | 15 | 是否给出明确时间窗口、触发条件、失效条件 |
| 决策纪律 | 20 | 是否遵守 `<6.0 不操作`、仓位、止损、反 FOMO |
| 增量信息 | 10 | B 组是否提供 A 组没有的新信息 |
| 可操作性 | 10 | entry、stop、sizing、watch trigger 是否具体 |

## 通过标准

B 组必须同时满足：

1. 10 个样本平均分比 A 组高至少 8 分。
2. 至少 7/10 个样本有明确增量信息。
3. 明显事实错误不超过 2/10 个样本。
4. 没有任何一次绕过本地 `<6.0 不操作` 门槛。
5. 没有任何一次写入真实 portfolio 或 trade-log。
6. 10 个样本的 `ab_grading.json` 都必须是 `status: final`。
7. 样本必须覆盖上表 10 个指定标的，不能用重复标的凑数。

## 判定结果

| 结果 | 后续动作 |
|---|---|
| PASS | 进入 Phase 5，吸收 runtime 工程能力 |
| PARTIAL | 保留 sidecar，只在复杂标的或冲突判断时调用 |
| FAIL | 停止主流程接入，仅作为人工参考资料 |

## 记录格式

每个样本写入：

```text
research/archive/YYYY-MM-DD-abtest-<ticker>/
├── a_old_flow.md
├── b_with_tradingagents.md
├── ab_grading.json
├── grading.md
└── summary.md
```

`ab_grading.json` 是机器可读评分源，`grading.md` 由脚本渲染。不要手工维护两套互相矛盾的分数。

样本完成审核后，把 `ab_grading.json` 的 `status` 从 `draft` 改为 `final`。聚合时只要存在 draft 样本，最终 verdict 不能为 PASS。

完成度审计还会检查 A/B 正文和渲染稿是否仍含 `TODO` / 模板占位。`status: final` 只能用于已经填完正文、增量说明和 gate check 的样本。

B 组正文必须明确引用当前 evidence mode 要求的证据文件，否则不能证明它真的使用了 TradingAgents-derived evidence。

`grading.md` 必须写清：

- A 组总分
- B 组总分
- B 组新增了什么
- B 组错了什么
- 是否改变最终操作建议
- 是否仍遵守本地评分门槛

## Protected 写入审计

A/B 开始前后各跑一次 protected snapshot，并生成 `protected_audit.json`。聚合时必须传入该文件；没有 protected audit 时最终 verdict 不能为 PASS。只要检测到 `state/portfolio.md`、`trades/trade-log.md` 等 protected 文件变化，最终 verdict 也不能为 PASS。

```bash
python3 integrations/tradingagents/ab_test.py snapshot-protected --out research/archive/YYYY-MM-DD-abtest-aggregate/protected_before.json
python3 integrations/tradingagents/ab_test.py snapshot-protected --out research/archive/YYYY-MM-DD-abtest-aggregate/protected_after.json
python3 integrations/tradingagents/ab_test.py audit-protected --before research/archive/YYYY-MM-DD-abtest-aggregate/protected_before.json --after research/archive/YYYY-MM-DD-abtest-aggregate/protected_after.json --out research/archive/YYYY-MM-DD-abtest-aggregate/protected_audit.json
```
