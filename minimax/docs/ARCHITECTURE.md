# 规有所依：SDD 工程上下文模块 —— 整体架构

> 版本：v1（2026-11-04）
> 提交目录：`powercontext-2026` 仓库 `2026-competition-ecosystem` 分支的 `minimax/`
> 赛题：MiniMax × OceanBase「规有所依——面向软件持续演进的 SDD 上下文管理系统」

## 1. 一句话方案

给定一个真实可运行的业务工程和一个自然语言开发任务，`sdd_context` 从 **seekdb** 中的规格/代码/测试索引里检索出任务适用的材料，组装成**带真实来源与行号的开发上下文**，交给 **MiniMax** 生成并应用代码补丁，运行目标测试与回归测试，最后把任务进展写入 **PowerContext**；模块重启后从 PowerContext 读回进展并继续使用。

整个验证样例、业务工程、上下文模块、补丁、测试日志、数据库查询记录和 MiniMax 开发记录全部放在 `minimax/` 内，评审可从干净环境按 README 复现。

## 2. 赛题拆解与验收映射

| # | 必做项 | 本方案的实现 | 可核对证据 |
|---|---|---|---|
| 1 | 能够运行 | `scripts/bootstrap.sh` 建 venv；`scripts/pc_server.sh start` 起 PowerContext；`scripts/demo.sh` 一条命令跑完导入→上下文→补丁→测试→状态→重启 | `evidence/run-*/summary.json`、`commands.log`、`README.md` |
| 2 | MiniMax 实际参与 | `sdd_context.minimax` 把上下文发给 MiniMax（OpenAI 兼容/原生两种协议），保存请求、响应、usage、延迟、补丁哈希；补丁与提交 diff 逐字对应 | `evidence/minimax/dev-record.jsonl`、`patches/0001-*.patch`、`code-diff.patch` |
| 3 | 上下文正确且规格更新生效 | seekdb 分块索引 + BM25 检索 + 按 spec_id/符号/测试名去重；规格更新后重新导入会删除旧块并写入新块，上下文立即使用新正文 | `evidence/run-*/context-v1.json`、`context-v2.json`、`context-assertions.json` |
| 4 | 数据库实际参与 | 本地 seekdb 1.4.0 服务存 sources/chunks/terms，检索用真实 SQL 查询；所有 SQL 写入查询日志 | `evidence/run-*/db-queries.log`、`db-stats.json`、`db-version.txt` |
| 5 | 状态能够复用 | 任务状态以 `SDD_TASK_STATE_V1` Memory 写入 PowerContext；重启 PowerContext 与模块后按 task_id 读回，`--resume` 把 done/todo/verifications 注入新上下文 | `evidence/run-*/state-save.json`、`state-after-restart.json`、`resume-context.json` |
| 6 | 代码修改有效 | 同一组目标测试在 before 因目标行为缺失而失败（断言失败，非环境错误），after 全通过；回归测试前后均通过 | `evidence/run-*/before-target.log`、`after-target.log`、`before-regression.log`、`after-regression.log` |

## 3. 总体架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         验证样例 scripts/demo.sh                     │
│  重置工作区 → 导入/更新规格 → 取上下文 → MiniMax 出补丁 → 应用补丁    │
│  → 目标+回归测试 → 写 PowerContext → 重启 → 读回 → 生成证据          │
└───────────────┬───────────────────────────────┬─────────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────────┐   ┌─────────────────────────────────┐
│  sdd_context（Python CLI）     │   │  PowerContext 1.4.1 Server      │
│  ├─ ingest：规格/代码/测试解析 │   │  ├─ Scope: taskhub-demo         │
│  ├─ retrieval：BM25 + 去重     │   │  ├─ Memory: sdd-task-state      │
│  ├─ context：JSON / Markdown   │   │  └─ SQLite 持久化（.runtime/pc） │
│  ├─ minimax：补丁生成与记录     │   └─────────────────────────────────┘
│  ├─ testrunner：目标/回归测试   │
│  └─ state：保存/读取/恢复       │
└───────┬───────────────┬───────┘
        │               │
        ▼               ▼
