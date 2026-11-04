# 六项必做验收状态

> 最近完整运行：`evidence/reference/`（**live MiniMax**，`mode=minimax`）
> 机器核验：`python3 scripts/verify_acceptance.py --run-dir evidence/reference`
> 结论：**6/6 PASS**

| # | 验收项 | 状态 | 证据 | 说明 |
|---|---|---|---|---|
| 1 | 能够运行 | PASS | `evidence/reference/commands.log`、`context-v2.json`、`db-stats.json`、`state-after-restart.json` | `scripts/run_final.sh` 从 baseline 复制工作区，依次完成导入、上下文、补丁、测试、状态保存/重启读取 |
| 2 | MiniMax 实际参与 | PASS | `evidence/reference/minimax/dev-record.jsonl`、`response-1.txt`、`applied.patch` | 真实调用 `MiniMax-M3`（`https://api.minimaxi.com/v1/chat/completions`），记录 usage、延迟、response/patch SHA，补丁成功应用 |
| 3 | 上下文正确且规格更新生效 | PASS | `context-v1.json`、`context-v2.json`、`assert-v1.json`、`assert-v2.json` | v1 不含 SPEC-API-013；更新规格并重新导入后 v2 含该条且正文含“包含截止当天”；来源 sha/行号可回查 |
| 4 | 数据库实际参与 | PASS | `db-version.txt`、`db-stats.json`、`db-queries.log`、`index-v2.json` | seekdb `5.7.25-OceanBase seekdb-v1.4.0.0`；10 sources / 66 chunks / 1993 terms；规格更新只重建 1 个文件 |
| 5 | 状态能够复用 | PASS | `state-save.json`、`state-after-restart.json`、`resume-context.json`、`pc-after-restart.txt` | 保存后重启 PowerContext 与新进程，读回 done/todo/verifications，并注入 `--resume` 上下文 |
| 6 | 代码修改有效 | PASS | `before-target.log`、`after-target.log`、`before-regression.log`、`after-regression.log`、`code-diff.patch` | 修改前目标测试 5 failed（断言失败，非环境错误），回归 12 passed；修改后目标 5 passed、回归 12 passed；测试文件前后逐字一致 |

## 通过条件

六项全部 PASS，得 20 分；任一项不通过得 0 分。本次参考运行六项全部通过。

## 复跑

```bash
cd /home/ice/dify-project/minimax
bash scripts/run_final.sh
```

`run_final.sh` 读取本机 `.env` 中的真实 `MINIMAX_API_KEY`，执行 live MiniMax 调用、测试、状态重启，替换 `evidence/reference/` 并再次核验六项。

无 Key 的离线演示：

```bash
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/run-replay-check
```

replay 运行会明确标记 `mode=replay`，第 2 项为 FAIL；它只用于离线复现其余五项，不能替代真实 MiniMax 调用。
