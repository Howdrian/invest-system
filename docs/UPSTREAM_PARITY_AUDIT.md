# Upstream Parity Audit

> Last verified: 2026-08-12
> Release branch: `codex/reports-v1-upstream-sync`
> Validated code SHA: `4f12aac5ebae`
> Current integration base: `upstream/main@3b98aa1d779a`
> Historical Reports base: `upstream/main@55946536a976`
> Old online main reference: `origin/main@7a8b4cf83e02`

## 结论

Reports 最初从 `55946536` 建线，本轮已在独立工作树把 9 个本地提交重放到 `upstream/main@3b98aa1d`，处理 14 组预测冲突并人工复核无冲突合并。验收代码对该 fetch 点为 `ahead 15 / behind 0`。

这是**点时本地 parity**：证明原产品面与 Reports 增量在该 SHA 上通过本地回归，不证明未来 upstream、云端 CI、Pages 或生产环境已同步。

## 原产品面与 Reports

| 范围 | 状态 | 本地证据 |
|---|---|---|
| Decision Signals / Run Flow / Usage / Watchlist / Scheduler / Portfolio | PRESERVED | full backend gate |
| Built-in Screening / Futu / Tushare / Responses API | PRESERVED | upstream regression + Web targeted/full gate |
| Reports API | RESTORED | `/api/v1/reports/latest`、`/artifacts`、`/artifacts/{id}`；OpenAPI static/runtime parity |
| Web Reports | RESTORED | `/reports`；Web lint/build/Vitest pass |
| ReportArtifact / Reader / Diagnostics | RESTORED | contract、semantic、Pages validators pass |
| Public Pages bundle | RESTORED_LOCAL | Reader-only allowlist 11 files / 19 links；未部署 |
| Legacy invest-brain public files | CLEAN_LOCAL | `legacyPublicFiles=0` |

Reports 是新增产品线，不替换原分析、筛选、组合、告警、设置或调度入口。完整 artifact、Diagnostics、ledger、memo 属维护面；公开 Pages 只允许 Reader HTML。

## Provider parity（点时代码级）

下列上游修复已进入当前 HEAD，并由 109 个目标测试与 full backend gate 验证：

- `02717771`：4/5 位裸港股代码路由；
- `90f62349`：Tencent 日 K 作为最终兜底；
- `20c399e7`：港股全市场实时快照缓存；
- `7fa29c7e`：Longbridge SDK keyword args；
- `748dba50`：YFinance 美股实时 PE/PB 与 data-quality。

本地 HK 指数、5 日历史、权限 permanent circuit 等增强同时保留。当前不再有 provider parity pending。
Longbridge SDK 参数契约已由测试覆盖；本轮未使用真实凭据执行 live smoke。

## 安全与配置不变量

- 非 loopback bind 必须 auth=true 且已存在有效管理员密码；middleware 运行时再次 fail-closed。
- 公网运行时关闭认证返回 409；专用关闭入口要求 current password；System Config 不得改 `is_editable=false`。
- PR Review 只运行可信默认分支脚本，通过 API 读取不可信 diff，不检出 fork 代码。
- Reports LLM 配置复用 `YAML > Channels > legacy`；Responses alias 保留 Router deployment；无效显式 YAML/channel 阻断降级。
- Daily Reports step 对齐主分析的 LLM、provider、Stock List 与 market region 配置。

## 本地复核

- Backend：`6174 passed, 4 deselected, 501 subtests`；syntax、flake8、deterministic、offline PASS。
- Web：lint、TypeScript/Vite build PASS；最终 Vitest `1108 passed / 2 skipped`。
- Desktop：50/50 tests；prod/full npm audit 0；DMG packaging framework pass，未含 backend bundle/签名。
- Dependency：Web/Desktop npm audit 0；Python pip check + pip-audit 0。
- Provider：109 targeted pass。
- OpenAPI：116 paths / 193 schemas，static/runtime 全量相等。
- Pages source：21/30/0 broken；Reader staging：11/19/0 broken。
- Semantic：11 departments、blocking 0；rejected 21、conditional 28。
- 结构：957 files / 427962 LOC / 220 large / 613 complex / 235 TODO-like / 5 cycles；Reader leak 0。
- Docker：compose config PASS；image build 首次下载超时，第二次在同一慢速包处中止，均未完成。

## 云端边界

- Pages：legacy `main/docs`；2026-08-12 三条维护 URL 仍 HTTP 200。
- candidate：未 push、无 PR、无 hosted checks。
- CI：Howdrian/invest-system 的 `ci.yml` endpoint 为 `state=deleted`，active workflow 无 CI。
- main：未保护；rulesets=[]；Actions all、sha pin false；secret scanning/push protection/Dependabot security updates disabled。
- Daily：最新是 2026-06-26 failure；Network Smoke 2026-08-12 success 只覆盖旧 `7a8b4cf8`。

## 发布判断

```text
LOCAL PARITY PASS AGAINST upstream/main@3b98aa1d
CLOUD RELEASE NO-GO
```
