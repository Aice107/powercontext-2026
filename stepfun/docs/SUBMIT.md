# 提交信息

## 1. 代码位置

| 项 | 值 |
|---|---|
| 仓库（私有导入后同名分支） | `powercontext-2026`（本地 worktree `/home/ice/dify-project`） |
| 分支 | `2026-competition-ecosystem` |
| 资产目录 | `stepfun/` |
| 提交记录 | `5d191d6e`（WebGPU 实测 + 降级链）、`e2149ef1`（首批实现） |
| 提交方式 | 本地 git commit（`stepfun/` 全量源码 + 文档 + 实测数据） |

> ⚠️ 当前环境无法访问 GitHub（`git ls-remote` 连接被重置），因此**远端尚未 push**。
> 需要 push 时，在有网络的机器上执行：
>
> ```bash
> cd <powercontext-2026 worktree>
> git push submission 2026-competition-ecosystem      # 或评测平台指定的提交方式
> ```
>
> 若评测平台要求单个 commit hash，请使用最终 push 后的 `HEAD`。

## 2. 提交内容清单

```
stepfun/
├─ README.md                     交付说明与快速开始
├─ docs/
│  ├─ ARCHITECTURE.md            架构设计（先设计后实现）
│  ├─ TECHNICAL_NOTE.md          一页技术说明（赛题 4.3）
│  ├─ COMPLIANCE.md              验收项 → 证据对照
│  ├─ REPRODUCE.md               复现步骤与常见问题
│  ├─ RESULTS.md                 实测数据（体积/延迟/质量/优化）
│  └─ PROGRESS.md                每小时进度与合规结论
├─ server/                       Node API（seekdb 读写，无推理）
├─ web/                          React + Vite + Transformers.js
├─ scripts/                      seekdb 启动、模型获取、基准、评测、冒烟、UI 流程
├─ eval/                         语料 12 篇 + 14 条查询（含相关性标注）
├─ automation/                   每小时合规检查脚本 + 报告
└─ results/                      实测 JSON + 界面截图
```

## 3. 关键提交物对应关系

| 赛题要求 | 提交物 |
|---|---|
| 可运行 Web 应用 | `stepfun/`（`npm install && npm run fetch-models && bash scripts/seekdb_server.sh start && npm run build && npm start`） |
| 完整源码 + 依赖 + 配置 | `server/`、`web/`、`package.json`、`package-lock.json`、`.npmrc`、`web/vite.config.ts` |
| 模型获取与量化步骤 | `scripts/fetch_models.mjs`；量化说明见 `docs/TECHNICAL_NOTE.md` §1 |
| seekdb 结构/索引配置 | `server/lib/db.mjs`（HNSW + ngram）、`docs/TECHNICAL_NOTE.md` §3 |
| 评测数据与生成方式 | `eval/corpus/`、`eval/queries.json`、`scripts/bench.mjs` |
| 一页技术说明 | `docs/TECHNICAL_NOTE.md` |

## 4. 复现最短路径

```bash
cd stepfun
npm install
npm run fetch-models
python3 -m venv .venv && .venv/bin/pip install pylibseekdb==1.4.0.post2
bash scripts/seekdb_server.sh start
npm run build && npm start          # http://127.0.0.1:5177
npm run smoke                       # 端到端冒烟（真实浏览器）
```

## 5. 环境与版本

| 组件 | 版本 |
|---|---|
| Node.js | v22.22.1 |
| seekdb | v1.4.0.0（`pylibseekdb==1.4.0.post2` 内置二进制） |
| seekdb-js | 1.4.0 |
| Transformers.js | 3.8.1（`onnxruntime-web` 1.22.0-dev） |
| 模型 | `Xenova/bge-small-zh-v1.5`（512 维） |
| 浏览器 | Chromium 131.0.6778.33（实测）；要求 Chrome/Edge 最新版 |
