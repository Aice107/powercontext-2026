# 规有所依：SDD 工程上下文模块（MiniMax × OceanBase）

本目录是赛题「规有所依——面向软件持续演进的 SDD 上下文管理系统」的完整提交物。它实现了一个可运行的工程上下文模块：从 **seekdb** 中的规格/代码/测试索引里检索任务适用材料，组装带真实来源与行号的开发上下文，交给 **MiniMax** 生成并应用代码补丁，运行目标测试与回归测试，最后把任务进展写入 **PowerContext**；模块重启后从 PowerContext 读回进展并继续使用。

- 提交仓库：`powercontext-2026`
- 分支：`2026-competition-ecosystem`
- 资产目录：`minimax/`
- 业务样例：`demo/baseline`（修改前）与 `demo/business`（修改后）的 TaskHub 服务
- 架构文档：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 六项验收状态：[ACCEPTANCE.md](ACCEPTANCE.md)
- 验证样例说明：[docs/VALIDATION.md](docs/VALIDATION.md)
- 一页技术说明：[docs/TECHNICAL_NOTE.md](docs/TECHNICAL_NOTE.md)

## 1. 5 分钟快速验证（无需 MiniMax Key）

```bash
cd minimax

# 1) Python 3.12 环境与依赖（uv 会读取 pyproject.toml）
bash scripts/bootstrap.sh

# 2) 启动本地 seekdb（工程资料索引）与 PowerContext（任务状态）
bash scripts/seekdb_server.sh start
bash scripts/pc_server.sh start

# 3) 端到端回放：导入 → 上下文 → 规格更新 → 应用已记录补丁 → 测试 → 状态重启
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check

# 4) 查看六项验收结果
.venv/bin/python scripts/verify_acceptance.py --run-dir evidence/run-replay-check
```

回放模式会明确标记 `mode=replay`，并让第 2 项「MiniMax 实际参与」保持 FAIL；它只用于验证其余五项和复现流程，**不能替代真实 MiniMax 调用**。

## 2. 依赖与版本

| 组件 | 版本 / 说明 |
|---|---|
| Python | 3.12（`pyproject.toml` 限制 `>=3.12,<3.13`） |
| uv | 用于创建 `.venv` 与安装依赖 |
| Flask | 3.x（TaskHub HTTP 服务） |
| pytest | 8.x（业务测试与模块测试） |
| seekdb | OceanBase seekdb 1.4.0.0；由 `pylibseekdb==1.4.0.post2` 包内的 `seekdb` 二进制启动 |
| PyMySQL | 1.x（通过 MySQL 协议访问 seekdb） |
| PowerContext | 1.4.1（`powercontext[cli,server]`，SQLite 后端） |
| MiniMax | OpenAI 兼容 / 原生 v2 协议，模型默认 `MiniMax-M2.1` |

`scripts/bootstrap.sh` 会检查 Python、Flask、PyMySQL、`pylibseekdb` 与 `powercontext`。如果 PowerContext CLI 缺失，执行：

```bash
uv tool install --force "powercontext[cli,server]==1.4.1"
```

## 3. 数据初始化与启动

### 3.1 seekdb

```bash
bash scripts/seekdb_server.sh start    # 默认 127.0.0.1:2893，数据在 .runtime/seekdb
bash scripts/seekdb_server.sh status
```

首次启动会创建数据目录；`scripts/seekdb_server.sh reset` 会停止并清空 `.runtime/seekdb` 后重启，用于干净复跑。数据库名为 `sdd`，表结构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §5。

### 3.2 PowerContext

```bash
bash scripts/pc_server.sh start        # 默认 127.0.0.1:8093，数据在 .runtime/pc
bash scripts/pc_server.sh status
```

`scripts/pc_server.sh restart` 用于验证任务状态在服务重启后仍可读取。

### 3.3 业务样例与索引

```bash
.venv/bin/python -m sdd_context \
  --seekdb-port 2893 \
  index --workspace demo/business
```

索引内容：`specs/task-api.md`、`app/*.py`、`tests/*.py`、`README.md`；写入 seekdb 的 `sources`、`chunks`、`terms` 表。

## 4. 调用入口

模块提供 CLI（`python -m sdd_context` / `sdd-context`），输入输出均为 JSON 或 Markdown。

```bash
# 导入（幂等；规格文件 sha256 变化时只重建该文件）
python -m sdd_context --seekdb-port 2893 index --workspace demo/business

# 生成开发上下文（JSON + Markdown）
python -m sdd_context --seekdb-port 2893 context \
  --workspace demo/business \
  --task-file validation/task.md \
  --task-id taskhub-due-before \
  --out .runtime/context.json --md .runtime/context.md

# 从 PowerContext 恢复进展后再生成上下文（跨进程/跨会话）
python -m sdd_context --seekdb-port 2893 context \
  --workspace demo/business \
  --task-file validation/task.md \
  --task-id taskhub-due-before \
  --resume --out .runtime/resume.json --md .runtime/resume.md

# 保存 / 读取 / 查看任务状态
python -m sdd_context state-save --state-file .runtime/state.json
python -m sdd_context state-load --task-id taskhub-due-before
python -m sdd_context status --task-id taskhub-due-before

# 运行测试并记录命令、退出码、日志
python -m sdd_context test --workspace demo/business \
  --target tests/test_due_before.py \
  --log .runtime/target.log --label target
```

