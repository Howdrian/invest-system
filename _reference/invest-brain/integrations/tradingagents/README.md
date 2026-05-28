# TradingAgents Integration

## 定位

这是 `投研` 系统的 TradingAgents 只读接入层。它的职责是把 TradingAgents 跑出来的外部报告归档、抽取成结构化证词，并交给本地 `invest-brain` 做红蓝对抗和评分。

它不是新的投研本体，也不是第二套 portfolio 系统。

当前有两条路线：

- 主线：`codex-native`。不调用 TradingAgents runtime，而是把它的多角色研究结构吸收到本地 Codex / invest-brain 流程里。
- 可选证据源：`sidecar`。真实运行 TradingAgents Python runtime，保存外部报告，再交给本地红队攻击。

`codex-native` 不需要额外 API key 或本地模型服务；`sidecar` 需要 TradingAgents 可调用的 LLM provider，或本机已安装模型的 Ollama。

## 不可越权

本目录内代码不得写入：

- `state/portfolio.md`
- `state/market-pulse.md`
- `state/watchlist.md`
- `trades/trade-log.md`
- `agents/`
- `frameworks/`
- `AGENTS.md`
- `skill.md`
- `memory.md`

TradingAgents 的 `Buy / Overweight / Hold / Underweight / Sell` 只能作为外部观点，不得映射成本地 `0-10` 评分。

## 输出目录

所有接入产出统一写入：

```text
research/archive/YYYY-MM-DD-tradingagents-<ticker>/
```

标准文件：

```text
research_plan.md
tradingagents_complete_report.md
tradingagents_full_state.json
tradingagents_extract.json
tradingagents_metadata.json
local_challenge.md
summary.md
```

`local_challenge.md` 由 `run_sidecar.py` 在生成 `tradingagents_extract.json` 后自动创建，是本地红蓝对抗的入口文件。

## 使用方式

### Codex-native 主线

初始化 10 个 Codex-native A/B 样本：

```bash
python3 integrations/tradingagents/codex_native.py init-pool --analysis-date 2026-05-05
```

也可以走批量入口：

```bash
python3 integrations/tradingagents/batch.py init-codex-native --analysis-date 2026-05-05
```

该命令会在每个 A/B 样本目录内生成：

```text
codex_native_plan.json
codex_native_prompt.md
```

B 组最终正文必须引用这两个文件，证明它使用的是吸收 TradingAgents 架构后的本地流程，而不是普通旧流程。

Codex-native 完成度审计：

```bash
python3 integrations/tradingagents/completion_audit.py \
  --analysis-date 2026-05-05 \
  --evidence-mode codex-native \
  --json-out research/archive/2026-05-05-abtest-aggregate/completion_audit.json \
  --md-out research/archive/2026-05-05-abtest-aggregate/completion_audit.md
```

更多边界见 `codex_native_workflow.md`。

用 Yahoo Finance/yfinance 市场快照填充 10 个 A/B 样本：

```bash
integrations/tradingagents/.cache/venv/bin/python \
  integrations/tradingagents/run_codex_native_ab.py \
  --analysis-date 2026-05-05
```

该脚本会写入每个样本的 `market_snapshot.json`、`a_old_flow.md`、`b_with_tradingagents.md`、`ab_grading.json`、`grading.md`、`summary.md`。它只写研究归档目录，不写 protected state。

### 批量执行入口

先生成批量计划，确认所有输出路径：

```bash
python3 integrations/tradingagents/batch.py plan \
  --analysis-date 2026-05-05 \
  --out research/archive/2026-05-05-abtest-aggregate/batch_plan.json
```

初始化 10 个 A/B 样本：

```bash
python3 integrations/tradingagents/batch.py init-ab --analysis-date 2026-05-05
```

有模型入口后，批量执行 10 个 sidecar：

```bash
python3 integrations/tradingagents/batch.py run-sidecars \
  --analysis-date 2026-05-05 \
  --llm-provider openai \
  --analysts market news fundamentals
```

批量入口仍然调用 `run_sidecar.py`，不会绕开只读边界。

### 0. 试跑前检查

```bash
python3 integrations/tradingagents/doctor.py
```

只有 `Ready for real sidecar run: true` 时，才进入真实 `--execute`。
如果不是 true，看 `Readiness Blockers` 和 `Next Actions`，它会明确是缺 provider key、缺 Ollama 模型，还是边界检查失败。

`doctor.py` 和 `run_sidecar.py` 会读取以下 `.env` 文件，只检查 key 是否存在，不打印 key 值：

```text
.env
integrations/tradingagents/.env
integrations/tradingagents/.cache/upstream/TradingAgents/.env
```

如果 TradingAgents package 不存在，先准备隔离环境：

