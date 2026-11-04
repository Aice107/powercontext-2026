# 验证样例说明

## 1. 任务描述

样例任务见 [validation/task.md](../validation/task.md)：

> 为 TaskHub 的 `GET /tasks` 增加可选 `due_before=YYYY-MM-DD` 截止日期上界筛选。
> 闭区间（包含截止当天）；与 `status`、`priority`、`assignee`、`limit`、`offset` 组合；
> 无 `due_date` 的任务排除；非法日期返回 400 `invalid_argument`；既有行为不变。

- 业务工程：`demo/baseline`（修改前）/ `demo/business`（修改后）
- 目标测试：`tests/test_due_before.py`（前后逐字相同）
- 回归测试：`tests/test_tasks_regression.py`（前后逐字相同）
- 代码补丁：`patches/0001-due-before-filter.patch`
- 规格更新补丁：`patches/0002-spec-due-before.patch`

## 2. 有效规格

`demo/baseline/specs/task-api.md` 是 v1，包含 SPEC-API-001/002/003/010/011/012/020/021/030，不含 due_before 条款。

`demo/business/specs/task-api.md` 是 v2，新增：

```text
SPEC-API-013 截止日期上界筛选 due_before
- 闭区间，包含截止当天
- due_date 为空的任务排除
- 与 status/priority/assignee/limit/offset 按 AND 组合
- 非法日期 400 invalid_argument，field=due_before
- 不传 due_before 时与 v1 完全一致
```

规格更新补丁只改 `specs/task-api.md`，不改代码或测试。

## 3. 初始数据

TaskHub 启动时向 SQLite 写入 8 条确定性种子任务（见 `app/store.py::SEED_TASKS`），覆盖：

- 有/无 `due_date`；
- 三种 `status`、三种 `priority`、三个 `assignee`；
- 边界日期 2026-01-31 与 2026-02-01；
- 用于分页的 id 1..8。

## 4. 操作步骤

### 4.1 一键运行

```bash
cd minimax
bash scripts/bootstrap.sh
bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start

# 回放（不需要 MiniMax Key；第 2 项为 FAIL）
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check

# 真实 MiniMax（需要 Key；六项全 PASS）
.venv/bin/python scripts/demo.py --mode minimax --run-id final
```

`scripts/demo.py` 的实际顺序：

1. 记录环境与版本。
2. 重置 `.runtime/seekdb` 并启动 seekdb；启动 PowerContext。
3. 复制 `demo/baseline` 到运行工作区。
4. `index` 导入 v1；`context` 生成上下文；断言**不含** SPEC-API-013。
5. 应用 `patches/0002-spec-due-before.patch`；重新 `index`；`context`；断言**包含** SPEC-API-013 且含“包含截止当天”。
6. 运行修改前目标测试（预期失败）与回归测试（预期通过）。
7. 用上下文调用 MiniMax（或回放 `patches/0001-due-before-filter.patch`）生成/应用补丁。
8. 运行修改后目标测试与回归测试（预期通过）。
9. 把任务状态写入 PowerContext；`pc_server.sh restart`；新进程 `state-load` 与 `context --resume`。
10. 生成 `code-diff.patch`、`db-stats.json`、`summary.json`、`acceptance.json`。

### 4.2 手工最小验证（只验证上下文）

```bash
cp -a demo/baseline .runtime/manual-workspace
.venv/bin/python -m sdd_context --seekdb-port 2893 index --workspace .runtime/manual-workspace
.venv/bin/python -m sdd_context --seekdb-port 2893 context \
  --workspace .runtime/manual-workspace \
  --task-file validation/task.md \
  --task-id taskhub-due-before \
  --out .runtime/manual-v1.json --md .runtime/manual-v1.md

# 更新规格并重新导入
patch -p1 -d .runtime/manual-workspace -i patches/0002-spec-due-before.patch
.venv/bin/python -m sdd_context --seekdb-port 2893 index --workspace .runtime/manual-workspace
.venv/bin/python -m sdd_context --seekdb-port 2893 context \
  --workspace .runtime/manual-workspace \
  --task-file validation/task.md \
  --task-id taskhub-due-before \
  --out .runtime/manual-v2.json --md .runtime/manual-v2.md

python scripts/assert_context.py --context .runtime/manual-v1.json --forbid-spec SPEC-API-013
python scripts/assert_context.py --context .runtime/manual-v2.json \
  --require-spec SPEC-API-013 --require-text '包含截止当天'
```