┌───────────────┐  ┌──────────────────────────────────────────────┐
│ seekdb 1.4.0   │  │ MiniMax API（OpenAI 兼容 / 原生 v2）          │
│ sources        │  │ 输入：任务 + 规格 + 代码 + 测试 + 进展         │
│ chunks         │  │ 输出：unified diff（只改 app/，不改 tests/specs）│
│ terms          │  └──────────────────────────────────────────────┘
│ task_runs      │
└───────────────┘
        ▲
        │ 索引
┌───────┴─────────────────────────────────────────────────────────────┐
│ 业务工程 TaskHub（Flask + SQLite，自带测试）                          │
│  specs/task-api.md   app/{api,store,validation}.py   tests/…         │
│  before 快照：无 due_before 过滤；after：实现 due_before（含当天）    │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 组件职责

| 组件 | 职责 | 不负责 |
|---|---|---|
| `sdd_context.ingest` | 按目录约定解析规格 Markdown、Python AST、测试 AST，切块、哈希、写 seekdb | 不判断代码对错 |
| `sdd_context.retrieval` | 从任务文本抽词/扩展同义词，SQL 查倒排，BM25 排序，按来源去重 | 不生成代码 |
| `sdd_context.context` | 组装 `sdd-context/v1` JSON 与给模型看的 Markdown，附来源/行号/哈希 | 不调用模型 |
| `sdd_context.minimax` | 组 prompt、调用 MiniMax、解析 diff、校验并应用、写开发记录 | 不伪造模型输出 |
| `sdd_context.testrunner` | 运行 pytest，记录命令、退出码、日志、摘要 | 不修改测试 |
| `sdd_context.state` | 通过 HTTP 与 PowerContext 交互，保存/读取任务状态 | 不把 PowerContext 当代码索引 |
| `PowerContext Server` | 跨会话保存任务进展与验证结果 | 不存规格/代码索引 |
| `seekdb` | 存工程资料、切块、倒排索引，提供检索 SQL | 不存任务会话状态 |
| `TaskHub` | 被修改的真实业务工程与测试 | 不依赖上下文模块运行 |

## 4. 目录布局

```text
minimax/
├── README.md                     # 运行说明（依赖、初始化、调用入口、测试、限制）
├── pyproject.toml                # sdd_context 包与依赖（Flask/pytest/pylibseekdb/PyMySQL）
├── docs/
│   ├── ARCHITECTURE.md           # 本文
│   ├── TECHNICAL_NOTE.md         # 一页技术说明
│   └── VALIDATION.md             # 验证样例说明、预期结果、重置方法
├── src/sdd_context/              # 上下文模块
│   ├── cli.py  db.py  ingest.py  retrieval.py  context.py
│   ├── minimax.py  testrunner.py  state.py  tokenizer.py  config.py
├── demo/
│   ├── baseline/                 # 修改前：TaskHub + specs v1 + 目标/回归测试
│   └── business/                 # 修改后：TaskHub + specs v2（含 due_before 规格）
├── patches/
│   ├── 0001-due-before-filter.patch   # 代码修改（MiniMax 产出/复核）
│   └── 0002-spec-due-before.patch     # 规格 v1→v2（用于规格更新验证）
├── validation/
│   ├── task.md                   # 任务描述（要改什么）
│   ├── expected-context.json     # 必须命中的 spec/code/test 来源
│   └── reset.md                  # 重置方法
├── scripts/
│   ├── bootstrap.sh              # 创建 venv、装依赖、检查 PowerContext
│   ├── pc_server.sh              # PowerContext 启停/重启
│   ├── demo.sh                   # 一键端到端验证
│   ├── verify_acceptance.py      # 六项必做自动核验
│   └── compliance_check.py       # 每小时合规巡检（供自动任务调用）
├── tests/                        # 上下文模块自身测试
├── evidence/                     # 运行产物（提交时保留关键证据）
├── PROGRESS_LOG.md               # 每小时汇报追加
└── ACCEPTANCE.md                 # 六项验收清单与当前状态
```

