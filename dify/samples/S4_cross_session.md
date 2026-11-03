# S4 跨会话记忆（新会话，同玩家）

**目的**：证明记忆**不在** Dify 会话窗口里，而在 seekdb 账本里。

## 初始状态
- 演示玩家 `p_demo01`，3 天前建档，账本 7 条（含"往酒坛里兑了半坛井水""掀了半张桌子"）

## 输入
1. **新建一个会话**（不要沿用 S2/S3 的对话）
2. 玩家标识填：`p_demo01`
3. 发送：`三娘，我回来了`

## 预期表现
- 档案块立刻带出 `GRUDGE=62 TIER=3 DAYS=3 RECENT=掀了半张桌子(5级,1天前);...`
- 三娘回应直接点名旧事（"又来了"），不需要玩家提示
- 说明：`p_demo01` 的跨会话状态来自 seekdb，而不是当前对话历史

## 证据
- `evidence/logs/S4_cross_session.log`
- `evidence/logs/S4_db_player.txt`（`visits/days_known/total_events` 与档案块一致）

## 恢复初始状态
`bash db/init.sh`
