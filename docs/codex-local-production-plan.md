# Mac 本地生产方案：Codex 执行后端，投研流程保持独立

> 状态：本地 Codex 后端及单次日报已验证；2026-09-06 正在上游更新后复验。未安装定时任务、未发布，尚未验收无人值守。
> 核验日期：2026-09-05。
> 当前目录：`/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`。
> 本文保留规划和验收边界；最新执行结果见 CURRENT_STATE.md，不把下方实施前快照当成当前状态。

## 1. 决策与边界

采用“Mac 生产、Codex 分析、本地 Web 交互、Pages 阅读”。不把项目改成一个让 Codex 自主操作所有事情的长 prompt。

- 业务与事实真源仍是原数据服务、Evidence、研究流程和 Artifact；Codex 是可替换的 AI 执行后端。
- Python 负责数据采集、材料分配、断点、校验、发布、通知。模型不修改源码、真实持仓、交易记录或发布权限。
- 复用现有 `GenerationBackend`、`AgentBackend` 和 Codex 实现，不新建通用模型网关、不搭另一个微服务系统。
- GCP/Vertex 和付费 API 不作为本部署自动 fallback；保留代码能力，不删原 provider，不删凭据。Codex 额度不足就保存进度、提醒，不自动购买额度或换账号。
- Hermes 只作为可选控制入口/通知接入，不成为日报必经节点。现有同名本地 OpenAI-compatible 通道不等于已验证的 Hermes 服务或免费模型。
- 保留原交互工作台。日报和个股分析共享数据与模型适配层，不强迫每次个股提问调用全部部门。
- 不以完整度分数代表上线：功能、内容质量、无人值守、公开发布分别验收。

## 2. 本次代码核验发现

| 现有实现 | 核验结论 | 本轮处理 |
|---|---|---|
| `src/llm/local_cli_backend.py` | 已有 codex_cli、临时 cwd、env 过滤、进程超时与最终消息读取 | 复用，核验 CLI 0.144.4 协议及配置隔离 |
| `src/agent/codex_agent_backend.py` / `codex_app_server_transport.py` | 已有实验性 Codex App Server、动态工具、取消/进程管理 | 复用原交互问股，不能假定所有 Agent 架构已兼容 |
| `src/daily_department_llm.py` | 两个默认 backend builder 明确拒绝非 LiteLLM | 打开部门文本生成适配，不经过 Gemini 候选 smoke |
| `.env.example` | 原分析、交互 Chat、部门研究有不同 backend 配置 | 增加一个本地部署示例，启动时打印有效路由而非密钥 |
| `scripts/run_research_daily_local.sh` | 原分析可选、market 默认 cn，日期 shell fallback；含两轮渲染/校验 | 统一日期/市场/当前运行输入；先保留契约必要的收尾，不为了少行数盲删 |
| 部门 resume | 以同日 success 复用，注释要求调用者保证输入未变 | 补输入/模型/prompt/依赖 hash 校验与失效传播 |
| 本机 Codex | `codex-cli 0.144.4`；`codex login status` 为 ChatGPT 登录 | 登录不等于模型请求、剩余额度或无人值守已通过 |
| Hermes | 当前 shell 未找到 hermes 可执行文件 | 安装位置、进程、后端和额度待只读定位，非首轮阻断 |

上一次云端模型修复 PR 不再作为 Codex 本地切换前提。实施前重新查 main/PR/diff，保留有用回归测试，不盲合过时的 Gemini 轮试策略。

## 3. 目标架构

```text
本地定时入口 / Web 手动任务 / 可选 Hermes 命令
  → 同一任务入口、互斥锁、运行记录
  → Daily Universe + 截止时间 + 各市场交易日
  → 原数据源、官方源、搜索源、已有分析缓存
  → Evidence / SourceHealth / 原个股与市场分析
  → 部门 Context Pack
  → 部门分析（Codex CLI）
  → Risk → RedTeam → CIO 初审
  → 可选一轮 Python 只读补数 → CIO 定稿
  → Artifact → ReaderViewModel
      ├─ 本地 Web/API + 私有 Diagnostics
      ├─ 本地私有完整报告
      └─ 公共白名单 Reader 包 → GitHub Pages → 通知

交互问股：
Web/Bot/API → 原会话与工具注册表 → Codex App Server
          → 原数据服务/查询工具 → 回答和引用
```

