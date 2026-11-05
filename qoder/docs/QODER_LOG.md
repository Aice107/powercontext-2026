# Qoder 开发记录（QODER LOG）

本项目的主要开发工作在 Qoder（桌面端 Agent）中以自然语言对话完成。
本文件按环节整理 Qoder 在各阶段做了什么；配图占位处请补对话截图，
账号 UID 用于评审核对站点归属与使用记录。

> **Qoder 账号 UID**：`<请填写>`（截图请隐去无关个人信息）

## 时间线与环节

### 环节 1：需求拆解与技术选型

- 输入赛题文档（qd.md），Qoder 梳理出硬性要求：基于 `2026-competition-ecosystem` 分支开发、
  资产放 `qoder/` 目录、至少实际使用 seekdb 或 PowerContext、最后用 Qoder Sites 发布。
- Qoder 调研了同分支上其他队伍（dify、minimax、stepfun）的资产组织方式，确定"自包含工程 + docs + evidence"的目录规范。
- 经确认定题：科研笔记管家 + 组会汇报草稿；两者都用（seekdb 记事、PowerContext 记人）；推理用本地 ONNX 零 Key 方案。

**截图 1**：`<对话截图：需求拆解与目录规范分析>`

### 环节 2：技术可行性验证（关键风险前置）

- Qoder 实测嵌入式 seekdb：`pylibseekdb.open()` 行为、同目录并发挂接、堆表约束、
  `dbms_hybrid_search` 的 DSL 支持边界。
- **重要发现**（全部实测，非猜测）：混合检索仅支持堆表；`range` 只接受数值常量（date/varchar 报 1210）→
  日期列改用 `int`（yyyymmdd）；`rank.rrf.rank_constant` 可用而 `weights` 不可用。
- 为确认 DSL 语法，Qoder 通过 GitHub API 拉取 seekdb 源码 `ob_query_parse.cpp` 对照，再逐项实测锁定可用写法。

**截图 2**：`<对话截图：DSL 逐项实测与源码对照>`

### 环节 3：编码

由 Qoder 完成的模块（约 20 个源文件）：

| 模块 | 说明 |
| --- | --- |
| `app/seekdb_kb.py` | 堆表 schema、upsert、混合检索 DSL 构造、单路对照、SQL 取证 |
| `app/memory.py` | PowerContext HTTP 客户端（scope/remember/search），JSONL 证据日志 |
| `app/draft.py` | 确定性草稿装配：记忆→版式开关、检索→证据分组与出处 |
| `app/embed_server.py` | OpenAI 兼容 `/v1/embeddings`（ONNX CPU，bge-small-zh-v1.5） |
| `app/ingest.py` | front matter 解析、按小节分块、标题拼入向量化文本 |
| `app/sql_literal.py` | 无参数绑定下的 SQL 字面量转义（配套注入测试） |
| `app/server.py`、`app/cli.py` | FastAPI 路由与命令行 |
| `web/` | 四页前端（检索 / 记忆 / 草稿 / 语料） |
| `scripts/` | setup / run_all / stop_all / verify / pc_service |
| `data/corpus/` | 16 篇示例语料 |

**截图 3**：`<对话截图：核心模块编写过程>`

### 环节 4：调试

Qoder 在运行中定位并修复的真实问题（均有对话记录）：

1. `tokenizer.get_special_tokens()` 在 tokenizers 0.23 不存在 → 改用 `token_to_id` 判存；
2. `connect(database='gewu')` 在库未建时报错 → 先连 `test` 建库再切换；
3. 建表语句在表已存在时崩溃 → 幂等化（忽略 code=1050）；
4. `Cursor.execute` 无参数绑定 → 自建转义层并加注入用例（先写后测中测出 `tags` 未 trim、标识符白名单过松两个问题）；
5. PowerContext 的 scope id 由服务端生成 → 客户端改为解析响应并以确定性 idempotency_key 复建；
6. 相对路径歧义导致 PowerContext 用错数据目录 → 环境文件改为以 `qoder/` 为基准并写入 `pc_service.sh`；
7. 草稿装配的三处迭代（版式开关元组遍历、memory 响应结构兼容、正文去除"标题·小节"前缀）。

**截图 4**：`<对话截图：调试与修复>`

### 环节 5：端到端验证与证据收集

- Qoder 编写 `scripts/verify.sh`，S0~S9 自动产出 `evidence/logs/` 全套证据；
- 设计并实测"有记忆 vs 无记忆"对照实验（`S8_draft.md` vs `S8b_draft_no_memory.md`），
  使"记忆被复用"成为可复核的文件差异；
- 浏览器内实测四页 UI（健康徽标、检索、召回、草稿、语料列表）。

**截图 5**：`<对话截图：验证脚本运行与 UI 实测>`

### 环节 6：发布

- 用 Qoder Sites 创建项目网站（`site/`）并发布，可见范围设为「任何人都可访问」；
- 提交分支与 commit 见 `docs/SUBMIT.md`。

**截图 6**：`<对话截图：Qoder Sites 发布>`

## 诚实说明

- 环节 2 中的部分底层探针（seekdb DSL 实测）在临时目录进行，未纳入仓库；
- `evidence/` 与 `docs/` 的整理亦由 Qoder 完成，人工参与集中在：确认选题、确认对照实验口径、最终审阅。