## 5. seekdb 数据模型

本地 seekdb 服务由 `pylibseekdb==1.4.0.post2` 包内的 `seekdb` 二进制启动（默认 `127.0.0.1:2893`，数据目录 `.runtime/seekdb`），`PyMySQL` 通过 MySQL 协议执行参数化 SQL。服务端持久化确保了“一个 CLI 进程写入、下一个 CLI 进程读取”的真实跨进程行为；`db-version.txt` 记录 `SELECT VERSION()` 返回的 `OceanBase seekdb-v1.4.0.0`。

```sql
CREATE TABLE sources (
  source_id   VARCHAR(64) PRIMARY KEY,
  kind        VARCHAR(16) NOT NULL,       -- spec | code | test | doc
  path        VARCHAR(512) NOT NULL,
  title       VARCHAR(256),
  sha256      CHAR(64) NOT NULL,
  imported_at VARCHAR(32) NOT NULL,
  UNIQUE KEY uk_sources_path (path)
);

CREATE TABLE chunks (
  chunk_id    VARCHAR(64) PRIMARY KEY,
  source_id   VARCHAR(64) NOT NULL,
  ordinal     INT NOT NULL,
  kind        VARCHAR(16) NOT NULL,
  path        VARCHAR(512) NOT NULL,
  start_line  INT NOT NULL,
  end_line    INT NOT NULL,
  text        MEDIUMTEXT NOT NULL,
  symbol      VARCHAR(256),
  spec_id     VARCHAR(64),
  title       VARCHAR(256),
  meta_json   MEDIUMTEXT,
  KEY idx_chunks_source (source_id),
  KEY idx_chunks_kind (kind),
  KEY idx_chunks_spec (spec_id)
) CHARACTER SET utf8mb4;

CREATE TABLE terms (
  term     VARCHAR(64) NOT NULL,
  chunk_id VARCHAR(64) NOT NULL,
  tf       INT NOT NULL,
  KEY idx_terms_term (term),
  KEY idx_terms_chunk (chunk_id)
) CHARACTER SET utf8mb4;

CREATE TABLE task_runs (
  run_id       VARCHAR(64) PRIMARY KEY,
  task_id      VARCHAR(64) NOT NULL,
  phase        VARCHAR(32) NOT NULL,
  status       VARCHAR(16) NOT NULL,
  started_at   VARCHAR(32) NOT NULL,
  finished_at  VARCHAR(32),
  summary_json MEDIUMTEXT,
  KEY idx_runs_task (task_id)
);
```

导入是**按文件幂等替换**：同一 `path` 的 `sha256` 未变则跳过；变化则删除该 source 的 chunks/terms 后重写。这样规格更新后旧内容不可能继续被检索到。

## 6. 导入、检索与上下文选择

### 6.1 切块规则

| 类型 | 解析 | 块 |
|---|---|---|
| 规格 | Markdown 标题 + `SPEC-XXX-NNN` 正则 | 每个带 spec_id 的小节一块；保留 heading、正文、起止行 |
| 代码 | Python `ast` | 每个函数/方法一块（qualname、签名、body、起止行）；类头一块；模块级常量一块 |
| 测试 | Python `ast` | 每个 `test_*` 函数一块；抽取 `assert`/`pytest.raises` 摘要 |
| 文档 | 纯文本按段落 | 每段一块（只作补充，不进入必选来源） |

块 ID = `sha256(path + start_line + end_line + spec_id/symbol)[:16]`，可重复生成。

### 6.2 词项与同义词

- ASCII：`[a-z0-9_]+`，拆分 snake_case/camelCase，长度 ≥2。
- 中文：连续汉字取 2-gram，并识别领域词。
- 同义词扩展（只增不减）：`筛选→filter`、`截止→due`、`日期→date`、`任务→task`、`列表→list`、`分页→pagination`、`状态→status`、`优先级→priority`、`回归→regression`、`测试→test`、`规格→spec`、`非法→invalid`、`包含→inclusive`。
- 任务“增加 due_before 过滤（含当天）”会同时产生 `due_before`、`due`、`filter`、`inclusive` 等词项。