```bash
python3 integrations/tradingagents/setup_env.py
```

隔离环境放在 `integrations/tradingagents/.cache/`，该目录不进入 git。
安装完成后，也可以直接用隔离 Python 运行：

```bash
integrations/tradingagents/.cache/venv/bin/python integrations/tradingagents/doctor.py
```

### 1. 只创建安全输出骨架

```bash
python3 integrations/tradingagents/run_sidecar.py \
  --ticker NVDA \
  --analysis-date 2026-05-05 \
  --dry-run
```

### 2. 导入一份已有 TradingAgents 报告

```bash
python3 integrations/tradingagents/run_sidecar.py \
  --ticker NVDA \
  --analysis-date 2026-05-05 \
  --from-report /path/to/complete_report.md
```

该命令会同时生成 `tradingagents_extract.json` 和 `local_challenge.md`。

### 3. 抽取已有报告

```bash
python3 integrations/tradingagents/parse_report.py \
  --ticker NVDA \
  --analysis-date 2026-05-05 \
  --report /path/to/tradingagents_complete_report.md \
  --out /path/to/tradingagents_extract.json
```

### 4. 生成本地红队挑战模板

```bash
python3 integrations/tradingagents/generate_challenge.py \
  --extract /path/to/tradingagents_extract.json \
  --out /path/to/local_challenge.md
```

### 5. 真实执行 TradingAgents

真实执行需要外部 `tradingagents` Python 包和对应 LLM API key。默认不执行真实运行，必须显式传入 `--execute`。

```bash
python3 integrations/tradingagents/run_sidecar.py \
  --ticker NVDA \
  --analysis-date 2026-05-05 \
  --execute \
  --llm-provider openai \
  --analysts market news fundamentals
```

真实执行仍只允许写入本次研究归档目录和 adapter cache。

使用本机 Ollama 时必须显式指定模型，脚本会检查本地是否已经安装：

```bash
python3 integrations/tradingagents/run_sidecar.py \
  --ticker NVDA \
  --analysis-date 2026-05-05 \
  --execute \
  --llm-provider ollama \
  --quick-model qwen3:latest \
  --deep-model qwen3:latest
```

### 6. 初始化 A/B 测试样本

```bash
python3 integrations/tradingagents/ab_test.py init-pool --analysis-date 2026-05-05
```

A/B 前后记录 protected 文件快照：

```bash
python3 integrations/tradingagents/ab_test.py snapshot-protected \
  --out research/archive/2026-05-05-abtest-aggregate/protected_before.json

python3 integrations/tradingagents/ab_test.py snapshot-protected \
  --out research/archive/2026-05-05-abtest-aggregate/protected_after.json

python3 integrations/tradingagents/ab_test.py audit-protected \
  --before research/archive/2026-05-05-abtest-aggregate/protected_before.json \
  --after research/archive/2026-05-05-abtest-aggregate/protected_after.json \
  --out research/archive/2026-05-05-abtest-aggregate/protected_audit.json
```

填完每个样本的 `ab_grading.json` 后，重新渲染：

```bash
python3 integrations/tradingagents/ab_test.py render \
  --grading-json research/archive/2026-05-05-abtest-nvda/ab_grading.json
```

只有已经审核完成的样本才能把 `status` 改成 `final`。聚合时只要存在 `draft` 样本，就不能 PASS。
聚合还会检查是否覆盖第一轮样本池的 10 个指定标的，不能用重复标的凑数。
最终完成度审计会拒绝仍含 `TODO` / 模板占位的 A/B 正文，也会要求 final 样本写清 `b_added` 和 `gate_check`。
B 组正文必须明确引用本标的 `tradingagents_extract.json` 和 `local_challenge.md`，否则不能证明新流程真的用了 sidecar 证据。

聚合 10 个样本：

```bash
python3 integrations/tradingagents/ab_test.py aggregate \
  --grading-json research/archive/2026-05-05-abtest-*/ab_grading.json \
  --protected-audit-json research/archive/2026-05-05-abtest-aggregate/protected_audit.json \
  --out research/archive/2026-05-05-abtest-aggregate/summary.md
```

最终完成度审计：

```bash
python3 integrations/tradingagents/completion_audit.py \
  --analysis-date 2026-05-05 \
  --evidence-mode sidecar \
  --json-out research/archive/2026-05-05-abtest-aggregate/completion_audit.json \
  --md-out research/archive/2026-05-05-abtest-aggregate/completion_audit.md
```

只有 `overall_passed: true` 时，才说明接入、真实 sidecar、A/B、protected 审计全部达标。

## 后续接入点

`tradingagents_extract.json` 是给本地红队使用的证词池。本地流程必须重新核对事实、走红蓝对抗、走 `scoring-card`，再决定是否更新真实状态。
