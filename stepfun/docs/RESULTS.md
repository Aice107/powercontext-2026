# 实测结果（原始数据见 `results/`）

> 全部数据来自本提交应用的真实运行：无头 Chromium 驱动真实页面 → 浏览器内 ONNX 推理 → HTTP → seekdb。
> 生成脚本：`scripts/bench.mjs`（质量 + 分阶段计时）、`scripts/optimizations.mjs`（优化对比）。

## 1. 测试条件（固定）

| 项 | 值 |
|---|---|
| 设备 | 8 vCPU / 9 GB 内存 / 无独立 GPU |
| 浏览器 | Chromium 131.0.6778.33（Playwright `chromium-1148`，headless） |
| Node | v22.22.1 |
| seekdb | OceanBase seekdb v1.4.0.0（本地 server 模式，127.0.0.1:2895） |
| 模型 | `Xenova/bge-small-zh-v1.5`（ONNX，512 维，cosine） |
| 推理后端 | WebAssembly（本机无 GPU，自动降级；线程数 4） |
| 语料 | `eval/corpus` 12 篇中文技术文档，4251 字，分为 20 个分块 |
| 查询集 | `eval/queries.json` 14 条中文查询，doc 级相关性标注 |
| 批大小 | 8（另有批处理消融实验） |
| 索引 | HNSW（m=16, ef_construction=200）+ ngram 全文索引（token size 2） |
| 重复次数 | 每条查询 3 次取中位数；导入 12 次取中位数 |

## 2. 模型体积与压缩比（同一口径：权重文件实际字节数）

| 档位 | 权重文件 | 体积 | 含运行时文件（config+tokenizer） | 压缩比（相对 FP32） |
|---|---|---|---|---|
| FP32 基线 | `onnx/model.onnx` | 94,851,877 B（90.46 MB） | 95,292,085 B | 1.00x |
| FP16 | `onnx/model_fp16.onnx` | 47,497,427 B（45.30 MB） | 47,937,635 B | **2.00x** |
| INT8 | `onnx/model_quantized.onnx` | 24,010,842 B（22.90 MB） | 24,451,050 B | **3.95x** |

INT8 为 ONNX Runtime 动态量化（权重 INT8，激活运行时量化）；SHA-256 见 `results/model-sizes.json`。

## 3. 分阶段计时（WASM，批大小 8）

单位 ms；「首次」= 浏览器冷缓存下加载模型，「预热」= 同上下文重新加载（HTTP 缓存命中）。

| 配置 | 模型体积 | 模型加载（首次 / 预热） | 文档向量化吞吐 | seekdb 写入 | 索引刷新 | 查询向量化 | seekdb 检索 | 端到端查询延迟 | Recall@5 | nDCG@10 |
|---|---|---|---|---|---|---|---|---|---|---|
| FP32 基线 | 90.46 MB | 1413.7 / 570.2 | 14.47 块/s | 5.15 | 402.6 | 5.80 | 6.38 | 17.00 | 1.00 | 1.000 |
| **INT8 (q8)** | 22.90 MB | **930.9 / 346.8** | **23.20 块/s** | 5.05 | 402.3 | 5.25 | 6.21 | **16.15** | 1.00 | 0.994 |
| FP16 | 45.30 MB | 1108.5 / 523.1 | 8.94 块/s | 9.40 | 703.5 | 20.00 | 6.37 | 31.85 | 1.00 | 1.000 |

结论：

- INT8 相比 FP32：体积 **-74.7%**（3.95x 压缩），冷加载 **-34%**，文档向量化吞吐 **+60.3%**，端到端延迟 **-5%**，检索质量几乎不变（nDCG@10 0.994 vs 1.000，14 条查询中 13 条排序一致）。
- FP16 在 **WASM** 上不占优（浏览器以 fp32 计算 + 类型转换），适合作为 WebGPU 的档位；因此应用默认 WASM 用 INT8、WebGPU 用 FP16。
- seekdb 检索耗时稳定在 6 ms 量级，端到端延迟主要来自查询向量化，符合「检索不是瓶颈」的预期。

原始文件：`results/bench-wasm-q8.json`、`bench-wasm-fp16.json`、`bench-wasm-fp32.json`、`results/quality-summary.json`。

