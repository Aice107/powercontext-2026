# S3 翻旧账（同类事件第二次）

**目的**：证明 seekdb 的**混合检索**结果真的进了台词——NPC 会主动复述旧账。

## 初始状态
- 已完成 S2（`p_guest01` 有 1 条 `drink/2` 记录）

## 输入
发送：`又往酒坛里兑水`

## 预期表现
- 记账块中 `REPEAT=1`（同类事件计数）、`SIM` 不为"无"，且首条命中 S2 那次（同义改写仍能命中）
- `DELTA=14`（12 + 屡教不改加成 2）
- 三娘回应**主动提起上次那笔账**，并评价这次手法/态度

## 证据
- `evidence/logs/S3_old_grudge.log`
- `evidence/logs/S3_sql_hybrid.txt`（同一条 SQL 的 EXPLAIN 与结果）

## 恢复初始状态
`bash db/init.sh`
