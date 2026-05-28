# Dashboard 产品标准（投研系统）

> 版本：v1.0  
> 日期：2026-05-26  
> 目标：把 Dashboard 从“扫描结果集合”改成“打开就知道今天该看什么、能不能信、下一步做什么”的投研工作台。  
> 边界：不自动交易；不绕过红蓝对抗、评分卡、仓位风控和用户确认；不新增付费数据源。

## 1. 直接标准

Dashboard 的首页不是日志页，也不是组件列表。首页先放“投研总摘要”，再回答 8 个问题：

1. 今日市场怎么了；
2. 今天这份报告能不能信；
3. 当前持仓风险在哪里；
4. 今天 AI 给出的事实、推理、结论是什么；
5. 最该盯的 1-3 件事是什么；
6. 市场状态一句话是什么；
7. 有没有新机会，为什么还不能直接交易；
8. 数据源哪里降级、影响什么、系统下一步怎么恢复。

硬规则：

- 有持仓时，首页优先级为：`投研总摘要 → 持仓风险总览 → 今日总判定 → AI 洞察/多维评级 → 今日最该盯 3 件事 → CIO/红蓝门控状态 → 机会摘要 → 数据可信度`。
- 首页最多 6-8 个决策卡；HTML 中首页级 `h3` 上限 12 个。超过就判定信息过载。
- 系统健康、证据链、工程诊断不得和投资机会混在同一阅读流里。
- 投研总摘要必须整合 Daily AI Summary、持仓影响、重要事项、CIO、红蓝、评分卡/仓位/用户确认状态；不得单独创造交易结论。
- AI 多维评级只展示 `市场环境 / 技术位置 / 催化剂清晰度 / 证据完整度 / 数据可信度 / 风险边界 / 持仓相关性`，不替代评分卡。
- 所有结论必须写成：`事实 → 推理 → 结论 → 缺口/下一步`。
- `source degraded` 不能只显示状态，必须解释主源/备用源/缓存、影响范围、下一次重试、是否需要 AI 诊断。
- Dashboard 产品审核不得轻易给 `PASS 5.0`：只要有 P1/P2 体验或契约缺口，最高只能 `PASS_WITH_WARNINGS`。
- 当前实现允许“首页变瘦”：`CIO 总审 / 阻断归因 / 数据降权 / 产品审核` 不必整块堆在首页，但必须在首页 1 次点击进入对应子页，并通过 `dashboard_product_review.py` 与 `dashboard_governance_audit.py` 验证。
- 当前视觉系统采用双主题：默认 `机构浅色投研工作台`，可切换 `Bloomberg 深色终端风`；主题选择写入浏览器 `localStorage`。浅色用于日常阅读和截图复盘，深色用于偏终端/行情查看；两套主题必须共用同一信息架构和交易安全边界。
- 红蓝对抗暂不升级成复杂群聊式多 Agent 辩论。现阶段保留 `蓝队 → 红队 → 仲裁 → scoring-card → 仓位风控 → 用户确认`，只在 Dashboard 上增加门控 stepper、持仓审查口径和证据就绪检查；没有价格、公告、持仓风险或 source health 时，只提示补证据，不启动完整红蓝。
- 新增/更新持仓后，默认先跑轻量持仓刷新：读取 `state/portfolio.md` → 补行情/公告/板块 → 生成 `portfolio_trigger_policy` → 更新 Dashboard。完整全源扫描仍按定时任务运行；轻量刷新不写持仓、不写交易记录。

## 2. 对标调研结论

