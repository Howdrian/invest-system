# Local Workspace Placement

> Last verified: 2026-08-12

## Current local path

`/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`

这是当前 upstream 同步后的发布候选工作树，分支为 `codex/reports-v1-upstream-sync`。验收代码 SHA `4f12aac5ebae` 基于 `upstream/main@3b98aa1d779a`，点时为 ahead 15 / behind 0。原 `/Users/hac/AI-Studio/投研/invest-system-release-candidate` 保留为同步前的干净参考线，不再是本次最终代码入口。

本地 parity、测试和 Git 提交不等于云端发布。线上 Pages 仍是旧 `main/docs`；2026-08-12 三条维护原文 URL 仍 HTTP 200。

## Boundary

- Runtime source：当前 repo 代码；历史 2026-07-17 运行产物仍位于旧 release-candidate 的 ignored docs 目录。
- Reports：`/reports`、`/api/v1/reports/*`、Evidence/SourceHealth、11 Agent、Reader/Diagnostics。
- 原产品面继续保留：chat、portfolio、screening、decision signals、alerts、usage、settings、scheduler 和 providers。
- `docs/reports/`、`docs/run_status/`、`docs/agent_memos/`、`docs/market_cycle/`、`docs/daily/`、`docs/index.html` 是生成物，不进源码 review。
- 完整 artifact/Diagnostics/memo/ledger 只在维护面；公开 Pages 只发布 Reader HTML allowlist。
- `.env`、DB、logs、cache、真实凭据不提交。

## Git

```bash
git -C /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812 status --short
git -C /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812 rev-list --left-right --count HEAD...upstream/main
```

发布前先 `git fetch --all --prune`，确认相对记录的 upstream SHA 无新增漂移，再运行 parity matrix。不要把本地 Pages staging、旧 main Network Smoke 或 DMG framework build 当成候选云验收。
