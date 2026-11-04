# 合规对照（赛题验收项 → 实现 → 证据 → 如何自证）

> 依据赛题 `xingcheng.md`：§2.2 端侧推理与量化、§2.3 seekdb 存储与混合检索、§2.4 性能优化、§3 验收标准。
> 自动检查：`node automation/hourly_check.mjs`（每小时由调度任务执行，报告写入 `automation/reports/`）。

## 一、功能与质量（§3.1）

| 验收项 | 实现位置 | 证据 |
|---|---|---|
| 完整流程：导入 → 向量化 → 写入 → 查询 → 排序结果 | `web/src/App.tsx`（importText / runSearch）、`server/lib/{kb,search}.mjs` | `npm run smoke` 通过；`results/screenshot.png` |
| 文档与查询 embedding 均本地计算 | `web/src/lib/embedder.worker.ts`（Web Worker + Transformers.js） | `grep -rn "transformers\|onnxruntime\|pipeline(" server/` 无结果；服务端只接收向量 |
| 无云端推理 API | 无任何 http 推理调用；模型由 `/models` 静态提供 | `grep -rn "api.openai\|api.anthropic\|http.*embed" web/src server` 无命中 |
| 模型量化 + 体积/压缩比/质量 | `q8`/`fp16`/`fp32` 三档 | `results/model-sizes.json`（压缩比 3.95x / 2.00x）、`docs/RESULTS.md` §2-§3 |
| WebGPU 优先 + WASM 自动降级 + 界面提示 | `web/src/lib/backend.ts`（requestAdapter 实测）、worker `init` 失败回落 | 顶栏徽标 `WebGPU/WASM · 档位`；`?backend=wasm` 可复现降级 |
| 向量/原文/元数据存于 seekdb | 集合 `id/document/embedding/metadata` | `server/lib/db.mjs`（Schema）、`server/lib/kb.mjs`（upsert） |
| 混合检索在 seekdb 内完成 | `collection.hybridSearch` → `DBMS_HYBRID_SEARCH` + RRF | 界面「查看 SQL 取证」显示 `SET @search_parm` / `GET_SQL` / 融合 SQL；`/api/evidence` |
| 增量导入 + 刷新后可检索 | `ingest`：按 docId 删除旧分块 → upsert → `refresh_index()` | `npm run smoke`（导入后立即检索命中）；`optimizations.json` 中 `visible: true` |
| 集合与会话状态一致 | `app_sessions` 表；检索以会话为准 | `server/lib/session.mjs`；每小时检查中的 `runtime-consistency` 项实测「会话A→a、会话B→b、增量可见=true」 |
| 可复现启动 | `scripts/seekdb_server.sh` + `npm start` | `docs/REPRODUCE.md` |

## 二、赛题禁止项自证

| 禁止项 | 自查方式 | 结论 |
|---|---|---|
| 调用云端推理 API | 服务端与前端均无推理 API 调用；模型权重来自本地/公开模型仓库 | ✅ 无 |
| 回放服务端预计算向量/检索结果 | 服务端不产生向量；向量由浏览器每次实时计算 | ✅ 无 |
| 把远程推理伪装成端侧 | 推理发生在浏览器 Worker（DevTools 可见 worker 线程与 ORT 运行） | ✅ 无 |
| 绕过 seekdb 存储/检索 | 无 SQLite/IndexedDB/内存索引；检索语句均由 seekdb 执行 | ✅ 无 |
| 客户端拼合两路检索结果 | 只调用一次 `hybridSearch`，结果直接渲染；界面可展开实际 SQL | ✅ 无 |

## 三、性能与质量测试方法（§3.2）落地

| 要求 | 落地 |
|---|---|
| 固定测试条件 | `docs/RESULTS.md` §1（设备/浏览器/模型/精度/批大小/seekdb 配置） |
| 模型体积同一口径 | `scripts/fetch_models.mjs` 按实际字节统计 + SHA-256 |
| 检索质量对比 | `eval/queries.json` + `scripts/bench.mjs`（Recall@5、nDCG@10、MRR@10） |
| 分阶段计时 | 模型加载（冷/热）、文档向量化、写入、刷新、查询向量化、seekdb 检索、端到端 |
| 首次与后续分开 | `modelLoadColdMs` / `modelLoadWarmMs`；每条查询重复 3 次取中位数 |
| 降级路径验证 | `?backend=wasm`（实测全流程）与 WebGPU 软件适配器（实测全流程）；无 adapter 时自动降级并提示 |

## 四、提交材料（§4）

| 材料 | 位置 |
|---|---|
| 可运行的 Web 应用 | `stepfun/`（`npm install && npm run fetch-models && bash scripts/seekdb_server.sh start && npm run build && npm start`） |
| 完整源码 + 依赖 + 配置 | `server/`、`web/`、`package.json`、`.npmrc`、`web/vite.config.ts` |
| 模型获取与量化步骤 | `scripts/fetch_models.mjs`；三档权重与量化方式见 `docs/TECHNICAL_NOTE.md` §1 |
| seekdb 集合结构与索引配置 | `server/lib/db.mjs`（VectorIndexConfig/FulltextIndexConfig）、`docs/TECHNICAL_NOTE.md` §3 |
| 复现数据/生成方式 | `eval/corpus/`、`eval/queries.json`、`scripts/bench.mjs`、`scripts/optimizations.mjs` |
| 一页技术说明 | `docs/TECHNICAL_NOTE.md` |
| 实测日志 | `results/`（model-sizes、bench-*、quality-summary、optimizations、runs/） |

## 五、已知风险（如实记录）

1. **WebGPU 仅有软件适配器数据**：本机无物理 GPU，使用 SwiftShader 软件 Vulkan 适配器跑通了 WebGPU 路径（端到端 129.75 ms、Recall@5=1.00），但吞吐不具参考价值；真实 GPU 加速比需在目标设备复测（`?backend=webgpu`）。
2. **评测语料规模小**：12 篇/4251 字，Recall 饱和（1.00），量化差异只能在 nDCG 与排序细节上体现。
3. **seekdb 部署形态**：采用本地 server（脚本启动）；若评测机无 `libaio`，需 `apt install libaio1` 或使用 Docker 镜像。
4. **模型体积不入库**：约 160 MB 权重由脚本下载，离线评测需预先执行一次 `npm run fetch-models`。
