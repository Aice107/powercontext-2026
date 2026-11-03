# S2 单次恶作剧记账

**目的**：证明"输入 → 判定 → 记一笔账 → 按档位回应"的主链路。

## 初始状态
- `p_guest01` 已建档，`grudge=0`，账本 0 条

## 输入
发送：`往酒坛里兑半坛水`

## 预期表现
- 判定为 `prank / drink / severity=2`
- seekdb 新增 1 条账本，`DELTA=12`，`GRUDGE=12`，`TIER=0`
- 三娘回应里出现**账本批注**（如"七月廿六，兑水半坛，记一笔"），并按和善档位给一次警告
- 返回体不是 500，且 `workflow` 状态为 succeeded

## 证据
- `evidence/logs/S2_prank.log`（含记账块 `EVENT/TYPE/SEV/DELTA/REPEAT/GRUDGE/TIER`）
- `evidence/logs/S2_db_ledger.txt`（该玩家的账本行）

## 恢复初始状态
`bash db/init.sh`，或换一个新的 `player_id`