| 来源 | 可吸收标准 | 我们的降级实现 |
|---|---|---|
| Bloomberg PORT | 组合、风险、绩效归因、压力情景、自动报告、AI commentary 放在同一组合工作流 | 免费源下先做持仓成本暴露、代理情景、持仓事件、数据降权，不做机构级 VaR/归因 |
| FactSet Performance / Portfolio Commentary | 绩效/归因/风险要有数据校验；AI commentary 需要 source-linked 证据 | AI 摘要必须链接 source_path/as_of；没有原文就标 `UNKNOWN`，不能补脑 |
| Morningstar Direct | 持仓影响、风险暴露、组合构建、压力情景和归因是组合页核心 | 首页先展示当前持仓和成本暴露；组合页再补当前价、浮盈亏、事件、板块联动 |
| LSEG Workspace | 新闻、研究、数据、分析和搜索发现是一个工作流；要能过滤噪音 | 机会页只保留主题热度、深评候选、催化剂；标题级新闻不能当交易依据 |
| Power BI | Dashboard 是当前状态总览；一屏讲故事；移除非必要信息；重要信息放上方 | 首页只放决策摘要，不放组件日志；详细表格进证据/系统页 |
| Tableau | 明确目标和受众；重要视图放左上；限制视图数量；需要更多视图就拆新 dashboard | 拆为首页、持仓、机会、证据链、系统健康五页 |
| GOV.UK Data Quality | 数据质量是 fit for purpose；要说明完整性、准确性、及时性、权衡和根因 | 源健康按可用性、降权、失败根因、fallback、影响范围、恢复动作展示 |
| FINRA Communications | 金融展示不能误导；收益与风险要平衡；移动端标签要准确易懂；复杂产品风险要显著 | 未门控交易建议禁用；历史动作、审查对象和红蓝/评分结论可展示；期权风险不能淡化 |

参考资料：

