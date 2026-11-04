# S7b PowerContext 不可用时的降级

**目的**：证明记忆层是"可选增强"，不是单点依赖——PC 挂了应用照常玩。

## 初始状态
- seekdb / inn-api / Dify 正常；PowerContext（:8090）**已停止**

## 输入
1. PC 停止时发送：`往酒坛里兑半坛水`
2. 恢复 PC 后发送：`三娘，我回来了`

## 预期表现

| 阶段 | 档案块 | 应用行为 |
| --- | --- | --- |
| PC 停止 | `MEMORY=无` | 仍正常记账、翻旧账、回应（`workflow succeeded`） |
| PC 恢复 | `MEMORY=柳三娘对陈三的印象：逐客…` | 记忆注入 prompt，回应带"她记得你这个人"的底色 |

实现上：`backend/app/pc.py` 3 秒超时 + 异常吞掉，只记 warning，不阻塞记账主链路。

## 证据
- `evidence/logs/S7b_pc_down.log`（两阶段对照）
- inn-api 日志里的 `powercontext ... failed` warning

## 注意
PowerContext 的记忆库与 seekdb 账本是**两套存储**：只跑 `db/init.sh` 不会清 PC 记忆，
可能出现"账本仇值 62、记忆里写着 92"。要两者一起重置用 `bash tools/reset-demo.sh`。

## 恢复初始状态
`bash tools/reset-demo.sh`