## 5. 预期结果

| 检查 | 预期 |
|---|---|
| v1 上下文 | 不含 SPEC-API-013；包含 `app/store.py::list_tasks`、`tests/test_due_before.py::*` |
| 重新导入 | 仅 1 个文件重建索引（spec），9 个文件 skipped；旧 spec chunks/terms 被删除 |
| v2 上下文 | 含 SPEC-API-013，正文含“包含截止当天”；来源 sha/行号可回查 |
| 修改前目标测试 | `5 failed`，失败原因是任务行为未实现（断言失败），不是 ImportError/collection error |
| 修改前回归测试 | `12 passed` |
| 修改后目标测试 | `5 passed` |
| 修改后回归测试 | `12 passed` |
| 测试文件 | 前后 `tests/` 内容逐字一致 |
| 代码差异 | `code-diff.patch` 只改 `app/api.py`、`app/store.py` |
| 状态复用 | PowerContext 重启后读回 done/todo/verifications；`--resume` 上下文含相同进展 |
| 数据库 | sources=10、chunks=66、terms>0；`db-queries.log` 有 `FROM terms` 与写入 SQL |

## 6. 预期上下文必要来源

见 [validation/expected-context.json](../validation/expected-context.json)。关键来源：

- 规格：`specs/task-api.md` → `SPEC-API-013`（v2）
- 代码：`app/store.py::list_tasks`、`app/api.py::create_app`
- 测试：`tests/test_due_before.py::test_due_before_includes_boundary_day` 等 5 条；
  `tests/test_tasks_regression.py::test_list_returns_seed_rows_and_pagination_metadata` 等回归用例

## 7. 重置方法

```bash
cd minimax
bash scripts/seekdb_server.sh reset       # 清空工程索引
bash scripts/pc_server.sh stop            # 如需清空 PowerContext 状态
rm -rf .runtime/pc
bash scripts/pc_server.sh start
rm -rf .runtime/demo-* evidence/run-replay-check evidence/run-final
```

只重置工作区、不清数据库：

```bash
rm -rf .runtime/demo-* && cp -a demo/baseline .runtime/manual-workspace
```

## 8. 证据位置

每次运行写入 `evidence/run-<id>/`：

| 文件 | 内容 |
|---|---|
| `commands.log` | 每步命令、cwd、退出码、耗时、日志 |
| `index-v1.json` / `index-v2.json` | 导入文件数、chunks、terms、db 统计 |
| `context-v1.json` / `context-v2.json` | 两次上下文（v1 无 013，v2 有 013） |
| `assert-v1.json` / `assert-v2.json` | 必要/禁止来源断言 |
| `before-target.log` / `after-target.log` | 目标测试日志（命令、退出码、断言） |
| `before-regression.log` / `after-regression.log` | 回归测试日志 |
| `db-version.txt` | seekdb 版本（`SELECT VERSION()`） |
| `db-queries.log` | seekdb SQL（含参数、行数、耗时） |
| `state-save.json` / `state-after-restart.json` / `resume-context.json` | PowerContext 保存、重启读取、复用上下文 |
| `minimax/dev-record.jsonl` / `prompt.md` / `response-*.txt` / `applied.patch` | MiniMax 开发记录（replay 时 `mode=replay`） |
| `code-diff.patch` | 修改前后代码差异 |
| `acceptance.json` | 六项机器核验 |

`evidence/reference/` 保存一次可审阅的 **live MiniMax** 参考运行（`MiniMax-M3`，6/6 PASS）；`--mode replay` 仅用于无 Key 的离线复现，第 2 项会标记 FAIL。
