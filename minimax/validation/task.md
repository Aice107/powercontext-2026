# 为 TaskHub 列表接口增加 due_before 截止日期筛选

## 任务

在 TaskHub 服务中，为 `GET /tasks` 增加可选的 `due_before=YYYY-MM-DD` 截止日期上界筛选。
调用方传入该参数时，只返回截止日期不晚于该日期的任务。

## 要改什么

- 筛选是闭区间：截止日期等于 `due_before` 的任务必须包含在结果中（包含截止当天）。
- `due_date` 为空的任务在启用该筛选时必须排除。
- `due_before` 必须与既有 `status`、`priority`、`assignee` 筛选以及 `limit`/`offset` 分页按 AND 组合生效，
  `total` 返回筛选后的总数。
- 非法日期（格式错误或 2026-02-30 这类不存在的日期）返回 400，错误 `code=invalid_argument`，
  `field=due_before`。
- 不传 `due_before` 时，既有列表行为、分页元数据、错误格式与状态码完全不变。

## 哪些原有行为必须保持

- `GET /tasks` 不传筛选参数时仍返回全部 8 条种子任务，按 id 升序。
- `status`、`priority`、`assignee` 筛选与分页仍然正确。
- 创建、读取、更新、删除任务的行为与错误格式不变。
- `tests/test_tasks_regression.py` 中的所有断言必须继续通过。
