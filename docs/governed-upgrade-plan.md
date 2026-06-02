# Governed 系统升级计划

> 最后更新: 2026-05-31
> Document status: PROPOSAL（路线图/实施建议，不是当前已落地事实；以代码、测试和 AGENTS.md 为准）
> 文档定位: invest-system 从「能跑」到「好用」的完整路线图
> 当前执行状态: 2026-05-31 已完成代码级落地；FMP 真实刷新、真实持仓数量计算、14天后效果对比仍依赖外部输入/时间窗口。

---

## 零、系统定位（宪法级）

三个系统各有角色，不互相替代：

```
投研本体 (invest-brain)     → 决策宪法 + 研究能力源
                               提供: 宏观框架、source health、红蓝协议、评分门控、
                                     CIO规则、深评队列、反讨好防火墙
                               不提供: 产品底座

invest-system              → 产品底座
                               提供: Web/API/Desktop、数据源管理、持仓账本、
                                     警报中心、回测引擎、GitHub Actions、通知推送
                               吸收: 投研的规则和能力

TradingAgents              → Agent 设计教科书
                               借鉴: 并行分析师、多轮互驳、工具专用化、prompt 结构
                               不采用: LangGraph/MongoDB/Redis/数据源/UI
```

**核心原则: 只有一个产品底座、一个组合账本、一个治理门控。其他都是 adapter、reference 或 sidecar。**

---

## 一、目标架构

```
invest-system 产品底座
  │
  ├─ ContextPack 层（统一输入契约）
  │   ├─ 股票层（每只不同: 行情/技术面/新闻/公告/基本面）
  │   ├─ 宏观层（全局共享: 利率/CPI/GDP/WTI/Regime/地缘概率）
  │   └─ 元数据（每个字段自带 source/as_of/status/fallback）
  │
  ├─ 情报发现层（每天一次）
  │   └─ 热榜/板块/事件 → "今日重点关注"
  │
  ├─ Agent 分析师层（并行、独立）
  │   ├─ Technical Analyst（技术面）
  │   ├─ Intel Analyst（新闻/事件/催化剂）
  │   ├─ Risk Analyst（风险事件评估）
  │   └─ Macro Analyst（全局背景，跑一次注入全体）
  │
  ├─ Governance 治理层
  │   ├─ RedBlue 两轮互驳（蓝3→红3→蓝反驳→红反驳→仲裁）
  │   ├─ Scoring 5维评分（< 6.0 = 不操作）
  │   ├─ CIO 投资判断（方向+仓位+条件+止损）
  │   └─ 硬门控 + 反讨好防火墙
  │
  └─ Evaluation 评估层
      ├─ Governed 结果落库（5维分数+红蓝裁决+CIO判断）
      └─ 14天后自动回测（方向正确率/收益/止损触发）
```

---

## 二、Phase 0: 验证底座（30 分钟）

**目标**: 确认 governed 模式真的在跑

做什么:
- 修改 `.env` 确保 `AGENT_MODE=true AGENT_ARCH=multi AGENT_ORCHESTRATOR_MODE=governed`
- 跑一只股票（如 600519 茅台）
- 确认 governed Agent 链路完整: Macro / Technical / Intel / Risk / RedBlue / Scoring / CIO / Decision
- 确认 governed 结果 ≠ standard 结果
- 确认结果写入数据库

验收标准:
- [ ] governed Agent 全部执行成功，每个有 Token 耗时记录
- [ ] governed 评分 ≠ standard 模式评分
- [ ] 数据库中有完整分析记录

---

## 三、Phase 1: 宏观复活 + CIO 升级（4-6 小时）

**目标**: Agent 不再「瞎着」看宏观，CIO 输出可用的投资判断

### 3.1 宏观数据通路

做什么:
1. 注册 FMP_API_KEY（免费，https://site.financialmodelingprep.com）
2. 从投研移植 `source_cache.py` → `invest-system/src/core/`
3. 从投研移植 `official_sources_scan.py` → 每天跑，拉 Treasury/BLS 数据
4. 从投研移植 `official_extensions_scan.py` → 每天跑，拉 BEA/EIA/FRED 数据
5. 移植 `macro_regime_refresh.py` + `market_regime_strategy.py` 核心逻辑

涉及文件:
- 新增: `src/macro/source_cache.py`
- 新增: `src/macro/official_sources.py`（合并 official_sources_scan + official_extensions_scan）
- 新增: `src/macro/macro_analyst.py`（Macro Analyst Agent，跑一次全员共享）
- 修改: `.env` 加 `FMP_API_KEY`

验收标准:
- [ ] `regime-report.md` 从 DEGRADED → REFRESHED
- [ ] 每天盘前自动拉取利率/CPI/WTI/Regime 数据
- [ ] Macro Analyst 产出结构化 macro_context

