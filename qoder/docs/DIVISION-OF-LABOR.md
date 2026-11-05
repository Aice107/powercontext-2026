# seekdb 与 PowerContext 的分工（DIVISION OF LABOR）

本项目同时使用 seekdb 与 PowerContext。分工原则一句话：**seekdb 记"事"，PowerContext 记"人"**。

| 维度 | seekdb | PowerContext |
| --- | --- | --- |
| 存什么 | 知识本身：论文摘录、实验记录、纪要、待办的分块（正文、向量、结构化字段） | 关于使用者的事实：汇报偏好、导师约束、进行中事项 |
| 为什么放这里 | 需要 向量 + 全文 + 结构化过滤 + 融合排序，且每条带出处 | 需要"说了一次，以后都算数"的跨会话生命周期（active/forgotten/merge） |
| 谁写入 | 应用直接写堆表 `chunks`（导入即索引） | 应用经 HTTP `POST /v1/memory/remember` 写入 |
| 谁查询 | `select dbms_hybrid_search.search('chunks', DSL)`，一条语句融合 | `POST /v1/memory/search`（hybrid 模式），草稿前召回偏好与约束 |
| 数据库 | 嵌入式实例（pylibseekdb），database `gewu` | **同一个**嵌入式实例，database `test`（`DATABASE_KIND=seekdb`） |
| 核对方式 | 界面"查看 SQL 取证"、`evidence/logs/S2~S5_*.json` 的 sql/dsl 字段 | `evidence/logs/S6~S9`（写入响应、召回 matched_by、JSONL 日志）、`S8_draft.md` 版式变化 |
| 明确不做 | 不存用户偏好（避免与记忆双写冲突） | 不存知识正文与实验数值（那是检索的事） |

## 两者如何咬合（一个具体例子）

生成组会草稿时：

1. **PowerContext 先答"怎么写"**：召回「结论先行」「先给数据」「挂出处」「提前一天发」→ 决定草稿的版式与内容取舍；
2. **seekdb 再答"写什么"**：在指定时间窗口和课题内混合检索实验/纪要/笔记 → 提供带出处的事实与数据；
3. 两者交汇于草稿：偏好决定"证据如何呈现"，检索决定"呈现哪些证据"。

删除任何一方，另一方都无法独立完成草稿——没有记忆，版式退回默认（`S8b_draft_no_memory.md`）；
没有检索，草稿没有任何事实与出处。

## seekdb 在 PowerContext 内部的角色

PowerContext Server 的存储后端被配置为 seekdb（`POWERCONTEXT_SERVER_DATABASE_KIND=seekdb`），
即**记忆的向量索引与检索也运行在同一个 seekdb 引擎上**（database `test`）。
这层关系通过 `GET /health/ready` 的 `checks.database=ready` 与
`powercontext server run` 日志中的 seekdb profile 初始化核对。
