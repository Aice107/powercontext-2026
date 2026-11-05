# 架构设计

## 1. 组件与端口

| 组件 | 端口 | 职责 | 代码 |
| --- | --- | --- | --- |
| 主应用（FastAPI） | 8712 | 页面、导入、检索、记忆、草稿装配 | `app/server.py` |
| PowerContext Server | 8000 | 记忆服务（atomic-memory / context） | PyPI `powercontext[server,seekdb]` 1.5.0 |
| 本地向量服务 | 8710 | OpenAI 兼容 `/v1/embeddings`（ONNX CPU） | `app/embed_server.py` |
| 嵌入式 seekdb | Unix socket | 一份实例、两个使用方（见 §3） | PyPI `pylibseekdb` 1.4.0.post2 |

所有组件同机部署，无 docker 需求；除 hf-mirror 的模型下载外，运行期没有任何外部网络调用。

## 2. 数据流

### 导入（写入即索引）

```
markdown 文本 ──front matter 解析──▶ 结构化字段（title/kind/project/date/tags）
              ──按 ## 小节分块──▶ Chunk（标题+小节拼进向量化文本，正文保持干净）
              ──本地 ONNX 向量化──▶ 512 维向量
              ──INSERT──▶ seekdb 堆表 chunks（向量列 + ngram 全文索引 + 标量列）
```

### 检索（融合在数据库内部）

```
查询文本 ──本地 ONNX──▶ 查询向量
        └──▶ 一条语句：select dbms_hybrid_search.search('chunks', '<DSL>')
             DSL = { query.match（ngram 全文）+ knn（向量 ANN，512d，l2）
                     + filter（term: project/kind；range: dd int 日期窗口，双通道同过滤）
                     + rank.rrf（k=30）+ size }
             ◀── JSON 命中列表（含 _score 与出处字段）
```

单路对照（`mode=vector` / `mode=fts`）走同一个 DSL 结构、去掉另一路，用于演示两路失败样本互补。

### 草稿（确定性装配）

```
PowerContext.search("写作偏好…")  ─┐
PowerContext.search("导师约束…")  ─┤─▶ 版式开关（结论先行 / 先给数据 / 挂出处 / 避免形容词 / 提前一天）
seekdb.search("实验 结果 数据",    ─┤─▶ 按类型分组：experiment→进展与数据、meeting→导师意见、paper/note→依据
  窗口+课题过滤)                    │
seekdb.search("待办", mode=fts)   ─┘─▶ 下周计划
                                      ▼
                          markdown 草稿 + 附录（记忆命中、偏好生效说明、实际 SQL）
```

装配规则是确定性的：同样的语料、记忆和窗口，输出逐字节一致，便于评审核对"哪条记忆改变了哪一段"。

## 3. 一个 seekdb 实例、两个使用方（核心设计）

PowerContext Server 配置 `POWERCONTEXT_SERVER_DATABASE_KIND=seekdb` 后，会把记忆表建在它打开的嵌入式 seekdb 里；
`pylibseekdb` 对同一 `db_dir` 的并发 `open` 是**挂接同一实例**（实测：A 进程写入，B 进程立即可见）。
因此 `deploy/powercontext.env` 把 `DATABASE_PATH` 指到与应用相同的 `.data/seekdb`：

- PowerContext 的记忆表在 database `test`；
- 应用的知识分块表在 database `gewu`；
- 一份存储、一套 SQL 引擎，进程间通过同一个 Unix socket 访问。

这使"seekdb 存知识、PowerContext 存记忆"不只是两个并行组件，而是共享同一个检索引擎。

## 4. 关键设计决策

| 决策 | 原因 |
| --- | --- |
| 堆表 `organization=heap` | seekdb 的 `dbms_hybrid_search` 仅支持堆表，普通主键表报 `code=1235`（实测） |
| 日期列用 `dd int`（yyyymmdd） | DSL 的 `range` 对 varchar/date 报 `code=1210`，对 int 数值可用（实测）；yyyymmdd 的整数比较与日期序一致 |
| `Cursor.execute` 无参数绑定 → 自建 `sql_literal.py` 转义 | pylibseekdb 只接受单个 SQL 字符串；转义反斜杠/引号/控制符，配套单元测试（`tests/test_sql_literal.py`） |
| 向量索引 `distance=l2` | 向量已单位归一化，l2 距离序与余弦相似序等价，且与 PowerContext 记忆索引的 distance 口径一致 |
| 全文索引 `with parser ngram` | 中文语料按空格切词基本失效；bigram 实测可命中"召回""量化"等词（语料 `exp-1029-ngram.md` 记录了同样的结论） |
| 标题+小节拼进向量化文本、正文保持干净 | 标题是该段最好的摘要，能提升标题级查询命中；草稿输出不需要重复前缀 |
| 嵌入式实例 + 挂接，而非独立 seekdb 服务 | 免 docker、免端口管理；PowerContext 与应用天然共享数据 |
| 草稿不用 LLM、模板确定性装配 | 评审可复现、可核对；技术结合的"实际作用"体现在检索与记忆，而非文本润色 |
| 本地 ONNX 向量（bge-small-zh-v1.5, 512d） | 评审零 Key 复现；查询侧加 bge 官方检索指令前缀，文档侧不加 |

## 5. 已知限制（如实说明）

- 语料为演示用途的 16 篇合成笔记（内容参照真实科研工作流撰写），非真实用户数据；
- 草稿的"避免形容词"是基于词表替换的保守实现，仅作记忆生效的可见演示；
- `rank.rrf.weights` 在 seekdb 1.4 上报语法错（实测），因此未提供双路权重调节；
- 多轮 `remember` 同文本会产生重复记忆条目，需要 PowerContext 的 lifecycle/merge 流程清理，本版本未做去重。
