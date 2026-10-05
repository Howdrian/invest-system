# invest-system 当前状态

> 核验日期：2026-09-08；最新真实日报为 **2026-09-08**。通过本轮本地可用验收，不是云端发布或预测胜率认证。
> 活跃目录：`/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`
> 分支：`codex/codex-local-runtime-20260905`；HEAD `af917c7a`，上游 `303f4e1c` 的 MERGE_HEAD 仍在。270条既有/本轮dirty混合修改，未commit/push。

## 现在可直接使用

- 原DSA交互工作台保留。Reports是同一Web/API的新增产品线，不是iframe、独立抓数系统或另一套LLM报告。
- 9/8重新采集数据、运行原个股/三市场分析、生成真实11部门日报；之后在同批材料上再生成一轮11部门。最终LLM success=11，fallback=0，1次重试，总12次生成调用。
- 当前走本机Codex，配置请求 `gpt-6-astra/high`，可用参数覆盖模型/强度；不调用GCP。包装器未返回实际resolved模型及token明细，不把请求模型当作后台观测证明，也不声称免费/不消耗额度。
- 首轮全链约47分钟；第二轮仅部门/CIO约29.5分钟。当前并发1。单次实测不是稳定延迟SLA；基本面曾接近300秒超时边界。
- 本期5家公司：茅台、宁德时代、比亚迪、中国平安、招商银行；手动自选与系统研究候选分开。港股6行业/主题代理、美股11行业ETF，不冒称全市场个股财报覆盖。
- 研究强调近期变化/未来1–2个月机会，但相关历史不截断；长期估值情景不伪装成两个月目标价。

## 四轮审核后改了什么

1. **内容与完整性**：静态独立部门页不再截前5条/180字；公司可展开同轮完整部门观点及证据。原DSA历史链接明确为独立短线分析，不冒充CIO综合意见。
2. **真实研究质量**：SOP强调财报原文主因、正向驱动、估值要求与分主题反证。CIO现在能明确选取/否决部门建议，区分研究评级与短线入场，不再所有主题都“继续观察”。
3. **后处理纠错**：摘要允许有据转述，不要求逐字复制正文；修复并列指数数字、否定放量及普通“组合”等误判。保留真正错数/错主体/不存在引用的检查，而非新增评级禁令。
4. **呈现**：首屏CIO具体选择+三市场要点；行业比较图、公司全文、独立部门文章式阅读。价格财务表不另给规则型“观察”评级，候选显示公司名称。方法折叠、诊断独立；桌面/手机/明暗主题检查，工程字段不裸露。

最后5条原句从保存的模型原文重新校验恢复，没有再调用LLM或人为改评级。旧拒绝记录结构不全，只恢复原文和引用，不重造目标价/入场字段；1条地缘旁支范围声明仍缺匹配引用，留在诊断。部门/红队/CIO没有在最后重校验后重新生成，详见[完整验收](../.local_archive/product-quality-20260908/FINAL_ACCEPTANCE.md)。

## 当前报告质量与验证

沿用同一六维自审量表：约 **70 → 82/100**。这是单期内容/产品质量评估，不是胜率、收益率或第三方评级。优点是明确推荐、财务口径/现金流归因、分主题反证裁决和全文下钻；行业经营数据与跨市场公司深度仍弱。

- 最终Backend **7369 passed，4 deselected，42 warnings，661 subtests passed**。
- Web **1229 passed，2 skipped**；lint 0错误/2条既有hooks警告；build通过。
- Python3.11 compile、AI assets、working/index两侧diff whitespace通过。
- Pages/snapshot/语义/时效/部门流审核通过；`legacy_public_files=[]`。
- 报告latest/list/detail、health及原核心只读API共10项200；latest/detail的readerV3与磁盘完全相同。
- 真实Web及静态各11部门、5公司、3市场要点；9个静态分报告200。全部保留论点可展开；目标工程字段0、页面JS异常0、390px横溢0。桌面/手机截图已目检。
- 原9/7artifact SHA未变；本轮生成产物仍ignored，真实.env/DB/日志未新增入git。配置值私密比对未检出泄漏，不等于全能密钥扫描。

## 数据边界：不是满市场“满血”

本期 `LIMITED_REVIEW`，42 verified facts、115 derived facts、14 discovery；critical missing计数0只是本期合同满足，不表示所有资料都齐全。

- provider记录68 success、17 failed；单源失败仍可由其他源覆盖，失败在Diagnostics可查，没有把失败改绿。
- 行情/财务等覆盖分数只针对本期5公司和规定资料，不代表财报每个经营变量都拆完。
- 港美主要是行业层；港股全行业、港美公司财报、A股行业资金/多期历史尚不全面。
- 宏观量化偏美国FRED；地缘的最新事件部分是搜索线索，真实通航、产量、库存与公司利润传导仍需针对性资料。
- 无真实持仓，组合收益/实际敞口不虚构。CIO本次2项补数复用已有资料，新增抓取0，不冒称2次新源成功。

## 架构与仍未交付

保留主干，不建议重建：

`原数据/原分析 → Evidence → 部门Context → 部门研究 → 风险/红队 → CIO取舍 → Artifact → Web/静态Reader`

1. **后续研究提升**：为重点行业补经营驱动和长期比较，扩大港美公司研究，连续复盘推荐/反证/失效条件。这些不是靠更多“安全门”解决。
2. **工程债**：dirty merge仍待专门审查提交；大文件/循环依赖未清零，本轮未重扫此前全仓规模，不用旧P0口径宣称整个架构无债。
3. **运行交付**：连续无人值守、睡眠恢复、远程Mac、Hermes/飞书、自动通知及云端Pages未验收。现在是本机可读/可生成，不是全天候服务。
4. **质量边界**：单期复审不能证明长期投资效果；财报做了关键原文抽样，不是逐公司全量审计。

## 怎么用

- [本机报告中心](http://127.0.0.1:8135/reports)
- [9/8正式日报](http://127.0.0.1:8135/reports/daily%3A2026-09-08)
- [9/8诊断](http://127.0.0.1:8135/reports/daily%3A2026-09-08/diagnostics)
- 手动生成：`scripts/run_research_codex_local.sh --date YYYY-MM-DD --market cn,hk,us --with-original-analysis`。使用本仓自选及模型配置，可附`--codex-model MODEL --reasoning-effort high`。每次会消耗本机Codex账号额度。
- 服务未运行时：`WEBUI_HOST=127.0.0.1 WEBUI_PORT=8135 SCHEDULE_ENABLED=false .venv311/bin/python server.py`。当前8135已在运行，不重复启动。
- 静态报告：`docs/reports/YYYY-MM-DD.html`；完整配置/模型/时间范围见[Codex运行说明](codex-research-runtime.md)。

源码/测试/长期文档与ignored报告/ledger/截图分开。旧release-candidate的.git仍被当前worktree共享，不可整目录删除；`.local_archive/codex-runtime`是活跃依赖。

[本轮四轮审核与最终验收](../.local_archive/product-quality-20260908/FINAL_ACCEPTANCE.md) / [Agent SOP](research-agent-sop.md) / [产品线](reports-product-line.md) / [技术债](TECH_DEBT_REGISTER.md)

本页是当前状态入口。上一份状态已保留在本轮本地验收备份；历史验收不是另一份当前真相源。
