# 运行证据

- `reference/`：随仓库提交的参考运行证据（当前为 `mode=replay`，第 2 项 MiniMax 实际参与为 FAIL；用于审阅其余五项与完整流程）。
- `run-*/`：本地运行产物，已被 `.gitignore` 忽略；正式提交前用真实 MiniMax 运行 `evidence/run-final/` 并替换 `reference/`。

每个运行的入口是 `acceptance.json` 与 `summary.json`；`commands.log` 记录每步命令、退出码、耗时与日志文件。
