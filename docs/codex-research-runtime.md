# Reports 模型配置：Codex 本地执行

状态：适配与单独验证阶段，不能以此文档宣称定时日报/Pages 已验收。

## 选择层次

| 配置 | 范围 | 空值行为 |
|---|---|---|
| GENERATION_BACKEND | 原个股/市场文本分析 | 按原系统默认 |
| AGENT_BACKEND | 原交互工具问股 | 按原系统默认 |
| RESEARCH_GENERATION_BACKEND | 部门日报 | 继承旧 AGENT_GENERATION_BACKEND |
| CODEX_CLI_MODEL | Codex 文本生成 | Codex 默认模型 |
| CODEX_CLI_REASONING_EFFORT | Codex 文本生成 | Codex 默认思考强度 |
| RESEARCH_CODEX_MODEL | 部门日报覆盖 | 继承 CODEX_CLI_MODEL |
| RESEARCH_CODEX_REASONING_EFFORT | 部门日报覆盖 | 继承 CODEX_CLI_REASONING_EFFORT |

模型是显式字符串，不硬编码型号。强度可填写 none/minimal/low/medium/high/xhigh/max/ultra；实际模型不一定支持全部档位，不支持时失败并反馈，不静默更改。

## 本地配置示例

```dotenv
GENERATION_BACKEND=codex_cli
GENERATION_FALLBACK_BACKEND=
AGENT_BACKEND=codex_app_server
RESEARCH_GENERATION_BACKEND=codex_cli
CODEX_CLI_MODEL=
CODEX_CLI_REASONING_EFFORT=high
RESEARCH_CODEX_MODEL=
RESEARCH_CODEX_REASONING_EFFORT=high
RESEARCH_AGENT_RUNTIME=llm
RESEARCH_AGENT_MAX_CONCURRENCY=1
LOCAL_CLI_BACKEND_MAX_CONCURRENCY=1
GENERATION_BACKEND_TIMEOUT_SECONDS=300
```

Reports 选择本地后端时直接调用已有 GenerationBackend，不运行 API 模型候选探测。不需要清除数据源密钥；它们仍用于 Python 抓数，不传给 CLI。

当前新增配置可从本地 `.env`/进程环境设置。交互 Chat 的模型设置属于已有 App Server 配置，不自动套用 Reports 参数。

设置页的 AI 模型分类也提供上述五个配置项（后端、通用模型/强度、研报模型/强度），保存后用于后续任务，不改变已启动进程。

## 项目专用 CLI 与手动入口

2026-09-05 实测：全局 CLI 0.144.4 调用本机选择的模型被服务器以“需要更新 Codex”拒绝；项目专用 0.153.4 的合成材料 canary 已通过。未替换全局 CLI。

```bash
npm install --prefix .local_archive/codex-runtime --no-audit --no-fund @openai/codex@0.153.4
scripts/run_research_codex_local.sh --help
scripts/run_research_codex_local.sh --date YYYY-MM-DD --with-original-analysis \
  --market cn,hk,us --symbols '600519,000001,AAPL,HK00700'
```

可追加 `--codex-model MODEL --reasoning-effort high`，仅覆盖本次研报；不指定则使用项目配置。通用原分析模型从 CODEX_CLI_* 读取。

wrapper 优先使用项目安装目录，可用 RESEARCH_CODEX_BIN_DIR 指定其他安装目录；不会在每次运行时安装或更新 CLI。当前安装目录位于 ignored 本地目录，属于在用依赖，不能按过期报告自动清理。部署定版后再统一运行依赖目录。

CLI canary 仅证明调用成功，不证明完整日报/交互工具/无人值守已通过。

## 研究时间设置（只影响新报告）

默认近期变化1个月、建议期限2个月；历史资料按部门相关性使用，不限近月。单条观点可另写更短/更长期限。两项属于本地日报设置，不改变原DSA问股周期，暂不放入其Web通用设置表。

```bash
# 一次运行覆盖；使用本仓自选，不强制添加示例股票
RESEARCH_RECENT_CHANGE_MONTHS=3 RESEARCH_OUTLOOK_MONTHS=6 \
  scripts/run_research_codex_local.sh --date YYYY-MM-DD --market cn,hk,us --with-original-analysis
```

