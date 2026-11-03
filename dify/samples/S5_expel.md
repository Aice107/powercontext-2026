# S5 屡教不改 → 逐客（条件分支）

**目的**：证明 Dify 的 IF/ELSE 分支按 seekdb 返回值真实改变走向。

## 初始状态
- `p_demo01` 已 `grudge=62`（T3），账本 7 条

## 输入
依次发送：
1. `往酒坛里兑半坛水`（T3 → grudge 76）
2. `再往酒坛里兑水`（grudge 92）
3. `掀了桌子`（violence/5 → 触顶 100）

## 预期表现
- 演示玩家初始仇值 62，前两次恶作剧后约 76 → 90，**第 2~3 次记账块即出现 `TIER=4`**（每次 +12~18）；
- 「是否逐客」节点命中 `true`，走「逐客令」LLM 节点而不是常规回应；
- 逐客词里必须引用账本里最重的一笔旧账（来自 `SIM`），并交代行李与账款。

## 证据
- `evidence/logs/S5_expel.log`
- `evidence/logs/S5_nodes.txt`（节点执行序列，含 if-else 的 selected_case_id）

## 恢复初始状态
`bash db/init.sh`