两种 Codex 入口分工明确：CLI 做有界材料到报告的生成；App Server 承接原交互工具循环。不是两套数据系统，也不是 Python 与 Codex 同时争夺同一工具循环。

## 4. 数据与分析不重复

### 4.1 数据保留

- A/H/US 行情、历史 K 线、技术指标、财务与估值：继续原 DataFetcherManager 能力，不为更换模型重新抓数。
- 公告/法披：CNINFO、SSE/SZSE、HKEX、SEC；宏观 FRED/已有官方源。
- 新闻与地缘：Tavily 多 key、GDELT、ReliefWeb、官方政策/制裁来源按现有配置使用。
- 付费增强保持 optional，源失败定位到域、标的和环节；“调用成功”与“当前标的有足够信息”分开。
- 采集层可以持有源密钥；Codex 只获得必要材料与来源，不获得密钥。

### 4.2 复用与证据等级

- 数值计算/指标是 derived_fact；原系统 AI 分析是 agent_opinion，不能因为来自原系统就升级为确定事实。
- 官方材料只有具体可核实的事实、时间、主体匹配才记 verified_fact；搜索结果、新闻摘要、外部评级不自动升事实。
- 原个股报告保留完整下钻。部门阅读其摘要及底层证据，只有发现增量问题才深入，不重复写一份同义个股报告。
- 同一运行按 symbol、operation、参数、as-of 缓存，采集/原分析/部门/CIO 补数共用。
- Evidence 入池、进入哪个 Context Pack、被谁引用、最后出现在哪个 Reader 段落，均能追踪。

### 4.3 时间与历史

- 统一记录 fetchedAt、publishedAt、eventTime、asOf、交易所时区、marketSession；无法取得的时间明确未知，不用抓取时间冒充事件时间。
- 日报日期与各市场数据日期分开。晨报可以包含前一交易日 A/H 收盘与最新已结束美股交易日，不冒充同一自然日同步实时。
- 宏观/财报按发布频率与滞后判断，不拿秒级行情标准衡量月度数据。
- 历史对比优先使用本地保存的可追溯快照；必要时从原 provider 补历史。修订值保留版本，历史回测不得混入之后公布的信息。
- 无 STOCK_LIST 不默认茅台；当前配置自选、持仓、候选、市场/宏观分组明确。

## 5. Codex 适配与额度

### 5.1 目标路由（实施后才能视为可用）

```dotenv
GENERATION_BACKEND=codex_cli
GENERATION_FALLBACK_BACKEND=
AGENT_BACKEND=codex_app_server
AGENT_GENERATION_BACKEND=codex_cli
RESEARCH_AGENT_RUNTIME=llm
LOCAL_CLI_BACKEND_MAX_CONCURRENCY=1
```

2026-09-05 已解除部门 LiteLLM 硬限制，并接入独立 RESEARCH_GENERATION_BACKEND / RESEARCH_CODEX_MODEL / RESEARCH_CODEX_REASONING_EFFORT。真实工厂走 Codex CLI，绕过 API 模型 smoke。完整日报与无人值守仍须分别验收，不能仅凭配置或 canary 判定完成。

- 复用已有 `GenerationResult`，记录实际 backend、模型、时长、attempt、usage（未知则 null）。不把 requested model 当 actual model。
- 有界 prompt + 最终消息读取；stdout 事件流只作运行日志，不能整个当报告正文。
- 正文允许 Markdown，程序持有结构化运行元信息。解析失败保留原文、最多一次定向修复，不以“有输出”当通过。
- CLI、部门 runner、外层任务采用同一总 deadline，避免内层 300 秒、外层 90 秒互相误杀。
- 成功 exit code 还要校验业务内容；非零、空文、截断、额度不足、登录过期、超时、取消分别处理。

### 5.2 账户、模型和并发

- 复用官方 CLI 的 ChatGPT 登录，不提取 token，不伪造 OpenAI-compatible 订阅代理。
- 本地运行仍发送材料到 OpenAI，不是离线模型；不要承诺零成本、无限额度或 SLA。
- 开始先固定本机账号可调用、短样例内容质量通过的一个模型和推理档位；写入项目运行配置，不硬编码旧模型名，不每天扫描所有候选。
- 默认全机投研 AI 并发 1，真实测试后最多试 2；与开发任务共享 Codex 用量。日报、交互问股和重试共用预算/并发控制。
- 查得到的用量如实记录；无法取得精确剩余额度时明确未知，不按 token 数换算虚构余额。
- 额度不足保存状态，停止无意义重试；不自动充值、兑换 reset、切 GCP 或轮换账户。

