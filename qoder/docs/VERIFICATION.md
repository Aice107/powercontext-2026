# 验证样例（VERIFICATION）

全部样例可用 `bash scripts/verify.sh` 一次跑完，原始输出保留在 `evidence/logs/`。
以下每一步都标注了"应看到什么"，以及对应证据文件。

初始数据：`data/corpus/` 16 篇示例语料（一位课题为「向量检索召回质量优化」的研究生的笔记，
内容为按真实科研工作流撰写的演示数据）。服务已按 REPRODUCE.md 启动。

---

## 样例 1：混合检索（seekdb 实际发挥作用）

**输入**：检索页输入 `怎么提升召回率`，模式 hybrid。

**操作**：`POST /api/search {"query":"怎么提升召回率","mode":"hybrid","size":5}`

**预期结果**（实测见 `evidence/logs/S2_search_semantic.json`）：

- 命中 5 条，Top 结果为《HNSW 图索引参数对召回率的影响》《实验记录 1019 基线召回评测》等；
- 每条命中带出处：`《标题》小节 / 类型 / 课题 / 日期 / doc_id`；
- 页面"查看 seekdb 取证"里能看到实际下发的一条 SQL：
  `select dbms_hybrid_search.search('chunks', '{"query":...,"knn":...,"rank":{"rrf":...}}')`——
  融合发生在 seekdb 内部，不是应用拼两个列表。

**反向验证（结构化过滤真的下推）**：输入 `多数派 确认 日志`、模式 fts、
课题 `vec-search`、窗口 `2026-10-26 ~ 2026-11-01`（证据 `evidence/logs/S5_filter_window.json`）：
语料里唯一含"多数派"的文档是 `project=coursework` 的《课程作业…共识算法复习笔记》，
开启过滤后**不再出现**，证明 term/range 过滤在数据库内生效。

## 样例 2：三种模式对照（失败样本互补）

**输入**：`量化会不会掉点`，分别用 hybrid / vector / fts（证据 `evidence/logs/S4_mode_*.json`）。

**预期结果**（实测）：

- vector 命中《小 embedding 模型的中文语义泛化》《标量量化…》（语义泛化生效）；
- fts 命中含"量化"字面的分块（字面精确生效）；
- hybrid 融合两者，且两路各自的失败样本在另一路被补回。

## 样例 3：记忆写入与跨会话召回（PowerContext 实际发挥作用）

**操作**：

1. `POST /api/memory/remember {"kind":"preference","text":"组会材料要结论先行"}`（另 3 条见 verify.sh S6，证据 `evidence/logs/S6_remember_*.json`）；
2. 新开一个进程（甚至重启服务后）召回：`GET /api/memory/recall?q=导师对材料的要求&mode=hybrid`。

**预期结果**（证据 `evidence/logs/S7_recall.json`）：

- 返回「组会材料必须提前一天发给导师」（constraint），`matched_by` 含 `vector`——
  说明该条记忆经本地 ONNX 向量化后按**语义**被召回，而非字面匹配；
- 每次写入/召回都在 `evidence/logs/S9_memory_journal.json`（JSONL）留有请求与响应记录。

## 样例 4：记忆改变草稿输出（记忆复用的可见证据）

**操作**：草稿页用窗口 `2026-10-26 ~ 2026-11-01` 生成（证据 `evidence/logs/S8_draft.json` / `S8_draft.md`）。

**预期结果**（实测输出头部）：

```markdown
# 组会汇报草稿（2026-10-26 ~ 2026-11-01）

> 提醒：按组会惯例，本材料需提前一天发出。（来自 PowerContext 记忆约束）

## 一句话结论      ← 「结论先行」：摘要置顶
## 关键数据        ← 「先给数据」：数据段在进展段之前
## 本周进展
- …〔实验记录 1030 混合检索对照 · 结论 · 2026-10-30〕   ← 「挂出处」
```

**对照实验（最重要的一步，证据 `evidence/logs/S8b_draft_no_memory.md`）**：
用未写入记忆的新 scope（`GEWU_SCOPE_OWNER=u_fresh python -m app.cli draft --since 2026-10-26 --until 2026-11-01`）
重新生成：抬头提醒消失、「一句话结论」从最前移到最后、「关键数据」退回「本周进展」之后、所有出处标注消失，
附录显示"本次没有命中的记忆偏好：按默认版式输出"。
对比 `S8_draft.md`（有记忆）与 `S8b_draft_no_memory.md`（无记忆）即可看到**记忆确实被保存并在后续使用中复用**。

## 样例 5：草稿证据链

草稿末尾附录包含：

- 时间窗口与课题过滤参数；
- seekdb 混合检索的命中数与耗时、实际 SQL；
- PowerContext 命中的记忆条目（含 kind 与原文）；
- 本次因记忆改变的输出清单（逐条对应规则）。

## 指定技术作用核对一览

| 技术 | 核对方法 | 证据 |
| --- | --- | --- |
| seekdb 混合检索 | 界面"查看 SQL 取证"；`S2/S3/S4/S5` 的 dsl 与 sql 字段 | `evidence/logs/S2~S5_*.json` |
| seekdb 向量列/全文索引 | `show indexes`（sqlite-free，见 S0 health 的 dim=512 与 by_kind 统计） | `evidence/logs/S0_health.json` |
| PowerContext 写入 | `S6_remember_*.json` 的 `changed:true` 与 artifact_id | `evidence/logs/S6_*.json` |
| PowerContext 语义召回 | `S7_recall.json` 的 `matched_by:["text","vector"]` | `evidence/logs/S7_recall.json` |
| 记忆复用生效 | 样例 4 的对照实验 | `evidence/logs/S8_draft.md` |
