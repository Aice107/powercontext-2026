# 提交信息

## 1. 代码位置

| 项 | 值 |
|---|---|
| 仓库（私有导入后同名分支） | `powercontext-2026`（本地 worktree `/home/ice/dify-project`） |
| 分支 | `2026-competition-ecosystem` |
| 资产目录 | `stepfun/` |
| 提交记录 | `e0b9a96f`（最新，含 stepfun 全量）、`5d191d6e`、`e2149ef1` |
| 推送状态 | ✅ **已推送到 `submission` 远端** `2026-competition-ecosystem` 分支（`2a6475ac..e0b9a96f`，fast-forward） |
| 远端仓库 | `github.com/Aice107/powercontext-2026` |
| 推送校验 | `git rev-parse submission/2026-competition-ecosystem` == 本地 HEAD |

推送命令（凭据通过临时 `GIT_ASKPASS` 一次性传入，不写入 git 配置、不进入仓库）：

```bash
cd <powercontext-2026 worktree>
git push submission 2026-competition-ecosystem
```

> 评测平台若要求单个 commit hash，使用 `e0b9a96f`（或其后的最新提交）。
> 安全提示：本次用于推送的 PAT 曾出现在会话中，推送完成后已删除本机临时凭据文件；建议在 GitHub 上**轮换/吊销**该 token。

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
