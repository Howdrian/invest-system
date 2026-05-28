# Repo Hygiene Checklist

> 用途：本地分享、推送、交接、让外部环境读取代码前，先防止密钥、缓存、模型、运行产物和保护文件误入版本库。这里不配置云端运行。

## 先看结论

- 代码、文档、轻量测试可以进入仓库。
- 密钥、broker 配置、缓存、模型、venv、日志、数据库、本地完整运行归档不要进入仓库。
- 保护文件默认不改；如果 diff 出现，必须确认是否真的进入交易流程。

## 检查项

### 1. 保护文件 diff

必须为空，除非用户明确进入真实交易写回流程：

```bash
git diff -- state/portfolio.md trades/trade-log.md agents/scoring-card.md agents/red-team-protocol.md
```

### 2. 密钥和本地身份

不要提交：

- `.env` / `.env.*`
- API key / token / broker credential
- service account json
- 私钥、证书、cookie、session

### 3. 大文件和运行产物

不要提交：

- `venv/`、`.venv/`
- `research/cache/`
- `integrations/**/.cache/`
- `integrations/**/models/`
- `integrations/**/checkpoints/`
- `*.pt`、`*.pth`、`*.ckpt`、`*.safetensors`
- `*.db`、`*.sqlite`、`*.sqlite3`
- `logs/`、`*.log`、`tmp/`

### 4. 投研归档

`research/archive/` 可以保存研究事实，但不要无筛选全量上传超大历史产物。需要分享时优先保留：

- 代表性 `summary.md`
- `00_one_screen_brief.html`
- 架构审计报告
- 小体积 JSON 样例

### 5. 外部项目和模型

外部 repo、模型权重和下载缓存不要 vendor 进本仓库。保留 adapter、README、status、测试和 pinned revision 说明即可。

## 最小本地检查流程

```bash
git status --short
git diff -- state/portfolio.md trades/trade-log.md agents/scoring-card.md agents/red-team-protocol.md
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s integrations -p 'test_*.py'
python3 scripts/architecture_audit.py --cycle-dir research/archive/2026-05-17-research-cycle-v4 --topic repo-hygiene-audit
```

## 判断标准

- 保护文件无 diff。
- 测试通过。
- 架构审计 PASS。
- `git status` 里没有密钥、缓存、模型、venv、日志、数据库。