上下文输出结构（`sdd-context/v1`）包含：`task`、`query_terms`、`specs`、`code`、`tests`、`progress`、`sources`、`required_sources`、`warnings`、`context_sha256`。每条来源都带 `path`、`start_line`、`end_line`、`sha256`，可回查真实文件。

## 5. 真实 MiniMax 开发闭环

```bash
# 只在本机 .env 中保存 Key，权限 600；不要提交
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY=...
chmod 600 .env

# 一条命令：启动服务、真实调用 MiniMax、测试、状态重启、替换 reference、核验六项
bash scripts/run_final.sh
```

MiniMax 配置项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MINIMAX_API_KEY` | 无 | 必填；只从环境/`.env` 读取，不写入仓库或日志 |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | API 基地址 |
| `MINIMAX_MODEL` | `MiniMax-M2.1` | 模型名 |
| `MINIMAX_API_STYLE` | `openai` | `openai`（`/chat/completions`）或 `native`（`/text/chatcompletion_v2`） |
| `MINIMAX_GROUP_ID` | 无 | 可选；native v2 端点的 GroupId |
| `MINIMAX_TIMEOUT` | `120` | 秒 |

开发记录写入 `evidence/run-<id>/minimax/dev-record.jsonl`：模型、端点、上下文 SHA、prompt SHA、usage、延迟、响应 SHA、补丁 SHA、是否应用；同时保存 `prompt.md`、`response-<n>.txt`、`applied.patch`。**不记录模型私有思维链，不记录 API Key。**

无 Key 时 `minimax` 命令会以退出码 2 失败并写 `BLOCKED.json`，不会伪造调用。

## 6. 验证样例

```bash
# 完整回放（5/6，可离线）
.venv/bin/python scripts/demo.py --mode replay --run-id replay-check

# 真实 MiniMax（6/6）
.venv/bin/python scripts/demo.py --mode minimax --run-id final
```

样例任务：为 TaskHub 的 `GET /tasks` 增加 `due_before=YYYY-MM-DD` 过滤（含当天、与既有筛选/分页组合、非法日期 400、无截止日期任务排除、既有行为不变）。

运行顺序、预期结果与重置方法见 [docs/VALIDATION.md](docs/VALIDATION.md)。核心断言：

- 规格 v1 导入后上下文**不含** `SPEC-API-013`；更新到 v2 并重新导入后**包含**，且正文含“包含截止当天”。
- 修改前目标测试 `5 failed`（断言失败，不是环境错误），回归 `12 passed`。
- 修改后目标 `5 passed`、回归 `12 passed`；测试文件前后逐字一致。
- PowerContext 重启后读回 `done/todo/verifications`，并在 `--resume` 上下文中出现。

## 7. 测试命令

```bash
# 业务工程（改后）
cd demo/business && ../../.venv/bin/python -m pytest -q

# 业务工程（改前，目标测试应失败）
cd demo/baseline && ../../.venv/bin/python -m pytest -q

# 上下文模块自身测试（需 seekdb 已启动；不可用时会 skip 集成用例）
.venv/bin/python -m pytest -q tests
```

## 8. 目录结构

```text
minimax/
├── README.md
├── pyproject.toml
├── docs/{ARCHITECTURE,TECHNICAL_NOTE,VALIDATION}.md
├── src/sdd_context/          # CLI、seekdb 索引、检索、上下文、MiniMax、测试、状态
├── demo/baseline/            # 修改前 TaskHub（specs v1 + app 无 due_before + 目标/回归测试）
├── demo/business/            # 修改后 TaskHub（specs v2 + app 实现 due_before）
├── patches/                  # 0001 代码补丁；0002 规格更新补丁
├── validation/               # 任务描述、预期来源、重置说明
├── scripts/                  # bootstrap/demo/verify/seekdb/pc/compliance
├── evidence/reference/       # 参考运行证据（含日志、上下文、状态、开发记录）
├── tests/                    # 上下文模块测试
├── ACCEPTANCE.md
└── PROGRESS_LOG.md
```

## 9. 已知限制

- 第 2 项需要真实 `MINIMAX_API_KEY`；仓库中不包含任何凭据。没有 Key 时只能跑 `replay`，且第 2 项保持 FAIL。
- 上下文模块不恢复完整 Agent 会话，只复用任务状态（题面 §2.4 允许）。
- 检索采用词项 + BM25，不依赖向量模型；中文用 2-gram 与领域同义词扩展。
- TaskHub 是为可复现验证提供的最小业务工程，不是完整生产服务；它包含真实 HTTP 接口、SQLite 持久化与 17 条测试。
- 本机演示默认端口：seekdb 2893、PowerContext 8093；如被占用可用 `SEEKDB_PORT` / `POWERCONTEXT_PORT` 覆盖。

## 10. 安全与许可

- 不提交真实凭据；`.env` 已在 `.gitignore` 中。
- 补丁只允许修改 `app/`；`tests/`、`specs/` 的修改会被拒绝。
- 复用开源组件时保留其许可证；本目录源码为本次赛题实现。
