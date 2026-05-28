# Research Cycle Architecture

## 一句话

用户入口是 `invest-brain`，完整扫描入口是 `scripts/run_research_cycle.py`。它只做机会发现和重评排队，不做交易，不改持仓，不改评分门控；专项用 `--lane commodity/geopolitics/a_share/us/hk/crypto` 聚焦深评。

## 入口分层

- **用户级 skill**：`/Users/hac/.agents/skills/invest-brain/SKILL.md`，只做薄入口和项目跳转。
- **项目内主路由**：`/Users/hac/AI-Studio/投研/skill.md`，定义完整投研流程、红蓝对抗、评分门控和写入边界。
- **项目内模块**：`scripts/`、`integrations/`、`frameworks/`、`agents/`，保留在项目里，不拆成一堆用户级 skill。
- **项目本地外部 skill**：`stock-analysis`、`technical-analysis`、`macro-regime-detector`、`position-sizer`、`macro-rates-monitor` 已放在 `.agents/skills/`，只在投研项目内按需调用；`.claude/skills/` 是兼容软链。
- **可选外部 challenger**：`integrations/tradingagents/`、`integrations/kronos/`，只产出独立证据，不替代本体评分、不写持仓。
- **外部工作流参考**：`anthropics/financial-services` 只作为 coverage / earnings / valuation / model-QC 架构参考；进入具体标的深评后按需吸收，不放进每日默认扫描。

默认逻辑：用户说“扫描 / 有什么机会 / 完整跑一遍”时走全源统一周期；用户明确说“只看公告/只看热榜/只看 Polymarket”时才单独调用子模块。

## 标准顺序

1. **Macro regime 读取/刷新**：`scripts/macro_regime_refresh.py` 先读 `state/regime-report.md`；超过 7 天且有 `FMP_API_KEY` 才调用外部 `macro-regime-detector` 刷新。FMP Stable ETF权限不足时用 Nasdaq 历史价 fallback，外部报告必须 6/6 组件可用才算 `refreshed`。默认只写归档，不改 state。
2. **事件情报**：近期/未来宏观、政策、行业、产业链催化剂。
3. **市场热榜**：扫描 A股/美股 成交活跃、涨跌幅、换手、行业/概念热度。
4. **A股增强**：对 A 股核心宽基、行业龙头、产业链龙头单独加权扫描。
5. **研报/机构观点**：扫描公开可访问的机构研报、策略展望、白皮书、深度报告；包含英文机构源和中文 A股主题源。
6. **免费官方源**：扫描 Treasury/NY Fed/BLS 宏观数据、SEC 美股公告和 SEC Company Facts。
7. **免费官方扩展源**：`scripts/official_extensions_scan.py` 扫描 BEA/EIA 相关序列、FRED fallback、FINRA short interest。
8. **免费源升级质量探针**：`scripts/free_data_source_probe.py` 分级 AKShare/efinance/edgartools/SEC Atom/GlobeNewswire/CFTC/EIA/Tradier/Alpha/Finnhub 等候选源；`needs_key`/`needs_install` 不等于已接入，`blocked_by_terms` 不自动化。
9. **官方公告/政策**：扫描 CNINFO A股公告和中国政府网政策推送。
9. **Crypto 轻量扫描**：默认只看 BTC/ETH，把它作为风险偏好温度计，不和股票同权重。
10. **Polymarket 概率**：只读外部概率，用于地缘/宏观概率校准。
11. **多维筛选漏斗**：把趋势、政策、研报、板块热度、热门成交/放量、技术形态分桶。
12. **候选合并**：生成 REVIEW / WATCH 队列。
13. **深度重评队列**：从 REVIEW / WATCH 中自动挑出最需要读原文和重评 thesis 的标的，输出 `11_deep_review_queue.md` 与 `deep_reviews/*.md`，并增加 evidence quality / price risk / next action；`--lane` 会过滤专项候选。
14. **第一轮自动重评摘要**：输出 `12_preliminary_deep_review.md`，给出 bull / bear / next action，但不替代红蓝对抗。
15. **源健康面板**：`scripts/source_health_dashboard.py` 输出 `13_source_health.md/json/html`，并给每个源标注 `usable/degraded/unavailable`、`criticality`、`blocking_level`；同时输出 `trade_review_usability`，区分核心源阻断和可选源降权。
16. **HTML 一屏结论**：`scripts/render_one_screen_brief.py` 输出 `00_one_screen_brief.html`，方便直接打开查看。
16.5. **Daily AI Digest**：固定 profile 或补跑完成后运行 `scripts/daily_ai_digest.py --generate-trade-reviews`，读取当天报告并生成 AI prompt、提醒状态和可选交易审查包；不交易、不写保护区。
17. **商品 Lane**：`scripts/commodity_lane.py` 输出 `15_commodity_lane.md/json/html`；当 `--lane commodity` 时 deep-review 只保留商品相关候选。
18. **商品基本面覆盖度**：`scripts/commodity_fundamentals.py` 输出 `16_commodity_fundamentals.md/json/html`，列出官方能源/宏观序列、事件、技术代理、FINRA拥挤度和仍缺的库存/期限结构/成本曲线。
19. **Options long-only 可选候选 Lane**：`scripts/options_chain_scan.py` 可单独跑；统一周期用 `--enable-options` 后输出独立 `options/18_options_candidates.*`；只允许 long call / long put / protective put，禁止卖方腿，`scoring_impact=0`。
20. **Kronos 可选量化 challenger**：`integrations/kronos/cli.py forecast` 可单独跑；统一周期用 `--enable-kronos` 后输出独立 `kronos/17_kronos_forecast.*`；默认不写入 `12_preliminary_deep_review.md`，`scoring_impact=0`。
21. **Coverage / Earnings / Valuation Workbench 可选深研层**：参考 Anthropic `market-researcher`、`earnings-reviewer`、`model-builder`、DCF、thesis/catalyst skills；只在具体 ticker/theme 已进入深评或用户明确要求时启用，输出研究归档，不写保护区。
22. **Model / Document QC 可选审查层**：参考 Anthropic `audit-xls`、deck/report QC 思路；只审查模型、报告、图表和来源一致性，不发布、不下单。
23. **L2.5 投委会只读审查**：仅在交易前或用户明确要求时使用 `agents/investment-committee-template.md` 与 `docs/pre-trade-evidence-pack-template.md`；不在日常扫描默认运行，不投票、不评分、不写保护区。
24. **红蓝对抗**：只有进入具体交易判断时才启动。
25. **评分门控**：仍然执行 `<6.0 = 不操作`。
26. **仓位/交易**：只有红蓝和评分通过后，才允许进入 position sizing 和交易记录写回。

