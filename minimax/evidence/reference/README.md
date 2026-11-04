# 参考运行（当前为 replay）

- 生成命令：`.venv/bin/python scripts/demo.py --mode replay --run-id reference-v2`
- 机器核验：`acceptance.json` → 5/6 PASS；第 2 项因未配置 `MINIMAX_API_KEY` 为 FAIL。
- 边界：`minimax/dev-record.jsonl` 明确标记 `mode=replay`，**不能**作为“MiniMax 实际参与”的证据。

正式提交前，配置真实 Key 并运行：

```bash
bash scripts/run_final.sh
```
