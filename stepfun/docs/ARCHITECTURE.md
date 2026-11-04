# 架构设计：端侧向量化 + seekdb 混合检索迷你知识库

> 赛题：seekdb × 阶跃星辰「端侧 AI 推理性能优化与 seekdb 混合检索」
> 资产目录：`stepfun/`（分支 `2026-competition-ecosystem`）

## 0. 设计目标与硬约束

先把赛题的硬约束翻译成可验证的架构约束，再据此选型：

| 赛题约束 | 架构约束 | 落地位置 |
|---|---|---|
| 文档与查询的 embedding 均在浏览器本地计算 | 推理只发生在浏览器（Web Worker），服务端**不得**存在任何 embedding 代码路径 | `web/src/lib/embedder.worker.ts` |
| 禁止调用云端推理 API | 模型文件由静态资源服务提供或从公开模型仓库下载，计算在本地 | `scripts/fetch_models.mjs`、`web/src/lib/model-config.ts` |
| 优先 WebGPU，不支持自动降级 WASM，并明确提示 | 启动时探测 `navigator.gpu` 并真正试连 adapter，失败回落 WASM；后端状态上报服务端并展示 | `web/src/lib/backend.ts`、`BackendBadge` |
| 模型需 INT8 或 FP16 方案，并报告体积/压缩比/质量 | 同一模型提供 fp32 / fp16 / q8 三种 ONNX 权重，可切换、可测量 | `scripts/fetch_models.mjs`、`eval/` |
| 向量、原文、元数据存于 seekdb | 所有持久化只落在 seekdb；服务端不使用任何文件/内存数据库 | `server/lib/db.mjs` |
| 混合检索由 seekdb 完成，不得客户端拼接 | 一次 `DBMS_HYBRID_SEARCH` 调用完成「全文召回 + 向量召回 + RRF 融合」，客户端只接收最终排序 | `server/lib/search.mjs` |
| 增量写入 + 索引刷新后新文档可检索 | 写入后 `refresh_index()`，并把刷新耗时计入指标 | `server/lib/kb.mjs` |
| 集合与会话状态一致 | 会话→集合的绑定持久化在 seekdb 中，切换后检索按会话解析 | `server/lib/session.mjs` |
| 可复现 | 一条 `npm run dev` 起服务；seekdb 启动脚本；固定模型版本与 SHA | `scripts/`、`README.md` |

## 1. 总体架构

```
┌──────────────────────────── Browser (Chrome / Edge) ────────────────────────────┐
│                                                                                 │
│  React SPA (Vite)                                                               │
│   ├─ ImportPanel  选择/粘贴文档 → 分块 → 调 Worker                               │
│   ├─ SearchPanel  查询 → 调 Worker 生成查询向量 → POST /api/search               │
│   ├─ BackendBadge 显示 WebGPU / WASM、INT8 / FP16、模型版本                       │
│   └─ MetricsPanel 分阶段耗时（加载/向量化/写入/检索/端到端）                      │
│                                                                                 │
│  Web Worker: Embedding Worker                                                   │
│   @huggingface/transformers (Transformers.js v3)                                 │
│   device = webgpu ──失败──▶ device = wasm                                        │
│   dtype  = q8 (INT8) | fp16 | fp32(baseline)                                     │
│   批处理 batch=8/16，带进度与吞吐统计                                             │
└───────────────┬─────────────────────────────────────────────────────────────────┘
                │ HTTP (JSON)：只传文本、向量、元数据，不传模型
                ▼
┌──────────────────────────── Node 服务端 (Express) ─────────────────────────────┐
│  /api/kbs     知识库（= seekdb 集合）生命周期                                    │
│  /api/session 会话→集合绑定（持久化于 seekdb 表 app_sessions）                     │
│  /api/ingest  批量 upsert（向量由浏览器算出后随请求提交）                          │
│  /api/refresh 索引刷新（refresh_index）并记录耗时                                 │
│  /api/search  调用 seekdb 混合检索（单条 DBMS_HYBRID_SEARCH 语句）                │
│  /api/metrics 指标落盘 + /api/evidence 返回最近执行的 SQL                         │
│                                                                                 │
│  seekdb-js SDK (seekdb 1.4.0)  ──server 模式──▶ 本地 seekdb 进程 (127.0.0.1:2895) │
└─────────────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────── seekdb (embedded/本地 server) ───────────────────────┐
│  sdk_collections            集合元数据（SDK 管理）                                │
│  app_sessions               会话 → 当前集合                                       │
│  kb_<id>                    每个知识库一张表：                                     │
│      id, document, embedding VECTOR(512), metadata JSON                          │
│      VECTOR INDEX (HNSW, cosine) + FULLTEXT INDEX (ngram)                        │
│  混合检索：DBMS_HYBRID_SEARCH.GET_SQL + RRF 融合 → 排序结果                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**为什么是「浏览器算向量 + 服务端只做数据库操作」？**
赛题要求推理在端侧、存储与检索在 seekdb。把 seekdb 放在 Node 进程里（server 模式）而非浏览器里，是因为 seekdb 是原生服务、无法跑在浏览器沙箱中；而向量计算留在浏览器，服务端只做「收向量 → 写库 → 查库」，任何一条路径都不产生 embedding，满足「端侧推理」的硬要求。服务端代码中不存在任何模型加载或推理调用，可用 `grep -r "transformers\|onnx" server/` 自证为空。

**为什么混合检索必须是一条语句？**
`DBMS_HYBRID_SEARCH` 在 seekdb 内部完成「全文检索 + 向量检索 + RRF 融合」，服务端只把 SDK 生成的最终 SQL 执行一次并原样返回排序结果。证据链：`/api/evidence` 返回的 `lastStatements` 中可见 `SET @search_parm = ...` 与 `DBMS_HYBRID_SEARCH.GET_SQL` / 最终查询语句，且客户端代码没有任何 `merge/combine/sort` 两路结果的逻辑。

## 2. 数据模型

### 2.1 知识库（集合）表结构

由 seekdb-js SDK `createCollection` 建立，物理表名 `kb_<collectionId>`：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(64) | 主键，`<docId>#<chunkIndex>` |
| `document` | STRING | 分块原文（检索结果直接回显原文） |
| `embedding` | VECTOR(512) | 端侧模型 `bge-small-zh-v1.5` 输出（512 维） |
| `metadata` | JSON | `{ source, docId, chunkIndex, charStart, charEnd, kb, createdAt }` |