## 4. 优化前后对比（WASM / INT8 / 同一语料）

### 4.1 多线程（跨源隔离开启，SharedArrayBuffer 可用）

| 线程数 | 批大小 | 20 块总耗时 | 吞吐 |
|---|---|---|---|
| 1 | 1 | 1620.0 ms | 7.41 块/s |
| 1 | 8 | 2024.5 ms | 5.93 块/s |
| 4 | 1 | 731.3 ms | 16.41 块/s |
| **4** | **8** | **682.0 ms** | **17.60 块/s** |

线程 1 → 4：吞吐 **2.21x**；在 4 线程下批处理 1 → 8 再提升 **7.3%**。
（单线程时批处理反而变慢 20%，说明批处理收益依赖并行度，不能盲目开大批次。）

### 4.2 索引刷新策略

| 策略 | 12 篇文档导入总耗时 | 刷新后可见 |
|---|---|---|
| 每篇导入都刷新 | 9216 ms | ✅ |
| 合并刷新（连续导入只刷新一次） | **2521 ms** | ✅ |

合并刷新把导入总耗时降低 **72.6%**（3.66x），且「刷新后新内容可检索」保持不变（脚本内二次检索验证）。

原始文件：`results/optimizations.json`。

## 5. 后端与降级验证

| 场景 | 结果 |
|---|---|
| 无 GPU 的 headless Chromium（默认） | 探测到 `navigator.gpu`，但 `requestAdapter()` 返回空 → 自动降级 WASM，界面徽标显示「WASM · Q8」，并给出降级原因 |
| 强制 `?backend=wasm` | 全流程可用（本文 §3/§4 所有数据） |
| WebGPU 路径（SwiftShader 软件 Vulkan 适配器） | 真实走通 WebGPU 执行路径，端到端检索可用（见下表） |
| WebGPU + FP16（设备不支持 fp16 着色器） | 自动改用同设备 INT8，界面提示原因，流程继续 |

### WebGPU 路径实测（软件适配器，仅证明路径可用）

本机无物理 GPU。通过 Chromium 自带 SwiftShader Vulkan ICD（`vk_swiftshader_icd.json`）暴露一个**软件 WebGPU 适配器**，从而真实执行 `device:'webgpu'` 分支：

| 配置 | 模型加载（首次/预热） | 向量化吞吐 | seekdb 检索 | 端到端查询 | Recall@5 | nDCG@10 |
|---|---|---|---|---|---|---|
| WebGPU + INT8（软件适配器） | 1853.1 / 1168.0 ms | 1.00 块/s | 6.42 ms | 129.75 ms | 1.00 | 0.951 |
| WebGPU + FP16（软件适配器） | 2090.7 / 1277.9 ms | 0.99 块/s | 6.61 ms | 143.35 ms | 1.00 | 0.951 |

⚠️ 该数据来自**软件光栅化**的 SwiftShader，吞吐没有参考价值（比 WASM 慢约 20 倍），只用于证明：WebGPU 设备选择、模型加载、推理、seekdb 写入/检索、界面提示在 WebGPU 后端下全部可用。
真实 GPU 上预期显著快于 WASM，需按 `docs/REPRODUCE.md` 在目标设备复测后替换本表。

## 6. 质量评测方法

- **相关性**：`eval/queries.json` 为每条查询标注 1~2 篇相关文档（doc 级）。检索结果按 docId 去重后取前 K。
- **Recall@K**：前 K 命中任一相关文档记 1，14 条查询取平均。
- **nDCG@10**：二值相关性，理想 DCG 按 `min(相关文档数, 10)` 计算。
- **MRR@10**：首个相关文档名次的倒数。
- 语料规模较小（12 篇），Recall 已饱和；量化差异体现在 nDCG 与排序细节上，结论按「不出现明显下降」判定。

## 7. 复现命令

```bash
bash scripts/seekdb_server.sh start
node server/index.mjs &            # 或 npm start（已 build）
npm run bench -- --backend=wasm --dtypes=q8,fp16,fp32 --repeats=3
node scripts/optimizations.mjs --backend=wasm
```
