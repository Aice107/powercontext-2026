# Dify 与 seekdb 的分工

赛题 §2.2 要求"指定技术必须在应用功能或部署运行中实际发挥作用"。本文件逐条说明。

## 1. Dify 承担核心流程编排

| 编排职责 | 对应节点 |
| --- | --- |
| 输入接收 | Start（query + player_id） |
| 读取上下文 | HTTP「读取档案」 |
| 语义判定 | 参数提取器「判定意图」（intent / action_type / severity / target / scene） |
| 条件判断 | IF/ELSE ×4（后端可用性、打烊、闲聊、逐客） |
| 状态与分支决策 | 依据记账返回的 TIER 选择逐客/常规回应 |
| 提示词组装 | 5 个 LLM 节点，各自不同的 system prompt 与档位规则 |
| 结果输出 | Answer ×5（长卷 / 逐客 / 常规 / 闲聊 / 兜底） |
| 异常兜底 | error_strategy + 「后端是否可用」分支 |

## 2. seekdb 承担数据与检索

| 作用 | 触发点 | 可核对材料 |
| --- | --- | --- |
| 玩家档案读写 | 每次进店 | `S1/S4` 日志中的档案块、`S4_db_player.txt` |
| 事件持久化 | 每次恶作剧/善举 | `S2_db_ledger.txt` |
| 向量 + 全文混合检索 | 每次记账后 | `S3_old_grudge.log`、`S3_sql_hybrid.txt` |
| 聚合统计 | 打烊结算 | `S6_settle.log` |
| 台词库检索（语气锚点） | 每次记账后按档位取两句 | `inn_line` 60 条（含 10 条和解句） |

## 3. PowerContext 承担记忆（可选层）

| 作用 | 触发点 | 可核对材料 |
| --- | --- | --- |
| Scope 建档 | 首次进店 / 首次记账 | `inn_pc_scope` 映射行（`S9_pc_scope.txt`） |
| 写"印象" | 每次记账后（kind=`current-state`，善举写 `task-outcome`） | PowerContext `search` 返回（`S9_pc_search.json`） |
| 召回"印象" | 每次进店 | 档案块的 `MEMORY=` 行（`S9_pc_memory.log`） |

只写"印象摘要"（档位 + 最近一次行为 + 仇值），不写对话原文；事件明细只在 seekdb，避免两边打架。

## 3.5 语气锚点（LINES）算谁的活

后端从 `inn_line` 按**本次档位**取两句原话，塞进返回块；Dify 只负责把它拼进 prompt 并要求"借语气不照抄"。

- 为什么不算叙事决策：后端给的是"这个档位的人说过什么"，不是"这次该说什么"；
- 为什么有价值：模型不用猜语气，T3 事件后能自然用上"房钱按三倍算""柴房门上我挂了铃铛"这类句子。

## 4. 边界

- inn-api **不做**语义判定：它不知道"兑水"是不是恶作剧，只知道收到 `severity=2` 就记一笔；
- inn-api **不算**档位：只把 `grudge` 映射成 `TIER` 供分支使用，态度与台词由 Dify 决定；
- seekdb **不存** Dify 的会话/应用数据（Dify 用自己的数据库）；
- PowerContext **不参与**判定与数值：它只回答"三娘怎么看待这个人"；
- 因此删掉 seekdb → 应用失去账本与检索（S7 可验证）；删掉 PowerContext → 只剩"事"没有"人"（记忆层静默跳过，应用仍可用）；删掉 Dify → 应用不存在。