### 3.2 CIO 规则重写（砍掉过度禁令）

**当前问题**: CIO 被设计成「流程管理员」，不允许给买卖建议、不允许提仓位、不允许说分数。实际上系统没有交易执行能力，这些禁令在防一个不存在的东西。

做什么:
- 改 `CioAgent` 的 `CIO_RULES` 字符串
- 改输出 JSON schema，增加 `investment_thesis` 字段
- 保留四条真正边界，砍掉多余禁令

改前 vs 改后:

```
改前 CIO 输出:
  Status: READY_FOR_REVIEW
  下一步: 用户审查

改后 CIO 输出:
  综合评分: 6.5/10 — 可考虑小仓试探

  方向判断: 谨慎看多（中等确信）
  核心理由:
    看多 — 盈利改善趋势确立，估值低于行业均值
    风险 — RSI 偏高，短期可能回调

  仓位建议: 2-5%（评分 6.0-7.0 档位）

  入场参考:
    观察区间: 回踩 XX 支撑位后
    止损参考: 跌破 XX（约 -8%）

  什么条件会改变判断:
    - 若季报不及预期 → 重新评估
    - 若突破 XX 阻力位 → 上调目标

  ⚠️ 以上为系统分析意见，非交易指令。最终决策由你做出。
```

保留的四条边界:
- Scoring < 6.0 = 仓位 0%（硬门控）
- 红队致命反对 → 必须说明为什么仍建议操作
- 不输出具体下单指令（「市价买入 1000 股」）
- 每一条结论标注「分析意见，非交易指令」

涉及文件:
- 修改: `src/agent/agents/governance/cio_agent.py`（CIO_RULES + system_prompt + JSON schema）

验收标准:
- [ ] CIO 输出包含 direction / confidence / core_reasoning / what_would_change
- [ ] CIO 引用了 Scoring 的 5 维分数
- [ ] CIO 引用了评分卡的仓位建议表
- [ ] < 6.0 时仓位强制 0%
- [ ] 每条结论带 disclaimer

---

## 四、Phase 2: 情报发现 + 持仓上下文（3-4 小时）

**目标**: 系统主动告诉你「今天该关注什么」，CIO 能看到持仓

### 4.1 情报发现层

做什么:
1. 从投研移植 `market_heat_scan.py` → A 股/美股热榜（成交额/涨跌/换手）
2. IntelAgent prompt 增强：加入催化剂发现、行业链条逻辑
3. 每天输出「今日关注摘要」: 热门板块、异动个股、事件窗口

涉及文件:
- 新增: `src/intel/market_heat.py`
- 修改: `src/agent/agents/intel_agent.py`（prompt 增强）
- 修改: `.github/workflows/00-daily-analysis.yml`（加 market_heat 步骤）

验收标准:
- [ ] 每天输出一份板块热度 + 异动列表
- [ ] IntelAgent 能引用催化剂和行业链条信息

### 4.2 持仓上下文注入 CIO

做什么:
- 在 `_run_governed_analysis()` 中，拉取当前持仓数据
- 注入到 CIO 的 `build_user_message()` 中

涉及文件:
- 修改: `src/core/pipeline.py`（`_run_governed_analysis` 中加持仓查询）
- 修改: `src/agent/agents/governance/cio_agent.py`（`build_user_message` 中接收持仓数据）

验收标准:
- [ ] CIO 能看到当前持仓、成本、浮盈亏
- [ ] CIO 能判断「已有 15% 仓位，不建议再加」

---

## 五、Phase 3: Agent 架构升级（3-4 小时）

**目标**: 吸收 TradingAgents 的并行设计 + 多轮辩论

### 5.1 分析师并行

做什么:
- Technical / Intel / Risk 从顺序执行改为并行（ThreadPoolExecutor, max_workers=3）
- 各自独立拉数据、写报告，不互相对看（消除锚定偏误）
- 顺序链从 74 秒 → ~35 秒

涉及文件:
- 修改: `src/agent/orchestrator.py`（`_build_agent_chain` + `run_agent_chain`）

验收标准:
- [ ] Technical/Intel/Risk 并行执行
- [ ] 任意 Agent 看不到其他 Agent 的输出（验证: 日志中无交叉引用）
- [ ] 单只总耗时下降 30%+

### 5.2 RedBlue 两轮互驳

做什么:
- 从一轮 3v3 → 两轮互驳
- 蓝队 3 论点 → 红队 3 攻击 → 蓝队反驳 → 红队反驳 → 仲裁

涉及文件:
- 修改: `src/agent/agents/governance/red_blue_agent.py`（system_prompt + 执行逻辑）

验收标准:
- [ ] RedBlue 输出中包含反驳回合
- [ ] 辩论深度显著提升（验证: 人工对比一轮 vs 两轮输出）

