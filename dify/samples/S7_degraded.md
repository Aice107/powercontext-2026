# S7 依赖不可用时的兜底

**目的**：证明 seekdb/后端掉线时应用不崩、有可读兜底（工程质量维度）。

## 初始状态
- 应用正常；`inn-api`（8010）或 seekdb（2881）已停止

## 输入
发送：任意一句话（如 `往酒坛里兑水`）

## 预期表现
- `/inn/session` 返回 5xx 或连接失败 → 命中「后端是否可用」的 `true` 分支（`status_code ≥ 400`）
- 输出固定兜底话术：「账本让雨打湿了……」，不返回 500 空白
- 本轮 `workflow_finished.status = partial-succeeded`（节点标 exception，但分支已短路到兜底），仍能看到完整回答
- 恢复依赖后，下一次对话自动回到正常链路（无需重发布 DSL）

## 证据
- `evidence/logs/S7_degraded.log`

## 复现步骤
```bash
# 1. 停掉后端（或 seekdb）
kill $(ss -lntp | awk '/:8010 /{print $NF}' | grep -oE '[0-9]+')
# 2. 跑一轮对话
INN_APP_ID=<app_id> bash tools/run_app.sh "往酒坛里兑水" p_demo01
# 3. 恢复
cd dify/backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 &
```