也可在本地`.env`填写上述两项，合法整数1..60；空值用1/2，非法值警告后回到默认。进程环境优先。`--codex-model` / `--reasoning-effort`照常选择模型和强度，未指定则不变。运行会消耗Codex账号额度。

Reader分别展示近期变化、建议适用期、历史参照；旧artifact不因配置改变而重写。若续跑旧日期，持久化的universe仍是该轮输入；要应用新配置需重建universe，不仅单独重跑Agent。完整入口会构建新universe，真实历史日报请保留，不以改日期代替新生成。

## 隔离与归因

- 实际 Codex 请求仍是联网模型；登录采用官方 CLI 机制，不提取认证 token，不承诺无限免费。
- 临时工作目录、最小环境变量；新配置对象默认禁用用户配置继承及不需要的 shell/apps/plugins/hooks/multi-agent/web-search；项目专用 CLI 使用 skip_host_skill_discovery，避免把个人全量技能说明塞进每个部门请求。
- 请求模型和思考强度写入运行诊断；未取得 resolved model 时 actual_model=null，不能把请求模型或 codex_cli 名称冒充已观测模型。
- 原分析应显式关闭 GENERATION_FALLBACK_BACKEND，避免失败后触发已有 API fallback。Reports 自身本地路径不会自动转 LiteLLM。
- 每次实际输出还需要业务/证据校验。CLI 成功与完整研报成功是两个状态。

此处只补当前中文 Reports 部署说明，不更改上游多语言总 README；后续产品交付文档再同步稳定配置。


## 本轮已补的运行边界

- Codex 本地入口通过 OS 文件锁串行化整份日报；重复启动返回 75。锁文件保留，进程退出/崩溃后内核自动释放，不用删文件猜是否过期。只覆盖此入口；原交互问股仍有自身的任务生命周期。
- 部门 `--resume-successful` 校验实际 Context Pack、SOP、模型、强度及 runner 实现 hash；变更会使相应部门及下游重跑。不再相信“同日期=同输入”。支持从未完成运行的 partial log 恢复。
- 如果 CIO 补数改变了 Evidence/SourceHealth，下一次恢复可能合理失效；不会为了节省调用复用过期观点。
- 空指数涨跌幅显示 N/A，不再导致港股市场报告崩溃，也不伪装为 0%。
- 后端测试的市场锁改为临时目录，避免离线测试等待正在运行的真实市场报告。
- 原同步 `/api/v1/agent/chat` 明确不支持 Codex；Web 使用有进度和取消支持的 `/api/v1/agent/chat/stream`。不要把同步接口 400 当作整个 Chat 不可用。
- 当前上游选股状态路径是 `/api/v1/screening/status`，不是历史方案中的 `/api/v1/alphasift/status`。

尚不能据此宣称：生产定时任务、跨进程全局模型并发、整刊 deadline、自动通知、公网发布、五日观察已完成。下一阶段必须在单次真实日报通过后收口。

## 本地面板与报告阅读

在项目根目录启动（前台，终端需保持运行）：

```bash
WEBUI_HOST=127.0.0.1 WEBUI_PORT=8135 SCHEDULE_ENABLED=false .venv311/bin/python server.py
```

访问 `/reports` 查看最新完整日报；`/reports/daily:YYYY-MM-DD` 读取指定日报，追加 `/diagnostics` 查看同一日报诊断。公司综合研究在日报内展开本期各部门完整观点；“原 DSA 短线分析”进入 `/reports/history:ID` 读取独立时点/策略原文，不代表当前CIO综合评级。静态 Pages 是同一日报的无服务器阅读版，不复制本地历史数据库。

服务与日报是两个进程：关掉服务不会删除报告，关闭浏览器也不会停止后台日报。`curl --fail http://127.0.0.1:8135/api/health` 检查 API，`/api/v1/reports/latest` 检查报告存在；只打开旧浏览器缓存不能证明服务在线。本轮运行的后台服务是本机临时可读服务，未安装开机启动/定时通知，不宣称全天候验收。
