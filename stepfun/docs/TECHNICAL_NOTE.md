# 一页技术说明

**项目**：端侧知识库（浏览器本地向量化 + seekdb 混合检索）· 目录 `stepfun/`

## 1. 模型与量化

| 项 | 内容 |
|---|---|
| 模型 | `bge-small-zh-v1.5`，来源 `Xenova/bge-small-zh-v1.5`（Hugging Face ONNX 转换版），512 维，cosine |
| 运行时 | Transformers.js 3.8.1 + ONNX Runtime Web 1.22（`@huggingface/transformers`） |
| 量化方式 | ONNX Runtime **动态量化 INT8**（权重 INT8 + 运行时激活量化）；另提供 **FP16** 与 **FP32** 权重用于对照 |
| 体积（实测字节） | FP32 90.46 MB · FP16 45.30 MB（**2.00x**）· INT8 22.90 MB（**3.95x**） |
| 质量变化 | 同一语料/索引/查询集下 Recall@5 = 1.00（三档相同）；nDCG@10 INT8 0.994 vs FP32 1.000（-0.6%） |
| 获取与校验 | `npm run fetch-models` 下载并写 `results/model-sizes.json`（含每个文件 SHA-256） |

## 2. 端侧运行与后端选择

- 推理全部在浏览器 **Web Worker** 中执行（`web/src/lib/embedder.worker.ts`），主线程只负责交互；服务端代码中不存在任何模型加载或推理调用。
- 启动顺序：检测 `navigator.gpu` → 真实 `requestAdapter()` → 得到 adapter 才用 `device:'webgpu'`（`dtype:'fp16'`）；否则 `device:'wasm'`（`dtype:'q8'`）。
- 二次兜底：WebGPU 初始化或预热推理抛错时，worker 自动以 WASM 重建并回传 `fallback` 原因；界面顶栏常驻徽标显示 `WebGPU/WASM`、量化档位与降级提示。
- 模型与 ORT 运行时均由同源静态目录提供（`/models`、`/ort`），不依赖 CDN；页面启用 COOP/COEP 以允许 WASM 多线程（SharedArrayBuffer）。
- 验证：本机无 GPU，实测「探测到 API 但无 adapter → 自动降级 WASM → 全流程可用」；`?backend=wasm|webgpu` 可强制复测。

## 3. seekdb 使用

| 项 | 内容 |
|---|---|
| 接入方式 | `seekdb` JS SDK 1.4.0（本地 server 模式，MySQL 协议，127.0.0.1:2895；启动脚本 `scripts/seekdb_server.sh`） |
| 集合结构 | 每个知识库一个集合：`id VARCHAR`、`document STRING`、`embedding VECTOR(512)`、`metadata JSON`（source/docId/chunkIndex/charStart/charEnd/kb） |
| 索引 | 向量：HNSW（m=16, ef_construction=200, cosine）；全文：ngram 分析器（token size 2，中文无需分词） |
| 混合检索 | `collection.hybridSearch({ query: {$contains}, knn: {queryEmbeddings}, rank: {rrf:{rankWindowSize:20, rankConstant:60}} })` → SDK 生成 `SET @search_parm` + `DBMS_HYBRID_SEARCH.GET_SQL`，seekdb 内部完成全文与向量两路召回及 RRF 融合，返回单一排序结果 |
| 客户端职责 | 只传查询向量与文本、只渲染数据库返回的排序；**不做两路结果拼合**（界面「查看 SQL 取证」可直接看到数据库执行语句） |
| 增量写入 | 同一 `docId` 重新导入：先按 docId 删除旧分块 → 批量 upsert（64/批）→ `refresh_index()`；刷新后立即检索验证 |
| 合并刷新 | 连续导入可用 `deferRefresh` 合并为一次刷新：12 篇导入 9216 ms → **2521 ms**（-72.6%），可见性不变 |

## 4. 状态管理与优化

- 会话状态：`app_sessions(session_id, active_kb)` 持久化在 seekdb；检索以服务端会话为准（客户端旧值不会串库），服务重启后仍一致。
- 文档登记：`app_docs(kb, doc_id, title, chunks, chars)` 支撑增量覆盖与统计。
- 优化手段与实测（WASM / INT8）：

| 优化 | 结果 |
|---|---|
| INT8 量化（vs FP32） | 体积 -74.7%，冷加载 -34%，向量化吞吐 +60.3%，端到端 17.0 → 16.2 ms |
| WASM 多线程（1 → 4 线程，COOP/COEP 开启） | 向量化吞吐 7.41 → 16.41 块/s（2.21x） |
| 批处理（4 线程下 1 → 8） | 16.41 → 17.60 块/s（+7.3%）；单线程下批处理反而 -20%，故按后端自适应批大小 |
| 合并索引刷新 | 导入总耗时 9216 → 2521 ms（3.66x） |
| 模型加载 | 本地同源 + 浏览器缓存：冷 931 ms / 预热 347 ms（INT8） |

- 端到端口径：查询提交 → 查询向量化 → seekdb 检索 → 结果渲染；实测 INT8 WASM 中位数 16.15 ms（seekdb 检索 6.21 ms）。

## 5. 边界与限制

- 本机无 GPU：WebGPU 仅验证探测/降级/提示路径，未给出 GPU 加速实测；代码与界面已就绪，需在有 GPU 的 Chrome/Edge 复测。
- 评测语料 12 篇（4251 字）、20 个分块，规模小导致 Recall 饱和；质量结论以 nDCG/MRR 与排序细节为准。
- Linux 下 seekdb 本地 server 需要 `libaio`；模型文件（约 160 MB）不入库，由脚本下载。
