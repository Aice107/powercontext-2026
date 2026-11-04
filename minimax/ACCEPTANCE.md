# 六项必做验收状态

> 最近一次完整运行：`evidence/run-test-replay2/`（mode=replay）
> 机器核验：`python3 scripts/verify_acceptance.py --run-dir evidence/run-test-replay2`

| # | 验收项 | 状态 | 证据 | 说明 |
|---|---|---|---|---|
| 1 | 能够运行 | PASS | `evidence/run-test-replay2/commands.log`、`context-v2.json`、`db-stats.json`、`state-after-restart.json` | `scripts/demo.py` 从 baseline 复制工作区，依次完成导入、上下文、补丁、测试、状态保存/重启读取 |
| 2 | MiniMax 实际参与 | **BLOCKED** | `evidence/run-test-replay2/minimax/dev-record.jsonl` | 当前只有 `mode=replay` 记录；需配置真实 `MINIMAX_API_KEY` 后重跑 `--mode minimax` |
| 3 | 上下文正确且规格更新生效 | PASS | `context-v1.json`、`context-v2.json`、`assert-v1.json`、`assert-v2.json` | v1 不含 SPEC-API-013；更新规格并重新导入后 v2 含该条且正文含“包含截止当天”；来源 sha/行号可回查 |
| 4 | 数据库实际参与 | PASS | `db-stats.json`、`db-queries.log`、`index-v2.json` | seekdb 中 10 sources / 66 chunks / 1993 terms；检索 SQL 与写入 SQL 均有记录；规格更新只重建 1 个文件 |
| 5 | 状态能够复用 | PASS | `state-save.json`、`state-after-restart.json`、`resume-context.json`、`pc-after-restart.txt` | 保存后重启 PowerContext 与新进程，读回 done/todo/verifications，并注入 `--resume` 上下文 |
| 6 | 代码修改有效 | PASS | `before-target.log`、`after-target.log`、`before-regression.log`、`after-regression.log`、`code-diff.patch` | 修改前目标测试 5 failed（断言失败，非环境错误），回归 12 passed；修改后目标 5 passed、回归 12 passed；测试文件前后逐字一致 |

## 通过条件

六项全部 PASS 才得 20 分；任一项不通过得 0 分。第 2 项当前为阻塞项，不能用 replay 记录替代真实 MiniMax 调用。

## 解除阻塞

```bash
cd /home/ice/dify-project/minimax
printf 'MINIMAX_API_KEY=%s\n' '真实 Key' > .env
chmod 600 .env
.venv/bin/python scripts/demo.py --mode minimax --run-id final
```

完成后把 `evidence/run-final/` 复制为 `evidence/reference/`，并确认：

```bash
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/run-final
```