索引：

- `VECTOR INDEX`：HNSW，`m=16`、`ef_construction=200`，距离 `cosine`；
- `FULLTEXT INDEX`：`ngram` 分析器（中文无需分词、中英混排可用；参数 `ngram_token_size=2`）。

### 2.2 会话状态表

```sql
CREATE TABLE IF NOT EXISTS app_sessions (
  session_id VARCHAR(64) PRIMARY KEY,
  active_collection VARCHAR(128) NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

会话状态持久化在 seekdb 而不是进程内存：连续导入、切换知识库、重启服务后，「检索结果与当前知识库一致」都能被验证（测试见 `automation/hourly_check.mjs` 的 `session-consistency` 项）。

## 3. 端侧推理设计

### 3.1 运行时与后端选择

- 运行时：Transformers.js v3（`@huggingface/transformers`），底层 ONNX Runtime Web。
- 探测顺序：
  1. `navigator.gpu` 存在 → `requestAdapter()` 真正拿 adapter（避免仅有 API 但无设备）；
  2. 拿到 adapter → `device: 'webgpu'`，`dtype: 'fp16'`（WebGPU 支持 fp16 算子；不支持时自动回落 q8）；
  3. 失败 → `device: 'wasm'`，`dtype: 'q8'`（WASM 走 INT8 权重 + 单线程/XNNPACK），并在 UI 顶部常驻徽标 `WASM · INT8`。
- 用户也可在设置中强制切换后端（用于对照实验），强制值记录在指标里。

### 3.2 量化方案

| 档位 | 权重文件 | 说明 |
|---|---|---|
| fp32 | `onnx/model.onnx` | 基线 |
| fp16 | `onnx/model_fp16.onnx` | 权重半精度，体积约为 fp32 的 50% |
| q8 (INT8) | `onnx/model_quantized.onnx` | ONNX Runtime 动态量化（per-channel，权重 INT8，激活动态量化），体积约为 fp32 的 25% |

压缩比 `= fp32 体积 / 量化后体积`，由 `scripts/fetch_models.mjs` 实测写入 `results/model-sizes.json`，质量变化由 `eval/` 的 Recall@K / nDCG@K 对比给出（同一评测集、同一索引参数、仅权重不同）。

### 3.3 分块与批处理

- 分块：按字符滑窗，默认 `chunkSize=320`、`overlap=64`，优先在换行/句末切分；块级元数据保留 `charStart/charEnd` 以便原文定位。
- 批处理：`batchSize` 可调（WASM 默认 8，WebGPU 默认 16），worker 内 `for` 循环按批调用 `embedder(batch, { pooling: 'mean', normalize: true })`，逐批回传进度，避免 UI 卡死。
- 吞吐指标：`tokens/s`、`chunks/s`、单批 p50/p95 耗时。

## 4. 检索设计

### 4.1 混合检索（默认）

```js
collection.hybridSearch({
  query:  { whereDocument: { $contains: query }, nResults: candidateK }, // 全文分支（ngram）
  knn:    { queryEmbeddings: [vector], nResults: candidateK },           // 向量分支
  rank:   { rrf: { rankWindowSize: 20, rankConstant: 60 } },             // seekdb 内部融合
  nResults: topK,
  include: ['documents', 'metadatas', 'distances'],
});
```

一次调用 → 一条 `DBMS_HYBRID_SEARCH` 语句 → 数据库内 RRF 融合 → 返回 topK。服务端不做二次排序（只按 `topK` 截断，由数据库完成）。

### 4.2 对照模式

为满足消融实验与降级验证，另提供 `mode=vector`（纯向量）与 `mode=fulltext`（纯全文），两者仍由 seekdb 执行；它们只用于对照组，不替代默认的数据库内混合检索。

### 4.3 索引刷新策略

- 写入：`upsert` 批次提交（默认 64 条/批），单批失败不污染已写入数据（按批幂等重试）。
- 刷新：每批写完后 `refresh_index()`；连续导入时合并刷新（debounce 400ms），避免每次小块都重建索引。
- 指标：写入耗时、刷新耗时、刷新后首查可见性（写入 N 条后立即查询其中一条的特征串，验证可检索）。

## 5. 状态与一致性

| 状态 | 存放 | 一致性手段 |
|---|---|---|
| 知识库列表 | seekdb `sdk_collections` | 每次读取实时查询 |
| 会话→当前知识库 | seekdb `app_sessions` | upsert 语义；服务重启后回读 |
| 分块与向量 | seekdb `kb_<id>` | 以 `<docId>#<chunk>` 为主键，重复导入为覆盖 |
| 前端当前知识库 | React state + 服务端会话 | 切换后强制刷新检索，指标标记 `kb` |

