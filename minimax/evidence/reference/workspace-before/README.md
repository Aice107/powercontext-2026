# TaskHub（验证用业务工程）

一个最小但真实的 Flask + SQLite 任务管理服务，用于 SDD 上下文模块的端到端验证。

## 运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app --db taskhub.sqlite3 --port 8011
curl http://127.0.0.1:8011/tasks
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| GET | `/tasks` | 列表；支持 `status`、`priority`、`assignee`、`limit`、`offset` |
| POST | `/tasks` | 创建；必填 `title`，可选 `description/status/priority/assignee/due_date` |
| GET | `/tasks/<id>` | 详情；不存在返回 404 JSON |
| PATCH | `/tasks/<id>` | 部分更新 |
| DELETE | `/tasks/<id>` | 删除；成功 204 |

错误格式：

```json
{"error": {"code": "invalid_argument", "message": "...", "field": "..."}}
```

## 测试

```bash
python -m pytest -q
```

`tests/test_tasks_regression.py` 锁定既有行为；`tests/test_due_before.py` 是本任务的目标测试。
