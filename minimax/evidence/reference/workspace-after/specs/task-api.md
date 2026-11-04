# TaskHub HTTP API 规格

- 规格版本：v2（新增 SPEC-API-013 截止日期上界筛选）
- 适用范围：`app/` 下的 HTTP 服务与数据访问层
- 变更约定：任何行为变更必须先更新本规格，再修改代码与测试

## 1. 通用约定

### SPEC-API-001 JSON 与状态码

所有接口返回 `application/json`。成功状态码为 200（查询/更新）、201（创建）或 204（删除）。
请求体必须是 JSON 对象；否则返回 400。

### SPEC-API-002 错误格式

错误响应统一为：

```json
{"error": {"code": "invalid_argument", "message": "...", "field": "..."}}
```

- 参数非法：400，`code=invalid_argument`。
- 资源不存在：404，`code=not_found`。

## 2. 任务字段

### SPEC-API-003 字段定义

任务包含 `id`、`title`、`description`、`status`、`priority`、`assignee`、`due_date`、
`created_at`、`updated_at`。

- `title`：必填，非空，最长 200 字符。
- `status`：`todo`、`in_progress`、`done` 之一，默认 `todo`。
- `priority`：`low`、`medium`、`high` 之一，默认 `medium`。
- `assignee`：可空字符串。
- `due_date`：可空，严格 `YYYY-MM-DD`；非法日期返回 400。
- 时间戳使用 UTC ISO 8601。

## 3. 任务列表

### SPEC-API-010 列表入口

`GET /tasks` 返回任务列表与分页元数据：

```json
{"items": [...], "total": 8, "limit": 50, "offset": 0}
```

`items` 按 `id` 升序排列。`total` 是应用筛选后的总数，不受 `limit`/`offset` 影响。

### SPEC-API-011 既有筛选

列表支持以下可选筛选参数，多个条件按 AND 组合：

- `status`：精确匹配状态；非法值返回 400。
- `priority`：精确匹配优先级；非法值返回 400。
- `assignee`：精确匹配负责人。

不传筛选参数时返回全部任务。

### SPEC-API-012 分页

- `limit`：默认 50，范围 1–100；非法值返回 400。
- `offset`：默认 0，必须是非负整数；非法值返回 400。
- 分页元数据必须原样返回实际生效的 `limit` 与 `offset`。

### SPEC-API-013 截止日期上界筛选 due_before

`GET /tasks` 支持可选参数 `due_before=YYYY-MM-DD`，只返回截止日期不晚于该日期的任务。

- 比较是闭区间：截止日期等于 `due_before` 的任务必须包含在结果中（包含截止当天）。
- `due_date` 为空的任务在启用该筛选时一律排除。
- `due_before` 必须与 `status`、`priority`、`assignee`、`limit`、`offset` 按 AND 组合生效；
  `total` 是筛选后的总数。
- 非法日期（格式错误或不存在的日期）返回 400，错误 `code=invalid_argument`，
  `field=due_before`。
- 不传 `due_before` 时行为与 v1 完全一致。

## 4. 单个任务

### SPEC-API-020 读取、更新与删除

- `GET /tasks/<id>`：返回任务；不存在返回 404。
- `PATCH /tasks/<id>`：部分更新；只校验并修改请求中出现的字段；不存在返回 404。
- `DELETE /tasks/<id>`：成功返回 204；不存在返回 404。

### SPEC-API-021 创建

`POST /tasks` 校验字段后创建任务，返回 201 与新任务。创建失败不得写入半条记录。

## 5. 兼容性

### SPEC-API-030 回归保证

本次变更不得改变既有接口的路径、字段名、分页元数据、错误格式与状态码。
`tests/test_tasks_regression.py` 中的断言是必须保持的行为基线。
