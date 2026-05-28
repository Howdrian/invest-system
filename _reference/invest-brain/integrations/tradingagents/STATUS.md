# TradingAgents Integration Status

## 当前状态

阶段：Phase 1 前置骨架完成；隔离 TradingAgents 运行环境已安装。

2026-05-05 路线修正：方案 2 `codex-native` 作为当前主线。原生 TradingAgents sidecar 保留为可选证据源，但不再是推进 A/B 的唯一前置条件。

已完成：

- 只读 adapter 目录建立
- 安全 schema 和输出路径限制
- TradingAgents 报告 parser
- local challenge 生成器
- A/B 测试 harness
- doctor readiness check
- isolated setup_env installer
- sample fixture
- stdlib unittest 校验
- A/B 测试 rubric
- `.env` provider key 读取支持
- `run_sidecar` 自动生成本地红队 challenge
- Ollama provider 显式模型 preflight
- A/B protected 文件快照与写入审计
- A/B `status: final` 硬门槛
- A/B 指定样本池覆盖硬门槛
- 完成度审计器 `completion_audit.py`
- 批量编排入口 `batch.py`
- A/B 正文占位符完成度审计
- B 组 sidecar 证据引用审计
- provider key 映射集中到 `provider_config.py`
- doctor readiness blockers / next actions
- Codex-native TradingAgents-inspired workflow 文档
- `codex_native.py` A/B 样本初始化入口
- completion audit 支持 `sidecar` / `codex-native` 两种证据模式
- batch 支持 `init-codex-native`

未完成：

- 原生 TradingAgents sidecar 尚未执行真实 run（可选证据源，仍缺 provider key 或本地模型）

Codex-native 主线完成：

- 10 标的 A/B 样本已填充真实市场快照和 A/B 正文
- Codex-native protected after 快照与审计已完成
- Codex-native A/B aggregate 已 PASS
- Codex-native completion audit 已 PASS

## 已验证

本地验证命令：

```bash
python3 -m unittest discover -s integrations/tradingagents -p 'test_*.py'
outdir=research/archive/2099-01-03-test-tradingagents-challenge
mkdir -p "$outdir"
python3 integrations/tradingagents/parse_report.py --ticker NVDA --analysis-date 2026-05-05 --report integrations/tradingagents/fixtures/sample_complete_report.md --out "$outdir/tradingagents_extract.json"
python3 integrations/tradingagents/generate_challenge.py --extract "$outdir/tradingagents_extract.json" --out "$outdir/local_challenge.md"
python3 integrations/tradingagents/run_sidecar.py --ticker TEST --analysis-date 2099-01-02 --dry-run
python3 integrations/tradingagents/ab_test.py init-sample --ticker NVDA --analysis-date 2099-01-05 --force
python3 integrations/tradingagents/ab_test.py aggregate --grading-json research/archive/2099-01-05-abtest-nvda/ab_grading.json --out research/archive/2099-01-05-abtest-aggregate/summary.md
python3 integrations/tradingagents/doctor.py
python3 integrations/tradingagents/setup_env.py --clone-only
python3 integrations/tradingagents/completion_audit.py --analysis-date 2026-05-05 --evidence-mode codex-native
python3 integrations/tradingagents/completion_audit.py --analysis-date 2026-05-05 --evidence-mode sidecar
python3 integrations/tradingagents/batch.py init-codex-native --analysis-date 2099-01-21 --force
```

验证结果：

- unittest：通过
- sample parser：通过
- local challenge generator：通过
- dry-run：通过
- A/B sample init：通过
- A/B aggregate：通过；draft 单样本会按预期判定 `FAIL`，不会误判达标
- setup_env：通过；TradingAgents 已安装到隔离 venv
- doctor：通过；isolated TradingAgents `0.2.4` 可导入，当前 `Ready for real sidecar run: False`
- execute preflight：通过；缺 `OPENAI_API_KEY` 时提前拒绝执行且不创建输出目录
- 临时测试归档已移入废纸篓
- TradingAgents remote HEAD 已核对：`7e9e7b83c7fcc18d941300b253c6ed24d985788d`
- Codex-native sample init：通过；测试归档已移入废纸篓
- Codex-native A/B generation：通过；10 个样本均已生成 `market_snapshot.json`、A/B 正文、final grading
- Codex-native completion audit：通过；当前输出 `overall_passed: true`