## 架构边界

- `scripts/run_research_cycle.py` 是调度器。
- 调度器带单组件超时保护，默认 300 秒；某个外部源卡住会标记失败，不会无限拖住整轮。
- `scripts/source_cache.py` 是公开源缓存层；默认 TTL 21600 秒，可用 `--cache-ttl-seconds 0` 关闭或 `--refresh-cache` 强制刷新。
- `scripts/macro_regime_refresh.py` 负责 macro regime 读取/过期刷新；没有 `FMP_API_KEY` 时只返回 stale/missing-key 状态，不编造；FMP ETF 402/legacy endpoint 问题由项目内 `macro-regime-detector` 通过 Nasdaq 历史价 fallback 处理。
- `scripts/daily_intelligence.py` 负责股票/ETF/行业事件雷达。
- `scripts/market_heat_scan.py` 负责 A股/美股 免费热榜雷达，最高只给 WATCH。
- `scripts/report_intelligence.py` 负责公开研报/机构观点雷达，覆盖全球宏观、AI半导体、A股策略、光模块/算力、国产半导体、新能源、资源、金融、军工/机器人等主题。
- `scripts/official_sources_scan.py` 负责免费官方源：Treasury/NY Fed/BLS 宏观数据、SEC 最近公告、SEC Company Facts 最新事实点。
- `scripts/official_extensions_scan.py` 负责免费官方扩展源：BEA/EIA 相关宏观/能源序列、FRED fallback、FINRA short interest。
- `scripts/free_data_source_probe.py` 负责免费/开源源升级质量探针：输出 `05c_free_source_upgrade.md` 和 source health 组件；只分级，不自动安装、不自动启用需 key 源、不进入交易评分。
- `scripts/official_announcements_scan.py` 负责免费公告/政策源：CNINFO A股公告 + 中国政府网政策推送。
- `scripts/crypto_scan.py` 负责 crypto 免费行情雷达，默认 `core` 只扫 BTC/ETH；`broad` 才扫更多 altcoin。
- `scripts/screening_funnel.py` 负责多维筛选漏斗，不新增数据源，只整合上游证据。
- `scripts/deep_review_candidates.py` 负责自动选择深度重评候选，并为每个候选汇总公告、SEC、研报、事件、热榜、政策上下文、official_extensions；同时给 evidence quality、price risk、next action，并支持 `--lane`。
- `agents/investment-committee-template.md` 与 `docs/pre-trade-evidence-pack-template.md` 是交易前 L2.5 只读审查模板；不由 `run_research_cycle.py` 默认调用，不产生交易评分。
- `scripts/source_health_dashboard.py` 负责源健康面板：`13_source_health.md/json/html`，含全局 `usable/degraded/unavailable`、交易审查 `trade_review_usability`、组件 `criticality/blocking_level`。
- `scripts/render_one_screen_brief.py` 负责 HTML 一屏结论：`00_one_screen_brief.html`。
- `scripts/commodity_lane.py` 负责商品专项 Lane：`15_commodity_lane.md/json/html`。
- `scripts/commodity_fundamentals.py` 负责商品基本面覆盖度：`16_commodity_fundamentals.md/json/html`。
- `scripts/options_data_probe.py` 负责期权数据源探测：Tradier/Polygon/Alpaca/IBKR/Yahoo fallback 可用性、字段、合约数。
- `scripts/options_chain_scan.py` 负责 long-only 期权候选扫描：`options/18_options_candidates.md/json/html`，只做候选，不下单。
- `scripts/daily_ai_digest.py` 负责每日 AI 主动简报输入和自动交易审查包触发：`YYYY-MM-DD-ai-digest/` 与可选 `YYYY-MM-DD-trade-review-<symbol>/`；同时输出 `blocked_candidates.json`，记录因源健康、过热、证据不足或非深评而未触发的候选。
- `scripts/weekly_rule_audit.py` 负责每周规则审计：`YYYY-MM-DD-ai-rule-audit/`。
- `scripts/market_regime_strategy.py` 负责主 Agent 市场状态与策略总控：读取宏观、跨资产、主题热度、地缘/Polymarket、源健康和深评队列，输出 `14_market_strategy.md/html/json`；它决定“偏热候选是等待承接、轮动补位、ETF/篮子替代，还是只观察”，但不输出买卖指令。
- `scripts/architecture_audit.py` 负责统一周期验收：检查数据源接线、文档边界、输出完整性、深度重评产物和保护区未误写。
- `integrations/polymarket/cli.py` 负责预测市场概率。
- `integrations/tradingagents/` 是 external challenger，不替代本体。
- `integrations/kronos/` 是 Kronos external quant-forecast challenger；真实 smoke 已通过，当前已接入统一周期可选 lane，输出 `kronos/17_kronos_forecast.md/json/html`，不进入评分、不改保护区。
- `docs/anthropic-financial-services-adoption.md` 是 Anthropic 官方金融工作流项目的本地采纳边界；只作为 workflow / packaging / paid-provider blueprint，不作为本地 runtime authority。
- `integrations/tradingview/` 是 alerts/webhook 入口，不是主行情源。
- `options/18_options_candidates.*` 是期权候选入口，不是交易指令。
- L2.5 投委会审查只读取 evidence pack，输出 role memos / conflict matrix / fatal objections，不投票、不评分、不写保护区。
- 信息获取边界见 `docs/information-access.md`。

