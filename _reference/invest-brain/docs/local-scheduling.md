# Local Scheduling — 投研本机定时 + Codex AI 复核

> 目的：用 macOS `launchd` 稳定跑数据，用 Codex automation 定时做 AI 复核；数据扫描和 AI 判断分层，避免重复重跑。

## 当前结论

- 数据扫描：macOS LaunchAgent，负责固定 profile、补跑、dashboard、source health、AI digest 输入。
- AI 复核：Codex automation，负责读当天 `ai_prompt.md` / dashboard / 深评队列，并写 AI review；写完后刷新 dashboard，让首屏出现 AI 洞察。
- Codex automation 不再重复跑重型扫描；只有报告缺失或 source health 不可用时，才调用 `scripts/schedule_catchup.py` 让本地脚本判断是否补跑。
- 如果 profile 报告已存在但 AI digest 缺失，Codex automation 只运行 `scripts/daily_ai_digest.py --generate-trade-reviews` 补齐 AI 输入，不重跑全源扫描。
- 持仓主动层：`scheduled_research.py` / `schedule_catchup.py` 会先运行 `scripts/portfolio_refresh_now.py`，补当前持仓行情、浮盈亏、公告/事件、板块联动和持仓触发策略；只读，不写保护区。
- AI 主动层：持仓刷新和数据跑完后调用 `scripts/daily_ai_digest.py --generate-trade-reviews`，生成每日 AI 简报输入和交易审查包；Codex automation 再读这些输入做 AI 解读。

## 已安装的 LaunchAgent

| Label | 时间 | 命令 | 说明 |
|---|---:|---|---|
| `com.hac.investbrain.asia-close` | 每天 15:40 | `scripts/scheduled_research.py --profile asia-close-review` | 脚本内判断 Asia/Bangkok 工作日；A/HK 收盘后运行 |
| `com.hac.investbrain.us-premarket` | 每天 19:45 | `scripts/scheduled_research.py --profile us-premarket-review` | 脚本内判断 Asia/Bangkok 工作日；美股盘前运行 |
| `com.hac.investbrain.catchup` | 加载时 + 每 2 小时 | `scripts/schedule_catchup.py` | 后台检查当天报告是否缺失，缺失才补跑；补跑后刷新 AI digest；不会开 Codex 窗口 |
| `com.hac.investbrain.weekly-rule-audit` | 周一 10:30 | `scripts/weekly_rule_audit.py` | 每周审计筛选/深评/AI触发规则是否符合交易理念 |

## 已启用的 Codex automation

| ID | 时间 | 模型 | 作用 | 输出 |
|---|---:|---|---|---|
| `asia-close-review` | 工作日 16:45 | `gpt-5.5 / xhigh` | A/HK 收盘后 AI 复核；必要时调用补跑检查；写完刷新 dashboard AI 洞察 | `research/archive/YYYY-MM-DD-ai-digest/asia_close_ai_review.md` |
| `us-premarket-review` | 工作日 20:45 | `gpt-5.5 / xhigh` | 美股盘前 AI 复核；必要时调用补跑检查；写完刷新 dashboard AI 洞察 | `research/archive/YYYY-MM-DD-ai-digest/us_premarket_ai_review.md` |
| `missed-run-catch-up-check` | 工作日 17:15、21:15 | `gpt-5.5 / xhigh` | 漏跑补查 + AI 简短复核；写完刷新 dashboard AI 洞察 | `research/archive/YYYY-MM-DD-ai-digest/catchup_ai_review.md` |
| `weekly-rule-ai-review` | 周一 11:00 | `gpt-5.5 / xhigh` | 每周交易规则 AI 审计复核 | `research/archive/YYYY-MM-DD-ai-rule-audit/ai_review.md` |

Codex automation 会产生独立后台任务记录，不在当前聊天里持续刷屏；查看结果优先看上述输出文件和 `dashboard.html`。

LaunchAgent 文件位置：

```text
~/Library/LaunchAgents/com.hac.investbrain.asia-close.plist
~/Library/LaunchAgents/com.hac.investbrain.us-premarket.plist
~/Library/LaunchAgents/com.hac.investbrain.catchup.plist
~/Library/LaunchAgents/com.hac.investbrain.weekly-rule-audit.plist
```

## 固定 profile

### Asia close

```bash
python3 scripts/run_research_cycle.py --topic asia-close-review --lane all
```

输出目录：

```text
research/archive/YYYY-MM-DD-asia-close-review/
```

### US premarket

```bash
python3 scripts/run_research_cycle.py --topic us-premarket-review --lane us
```

输出目录：

```text
research/archive/YYYY-MM-DD-us-premarket-review/
```

## 补跑规则

`scripts/schedule_catchup.py` 按 Asia/Bangkok 时间检查：

