# S9 PowerContext 记忆（印象层）

**目的**：证明 PowerContext 不是"装了没用"，而是真的保存并复用了对玩家的印象。

## 初始状态
- PowerContext Server 已启动（`PC_BASE_URL=http://127.0.0.1:8090`），`inn_pc_scope` 为空
- `p_demo01` 账本已有 7 条旧账，仇值 62

## 输入（按顺序）
1. 任意一次恶作剧：`往酒坛里兑水`
2. 再次进店：`三娘，我回来了`

## 预期表现
- 第 1 步后：`inn_pc_scope` 出现 `p_demo01 -> scp_xxx`；PowerContext 里出现一条 `current-state` 记忆
- 第 2 步的档案块多出一行 `MEMORY=柳三娘对陈三（p_demo01）的印象：…仇值 76。`
- 该行随档案块进入「三娘回应」的 system prompt，因此回应会体现"她记得你这个人的整体印象"，
  而不只是复述某一笔账

## 证据
- `evidence/logs/S9_pc_memory.log`（两次调用的节点输出）
- `evidence/logs/S9_pc_scope.txt`（`inn_pc_scope` 映射行）
- `evidence/logs/S9_pc_search.json`（直接调用 PowerContext 的 search 响应）

## 复现步骤
```bash
# 1. 起 PC（sqlite 后端，无需外部依赖）
powercontext server run --host 127.0.0.1 --port 8090 --env-file ../.pc/pc.env
# 2. 起 inn-api 时带 PC_BASE_URL
# 3. 跑 S9 两步
INN_APP_ID=<app_id> bash tools/run_app.sh "往酒坛里兑水" p_demo01
INN_APP_ID=<app_id> bash tools/run_app.sh "三娘，我回来了" p_demo01
```

## 恢复初始状态
```bash
rm -f ../.pc/pc.db          # 清空 PC 记忆（sqlite 文件后端）
mysql -h127.0.0.1 -P2891 -uroot -e "DELETE FROM inn.inn_pc_scope;"
bash db/init.sh
```