## 写入边界

统一周期只写：

- `research/archive/YYYY-MM-DD-<topic>/`

默认不写：

- `state/portfolio.md`
- `trades/trade-log.md`
- `agents/scoring-card.md`
- `agents/red-team-protocol.md`

## 验收入口

完成一次全源 smoke 后，运行 `scripts/architecture_audit.py --cycle-dir <research/archive/YYYY-MM-DD-topic>`。通过条件：

1. 统一周期组件全部 `rc=0`。
2. `00` 到 `13` 的研究产物齐全，包括 `00_one_screen_brief.html` 和 `13_source_health.md/html/json`；`13_source_health.json.usability_verdict=unavailable` 时验收失败，`degraded` 只能降级使用。
3. `11_deep_review_queue.*`、`12_preliminary_deep_review.md`、`deep_reviews/*.md` 都存在，且候选带 evidence quality / price risk / next action。
4. `paid_api_required=false`，`protected_writeback=false`。
5. `state/portfolio.md`、`trades/trade-log.md`、`agents/scoring-card.md`、`agents/red-team-protocol.md` 无 diff。
6. 如果本轮包含 Options，`options/18_options_candidates.*` 必须独立存在，且 JSON 中 `protected_writeback=false`、无卖方腿。
7. 如果本轮包含 Kronos，`kronos/17_kronos_forecast.*` 必须独立存在，且 JSON 中 `scoring_impact=0`、`protected_writeback=false`。

## 当前免费数据源

- SEC EDGAR 直连要求设置 `SEC_USER_AGENT` 或 `--official-sec-user-agent`，必须包含可联系邮箱；本地 `.env` 会自动读取且被 git 忽略。默认美股龙头 CIK 有本地静态映射，避免每次下载完整 SEC ticker map；未知 ticker 才回退查 SEC ticker map。