### 5.3 权限与外部内容

- 分析进程在独立材料目录执行，不在源码根目录运行通用“帮我完成”任务。
- 使用受控 Codex 配置，核验关闭不需要的用户插件、MCP、hooks、shell/文件工具；read-only sandbox 本身不等于无法读取其他私人文件。
- 补数只由已有 Python 只读工具执行；新闻/公告里的指令只是数据，不能改变岗位职责或触发本地命令。
- 发布器单独持有最小发布凭据；模型看不到 GitHub token、通知 webhook、真实 env、数据库认证。
- 不使用 bypass sandbox/approval 作为无人值守的解决办法。认证文件不进源码、报告包或常规运行归档。

## 6. Agent 职责、SOP 与推理质量

| 部门 | 必要输入 | 应交付内容 |
|---|---|---|
| Macro | 利率、通胀、信用、流动性、政策 | regime 判断、变化、市场传导 |
| GeoPolicy | 冲突、制裁、贸易、官方政策与及时新闻 | 事件→暴露→可能影响，区分确认事实与情景 |
| Market | A/H/US 指数、宽度、资金 | 市场比较，不能把少数股票外推全市场 |
| Sector | 行业/概念、资金、候选 | 强弱结构、催化、持续性与反例 |
| Fundamental | 财报、现金流、估值、公告、原个股摘要 | 盈利驱动、估值依据、关键变化 |
| Technical | K 线、量价、指标 | 趋势、关键区间、失效条件 |
| Intel | 新闻、公告、来源与时间 | 增量事实/线索、与旧消息的区别 |
| Portfolio | 实际持仓快照或明确无持仓 | 有快照则分析暴露；没有则不虚构持仓 |
| Risk | 部门摘要与关键证据 | 风险排序、概率/影响的依据、触发条件 |
| RedTeam | 主论点、部门证据、Risk | 最强替代解释及可区分证据，不强制唱反调 |
| CIO | 部门结论、Risk/RedTeam、关键证据 | 主判断、取舍理由、行动/观察建议、失效条件 |

- 每个岗位有明确边界，不新增人物扮演层。保留已打磨 SOP，只删除重复约束和格式性废话。
- 给可读论证：结论、依据、推导摘要、反证、下一步；不要求披露模型内部逐 token 思考过程。
- 反证是检验主论点，不是必须得出相反结论。CIO 写清采纳哪种解释、为何、什么条件会改变判断。
- 有真实缺口才显示；没有就隐藏。数据不足可以提出有条件的研究建议，不增加“没满血就禁止说话”的通用安全门。
- 无持仓时 Portfolio 可以明确 not_applicable；验收不为凑 11 个调用而要求空部门浪费额度，也不能伪称真实组合分析成功。
- 验收 universe 含 A/H/US 时三市场均有分析或具体缺口。不是按篇幅机械同权，不用一条 A 股结论代表三地市场。

### CIO 一轮补数

仅在关键判断有可补缺口时产生 typed data_requests，Python 调用已注册只读 provider。最多一轮、最多 8 请求、每请求和整体有 deadline。补得的材料进入 Evidence 后再提交 CIO；改变部门结论时只重跑受影响部门及其下游，不全量重来。失败说明剩余影响，不伪造成功。

## 7. 无人值守：一个调度器、一套运行状态

- 默认 Mac 原生 launchd 作为唯一生产调度器；Hermes/Web/手动命令只调用同一任务入口。保留上游 scheduler 功能但生产配置不得双重启动日报。
- 本轮规划不安装定时任务。实施时查已有 scheduler/automations，避免重复。
- 建议首版每日 Asia/Shanghai 08:30 发跨市场晨报；按市场日历说明数据截至日，不称全球实时报告。若后续需要 A/H 收盘刊，在同一 pipeline 增加 edition，不再建第二套系统。
- 生产从固定版本运行；开发 checkout 不用于定时任务。CLI/依赖不在日报开始前自动升级，升级须过 canary。
- 运行锁涵盖手动、Web、Hermes、定时任务；过期锁需要验证进程所有权和 heartbeat，不能只靠删 lock 文件。
- Mac 重启后在已登录的对应用户环境恢复；FileVault 开机解锁、系统登录是单机部署前提，不绕过。后台运行不依赖 Codex 图形窗口打开。
- 休眠/断网错过执行后检查最近成功刊次与时间窗，只补合适的一刊，不重放积压多天请求；远程监控缺失时承认关机本身不能本机发告警。

