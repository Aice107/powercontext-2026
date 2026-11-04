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
| 技术使用记录 | `evidence/reference/db-queries.log`、`state-save.json`、`state-after-restart.json`、`minimax/dev-record.jsonl`（当前为 replay，见第 3 节） |
| 一页技术说明 | `docs/TECHNICAL_NOTE.md` |
| 六项验收 | `ACCEPTANCE.md`、`evidence/reference/acceptance.json` |

## 2. 复现命令

```bash
cd minimax
bash scripts/bootstrap.sh
bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start

# 离线回放（5/6；第 2 项明确 FAIL）
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/run-replay-check

# 真实 MiniMax（6/6；需要 Key）
.venv/bin/python scripts/demo.py --mode minimax --run-id final
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/run-final
```

## 3. 当前状态与唯一阻塞

当前 `evidence/reference/` 是 clean 流程的 **replay** 运行：1/3/4/5/6 五项 PASS，第 2 项因未配置真实 `MINIMAX_API_KEY` 为 FAIL。`minimax/dev-record.jsonl` 明确标记 `mode=replay`，不会冒充真实调用。

完成第 2 项：

```bash
cd minimax
printf 'MINIMAX_API_KEY=%s\n' '真实 Token Plan Key' > .env
chmod 600 .env
.venv/bin/python scripts/demo.py --mode minimax --run-id final
cp -a evidence/run-final/. evidence/reference/
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/reference
```

预期输出：`OVERALL: PASS`，六项全部 `[PASS]`。

## 4. 说明

- 不提交真实凭据；`.env` 被 `.gitignore` 忽略。
- `patches/0001` 只改 `app/`，不改 `tests/`/`specs/`；目标测试前后逐字一致。
- `evidence/reference/` 中的绝对路径来自本机运行，不影响从源码复现。
