# 进度快照（暂停点）

暂停时间：2026-11-05。本文件记录已验证事实、已做决策和未完成项，下次可从这里继续。

## 1. 赛题要求（来自 `/home/ice/Downloads/qd.md`）

- 基线：`oceanbase/powercontext` 分支 `2026-competition-ecosystem`；**项目资产放进该分支的 `qoder/` 目录**（他人队伍分别是 `dify/`、`minimax/`、`stepfun/`，都是自包含工程 + `docs/` + `evidence/`）。
- 必须：用 Qoder 开发（保留开发记录）+ 实际用到 seekdb 或 PowerContext（至少一种，两者都用要说明分工）+ 用 Qoder Sites 发布网站并设为"任何人可访问"。
- 提交材料：网站网址、代码仓库、运行说明、验证样例、Qoder 开发记录（含账号 UID）、使用效果材料（鼓励）。
- 配置示例用占位值，**不提交任何真实凭据**。

## 2. 已定方向（用户已确认）

- 项目：**格物 Gewu —— 科研笔记管家 + 组会汇报草稿**。导入论文/实验/会议纪要 → seekdb 混合检索给出处 → 生成组会草稿；PowerContext 记研究方向、写作偏好、上次进度并在下次复用。
- 技术分工一句话：**seekdb 存"知识"并做混合检索，PowerContext 存"人"（偏好与进度）并跨会话复用**。
- 推理：**本地 ONNX 小模型，零外部 API Key**（评审可完整复现）。
- 草稿装配走**确定性模板**（可核对、可复现），LLM 润色为可选开关。

## 3. 工作区布局

| 路径 | 说明 |
| --- | --- |
| `/home/ice/Documents/Qoder/2026-11-04/6d2a8b53/repo` | PowerContext 源码（分支 `competition-work`），仅作参考 |
| `.../submission` | **交付工作树**，git worktree，分支 `qoder-submission`，基于 `origin/2026-competition-ecosystem` |
| `.../submission/qoder` | 项目资产目录 |
| `.../.venv-app` | 依赖已装好并验证：powercontext 1.5.0[server,client,seekdb]、pylibseekdb 1.4.0.post2、onnxruntime 1.31.1、tokenizers、fastapi、uvicorn、httpx、pymysql、pyobvector |
| `.../.model-probe` | 已下载的模型文件，待移动到 `qoder/.data/models/bge-small-zh-v1.5-onnx/`（model.onnx 94.8MB、tokenizer.json、tokenizer_config.json、config.json） |

模型来源：`https://hf-mirror.com/Xenova/bge-small-zh-v1.5/resolve/main/...`（直连 huggingface.co 不通，必须用镜像；`fetch_model.sh` 还没写）。

工作树命令：`cd submission && git status`。远端 URL 目前含 token，收尾前必须清掉。

## 4. 已验证的技术事实

### seekdb（无 docker，嵌入式）

- `import pylibseekdb as sk; sk.open(db_dir=...)` → 返回 instance，`connection_options()` 给出 `{'user':'root','unix_socket':'/tmp/pylibseekdb-uds-<pid>-<rand>/run/sql.sock'}`。**没有 TCP 端口**。
- **db_dir 必须已存在**（`os.makedirs(db_dir)`），否则偶发 `seekdb_open failed: code=-1`；重试即可。
- **同一 db_dir 可被多个进程并发 open，共享同一份数据**（实测 B 进程读到 A 进程写入）。所以 PowerContext 打开的嵌入式 seekdb，我们的 app 可以用同一路径再 open 一次接上去 —— 一个实例、两个使用方。
- `instance.connect(database='test', autocommit=False)`；**默认非自动提交，写入必须 commit**（早期探针"查不到数据"就是这个原因）。
- `Cursor.execute(sql, /)`：**只接受一个位置字符串参数，没有占位符绑定**。所有 SQL 必须自己拼字符串 → 需要严格的字面量转义（反斜杠、单引号），并写转义测试。
- 版本：`5.7.25-OceanBase seekdb-v1.4.0.0`。
- DDL 可用形式：
  - `create table t (id varchar(32) primary key, grp varchar(32), d date, c text, v vector(4)) organization=heap`
  - `create vector index vi on t(v) with (distance=l2, type=hnsw)`
  - `create fulltext index fi on t(c) with parser ngram` ← 中文检索靠它，`match(c) against('召回')` 实测命中
  - `select id, l2_distance(v,'[0.1,0.2,0.3,0.4]') d from t order by d limit 3`、`... approximate order by d limit 5`
