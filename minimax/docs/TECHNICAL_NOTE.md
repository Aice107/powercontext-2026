# 一页技术说明

## 模块结构

```text
sdd_context CLI
├── ingest.py     规格 Markdown / Python AST / 测试 AST → chunks
├── db.py         seekdb（MySQL 协议）sources/chunks/terms/import_events
├── retrieval.py  词项 SQL → BM25 → 按 spec_id/符号/测试名去重
├── context.py    组装 sdd-context/v1 JSON 与 MiniMax 可读 Markdown
├── minimax.py    prompt、HTTP 调用、diff 校验/应用、开发记录
├── testrunner.py pytest 命令/退出码/摘要/日志
└── state.py      PowerContext Scope + Memory（SDD_TASK_STATE_V1）
```

调用入口是 `python -m sdd_context`（安装后为 `sdd-context`），支持 `index`、`context`、`state-save`、`state-load`、`status`、`test`、`minimax`、`apply-patch`、`db-stats`。输入任务是一个 Markdown 文件；输出为 `sdd-context/v1` JSON 和 Markdown。

## 上下文选择方式

1. **切块**：规格按 `SPEC-XXX-NNN` 标题切；代码按 AST 的函数/类/方法切；测试按 `test_*` 函数切，块保留真实路径与起止行。
2. **索引**：`sources` 存文件级 sha256；`chunks` 存块正文、符号、spec_id、行号；`terms` 存倒排词频。按 path 哈希幂等替换，规格更新后旧块先删后写。
3. **查询**：任务文本经 ASCII 标识符拆分、中文 2-gram、领域同义词扩展（筛选→filter、截止→due、包含→inclusive 等）后，用一条 SQL 从 `terms` 取候选块，再用 SQL 统计 df，计算 BM25（k1=1.2，b=0.75）。
4. **组装**：按 spec/code/test 去重取 Top-K，输出正文、路径、行号、sha256、匹配词和分数；缺类别时写 `warnings`，不编造来源。
5. **规格更新**：重新导入时只重建 sha256 变化的文件；验证脚本断言 v1 无 `SPEC-API-013`、v2 有且正文为更新后的“包含截止当天”。

## 三项技术的分工

| 技术 | 实际承担的工作 | 证据 |
|---|---|---|
| MiniMax | 接收任务 + 上下文 Markdown，生成 unified diff；模块校验、应用并记录 usage/延迟/patch SHA | `evidence/run-*/minimax/dev-record.jsonl`、`response-*.txt`、`applied.patch` |
| seekdb 1.4.0 | 存工程资料、切块、倒排索引；所有检索与写入走 SQL；规格更新只重建变化文件 | `db-stats.json`、`db-queries.log`、`index-v2.json` |
| PowerContext 1.4.1 | 以 `sdd-task-state` Memory 保存任务 done/todo/verifications；重启后按 task_id 读回并注入 `--resume` 上下文 | `state-save.json`、`state-after-restart.json`、`resume-context.json` |

## 业务样例与修改

TaskHub 是 Flask + SQLite 的任务管理服务，含 12 条回归测试与 5 条目标测试。修改为 `GET /tasks` 增加 `due_before` 闭区间筛选、非法日期 400、与既有筛选/分页组合、无日期任务排除。修改前目标测试因行为缺失断言失败；修改后目标与回归全部通过，测试文件未改动。

## 边界

- 只恢复任务状态，不恢复完整 Agent 会话（题面允许）。
- 不依赖向量模型；中文检索用 2-gram + 同义词。
- 无 `MINIMAX_API_KEY` 时拒绝伪造，`minimax` 命令失败并写 `BLOCKED.json`；`--patch-file` 只用于回放验证，记录明确标记 `mode=replay`，不计入“MiniMax 实际参与”。
