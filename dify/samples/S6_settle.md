# S6 打烊结算（《账本长卷》与结局）

**目的**：证明结算聚合与结局判定走的是真实账本数据。

## 初始状态
- `p_demo01`：7 条事件、仇值 62、3 天 4 次住店

## 输入
发送：`打烊，结账`

## 预期表现
- `/inn/settle?format=block` 返回 `EVENTS/ATTACK/REPAIR/VISITS/DAYS/TOP/RUMORS`
- 若演示玩家有传闻，长卷里会引用（`RUMORS` 非"无"）
- 「是否打烊」分支命中 `true`
- 输出一份《账本长卷》：逐条念 TOP 账目、给总评、给结局判词（本例应为"相忘于江湖"或"逐客令"）

## 证据
- `evidence/logs/S6_settle.log`

## 恢复初始状态
`bash db/init.sh`