- [Bloomberg Portfolio & Risk Analytics](https://professional.bloomberg.com/products/bloomberg-terminal/portfolio-analytics/)
- [FactSet Performance Solutions](https://www.factset.com/lp/performance-solutions)
- [FactSet AI-Powered Portfolio Commentary](https://www.factset.com/marketplace/catalog/product/portfolio-commentary)
- [Morningstar Direct Portfolio Management](https://www.morningstar.com/business/products/direct/portfolio-management-tool)
- [LSEG Workspace](https://www.lseg.com/en/data-analytics/products/workspace)
- [Power BI dashboard design tips](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips)
- [Tableau dashboard best practices](https://help.tableau.com/current/pro/desktop/en-us/dashboards_best_practices.htm)
- [GOV.UK Data Quality Framework](https://www.gov.uk/government/publications/the-government-data-quality-framework/the-government-data-quality-framework/)
- [FINRA Communications with the Public](https://www.finra.org/rules-guidance/guidance/reports/2024-finra-annual-regulatory-oversight-report/communication-with-public)

## 3. 用户目标

### 10 秒内

用户必须看到：

- 今日总判定：可读 / 降权可读 / 不足以交易 / 阻断；
- 当前持仓：标的、成本、成本暴露、缺失的价格/浮盈亏；
- 今日最该盯的 1-3 件事；
- 数据可信度一句话。

### 30 秒内

用户必须知道：

- AI 的事实、推理、结论；
- 如果不能交易，卡在哪里；
- 需要补哪个证据；
- 下一次自动补跑/重试什么时候；
- 哪些内容可以进入子页面继续看。

## 4. 页面层级标准

| 页面 | 目的 | 首页可露出 | 详细内容 |
|---|---|---|---|
| `dashboard.html` | 负责人首页 | 只放结论、持仓风险、AI摘要、Top 3、机会摘要、数据可信度 | 不放组件日志，不放大表格 |
| `dashboard_portfolio.html` | 持仓风险页 | 首页跳转 | 当前价、浮盈亏、持仓事件、板块联动、止损/失效条件缺口 |
| `dashboard_opportunities.html` | 机会页 | 首页只放摘要 | 市场结构、主题热度、深评候选、催化剂、图表 |
| `dashboard_evidence.html` | 证据链页 | 首页只放状态和链接 | CIO、子 Agent、阻断归因、红蓝预审、证据包 |
| `dashboard_system.html` | 系统健康页 | 首页只放数据可信度摘要 | source health、recovery plan、自动化、补跑、产品审核 |

## 5. 卡片标准

每个卡片必须符合：

```text
标题：用户语言，不是工程字段
一句话结论：最多 22 个汉字或一短句
事实：最多 3 条，带 source_path/as_of
推理：为什么这个事实影响持仓/机会/风险
结论：观察/等待/补证据/可进入红蓝，不出现买卖指令
下一步：系统下一步 + 用户可选动作
```

卡片禁止：

- 只显示 `WARN/OK/BLOCKED_BY_FATAL` 这类裸枚举；
- 堆组件成功/失败日志；
- 把“预审材料已生成”写成交易机会；
- 把热度或标题新闻当买点；
- 没有数据来源的数字。

## 6. 图表标准

| 数据类型 | 推荐图表 | 禁用/慎用 |
|---|---|---|
| 标的价格/指数时间序列 | 折线图 + 最新点 + 关键事件标注 | 多条不同量纲共用一轴 |
| 持仓成本/市值/现金 | 条形图、瀑布图、暴露条 | 饼图类别超过 6 个 |
| 行业/主题热度 | 横向条形图、热力矩阵 | 只有颜色没有数值/排序 |
| 证据状态 | 矩阵、状态表 | 折线图 |
| 催化剂时间 | 时间轴 | 散点图 |
| 源健康 | 状态矩阵 + 降权说明 | 把系统错误和投资机会放一张图 |
| 期权风险 | 最大亏损/到期/IV/OI 表格 + 风险标签 | 展示潜在收益但不展示最大亏损 |

## 7. 数据质量展示标准

`source degraded` 必须显示：

- 主源名称；
- 失败类型；
- 是否启用备用源/缓存；
- 备用源质量等级；
- 最近成功时间；
- 最近失败时间；
- 连续失败次数；
- 数据新鲜度；
- 影响范围：持仓 / 机会 / 宏观 / 证据链 / 交易预审；
- 下一次自动重试；
- 是否需要 Codex AI 诊断；
- 用户是否需要提供 key、手动确认或等待。

降权文案模板：

```text
本轮可读，但 {component_label} 使用 {fallback_label}，连续失败 {failure_streak} 次。
影响：{impact_scope} 只能作为观察线索，不能作为满血交易证据。
系统下一步：{next_retry_at} 自动重试；若继续失败，AI 诊断根因并给人工处理建议。
```

## 8. 金融表达边界

Dashboard 允许：

- 观察；
- 等待承接；
- 补证据；
- 进入红蓝对抗；
- 数据降权；
- 交易门控未完成。

Dashboard 禁止的是“未完成交易门控前的行动建议”，不是禁止词本身。

允许出现：

- 历史事实：`用户已买入 160644 39手`；
- 审查对象：`本次是买入审查 / 加仓审查`；
- 红蓝或评分引用：`红蓝结论建议不操作`、`评分通过后等待用户确认`；
- 风险披露：解释为什么未过门控不能交易。

禁止出现：

- `建议现在买入 / 可以加仓 / 立即下单 / 小底仓参与`；
- 确定性收益、低风险高收益；
- 期权亏损有限但不展示最大亏损；
- 标题新闻直接推导交易。

## 9. Dashboard Governance 评分标准

满分 `5.0` 只在全部满足时给出：

- 首页 `h3` 不超过 12；
- 首屏包含投研总摘要；有持仓时首屏包含持仓风险总览；
- 有持仓时必须能看到最新价/浮盈亏或明确缺失原因、公告状态、板块联动、持仓审查状态和今日 Top 3 watch；
- 今日 CIO 或 AI digest 没有偏离当前持仓优先级；
- 数据源降级时有 recovery 深度字段；
- 七类 view-model 契约完整；
- 没有工程字段、绝对路径、未门控交易建议；
- 截图级阅读检查通过；
- 证据链能追溯 source_path/as_of；
- 系统健康与投资机会分离。

硬性降级：

| 情况 | 最高 verdict |
|---|---|
| 出现未门控交易建议或本机路径 | `BLOCKED` |
| 首页信息过载、持仓不在首屏、CIO 偏离持仓 | `PASS_WITH_WARNINGS` |
| 有持仓但缺最新价/浮盈亏/公告/板块/持仓审查状态 | `PASS_WITH_WARNINGS` |
| 数据源降级但无恢复说明 | `PASS_WITH_WARNINGS` 或 `BLOCKED` |
| 缺 view-model 契约 | `PASS_WITH_WARNINGS` |
| 只有静态字符串检查，未做截图/链路审核 | `PASS_WITH_WARNINGS` |

## 10. 验收问题

每次 Dashboard 改版后必须回答：

- 10 秒内能否知道今天该看什么；
- 当前持仓是否在首屏；
- 是否能看到成本暴露、浮盈亏状态、风险缺口；
- 是否有 AI 的事实 → 推理 → 结论；
- source degraded 是否说明主源、备用源、影响和下一步；
- 系统健康是否与投资机会分离；
- 是否没有交易执行误导词；
- 产品审核是否没有轻易给 `PASS 5.0`。
