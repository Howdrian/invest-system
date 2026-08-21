# Reports Agent SOP / Prompt 边界

> Last verified: 2026-08-12
> 目标：让部门 Agent 像投研部门，不像角色扮演；让 Reader 只展示结论、依据、反证和下一步。

## 运行链路

```text
Daily Universe
→ Evidence Pool
→ Department Context Pack
→ LLM Department Agents
→ Atomic Claim Semantic Gate
→ Risk / RedTeam
→ CIO Scenario Adjudication
→ ReaderV3 / Diagnostics
```

硬边界：

- Agent 不直接抓数、不读本地文件、不改持仓。
- Agent 只读分配给自己的 Context Pack。
- Agent 必须引用 evidence id；引用不存在则失败或 fallback。
- evidence id 存在仍不够：主体、指标、时间、来源等级和结论语义必须匹配。
- 搜索、新闻、Tavily、GDELT、研报观点只能作为 discovery/opinion。
- 最终默认 Reader 只读 CIO + 分部门摘要 + 证据样例。
- MacroAgent 不得用长期国债收益率与政策利率比较来判断收益率曲线；必须使用 10Y-2Y、10Y-3M 等可比国债期限。
- 单点数据不能支撑“历史低位/高位/分位”结论；无历史分布 evidence 时，相关比较结论会被语义门剔除并写入 Diagnostics。
- 因果、机制、未来路径默认属于 hypothesis；没有直接证据时必须改成“如果/待验证情景”，不能伪装成事实。
- 原系统 LLM 分析、外部研报和搜索摘要都是 opinion/discovery 输入，不是 verified fact。

## Prompt 分层

每个 Agent 都有岗位边界。不是每个 Agent 都做人设。

| Agent | Prompt 强度 | 输入边界 |
|---|---|---|
| CIOAgent | 深度 SOP | 部门结论、红队、风险、核心 evidence、source health 摘要 |
| RedTeamAgent | 深度 SOP | 部门摘要、风险输出、核心 evidence |
| RiskAgent | 深度 SOP | 部门摘要、风险 evidence、decision signals |
| FundamentalAgent | 深度 SOP | 财务、估值、SEC/CNINFO/HKEX/SSE/SZSE、公告 |
| MacroAgent | 深度 SOP | FRED、利率、通胀、信用、流动性、能源 |
| GeoPolicyAgent | 深度 SOP | GDELT、Tavily、ReliefWeb、制裁、冲突、贸易政策 |
| MarketAgent | 轻量岗位卡 | 本轮已覆盖市场的指数、市场宽度、资金面、市场统计；不强求不存在的三地同构数据 |
| SectorAgent | 轻量岗位卡 | 行业、风格、热点、候选池 |
| TechnicalAgent | 轻量岗位卡 | K 线、趋势、量价、指标 |
| IntelAgent | 轻量岗位卡 | 公告、新闻、搜索线索、催化剂 |
| PortfolioAgent | 轻量岗位卡 | 持仓、自选、组合暴露；已确认空仓与持仓快照未知必须分开 |

## 女娲使用边界

可用：

- 离线打磨 CIO / RedTeam / Risk / Fundamental / Macro / GeoPolicy 的岗位 SOP。
- 提炼角色职责、分析框架、禁止事项、质量检查表。
- 做 prompt 质量复核。

不可用：

- 不参与运行时事实判断。
- 不生成 verified fact。
- 不替代数据源。
- 不直接写投资结论。

## 输入与输出收口

- 共享规则只保留证据等级、时点、因果、universe 和真实缺口 6 类硬约束。
- 部门 Prompt 只追加本部门的分析方法，不再重复 provider、原报告摘录和全量上下文。
- 岗位 `avoid`、部门分析规则、输出合同各自只出现一次；system prompt 只负责角色和输出入口，不再复述证据政策。
- 原系统 LLM 结论以紧凑 opinion 输入给相关部门；Risk / RedTeam / CIO 只读部门结论和关键 evidence，不重读原报告。
- 运行时要求单一 JSON object，用 backend 的 JSON mode 约束。
- Markdown 解析只作历史产物/兼容 fallback，不是新 Prompt 的双轨输出合同。

必须包含：

```text
结论
依据
引用 evidence id
反证
待确认项
下一步
置信度
```

待确认项规则：

- 没有会改变结论的缺口，就写空数组或“无”。
- 不允许为了模板完整硬写“数据缺口”。
- 单个 provider 失败但同域已有 verified/derived evidence，只能写“待确认/需补强”，不能写“无法分析”。
- “无 / 暂无 / 无关键缺口”不会进入 Reader 的待确认项统计。
- 已确认持仓为 0 是业务状态，不是数据缺口；只有持仓快照未接入才记待确认项。
- 市场部门只比较已有市场级证据的市场。只有个股样本时明确为样本，不要求 Agent 虚构对应市场宽度。
- 当前估值可以展示；“历史低/高位”必须有本地历史分位或同业基准，至少 20 个日度样本前不输出历史分位。

CIO 的下一步必须覆盖：

```text
不做什么
看什么
下次复核什么
```

如果 CIO 未完整给出，Reader 会从 CIO 待确认项、Risk 和 RedTeam 的触发条件补齐，但不会展示工程修复术语。

## Reader 规则

ReaderV3 固定展示：

1. 今日总判断
2. 核心理由
3. 下一步
4. 报告主线：市场、宏观与地缘、行业/风格、候选、重点个股、持仓、风险、数据可信度
5. 分部门摘要
6. 证据与可信度

默认 Reader 禁止显示：

```text
ReportArtifact
sourceHealthV2
providerMatrix
RAW_AGENT
DERIVED_FROM_ARTIFACT
claimPolicy
artifactId
errorType
fallbackTo
recordCount
runMatrix
evidence_ledger
provider_runs
```

这些只进 Diagnostics。

## 正反观点裁决

RedTeam 不是把正方结论机械取反。它必须指出：替代解释、证据薄弱点、失效条件和遗漏风险。

CIO 必须输出：

1. 正反双方共同确认的事实；
2. 当前基准情景；
3. 最强替代情景；
4. 为什么暂时采用基准情景；
5. 哪些可观测触发器会推翻判断。

Reader 只展示通过 semantic gate 的事实；推断统一条件化。SourceHealth 高不等于结论高确定性。

## 验收

- 11 个 LLM Agent success。
- fallback = 0。
- 每个部门有结论、依据、反证、下一步、evidence id。
- RedTeam 有反证。
- CIO 不写空泛“中性/可用”。
- Reader 默认页工程字段扫描 = 0。
- 无关键缺口时，Reader 不把普通待确认项当主阻断。