### 运行记录与断点

复用 run matrix，不再新建平行总账。runId 唯一，reportDate/edition 与输入截止时间单独记录。

恢复必须匹配：代码版本、prompt 版本、模型/CLI 配置、universe、部门 evidence、依赖 memo 的 hash。相同输入只重跑失败环节；变更输入使受影响节点和下游失效。跨日不复用“昨日成功”为今日分析。

阶段状态至少区分：pending/running/success/partial/failed/waiting_auth/waiting_quota/not_applicable。生成成功、发布成功、通知成功分开；发布失败不重新调用模型。

为单请求/单部门/整份日报设可配置 deadline 和总尝试上限。基线先以 4 标的测量，首版目标一刊 45 分钟内、60 分钟终止并保留结果；这是验收目标，不是当前性能事实。

## 8. 数据留存与项目整理

- 源码、长期文档、最小 fixtures 入 Git；日报、provider/evidence 日志、模型原文、私有报告仍由 ignore 保护。
- 复用 runtime/staging/public 边界，不为了本次部署另迁移全部目录。raw、normalized evidence、agent output、artifact、public projection 通过 manifest 关联。
- 原始响应建议 30 天、详细诊断 14 天；证据快照和报告保留 180 天；均为可配置建议，实施前核容量。
- 被保留报告引用的证据必须跟随保留；长留报告可压缩归档整套最小可追源包。
- 清理只按 manifest、先移到本地归档/废纸篓；不碰活动运行、真实 DB、env、凭据或未知文件。
- 备份保留 schema 版本、来源、时间与校验和；做一次临时目录恢复测试。交易记录不纳入任何自动修改路径。

## 9. 报告与 UI

不重新写整个 Web app。继续唯一 ReaderViewModel：API/Web/静态 HTML 一致，不能靠不同层各自洗工程词。

保留 ReportArtifact v1 兼容、既有 reports API 路径和 readerV3 文案来源。只 additive 扩充执行后端/实际模型/输入版本等诊断元信息。私有完整 artifact 与公共 Reader 投影同源，但内容权限不同；“同 contract”不等于把同一份私人 JSON 全部公开。

1. 首屏：今日判断、核心依据、主要风险、下一步、报告/数据截止时间。
2. A/H/US 分组，能展开每只纳入标的的完整结论；未分析的标的说明原因。
3. 部门摘要可展开依据、推导摘要、反证、下一步、来源与时间。
4. 无真实缺口不显示缺口卡；不让健康小数代替研究结论。
5. 简单运行页：本次在哪一步、上次成功时间、缺什么、如何恢复。raw 仅在私有 Diagnostics。
6. 手机上也能读：360px/桌面无横向溢出，正文层级清楚，展开/收起和键盘操作可用。

Pages 是本地成品的公共只读出口，不是另一套分析系统；交互 Web 留在 Mac，默认 loopback/已有认证，不公开后端端口。

## 10. Pages 与通知发布

- 宏观/市场等公共报告与私人持仓报告分开投影。真实持仓、成本、仓位规模、原始上下文、维护诊断默认不公开。
- 本机发布器只导出白名单 Reader HTML/CSS/资源，先通过 public bundle/privacy/link validator。
- 推荐使用独立 `pages-artifacts` 发布分支保存纯静态成品；GitHub 托管 workflow checkout 该分支 → upload-pages-artifact → deploy-pages，不调用模型、不复制 Codex 登录态。
- 源码主线继续 CI，不再定时启动付费云端分析；保留上游 workflow 文件但明确默认部署模式，避免双跑。
- 本机不充当可执行任意 PR 代码的公共 self-hosted runner。发布凭据限单仓发布所需权限，不自动扩大组织权限。
- 生成成功后失败只重试发布；部署完核验公网 runId/日期/内容，不以 HTTP 200 或 dispatch 成功代替新日报已上线。
- 最新入口只在部署成功后前进；失败时保留上一份成功报告并标明时间。
- 公共诊断、raw artifact、provider/evidence 原始包和旧 invest-brain 路径应 404。公共证据显示可公开的简述和外部来源，不直接上传私有 ledger。
- 通知从现有配置选择已接通渠道，发送摘要+链接；去重，记录 delivery id。没有有效渠道是明确未完成项，不虚报收到。

