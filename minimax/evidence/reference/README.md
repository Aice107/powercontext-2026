# 参考运行（live MiniMax）

- 生成命令：`.venv/bin/python scripts/demo.py --mode minimax --run-id final`
- 模型：`MiniMax-M3`；端点：`https://api.minimaxi.com/v1/chat/completions`。
本目录的 `minimax/dev-record.jsonl` 包含 `mode=minimax`、`applied=true` 的真实记录。
- 机器核验：`.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/reference` → 6/6 PASS。
