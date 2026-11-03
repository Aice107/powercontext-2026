# S1 首次入店（冷启动）

**目的**：证明空账本也能正常开张，且玩家标识自动建档。

## 初始状态
- seekdb 中不存在 `p_guest01`（可用 `SELECT * FROM inn_player WHERE player_id='p_guest01'` 复核，返回空）

## 输入
1. 打开应用《记仇客栈》
2. 玩家标识留空（或填 `p_guest01`）
3. 发送：`我来了`

## 操作步骤
1. 首次进入会看到开场白与四个建议问题；
2. 直接发送上述输入。

## 预期表现
- 三娘用招待口吻回应（TIER=0 和善），不提旧账（账本是空的）；
- 后端 `/inn/session` 返回 200，建档 `GRUDGE=0 TIER=0 EVENTS=0 RECENT=无`；
- 判定节点判为 `chat`，不产生账本记录（`inn_ledger` 行数不变）。

## 证据
- `evidence/logs/S1_first_visit.log`
- `evidence/logs/S1_db_after.txt`（事件数仍为 0）

## 恢复初始状态
`bash db/init.sh`（会清掉演示玩家之外的临时玩家）