## 11. 原系统功能不退化清单

逐项登记 code path、backend、配置、测试、真实 canary，不能只检查页面返回 200。

| 功能 | 目标 | 核验 |
|---|---|---|
| 原个股分析 | Codex CLI | A/H/US 各一例有完整原报告、历史持久化 |
| 原市场复盘 | Codex CLI | 三市场日期/摘要/来源齐全 |
| 新部门日报 | Codex CLI | 所有适用部门、RedTeam、CIO 真实完成 |
| Chat/策略问股 | 现有 Codex App Server | 真实本地数据工具往返、多轮、流式、取消 |
| 原多 Agent/高级策略 | 逐个查能力边界 | 不以 single-agent Chat 通过代替；不兼容则实现必要适配，或明确列未交付功能 |
| Watchlist/Portfolio/History | 原服务和存储 | CRUD/只读分析边界正确，不改真实记录 |
| Screening/Signals/Backtest | 保留原规则/数据链，AI 子步骤按需适配 | 原测试+最小业务 smoke，不从日报顺手跑全历史回测 |
| 设置/用量/通知 | 显示有效后端与真实状态 | 无 API key 要求假阻断；usage 未知不报 0；渠道真实送达 |

首版已承诺的日报、个股、市场、交互问股是必验功能；其他支持范围明确标 VERIFIED/UNSUPPORTED/NOT_TESTED。仍有核心 UNSUPPORTED 不得宣称“全项目所有功能可直接用”。

## 12. 分阶段实施与退出标准

| 阶段 | 动作 | 通过后才进入下一阶段 |
|---|---|---|
| P0 基线/路由 | 记录 HEAD、PR、测试历史与差异；列全部 AI 调用与费用来源；定位生产 Mac/Hermes/调度 | 路由表完整，方案无隐式 GCP fallback；不把旧测试当当前新证明 |
| P1 适配 | 复用 Codex CLI/App Server；解除部门 LiteLLM 硬限制；统一配置/deadline/输出元信息 | 离线 fake CLI/transport 全过；一份真实部门 canary 成功；GCP 调用为 0 |
| P2 数据/流程 | 统一 universe/日期/缓存/Context Pack；校验恢复 hash；补数边界 | 原始数据→Evidence→部门→Reader 可追；相同输入不重跑；变更输入正确失效 |
| P3 内容/产品 | 完整日报、单股/市场报告、交互问股；Reader/Diagnostics/私有投影 | 内容质量表通过；三市场可读；无工程字段泄漏与隐私泄漏 |
| P4 本机生产 | 固定部署版本、单调度、锁、有限重试、恢复、日志与通知 | 断网/额度/登录/重启/发布失败故障演练通过 |
| P5 公共发布 | public-only bundle、发布分支、Pages workflow、公网检查 | 公网确为本次报告，子页面正常，旧 raw 路径 404，通知送达 |
| P6 观察/交付 | 连续 5 个计划运行日观察，记录耗时、人工干预、额度/源失败 | 5/5 按计划成功交付；任何修复注明并重新观察受影响环节；出最终验收与操作手册 |

阶段状态不是主观百分比。一次成功只能叫“单次闭环通过”；观察结束才叫“定时运行验收通过”，也不承诺永久零故障。

## 13. 测试矩阵

### 13.1 离线自动化

- Codex CLI：登录缺失、命令不存在、输出为空、截断、非零退出、额度错误、超时、取消、输出过大、Unicode、最终消息与 stdout 分离、子进程回收。
- Backend：显式 codex 路由不触发 LiteLLM smoke；原分析/部门/Chat 配置互不串线；缺失值不会回落 GCP；用户全局配置改变不改变生产计费路径。
- 工具：App Server 真实协议 fixture、工具参数与 symbol 范围、工具结果回传、并发取消、无任意命令/凭据访问。
- Evidence：过期/未来/跨标的/冒充事实/注入指令/缺来源；抓取时间不冒充发布日期；来源失败不等于无全部信息。
- Resume：同 hash 复用、prompt/model/universe/evidence 任一改变失效、下游失效、跨日隔离、并发去重。
- 部门：无需数据时 not_applicable、不是伪 success；反证与 CIO 取舍；缺口不强制输出；无凭空证据 ID。
- 发布：白名单、持仓字段隔离、路径穿越/符号链接/未知资源拒绝、原子 latest、失败不前进、通知去重。