## 2026-05-05 继续校验

目标拆解：

| 要求 | 当前证据 | 结论 |
|---|---|---|
| 开始执行接入规划 | `integrations/tradingagents/` 已建立，含 sidecar、parser、challenge、A/B、doctor、setup_env | 已完成 |
| 只读接入 | `schemas.py` 限制输出只在 `research/archive` 和 adapter `.cache`，doctor 显示 protected paths blocked | 已完成 |
| 没有冗余架构 | README 明确 TradingAgents 不是第二套 portfolio，本地红蓝对抗/评分/风控仍是本体 | 已完成 |
| 持续校验 | unittest 当前 30 项通过；doctor 当前边界通过；completion_audit 两种 evidence mode 当前都正确判定未完成 | 已完成到当前阶段 |
| 接入本地红队 challenge | `run_sidecar.py` 现在会在产生 extract 后自动写入 `local_challenge.md` | 已完成到 adapter 层 |
| 真实 TradingAgents sidecar run | 当前缺 provider key，`Ready for real sidecar run: False` | 未完成 |
| 10 标的 A/B 测试 | harness 已通过防误判测试，但真实样本未跑 | 未完成 |
| A/B protected 写入审计 | `ab_test.py` 支持 snapshot/audit；没有 audit 或 protected 文件变化时都不能 PASS | 已完成到 harness 层 |
| A/B 样本定稿状态 | `ab_test.py` 要求所有样本 `status=final` 才可能 PASS | 已完成到 harness 层 |
| A/B 样本池覆盖 | `ab_test.py` 要求覆盖 rubric 中 10 个指定标的，不能重复凑数 | 已完成到 harness 层 |
| 最终完成度审计 | `completion_audit.py` 可按 `sidecar` 检查 10 个真实 sidecar，或按 `codex-native` 检查 10 个 Codex-native artifacts；两者都要求 10 个 final A/B、protected audit、A/B PASS | 已完成到 harness 层 |
| 批量执行编排 | `batch.py` 可生成计划、初始化 10 个 A/B、批量执行 sidecar、写 protected 快照、跑完成审计 | 已完成到 harness 层 |
| A/B 正文完整性 | `completion_audit.py` 会拒绝仍含 `TODO` / 模板占位、缺 `b_added` 或缺 `gate_check` 的 final 样本 | 已完成到 harness 层 |
| B 组证据接入性 | `completion_audit.py` 按 evidence mode 要求 B 组引用 `tradingagents_extract.json` + `local_challenge.md`，或 `codex_native_plan.json` + `codex_native_prompt.md` | 已完成到 harness 层 |
| provider 配置去冗余 | `doctor.py` 和 `run_sidecar.py` 共用 `provider_config.py`，避免 key 清单漂移 | 已完成 |
| readiness 可诊断性 | `doctor.py` 输出机器可读 `readiness_blockers` 和 `next_actions` | 已完成 |
| 证明新流程质量更高 | 需要真实 A/B 聚合 PASS | 未完成 |

最新检查：