- 16:20 后：如果当天 `YYYY-MM-DD-asia-close-review` 缺 `summary.md` / `00_one_screen_brief.html` / `run_metadata.json` / `13_source_health.json`，补跑 Asia close。
- 20:20 后：如果当天 `YYYY-MM-DD-us-premarket-review` 缺上述文件，补跑 US premarket。
- 报告必须是在对应 profile 的预定开始时间附近或之后生成才算有效：Asia close 最早有效时间为 15:30，US premarket 最早有效时间为 19:35。凌晨或手动提前生成的同名目录不会阻止晚间补跑。
- `13_source_health.json.usability_verdict = unavailable` 不算有效报告，会进入补跑/延迟重试；`degraded` 算可读但页面会要求降权。
- 有效报告已存在就不重复跑。
- 如果当天全源报告不缺，但 `portfolio_monitor.json` 缺失、超过 2 小时或持仓行情未刷新，catch-up 只跑轻量持仓刷新，不重跑完整全源扫描。
- 周末直接跳过。

## 日志

```text
logs/scheduled/
├── launchd-asia-close.out.log
├── launchd-asia-close.err.log
├── launchd-us-premarket.out.log
├── launchd-us-premarket.err.log
├── launchd-catchup.out.log
└── launchd-catchup.err.log
```

`logs/` 已被 `.gitignore` 忽略。

## 每日控制台

每次 `scheduled_research.py` 跑完，以及每次 `schedule_catchup.py` 检查完，都会先刷新持仓监控和 AI digest，再刷新：

```text
dashboard.html
```

它聚合：

- 今日两个 profile 是否有效；
- 当前持仓最新价、市值、浮盈亏、公告/事件、板块联动和是否触发持仓审查；
- 数据源总探针：行情、热榜、新闻、官方源、公告、Crypto、Polymarket、期权 fallback 是否通畅；
- 今日总判定：不可用于交易 / 可读但降权 / 可用于复核；
- 系统问题诊断：问题大小、问题位置、影响、修复状态；
- 是否需要补跑；
- 市场快照：市场分布、行业热度、异动热榜、宏观 regime、crypto 风险偏好；
- 投研洞察：哪些信号可读、哪些只能降权预览、主要数据缺口；
- AI 洞察：Codex 自动化复核后的“关注什么、为什么、缺什么、下一步”；
- 红蓝工作台：有预审包就直接展示红蓝材料入口，避免用户再问“要不要对抗”；
- 相对上一轮变化：新增/掉出/延续候选、优先级变化、源健康变化；
- 走势：候选数、最高优先级、源可用性等投研内部指标；行情源不可用时不伪造价格图；
- 一屏简报、深评队列、源健康入口；
- 今日深评候选；
- 本机后台任务状态；
- Codex 自动化记录状态。

每次固定 profile 跑完后，还会刷新当天：

```text
research/archive/YYYY-MM-DD-data-source-probe/
```

该探针只读检查核心免费源；必需源失败会让 dashboard 明确提示，期权 Yahoo fallback 和 GDELT 这类可选源失败不阻断主流程。

每次固定 profile 或补跑后，还会刷新当天：

```text
research/archive/YYYY-MM-DD-ai-digest/
research/archive/YYYY-MM-DD-trade-review-<symbol>/  # 仅有强候选时
```

AI digest 只做提醒和交易审查触发，不下单、不写持仓、不改评分卡。

## 查看状态

```bash
launchctl print gui/$(id -u)/com.hac.investbrain.asia-close
launchctl print gui/$(id -u)/com.hac.investbrain.us-premarket
launchctl print gui/$(id -u)/com.hac.investbrain.catchup
launchctl print gui/$(id -u)/com.hac.investbrain.weekly-rule-audit
```

## 手动运行

只跑 Asia close：

```bash
python3 scripts/scheduled_research.py --profile asia-close-review
```

只跑 US premarket：

```bash
python3 scripts/scheduled_research.py --profile us-premarket-review
```

只做补跑检查：

```bash
python3 scripts/schedule_catchup.py
```

查看补跑脚本参数：

```bash
python3 scripts/schedule_catchup.py --help
```

周末调试时可显式允许检查：

```bash
python3 scripts/schedule_catchup.py --force-weekend
```

生成每日 AI 简报/交易审查包：

```bash
python3 scripts/daily_ai_digest.py --generate-trade-reviews
```

运行每周规则审计：

```bash
python3 scripts/weekly_rule_audit.py
```

## 停用

```bash
launchctl bootout gui/$(id -u)/com.hac.investbrain.asia-close
launchctl bootout gui/$(id -u)/com.hac.investbrain.us-premarket
launchctl bootout gui/$(id -u)/com.hac.investbrain.catchup
launchctl bootout gui/$(id -u)/com.hac.investbrain.weekly-rule-audit
```

## 电脑关机/睡眠

- 电脑开机且用户环境可运行时：launchd 会后台运行。
- 睡眠期间不保证准点执行；唤醒后 catchup 会按间隔检查并补当天缺失报告。
- 关机期间不会运行；开机后 catchup 会检查当天是否漏跑。
- 如果要电脑关机也保证执行，需要 VPS/云端 runner。