### 6.3 检索 SQL 与排序

1. 对 query 词项去重，SQL 查 `terms` + `chunks` + `sources`，一次取回候选块与 tf。
2. SQL 查每个 term 的 `COUNT(DISTINCT chunk_id)` 作为 df，计算 BM25（k1=1.2, b=0.75）。
3. 分值加成：spec 命中标题/spec_id +20%；test 命中测试名 +10%；同文件多块不重复加分。
4. 按类别取 Top-K，去重键：spec=`spec_id`，code=`path::symbol`，test=`path::symbol`。
5. 若某类为空，输出 `warnings`，不编造来源。

`db-queries.log` 记录每条检索 SQL（截断）、参数、命中行数、耗时，作为“数据库查询记录”。

### 6.4 上下文输出

`sdd-context/v1` JSON 的关键字段：

```json
{
  "schema": "sdd-context/v1",
  "task": {"id": "taskhub-due-before", "title": "...", "description": "...", "workspace": "..."},
  "query_terms": ["due_before", "due", "filter", "inclusive"],
  "specs": [{"spec_id": "SPEC-API-013", "path": "specs/task-api.md", "start_line": 61, "end_line": 82, "sha256": "...", "text": "..."}],
  "code":  [{"path": "app/store.py", "symbol": "list_tasks", "start_line": 44, "end_line": 78, "sha256": "...", "text": "..."}],
  "tests": [{"path": "tests/test_due_before.py", "symbol": "test_due_before_includes_boundary_day", "...": "..."}],
  "progress": {"done": [], "todo": [], "verifications": []},
  "sources": [{"path": "...", "sha256": "..."}],
  "warnings": []
}
```

Markdown 渲染把 specs/code/tests/progress 分成四节，每条都带 `path:start-end` 和 sha256 前缀，直接作为 MiniMax 的上下文。

## 7. MiniMax 开发闭环

### 7.1 调用

- 默认 OpenAI 兼容：`POST {MINIMAX_BASE_URL}/chat/completions`，`model=MINIMAX_MODEL`（默认 `MiniMax-M3`），`temperature=0.1`。参考运行使用 `https://api.minimaxi.com/v1`；国际 Key 可改用 `https://api.minimax.io/v1`。
- 可切换原生：`MINIMAX_API_STYLE=native` → `POST {MINIMAX_BASE_URL}/text/chatcompletion_v2`。
- 凭据只从 `MINIMAX_API_KEY` 读取，不写入仓库、不写入日志、不写入 PowerContext。
- 请求记录：`task_id`、`model`、`endpoint`、`context_sha256`、`prompt_sha256`、`started_at`、`latency_ms`、`usage`。
- 响应记录：原始文本、解析出的 diff、`patch_sha256`、是否应用成功。**不记录模型私有思维链。**

### 7.2 约束 prompt

系统提示固定要求：
1. 只输出一个 unified diff 代码块；
2. 只允许修改 `app/` 下的文件，禁止修改 `tests/`、`specs/`；
3. 必须满足上下文中的全部 SPEC-API-013 条款；
4. 不得改变既有分页/过滤/错误格式行为；
5. 不得删除或跳过测试。

### 7.3 应用与校验

