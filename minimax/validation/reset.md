# 重置方法

## 完全重置（推荐用于评审复跑）

```bash
cd minimax
bash scripts/pc_server.sh stop
bash scripts/seekdb_server.sh stop
rm -rf .runtime
rm -rf evidence/run-final
bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start
```

`rm -rf .runtime` 会删除 seekdb 数据、PowerContext SQLite 数据、工作区副本与临时日志；不会删除源码、规格、测试或补丁。

## 只重置运行工作区

```bash
rm -rf .runtime/demo-* .runtime/manual-workspace
cp -a demo/baseline .runtime/manual-workspace
```

## 只重置 PowerContext 任务状态

```bash
bash scripts/pc_server.sh stop
rm -rf .runtime/pc
bash scripts/pc_server.sh start
```

## 只重置 seekdb 工程索引

```bash
bash scripts/seekdb_server.sh reset
```

`reset` 会停止服务、清空 `.runtime/seekdb` 并重启；之后需要重新执行 `index`。

## 重新生成证据

```bash
# 回放（5/6，离线）
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check

# 真实 MiniMax（6/6，需要 Key）
.venv/bin/python scripts/demo.py --mode minimax --run-id final
```

每次运行使用新的 `--run-id`，不会覆盖已有证据；确认无误后将 `evidence/run-final/` 复制为 `evidence/reference/`。
