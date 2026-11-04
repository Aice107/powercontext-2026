# 复现步骤

## 0. 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Node.js | ≥ 20（本次实测 v22.22.1） | 服务端 + 构建 |
| 浏览器 | Chrome / Edge 最新版（本次实测 Chromium 131） | 端侧推理需要 WebAssembly；WebGPU 需浏览器支持 |
| seekdb | 1.4.0（`pylibseekdb==1.4.0.post2` 内含可执行文件） | 本地 server 模式 |
| 可选 | Python 3.10+（仅用于安装 pylibseekdb） | 也可用 Docker |
| 可选 | Playwright Chromium（`~/.cache/ms-playwright`） | 运行基准与冒烟脚本 |

Linux 下 seekdb 依赖 `libaio`：`apt install libaio1`（或使用 `pylibseekdb` 自带 libaio 目录）。

## 1. 安装与准备

```bash
cd stepfun
npm install                      # .npmrc 已设置 legacy-peer-deps

# 模型权重（约 160 MB，写入 models/，并生成 results/model-sizes.json）
npm run fetch-models

# seekdb（首次会创建 .seekdb/data）
python3 -m venv .venv && .venv/bin/pip install pylibseekdb==1.4.0.post2
bash scripts/seekdb_server.sh start
bash scripts/seekdb_server.sh status
```

> 也可以指向已有 seekdb：`SEEKDB_BIN=/path/to/seekdb bash scripts/seekdb_server.sh start`，
> 或使用外部 server：`SEEKDB_HOST=127.0.0.1 SEEKDB_PORT=2881 SEEKDB_USER=root node server/index.mjs`。

## 2. 启动应用

生产模式（单端口，服务端同时托管前端与模型）：

```bash
npm run build
npm start                        # http://127.0.0.1:5177
```

开发模式（热更新，Vite 5178 代理 /api 与 /models）：

```bash
npm run dev
```

## 3. 手工验收清单

1. 首页顶栏显示 `WASM · Q8`（无 GPU 环境）或 `WebGPU · FP16`（有 GPU），并显示 seekdb 已连接。
2. 创建知识库 `demo`。
3. 导入一段中文文本 → 观察「端侧向量化 / 写入 seekdb / 索引刷新 / 端到端」耗时。
4. 立即用刚导入内容中的关键词检索 → 结果命中（证明刷新后可见）。
5. 点「查看 SQL 取证」→ 可见 `SET @search_parm`、`DBMS_HYBRID_SEARCH.GET_SQL` 与融合查询语句（证明混合检索在数据库内完成）。
6. 切换「量化档位」为 FP32 → 顶栏变化、重新加载模型；重复检索对比质量与延迟。
7. 追加导入第二篇文档 → 检索结果只反映当前知识库（会话状态一致）。
8. 新建第二个知识库并切换 → 检索结果随会话切换，不串库。

## 4. 自动化验证

```bash
# 端到端冒烟（真实浏览器，自动降级 WASM，导入 + 混合检索 + 刷新可见）
npm run smoke -- --backend=auto

# 分阶段计时 + 检索质量（q8 / fp16 / fp32）
npm run bench -- --backend=wasm --dtypes=q8,fp16,fp32 --repeats=3

# 优化前后对比（线程数 × 批大小、逐次刷新 vs 合并刷新）
node scripts/optimizations.mjs --backend=wasm

# 合规自检（每小时由调度任务执行）
node automation/hourly_check.mjs
```

## 5. 产物位置

| 文件 | 内容 |
|---|---|
| `results/model-sizes.json` | 三档权重字节数、压缩比、SHA-256 |
| `results/bench-<backend>-<dtype>.json` | 分阶段计时、吞吐、质量明细 |
| `results/quality-summary.json` | 三档配置汇总（中位数） |
| `results/optimizations.json` | 线程/批处理/刷新策略对比 |
| `results/runs/*.json` | 每次导入/检索的原始运行记录（含时间戳） |
| `automation/reports/*.md` | 每小时合规检查报告 |

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| `seekdb 未就绪` 横幅 | `bash scripts/seekdb_server.sh start`；查看 `.seekdb/server.log` |
| 模型加载 404 / 一直「模型加载中」 | 先 `npm run fetch-models`；或设置 `MODEL_ID` 从公开镜像下载 |
| 浏览器报 `SharedArrayBuffer is not defined` | 服务端未返回 COOP/COEP（用 `npm start`，不要直接打开 dist/index.html） |
| WASM 后端很慢 | 确认 `?threads=4` 或默认 4 线程；单线程吞吐约为 1/2.2 |
| `libaio.so.1: cannot open shared object file` | `apt install libaio1`，或将 pylibseekdb 目录加入 `LD_LIBRARY_PATH` |