1. 从响应中提取 ```diff 块（或整段以 `diff --git` 开头的内容）。
2. `git apply --check` 校验；失败则把错误回传模型重试一次（最多 2 次）。
3. `git apply` 应用到工作区；记录 `applied=true`、`patch_sha256`。
4. `patches/0001-due-before-filter.patch` 是最终应用成功的补丁；提交的 `demo/business` 与该补丁结果一致。
5. 开发记录与代码差异通过 `patch_sha256` 和 `git diff` 对应。

### 7.4 没有 API Key 时的行为

`minimax` 命令立即以退出码 2 失败，并写 `evidence/minimax/BLOCKED.json`，**不会伪造模型调用**。验证样例支持 `--patch-file` 回放已记录补丁；回放证据会明确标记 `mode=replay`，不会被当作 MiniMax 实际参与的证据。

## 8. PowerContext 状态模型

### 8.1 Scope 与 Server

- Server：`powercontext==1.4.1`，SQLite 后端，数据在 `minimax/.runtime/pc/pc.db`，端口默认 `8093`。
- Scope 用固定 `idempotency_key="sdd-context-taskhub-demo"` 创建，重启/重跑得到同一 `scope_id`。
- 脚本 `scripts/pc_server.sh` 负责 start/stop/restart/status；`demo.sh` 会实际重启一次以证明持久化。

### 8.2 状态 Memory

```text
kind = "sdd-task-state"
text = "SDD_TASK_STATE_V1 " + JSON
JSON = {
  "schema": "sdd-task-state/v1",
  "task_id": "taskhub-due-before",
  "status": "implemented",
  "workspace": "...",
  "context_sha256": "...",
  "done": ["读取规格与代码", "应用 MiniMax 补丁", "目标测试通过"],
  "todo": ["等待评审复跑"],
  "verifications": [
    {"name": "target", "command": "python -m pytest ...", "exit_code": 0, "summary": "5 passed"},
    {"name": "regression", "command": "...", "exit_code": 0, "summary": "12 passed"}
  ],
  "next_step": "评审按 README 复跑；如需继续则修改 todo",
  "saved_at": "2026-11-04T14:00:00.123456+00:00"
}
```

### 8.3 保存与读取

- 保存：`POST /v1/memory/remember`（`reason` 记录是哪个验证阶段写入）。
- 读取：`POST /v1/memory/entries/list` 拉取 scope 内 Memory，筛 `kind=="sdd-task-state"` 且文本前缀匹配 `task_id`，按 `saved_at` 取最新；解析 JSON。
- 复用：`sdd_context context --resume --task-id ...` 把 progress 注入上下文；`sdd_context status --task-id ...` 打印 done/todo/verifications/next_step；`demo.sh` 重启 Server 和新进程后再读，断言内容一致。
- 不要求恢复完整 Agent 会话，符合题面 §2.4 的边界。

## 9. 业务样例与目标修改

- 业务工程：`TaskHub`，Flask + SQLite 的任务管理 API，自带 12 条回归测试。
- 修改任务：为 `GET /tasks` 增加 `due_before=YYYY-MM-DD` 上界筛选。
- 目标行为（SPEC-API-013）：
  1. 含当天（`due_date <= due_before`）；
  2. 与 `status`/`priority`/`assignee`/`limit`/`offset` 组合生效；
  3. 无 `due_date` 的任务在筛选时排除；
  4. 非法日期返回 400 `invalid_argument`；
  5. 不改变既有接口、分页元数据和错误格式。
- before：`due_before` 被忽略，返回全部任务 → 目标测试断言失败。
- after：`app/validation.py` 增加日期解析，`app/store.py` 增加 SQL 条件，`app/api.py` 传入参数 → 目标测试通过，回归测试仍通过。
- 目标测试 `tests/test_due_before.py` 在 before/after 两棵树中**逐字相同**；补丁只改 `app/`。

## 10. 验证样例与证据

`scripts/demo.sh` 的顺序（每步写 `commands.log`）：

1. 记录环境：Python、依赖版本、git commit、PowerContext 版本。
2. 复制 `demo/baseline` 到 `.runtime/run-*/workspace`。
3. `sdd_context import`（specs v1）→ `context` → 断言 **不含** SPEC-API-013。
4. 应用 `patches/0002-spec-due-before.patch`（规格 v1→v2）→ 重新 `import` → `context` → 断言 **包含** SPEC-API-013 且正文含“包含截止当天”。
5. 运行 before 目标测试（预期失败，且日志必须是断言失败而不是 ImportError/环境错误）与回归测试（预期通过）。
6. 把最终上下文写入 `context-for-minimax.md`，调用 MiniMax（或 `--patch-file` 回放）生成/读取补丁。
7. `git apply` 补丁 → 运行 after 目标测试与回归测试（均预期通过）。
8. `sdd_context state save` → 重启 PowerContext → 新进程 `state load` / `context --resume` → 断言 done/todo/verifications 与保存前一致。
9. 生成 `db-stats.json`（各表行数、查询次数）、`minimax/dev-record.jsonl`、`summary.json`。
10. `scripts/verify_acceptance.py` 按六项必做检查证据，输出 PASS/FAIL 与缺失项。

验收脚本对“修改前目标测试失败”的判定：退出码非 0 且日志包含 `FAILED tests/test_due_before.py`，且不包含 `ModuleNotFoundError`/`ImportError`/`error during collection`。

## 11. 可复现与安全

- Python 3.12；`uv sync` 安装；`pylibseekdb==1.4.0.post2`、`PyMySQL`、`Flask`、`pytest`。
- PowerContext `1.4.1` 通过 `uv tool install --force "powercontext[cli,server]==1.4.1"` 安装；SQLite 后端无需外部服务。
- 不提交 `.venv/`、`.runtime/`、`evidence/run-*/` 中的大日志、任何 API Key。
- 配置只提供占位值：`MINIMAX_API_KEY=<set-me>`；`.env.example` 不含真实凭据。
- 补丁与上下文中的来源均来自工作区真实文件；行号、sha256 可回查。
- 不使用隐藏标注、不按题目 ID 返回固定答案；规格更新后必须由重新导入驱动结果变化。

## 12. 里程碑

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| M0 | 架构、验收矩阵、目录骨架 | 本文 + `ACCEPTANCE.md` |
| M1 | TaskHub before/after + 目标/回归测试 | before 目标失败、回归通过；after 全通过（手工补丁） |
| M2 | seekdb 导入/索引/检索 | 规格 v1→v2 后上下文变化 |
| M3 | PowerContext 保存/重启读取 | 重启后 done/todo/verifications 一致 |
| M4 | MiniMax 实际生成补丁与记录 | dev-record 与提交 diff 对应 |
| M5 | demo + 证据 + 六项核验 | `verify_acceptance.py` 全 PASS |
| M6 | 文档、清理、提交 | 干净环境按 README 复跑成功 |

## 13. 风险与对策

| 风险 | 对策 |
|---|---|
| 评审环境没有 MiniMax Key | README 明确配置；无 Key 时命令失败并记录 BLOCKED，不伪造；提交开发记录需在开发阶段用真实 Key 生成 |
| PowerContext 安装/启动失败 | 提供 `pc_server.sh` 自动创建 SQLite 配置、健康检查与日志；README 给出 uv 安装命令 |
| seekdb 二进制与 Python/系统库不匹配 | 固定 Python 3.12 与 `pylibseekdb==1.4.0.post2`；`seekdb_server.sh` 设置 `LD_LIBRARY_PATH`，`bootstrap.sh` 检查版本 |
| 检索召回不到目标块 | 中文 2-gram + 领域同义词 + 标题/spec_id 加成；验证脚本断言必须命中的三条来源 |
| MiniMax 补丁不稳定 | 只给最小上下文与严格约束；`git apply --check` 失败重试一次；最终提交固定补丁与记录 |
| 规格更新后旧块残留 | 按 path 哈希幂等替换；重新导入时先删 chunks/terms 再写 |
| 评审认为业务工程是自造的 | README 说明 TaskHub 是为可复现验证提供的最小业务工程，非从零 Agent 框架；测试与接口均为真实可运行代码 |

## 14. 非目标

- 不实现完整 Agent 框架、IDE 插件或 MCP Server（CLI 即调用入口）。
- 不恢复完整 Agent 会话，只复用任务状态（题面允许）。
- 不做向量检索/重排；本题只要求数据库参与检索，词项索引已足够。
- 不把 PowerContext 当作代码索引；规格/代码/测试索引只放 seekdb。
