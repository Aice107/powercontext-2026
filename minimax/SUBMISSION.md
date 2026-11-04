# 提交清单与复核入口

- 仓库：`powercontext-2026`
- 分支：`2026-competition-ecosystem`
- 资产目录：`minimax/`
- 最终 commit：以本目录所在分支的 `git log -1 --format=%H` 为准（本文件随代码一起提交）

## 1. 材料对照

| 赛题要求 | 本目录文件 |
|---|---|
| 完整源码 | `src/sdd_context/`、`scripts/`、`pyproject.toml`、`uv.lock` |
| 运行说明 | `README.md`（依赖、配置、初始化、调用入口、测试、已知限制） |
| 验证样例 | `validation/task.md`、`validation/expected-context.json`、`validation/reset.md`、`demo/baseline`、`demo/business` |
| 代码与测试 | `demo/baseline`（修改前）、`demo/business`（修改后）、`patches/0001-due-before-filter.patch`、`patches/0002-spec-due-before.patch`、`evidence/reference/code-diff.patch`、`evidence/reference/*target*.log`、`evidence/reference/*regression*.log` |
| 技术使用记录 | `evidence/reference/minimax/dev-record.jsonl`（live `MiniMax-M3`）、`evidence/reference/db-queries.log`、`state-save.json`、`state-after-restart.json` |
| 一页技术说明 | `docs/TECHNICAL_NOTE.md` |
| 六项验收 | `ACCEPTANCE.md`、`evidence/reference/acceptance.json` |

## 2. 复现命令

```bash
cd minimax
bash scripts/bootstrap.sh
bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start

# 真实 MiniMax（6/6；需要本机 .env 中的 Key）
bash scripts/run_final.sh

# 机器核验
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/reference

# 无 Key 的离线回放（5/6；第 2 项明确 FAIL）
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check
```

## 3. 当前状态

`evidence/reference/` 是一次完整的 **live MiniMax** 运行：

- 模型：`MiniMax-M3`
- 端点：`https://api.minimaxi.com/v1/chat/completions`
- 记录：`mode=minimax`、`applied=true`、usage/延迟/response SHA/patch SHA 完整
- 验收：`acceptance.json` → **6/6 PASS**

> 仓库不包含任何真实凭据；`.env` 被 `.gitignore` 排除。复跑需要在本机 `.env` 中提供 `MINIMAX_API_KEY`。

## 4. 说明

- `patches/0001` 只改 `app/`，不改 `tests/`/`specs/`；目标测试前后逐字一致。
- `evidence/reference/` 中的绝对路径来自本机运行，不影响从源码复现。
- 上下文模块的补丁应用器会按补丁正文做上下文匹配，修复 LLM diff 行号偏移；仍只允许 `app/` 路径。

## 5. 远端提交

本机已配置 `submission` 远端：

```text
submission  https://github.com/Aice107/powercontext-2026.git
```

本地分支 `2026-competition-ecosystem` 已包含全部提交；本机没有可用的 GitHub 推送凭据
（HTTPS 无 credential helper，SSH 无 key），因此尚未推送。请在具备凭据的环境执行：

```bash
cd /home/ice/dify-project
git push submission 2026-competition-ecosystem
```

推送后核对：

```bash
git ls-remote submission refs/heads/2026-competition-ecosystem
git rev-parse HEAD
```

两个 SHA 应一致；平台提交时使用该完整 40 位 SHA。
