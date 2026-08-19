# 本地工作区路由

> Last verified: 2026-08-19 21:11 CST

## 当前代码入口

`/Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812`

这是当前 upstream 同步后的发布候选工作树，分支为 `codex/reports-v1-upstream-sync`。验收代码 SHA `5de0183abf2f` 基于 `upstream/main@cfd6b0a5fb9c`；点时为 ahead 22 / behind 0。原 `/Users/hac/AI-Studio/投研/invest-system-release-candidate` 只保留同步前参考线和 2026-07-17 ignored 运行产物，不再是最终代码入口。

本地 parity、测试和 Git 提交不等于云端发布。线上 Pages 仍是旧 `main:/docs@7a8b4cf8`；2026-08-19 三条维护原文 URL 仍 HTTP 200。候选分支未 push、PR 0，云端 CI workflow 仍为 deleted。

## 目录边界

- Runtime source：当前 repo 代码；历史 2026-07-17 运行产物位于旧 release-candidate 的 ignored docs 目录。
- Runtime environment：当前工作树 `.venv311` 已新鲜安装并用于最终 Python gate、依赖审计和 authenticated Playwright 后端，不再借用旧参考线解释器。
- Runtime local state：`.env`、DB、logs、cache、Node/Python 依赖和生成报告，由 `.gitignore` 保护，不提交。
- Archive：`/Users/hac/AI-Studio/投研/_legacy/invest-system-worktree-archives/20260717/` 与 `_legacy/invest-brain/` 只作历史参考。
- 完整 artifact/Diagnostics/memo/ledger 只在维护面；公开 Pages 只发布 Reader HTML allowlist。
- 两个工作树共享 Git common dir；不要手工删除 `.git` 元数据。清理旧 worktree 属独立动作，最终汇报后另获确认。

## 当前验收边界

- 代码锚点 `5de0183a`：backend `6248 passed`、Agent timeout targeted 536、merge semantic matrix 557、authenticated Playwright `12/12`、Python dependency audit 0。
- Agent 满池 queue stall 已 fail-closed：0.5 秒 cooperative grace 后仅取消未启动 future，返回 queued/non-retriable timeout；红测约 1.21 秒降至 0.60 秒，本地代码复审 P0/P1 为 0。
- Playwright 使用真实本地 login/backend 与临时 DB，但 Chat/report API 是 hermetic fixture；不证明真实 LLM/provider 或生产链。
- Web 代码本轮未变；沿用 Vitest `1108/2`、lint、TypeScript、build 和 audit 0 证据。
- Desktop 代码本轮未变；仅验证 Electron `41.10.3` / Node `22.12.0` 下 50/50 tests、audit 0 和未签名 DMG 框架；缺 backend bundle、Windows、签名和公证。
- Pages 21/30 与 staging 11/19 是当前 validator 对 **2026-07-17 历史产物**的重跑，不是 `5de0183a` 新生成日报。
- Docker daemon/compose config 通过，但 build 卡在 `docker/dockerfile:1.7` frontend；无镜像、import 或 health smoke。
- Network Smoke #59 的 success 仍是旧 main false-green，不得当候选验收。

## 常用核验

```bash
git -C /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812 status --short
git -C /Users/hac/AI-Studio/投研/invest-system-upstream-sync-20260812 rev-list --left-right --count HEAD...upstream/main
```

发布前先 `git fetch --all --prune`，确认相对记录的 upstream SHA 无新增漂移，再运行 parity matrix。不要把本地 Pages staging、旧 main Network Smoke 或 DMG framework build 当成候选云验收。