### 5.3 提示词升级

做什么:
- 参照 TradingAgents 的 Market Analyst，给每个 Agent 的工具加 Usage + Tips
- 例如: "RSI: 70/30 为超买/超卖阈值。注意：强趋势中 RSI 可能持续极端，此时不要单独依赖 RSI"

涉及文件:
- 修改: `src/agent/agents/technical_agent.py`
- 修改: `src/agent/agents/intel_agent.py`
- 修改: `src/agent/agents/risk_agent.py`

验收标准:
- [ ] 每个工具函数有对应的 Usage + Tips 描述

---

## 六、Phase 4: 回测闭环（需积累 14 天数据后）

**目标**: 验证 governed 评分是否比 standard 评分更准

做什么:
1. Governed 结果落库：5 维分数、RedBlue 裁决、CIO 判断、Decision 输出
2. 14 天后自动回测：方向正确率、模拟收益、止损触发率
3. 对比 governed vs standard 的准确率差异

涉及文件:
- 修改: `src/core/pipeline.py`（governed 结果落库）
- 修改: `src/core/backtest_engine.py`（读取 governed 评分）
- 新增: `src/services/governed_backtest.py`

验收标准:
- [ ] 每只股票每次 governed 分析完整落库
- [ ] 14 天后可查询「当时说 BLOCKED，实际跌了没有」
- [ ] governed 准确率 > standard 准确率（预期）

---

## 七、Phase 5: 深度增强（未来，不在此次计划内）

| 模块 | 何时做 | 理由 |
|------|--------|------|
| 候选筛选 / deep review 队列 | 自选/代表池超过少量 smoke 标的，或需要日常机会发现时 | 26 只代表池不应每次全量跑 governed；应先由热榜、公告、研报、事件、技术形态和宏观状态缩小到 3-6 个深评候选 |
| 机构研报注入 | Phase 4 之后 | 有价值但不阻塞主流程 |
| 商品/期权/Kronos | 你做这些品种时 | 目前不做 |
| source_health_dashboard | Phase 1 宏稳后 | 数据源稳定后再监控 |

> 2026-06-01 口径修正：`STOCK_LIST` 在 GitHub / invest-system 里只是“实际分析范围”的静态配置，不等同于投研系统里的“当前最值得深评池”。龙头/ETF 应保留为代表池或观察宇宙；日常 governed 深度分析应优先跑经过筛选漏斗触发的少数候选，避免把覆盖池误用成交易审查池。

---

## 八、明确不做的

| 不做什么 | 理由 |
|---------|------|
| 移植 68 个投研脚本全部 | 产品和数据层已有 invest-system 替代 |
| 换 TradingAgents 底座 | LangGraph/MongoDB/Redis 太重，且无 A 股 |
| 复制第二套持仓账本 | 只能有一个 live portfolio |
| 复制第二套 dashboard | invest-system Web 已有 |
| 移植 39 个测试脚本 | 在新系统里重写，不搬旧的 |
| 保留旧 standard mode 回测代表 governed 质量 | 两个评分体系完全不同 |
| 不允许 CIO 给买卖建议 | 系统没有交易执行能力，禁令在防不存在的事 |

---

## 九、检查清单

- [x] P0: Governed 8 Agent 链路已在代码中接通（Macro / Technical / Intel / Risk / RedBlue / Scoring / CIO / Decision）
- [x] P0: 真实 LLM 跑一只股票并确认每个 Agent 的 Token/耗时记录（2026-06-01 已用 600519 smoke）
- [x] P1: Regime-report 从 DEGRADED → REFRESHED（2026-06-01 已用 FMP key 在线刷新）
- [x] P1: Macro Analyst 产出结构化 macro_context（无 key 时 fail-open 为 DEGRADED）
- [x] P1: CIO 输出包含 direction/score/sizing/conditions/disclaimer，并保留 <6.0 强制 0% 门控
- [x] P2: 每日热榜 + 关注摘要入口已接入（live 热榜失败时降级为 watchlist 摘要）
- [x] P2: CIO 能看到持仓上下文（数量计算仍需要真实账户权益/现金/当前价）
- [x] P3: Technical / Intel / Risk 分析师并行执行
- [x] P3: RedBlue 两轮互驳
- [x] P3: Technical / Intel / Risk 增加 Usage + Tips
- [x] P4: Governed 结果落库 + 回测读取 CIO trade_plan action
- [ ] P4: 14 天后验证 governed 准确率 > standard 准确率（需要自然积累或历史样本）
- [ ] 每只股票 < 2 分钟（2026-06-01 真实 smoke 约 5 分钟，暂未达标）
- [ ] 26 只全量 < 30 分钟（不再作为默认目标；全量代表池应先筛选再深跑）