- Yahoo chart public endpoint：股票/ETF/A股/港股日线。
- Eastmoney push2 public endpoint：A股成交额、涨跌幅、换手、主力净流入、行业/概念热榜。
- Yahoo Finance screener public endpoint：美股涨幅榜、跌幅榜、活跃成交榜。
- Google News RSS：新闻 fallback。
- GDELT：全球新闻事件，可能限流。
- Google News RSS 中英文研报查询：公开机构观点和策略报告发现。
- Treasury/NY Fed/BLS/SEC public endpoints：免费官方宏观、美股公告、SEC Company Facts 财务事实源。
- BEA/EIA/FRED/FINRA：GDP/PCE、能源序列、short interest 等免费官方扩展源。
- CNINFO / Gov.cn：A股公告和中国政策原文线索。
- CoinGecko + Binance public fallback：crypto；统一流程默认只用 BTC/ETH。
- Polymarket Gamma/CLOB/Data：预测市场概率。
- Kronos：不是数据源；作为可选外部量化预测 challenger，默认只做 `kronos/17_kronos_forecast.*` 独立证据。上游参考 `shiyu-coder/Kronos`，2026-05-18 已通过真实 `Kronos-mini` pinned-model smoke；已接 `--enable-kronos` 可选 lane，默认仍不进评分。
- Anthropic financial-services：不是数据源；作为官方金融 Agent/Skill/Workflow 架构参考。它列出的 FactSet、S&P Global、Daloopa、Morningstar、LSEG、Aiera 等属于未来 Tier 2 paid provider blueprint，未接入时不影响当前免费源主流程。

## 仍然不是满血版的地方

1. A股已有免费热榜粗筛，但不是 Wind/iFinD/财联社级别的全量极速行情。
2. 研报层只能扫公开可访问内容；付费券商研报、Wind/iFinD/财联社内参默认拿不到。
3. 新闻流没有财联社/Wind/iFinD 的速度。
4. 美股热榜来自 Yahoo public screener，够做机会发现，不等于机构级实时 tape。
5. TradingView webhook 还没有本地 receiver，需要用户在 TradingView 里配置告警后才能进入系统。
6. SEC Company Facts 已进入统一源，但基本面深度仍需要 stock-analysis / 财报原文层进入单标的重评后再跑。
7. `macro-regime-detector` 仍保持项目本地独立 skill；统一周期已通过 `macro_regime_refresh.py` 读取/按需刷新。没有 `FMP_API_KEY` 时只能返回 stale/missing-key；有 key 但 FMP ETF权限不足时用 Nasdaq 历史价 fallback，且 6/6 组件完整才算满血刷新。
8. BEA direct API 可用免费 key 增强；EIA 当前通过 FRED mirrored series 覆盖 WTI/汽油等核心序列，EIA direct 库存/产量细项仍待补。
9. Kronos 已通过 Phase 0/1 + 真实 pinned-model smoke，并已接入 Phase 2 可选 lane；进入评分前仍缺 walk-forward、baseline、无 lookahead 验证。后验监控见 `docs/kronos-monitoring.md`。
10. Anthropic financial-services 的 paid MCP/provider 层尚未接入；当前只吸收架构和工作流规范，不声称拥有 FactSet/CapIQ/Daloopa/LSEG 等付费数据能力。

## 筛选漏斗原则

默认不对每只股票做深扫，而是按漏斗缩小范围：

1. 趋势/宏观/政策/产业事件先定方向。
2. 研报/机构观点只做只读证据补充。
3. 市场热榜先看 A股/美股 的成交额、涨跌幅、换手、行业/概念热度。
4. 板块热度看 REVIEW/WATCH 密度、5日变化和放量代理。
5. 个股只在代表池、异动池、热门成交/放量池里进入重评。
6. 技术面分为 momentum breakout、oversold reversal、hot turnover/volume、sharp pullback。
7. Crypto 默认只看 BTC/ETH，单独做风险偏好提醒，不和股票评分混成一套。
8. 深度重评只给“该不该重评”的优先级：`DEEP_REVIEW_NOW` / `DEEP_REVIEW_WAIT_ENTRY` / `DEEP_REVIEW_EVIDENCE_CHECK` / `WATCH_ONLY_RECHECK`，不输出买卖指令。
9. 主 Agent 必须读取 `14_market_strategy` 先判市场状态，再解释候选策略：短期 risk-on/轮动 里，过热候选不能直接追，但也不能被简单删成“无机会”；它应进入等待承接、ETF/篮子替代、轮动补位或弱转强确认清单。
10. 深度重评默认最多同市场 4 个标的，做到 A股加权但不完全挤掉美股/ETF；如要纯 A股专项可用 `--deep-review-max-same-market 0` 关闭分散上限。
11. `12_preliminary_deep_review.md` 是自动摘要，只用于决定下一步重评动作，不可当成最终投资结论。
12. `00_one_screen_brief.html` 是观看入口；`13_source_health.html` 是源健康入口；`14_market_strategy.html` 是市场状态与策略总控入口；`15_commodity_lane.html` 是商品专项观看入口；`16_commodity_fundamentals.html` 是商品基本面覆盖度入口。