- 混合检索（本项目核心）：**只有堆表支持**，普通主键表报 `code=1235 table with user provided primary key not supported`。
  - 调用：`select dbms_hybrid_search.search('<table>', '<DSL JSON>')`，返回 JSON 字符串，元素含 `_score` 与各字段。
  - **已实测全部可用（2026-11-05）**：
    - `{"query":{"match":{"c":"..."}}}` / `{"query":{"term":{"grp":"v"}}}` / `bool.must + bool.filter`
    - `knn: {"field","k","query_vector":"[...]","filter":[...]}`（knn 通道可带自己的 filter）
    - `rank: {"rrf":{"rank_constant":30}}`（`weights` 数组语法报 SQL 语法错，不用）
    - 双通道同 filter + rrf 的完整组合 ✅
  - **已实测不可用**：`match_all`+knn（1235）、range 作用于 varchar/date（1210）→ **日期过滤一律用 `dd int`（yyyymmdd）**，int range 实测可用；`_source:false`+`fields` 组合 1210。
  - DSL 语法依据：seekdb 源码 `src/sql/hybrid_search/ob_query_parse.cpp`（支持 query/knn/_source/size/rank(rrf: rank_constant,rank_window_size)、bool(must/should/filter/boost)、match/term/terms/range(gt,gte,lt,lte)）。
- 机器上已有一个**别人启动的独立 seekdb 服务**（PID 7095，`/home/ice/seekdb-submit/...`，端口 3400，2GB）。不要动它，也别复用它的端口。

### PowerContext

- 启动：`powercontext server run --env-file <file>`，默认端口 8000；`GET /health/live`、`/health/ready`、`/v1/capabilities`。
- 关键环境变量（`POWERCONTEXT_SERVER_` 前缀）：
  - `DATABASE_KIND=sqlite|seekdb|oceanbase`；`DATABASE_PATH=<嵌入式 seekdb 目录>`；`DATABASE_DATABASE` 在 seekdb 下实现里是 `Literal["test"]`（PowerContext 的表会落在 database `test`）
  - `ACCESS_MODE=disabled`（本地免 token）
  - `INFERENCE_EMBEDDING_MODEL` / `_BASE_URL` / `_PROFILE_ID` / `_DIMENSION` / `_SEND_DIMENSIONS=false`（固定维度模型要关）/ `_NORMALIZATION=unit` / `_BATCH_SIZE`
  - 基础记忆模式不需要任何模型；配置 embedding 后才用语义召回。
- HTTP 端点与请求体（源码 `openapi/powercontext.yaml` 已核对）：
  - `POST /v1/scopes`：`{title, summary, idempotency_key}`（三者必填）
  - `POST /v1/memory/remember`：`{scope_id, kind, text}` 必填，可选 `reason`、`description`、`expected_revision`；`kind` 是自由字符串（≤128）
  - `POST /v1/memory/search`：`{scope_id, query}` 必填，可选 `limit`、`tag_filter{tags,match}`、`mode ∈ auto|fts|vector|hybrid`
  - `POST /v1/context/prepare`：`{scope_id, query}` 必填，可选 `max_bytes`、`include_code`、`include_receipt`、`assembly`
  - 其它可用：`POST /v1/sources/content`、`/v1/atomic-memory/{list,search,lifecycle,merges}`、`/v1/topic-memory/*`、`/v1/handoff/*`
- Python SDK：`powercontext.client.PowerContextClient(base_url=, token=)`。