### 13.2 内容质量（人工主审，机器辅助）

使用同一份真实冻结材料比较旧报告与 Codex 新报告，禁止换了数据后声称仅模型带来提升。再用当前数据做端到端。

| 维度 | 标准 |
|---|---|
| 事实/时间/单位 | 核心价格、增长率、日期、币种抽样均可核；严重编造/跨标的/未来信息错误为 0 |
| 推理 | 主结论说明依据及传导，不仅“可用/中性”；推论明确为判断，不强制写成怯弱措辞 |
| 反证取舍 | 至少一项有实质的替代解释/失效条件，CIO 解释为什么采纳/不采纳 |
| 市场覆盖 | 所有实际纳入市场/标的都有结论或明确未分析原因，不是 A 股独占 |
| 实用性 | 知道看什么、触发什么会改变判断，建议有边界但不被冗余门禁禁言 |
| 可读性 | 首屏能理解总判断，展开能读专业依据；无重复卡片或工程词堆叠 |

建议各维度 1–5 分、均不低于 4；评分是审查量表，不是可靠性概率。报告可用不等于投资收益已验证；收益需后续真实时间序列跟踪，不能由一次日报证明。

### 13.3 基础全仓 gate

在当前目录运行已有命令：

```bash
.venv311/bin/python -m compileall -q main.py server.py api bot data_provider scripts src
PYTHON=.venv311/bin/python ./scripts/ci_gate.sh
.venv311/bin/python scripts/check_ai_assets.py
git diff --check
(cd apps/dsa-web && npm test -- --maxWorkers=1 && npm run lint && npm run build)
```

当日真实生成后运行现有 Pages validator；API 测 latest/list/detail 返回同一 run，检查原主要 API 和页面业务行为，不只是状态码。Web 真浏览器测试桌面/手机、部门展开、个股下钻、历史、Chat、诊断隐藏。

真实 Codex canary/日报消耗订阅用量，与离线 gate 分开记录；本轮规划未执行这些命令或任何模型调用。

## 14. 手动使用与交付件

改造后保留原入口，新增 resume/publish 操作时在 help 明示；不把待实现参数伪装成现有命令。

```bash
cd /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812
# 以下现有日报入口需先完成 Codex 适配和部署配置；符号只是验收样例。
scripts/run_research_daily_local.sh --runtime llm --with-original-analysis \
  --market cn,hk,us --symbols '600519,000001,AAPL,HK00700'
.venv311/bin/python server.py
```

最终操作手册给出部署机上真实可执行的：立即生成、查看进度、恢复失败部门、仅重试发布、打开最新/历史报告、暂停/恢复定时任务、更新/回滚、故障诊断路径。实际 Web 端口以启动配置为准，不假定固定端口。

交付文档：AI 路由/费用表、架构图、功能兼容表、数据流审计、prompt/质量对比、故障演练记录、5 次运行证据、公开网址、操作手册。更新 CURRENT_STATE/INDEX/CHANGELOG/技术债台账；P0 0、P1 无未解释阻断、继承债真实打标。

回滚保留上一版本、配置和上一份成功公开包；回滚代码不自动启用旧 GCP 配置。停用定时任务不删除数据。分支/worktree/历史清理单独确认，删除类动作先归档。

## 15. 尚需实施时核验，不阻塞此规划

- 全天在线 Mac 是否就是当前机器、是否对应同一已登录用户；Hermes 服务实际在哪里。
- Codex 当前可用模型、真实用量和无人值守认证；只能 canary 证明，不能用 login status 替代。
- 通知渠道、默认真实 universe；沿用配置但不能把验收四只股票写成用户最终投资范围。
- 部署时确认 08:30 刊次和是否允许公开个股观察名单；默认私人持仓不公开。
- 电源/休眠/FileVault、磁盘容量、现有后台调度和发布权限。只报告确实需要用户协助的阻断。

## 官方依据

- Codex 非交互运行与官方登录复用：https://learn.chatgpt.com/docs/non-interactive-mode
- ChatGPT 订阅登录与 API key 计费路径区别：https://learn.chatgpt.com/docs/auth
- Codex App Server 协议：https://learn.chatgpt.com/docs/app-server

以上说明技术接入方式，不证明本账户有无限额度，也不替代真实本机验证。