- TradingAgents package：隔离 venv 可导入，版本 `0.2.4`
- Provider key：未发现
- Ollama：本机有程序，但当前没有已安装模型
- Unit tests：30 项通过
- completion_audit sidecar：通过；当前状态会正确输出 `overall_passed: false`，缺口为真实 sidecar、A/B 样本、protected audit、A/B PASS
- completion_audit codex-native：通过；当前状态会正确输出 `overall_passed: false`，缺口为 Codex-native A/B artifacts、A/B 样本、protected audit、A/B PASS
- batch run-sidecars preflight：通过；缺 provider key 时输出结构化错误且不创建 sidecar 目录
- A/B placeholder audit：通过；final 样本如果正文仍是模板 TODO 会被 completion_audit 拒绝
- B evidence-link audit：通过；B 组正文如果不引用当前 evidence mode 要求的证据文件，会被 completion_audit 拒绝
- provider config centralization：通过；`doctor.py` 和 `run_sidecar.py` 共用同一 provider key 映射
- doctor readiness blockers：通过；当前明确输出缺 cloud provider key，以及 Ollama 已安装但无模型
- `.env`：doctor/run_sidecar 现在会读取 `.env`、`integrations/tradingagents/.env`、上游 `.env`，但不打印 key 值
- Codex-native 主线：已落地 `codex_native.py`、`codex_native_workflow.md`，可初始化不依赖 provider key 的 B 组样本证据
- completion audit evidence mode：可用 `--evidence-mode sidecar` 保持原生 TradingAgents 口径，或用 `--evidence-mode codex-native` 检查方案 2 口径
- Codex-native A/B 样本池：`research/archive/2026-05-05-abtest-*` 10 个目录已完成，均包含 `codex_native_plan.json`、`codex_native_prompt.md`、`market_snapshot.json`、A/B 正文与 final grading
- Protected snapshot：`research/archive/2026-05-05-abtest-aggregate/protected_before.json` 已生成
- Protected after/audit：`protected_after.json` 与 `protected_audit.json` 已生成；`writeback_violation=false`
- Batch plan：`research/archive/2026-05-05-abtest-aggregate/batch_plan.json` 已生成
- A/B aggregate：`summary.md` 显示 `PASS`，average B-A delta `30.0`，incremental info `10/10`，factual errors `0`，gate bypass `0`
- 当前完成度审计：`research/archive/2026-05-05-abtest-aggregate/completion_audit.json` / `.md` 已写入，结果为完成
- Final goal audit：`research/archive/2026-05-05-abtest-aggregate/final_goal_audit.md` 已写入

## 方案选择

当前建议：

- 主线走方案 2：Codex-native 吸收 TradingAgents 架构。
- 方案 1：原生 TradingAgents sidecar 作为可选外部证据源。
- 方案 3：`codex exec` bridge 暂不进入主线，只能作为 spike。

原因：

- Codex CLI 是 agent 客户端，不是 TradingAgents 可直接调用的聊天模型服务。
- 强行桥接会让运行慢、结构化输出不稳定，并把 agent 行为和模型调用混在一起。
- Codex-native 可以直接复用当前 Codex 能力，同时保留本地红蓝对抗、评分门控和唯一状态源。

## 下一步

1. 若以后要评估原生 TradingAgents runtime，再补 provider key 或 Ollama 模型，走 sidecar 口径。
2. 若要把 Codex-native 流程常态化，可把 `run_codex_native_ab.py` 的角色结构提炼进正式 invest-brain 操作模板。

## 当前阻塞

主线不再被 API key 阻塞；可以用 Codex-native 方式继续推进。

原生 TradingAgents sidecar 仍需要 LLM provider API key 或本机 Ollama 模型。当前 shell 环境中未发现：

- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `ANTHROPIC_API_KEY`
- `XAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `DASHSCOPE_API_KEY`
- `ZHIPU_API_KEY`
- `OPENROUTER_API_KEY`
- `AZURE_OPENAI_API_KEY`

因此目前已完成 adapter、parser、dry-run、fixture 校验、隔离安装；不能完成原生 TradingAgents sidecar run，也不能完成原生 sidecar A/B。

更准确地说：

- 不能完成原生 TradingAgents sidecar A/B。
- 可以继续完成 Codex-native A/B。

## 质量门槛

进入深度合并前必须满足：

- 10 个 A/B 样本中至少 7 个有明确增量信息
- B 组平均分比 A 组高至少 8 分
- 明显事实错误不超过 2/10
- 任何情况下不得绕过本地 `<6.0 不操作`
- 不得写入真实 portfolio / trade-log
