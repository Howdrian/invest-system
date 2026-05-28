# Codex-Native TradingAgents Workflow

## 结论

方案 2 是当前主线：保留本地 `投研` 系统作为本体，把 TradingAgents 的多角色研究流程吸收到 Codex-native 工作流里。TradingAgents 原生 runtime 仍保留为可选 sidecar，但不再作为推进 A/B 的唯一前置条件。

原因很简单：Codex CLI 是 agent 运行环境，不是 TradingAgents 期望的 OpenAI-compatible 模型接口。用 `codex exec` 硬桥接 TradingAgents 属于方案 3，可以实验，但不适合做主线。

## 三种方案

| 方案 | 定位 | 是否需要 API key / 本地模型 | 适合做主线 |
|---|---|---:|---:|
| 方案 1：原生 TradingAgents sidecar | 跑 TradingAgents Python runtime，保存外部报告 | 是 | 否，作为可选证据源 |
| 方案 2：Codex-native 吸收 | 用 Codex 执行本地投研流程，吸收 TradingAgents 的角色结构 | 否 | 是 |
| 方案 3：Codex exec 桥 | TradingAgents 每次模型调用都转给 `codex exec` | 否，但接口脆弱 | 否，只能 spike |

## 方案 2 的本体边界

保留：

- `agents/red-team-protocol.md`
- `agents/scoring-card.md`
- `frameworks/`
- `state/portfolio.md`
- `state/market-pulse.md`
- `state/watchlist.md`
- `trades/trade-log.md`

吸收：

- analyst role separation
- bull-vs-bear debate
- risk manager review
- portfolio manager synthesis
- complete report artifact
- structured decision log

不做：

- 不建第二套 portfolio
- 不建第二套 0-10 评分
- 不把 TradingAgents rating 映射成本地分数
- 不让 A/B 流程写 protected state
- 不为了接入而复制 TradingAgents 源码进主目录

## A/B 口径

A 组：原本地 `invest-brain` 流程。

B 组：Codex-native TradingAgents-inspired 流程。B 组必须引用本样本里的：

- `codex_native_plan.json`
- `codex_native_prompt.md`

最终判断仍走 `ab_test.py` 的质量门：

- 10 个指定样本
- 全部 `status: final`
- B 组平均分比 A 组高至少 8 分
- 至少 7/10 有明确增量信息
- B 组明显事实错误不超过 2 个
- 不绕过 `<6.0 = 不操作`
- protected 文件审计干净

## 命令

初始化 10 个 Codex-native A/B 样本：

```bash
python3 integrations/tradingagents/codex_native.py init-pool --analysis-date 2026-05-05
```

或通过批量入口：

```bash
python3 integrations/tradingagents/batch.py init-codex-native --analysis-date 2026-05-05
```

使用 Codex-native 口径跑最终审计：

```bash
python3 integrations/tradingagents/completion_audit.py \
  --analysis-date 2026-05-05 \
  --evidence-mode codex-native \
  --json-out research/archive/2026-05-05-abtest-aggregate/completion_audit.json \
  --md-out research/archive/2026-05-05-abtest-aggregate/completion_audit.md
```

## 什么时候还用原生 sidecar

只有当我们想验证 TradingAgents 原生 runtime 是否能稳定提供额外证据时，才需要方案 1。那时要么配置 cloud provider API key，要么本机安装 Ollama 模型。

原生 sidecar 的输出只能进入证据池，不能成为本地状态源。
