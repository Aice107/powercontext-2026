# 设计说明

## 1. 数据模型

| 表 | 关键字段 | 作用 |
| --- | --- | --- |
| `inn_player` | `player_id`, `grudge`, `visits`, `days_known`, `total_events`, `last_session_id` | 玩家档案与仇值权威来源 |
| `inn_ledger` | `action_text`, `action_type`, `severity`, `grudge_after`, `embedding VECTOR(1024)` | 事件事实 + 检索源（向量索引 + ngram 全文索引） |
| `inn_rumor` | `rumor_text`, `spread`, `embedding` | 传闻（由高严重度事件派生） |
| `inn_line` | `tier`, `scene`, `tone`, `text` | 台词库，给 LLM 提供语气锚点 |
| `inn_daily` | `player_id`, `day`, `events`, `delta` | 预留的日报聚合 |

## 2. 仇值规则（`backend/app/rules.py`）

```
severity >= 1 : delta = severity*6 + min(同类事件历史次数, 3)*2
severity <= -1: delta = severity*8         # 善举，降仇值
grudge = clamp(0, 100, grudge + delta)
```

档位映射（纯函数，供 Dify 分支使用）：

```
grudge >= 80 → 4 逐客
grudge >= 60 → 3 报复
grudge >= 40 → 2 冷脸
grudge >= 20 → 1 戒备
否则          → 0 和善
```

## 3. 混合检索（翻旧账）

```sql
SELECT id, action_text, severity, created_at,
       COSINE_SIMILARITY(embedding, :vec) AS vsim,
       MATCH(action_text) AGAINST (:text) AS ft
  FROM inn_ledger
 WHERE player_id = :pid AND id <> :current AND severity >= 1
 ORDER BY 0.7 * COSINE_SIMILARITY(embedding, :vec)
        + 0.3 * (MATCH(action_text) AGAINST (:text) > 0) DESC
 LIMIT 3;
```

- 结构化过滤：`player_id`、`severity`、`排除当前事件`；
- 向量：`VECTOR(1024)` + HNSW（`WITH (distance=cosine, type=hnsw)`）；
- 全文：`WITH PARSER ngram`，中文可命中（"兑水"能匹配"往酒坛里兑半坛水"）。

## 4. 上下文块协议（format=block）

Dify 的 HTTP 节点只能拿到响应 `body` 文本，且本环境没有代码沙箱（无法用 Code 节点解析 JSON），
因此后端额外提供 `format=block`，返回 `KEY=VALUE` 行文本：

```
PLAYER=p_demo01   GRUDGE=62   TIER=3   VISITS=4   DAYS=3   EVENTS=7
RECENT=掀了半张桌子(5级,1天前);吓跑了两个住店的客人(4级,1天前)
```

好处：
1. 一行就能直接塞进 LLM prompt（省一次结构化解析）；
2. Dify 可以用 `contains "TIER=4"` 做分支，判定条件在 DSL 里可见、可审计；
3. 人可读，日志即证据。

## 5. 异常处理

- HTTP 节点设置 `error_strategy: default-value`（status_code=500, body=OFFLINE）；
- 入口分支「后端是否可用」按 `status_code ≥ 400` 短路到兜底话术；
- 兜底时 `workflow_finished.status = partial-succeeded`，但用户能看到完整回答（S7）。