### 本地 ONNX embedding

- 已实测：512 维、mean pooling + L2 归一化、CPU 4 条 24ms。
- 语义区分度正常（同主题 0.61 / 无关 0.28）。
- 需要 `enable_padding`，否则 `encode_batch` 出变长数组报错；special tokens 用前要先查 `get_special_tokens()` 避免重复注册。
- bge 中文检索用法：**查询侧加前缀** `为这个句子生成表示以用于检索文章：`，文档侧不加（已在 `embedder.py` 实现）。

## 5. 已写文件

| 文件 | 状态 |
| --- | --- |
| `qoder/data/corpus/*.md` | ✅ 13 篇示例语料（论文摘录 5、实验记录 5、会议纪要 2、待办 1），带 front matter：`title/kind/project/date/tags/origin`。日期覆盖 2026-09-08 ~ 2026-11-02，"上一周"窗口取 2026-10-26 ~ 2026-11-01；含 1 篇 `project=coursework` 用来验证标签过滤 |
| `qoder/app/config.py` | ✅ 环境变量配置（`GEWU_HOME`、`GEWU_SEEKDB_DIR`、`GEWU_MODEL_DIR`、`GEWU_PC_URL`、`GEWU_PORT=8712` 等） |
| `qoder/app/embedder.py` | ✅ ONNX 向量化封装 |

## 6. 下一步（按顺序）

1. 移动模型到 `qoder/.data/models/bge-small-zh-v1.5-onnx/`，写 `scripts/fetch_model.sh`（hf-mirror，带校验和可选 int8）。
2. `app/sql_literal.py`（严格转义 + 单测）；`app/seekdb_kb.py`（open/attach、heap 表、schema：日期用 `dd int` yyyymmdd、upsert、hybrid_search（双通道 filter + rrf）、单路对照、暴露执行 SQL 给前端做"取证"）。
3. `app/embed_server.py`：独立 OpenAI 兼容 `/v1/embeddings` 服务，端口 8710。PowerContext 指向它，避免和主 app 形成启动顺序依赖。
4. `app/ingest.py`（front matter 解析 + 按 `##` 小节分块，标题拼进 embedding 文本）。
5. `app/memory.py`（PowerContext 客户端：ensure scope / remember / search / prepare，每次请求响应落到 JSONL 证据日志）。
6. `app/draft.py`（确定性装配：seekdb 证据 + PowerContext 偏好 → 组会草稿；偏好改变输出顺序与内容，用于"记忆复用"演示）。
7. `app/server.py` + `web/`（导入/检索/记忆/草稿四页；展示 SQL、分数、出处、记忆读写记录）。
8. `app/cli.py` + `scripts/`（`setup.sh`、`run.sh`、`reset.sh`、`demo_flow.sh` 采集 evidence）。
9. **验证 PowerContext Server 以 `DATABASE_KIND=seekdb` + 本地 embedding 真跑通**（读写记忆并在 seekdb 里留下向量）。
10. `docs/`：README、ARCHITECTURE、REPRODUCE、VERIFICATION、COMPLIANCE（逐条验收→证据）、DIVISION-OF-LABOR、QODER_LOG、SUBMIT。
11. Qoder Sites 发布项目网站 + 设为公开；提交推送 `qoder-submission`。

## 7. 待办风险

- **安全**：开发过程中使用过的凭据只存在于本地 clone 的 remote URL，未进入任何提交或文件；发布前已复查 `qoder/` 内不含 `.env`、token、`.data/`。
- 磁盘只剩约 11GB、内存 9GB（已有 seekdb 占 2GB），PowerContext server + 嵌入式 seekdb + embedder 同跑要注意内存；不要在本机跑第二个大模型。
- 混合检索 DSL 若确实不支持 filter/rrf，需要改设计（应用层过滤 or 分路 SQL），并在 `docs/` 里如实说明，不能夸大。
- 使用效果数据只做真实的自测与站点访问统计，**不编造用户数**。