## 6. 性能优化点与测量口径

| 优化 | 手段 | 测量 |
|---|---|---|
| 模型加载 | 本地静态资源 + 浏览器 HTTP 缓存；`dtype` 选择最小可用权重 | `modelLoadMs`（首次/二次） |
| 向量化 | 批处理 + WebGPU；向量 float32 → 传输时降为 2 位小数的 JSON（可配置） | `embedChunksPerSec`、`embedMs` |
| 写入 | 批量 upsert（64/批）、事务外合并 | `ingestMs` |
| 索引刷新 | 合并刷新（debounce） | `refreshMs` |
| 检索 | HNSW + ngram 全文；候选窗口 `candidateK = 4 × topK` | `searchMs`（服务端）、`e2eMs`（提交→渲染） |

端到端口径：`t_query_submit → results_rendered`，浏览器 `performance.now()` 打点，服务端返回各阶段 `timings`，前端合并为一条 `run` 记录（`/api/metrics` 落盘 `results/runs/*.json`）。

## 7. 目录结构

```
stepfun/
├─ server/                 Node API（仅数据库读写，无推理）
│  ├─ index.mjs            路由与静态资源
│  └─ lib/{db,kb,session,search,metrics,chunk,evidence}.mjs
├─ web/                    React + Vite 前端
│  └─ src/{components,lib,styles}
├─ scripts/                seekdb 启动、模型获取、基准、评测
├─ eval/                   语料、查询集、qrels、结果
├─ automation/             每小时汇报与合规检查
├─ docs/                   架构、技术说明、复现、合规、结果
└─ results/                实测数据（体积、runs、报告）
```

## 8. 失败模式与降级

| 失败 | 表现 | 处理 |
|---|---|---|
| 无 WebGPU | 探测失败 | 自动 WASM + 徽标提示，全流程可用 |
| 模型文件缺失 | 加载 404 | 提示 `npm run fetch-models`；允许远端镜像回退 |
| seekdb 未启动 | 健康检查失败 | 首页显示修复命令，接口 503 并给出 `scripts/seekdb_server.sh start` |
| 索引未刷新 | 新文档检索不到 | 服务端在 ingest 完成后强制 refresh；校验项 `refresh-visibility` |
| 会话中切换集合 | 结果串库 | 检索请求以服务端会话的 `active_collection` 为准，忽略客户端旧值 |
```
