# 记仇客栈 · Grudge Inn

> 赛题：Dify × OceanBase ｜ Just for Fun——用 Dify 做一个好玩的智能应用
> 技术选型：**Dify（必选）+ seekdb**（应用数据与混合检索）+ **PowerContext**（印象记忆，可选层）
> 开发基线：`oceanbase/powercontext` 分支 `2026-competition-ecosystem`，资产位于 `dify/`

一个会记住你每一次恶作剧的 AI 客栈：老板娘柳三娘把每一笔劣迹记在账本上，
下次见面她会翻出来，一条条念给你听。

---

## 1. 作品创意与玩法

### 1.1 创意

赛题举例"一个会记住玩家恶作剧的 NPC"。本作品把它做成三层可验证的机制：

| 层 | 玩家感知 | 实现 |
| --- | --- | --- |
| 记得住 | 新开会话她仍然认得你 | seekdb 账本按玩家持久化，跨会话读取 |
| 算得清 | 仇值 0→100 分五档，态度肉眼可见地变 | 每次事件累加仇值，档位决定语气与报复方式 |
| 翻得出 | 她会主动复述"上次你也是这么干的" | seekdb 单条 SQL：结构化过滤 + 向量相似 + 全文命中 |

### 1.2 玩法

1. **入店**：应用给四个建议问题（兑水、偷吃酱牛肉、回访、打烊），也可以自由输入；
2. **搞事**：任何"恶作剧/善举/闲聊/打烊"都由 Dify 判定成结构化事件（类型、严重度、对象、场景）；
3. **记账**：事件写入 seekdb 账本，仇值按 `严重度×6 + 屡教不改加成` 累加（上限 100）；
4. **回应**：三娘按档位回应，并在回应里带一句账本批注；只要账本里有相似旧账，她就会"翻旧账"（同类事件重复时还会点明"屡教不改"）；
5. **逐客**：仇值触顶（TIER=4）时走独立分支，她下逐客令并引用最重的那笔旧账；
6. **打烊**：输入"打烊/结账"生成《账本长卷》（逐条念账 + 总评 + 结局判词）；
7. **求原谅**：仇值满 100 之后继续作恶会被逐客，但做善举（修屋顶/赔钱/劈柴）仍走正常对话，
   仇值按 `severity×8` 回落——"被赶出去的人还能哄回来"是刻意留的回头路。

### 1.3 档位

| 仇值 | 档位 | 态度 | 行为 |
| ---: | --- | --- | --- |
| 0–19 | T0 和善 | 热情招呼，可给好处 | 正常做生意 |
| 20–39 | T1 戒备 | 话里带刺、加价 | 提醒你她记着 |
| 40–59 | T2 冷脸 | 冷淡、使绊子 | 端汤多放半勺盐 |
| 60–79 | T3 报复 | 明着报复 | 被窝放花椒、行李挪柴房 |
| 80–100 | T4 逐客 | 下逐客令 | 触发独立分支 |

### 1.4 体验方式（3 分钟，已逐步实测）

玩家标识填 **`p_demo01`**（预置：仇值 62 / T3 报复 / 7 条旧账），依次发送：

| 步骤 | 输入 | 应看到 |
| ---: | --- | --- |
| 1 | `往酒坛里兑半坛水` | 记账批注 + **翻旧账**（"三天前你就兑过一回井水…手法倒退步了"），仇值 62 → 76 |
| 2 | `又往酒坛里兑水` | 再记一笔，仇值 76 → 92，`TIER=4` → **逐客令**（引用最重旧账 + 交代行李账款） |
| 3 | `打烊，结账` | 《账本长卷》：逐条念账 + 总评 + 判词（被赶出去也照样给你算账） |
| 4 | `我帮你把柴劈了，再赔你两吊钱` | 彩蛋：被逐之后仍可**求原谅**，仇值回落、语气变软 |

> 想从更"温和"的起点体验：用 `p_tier1`（仇值 28 / T1 戒备）或 `p_tier2`（48 / T2 冷脸），同一句话能看到三种不同反应（见 `samples/S8_tier_gradient.md`）。
> 想重置回初始状态：`bash tools/reset-demo.sh`（重建 seekdb 数据 + 清空 PowerContext 记忆）。

---

## 2. 技术架构与分工

```
玩家 ──► Dify Chatflow（编排：判定 / 分支 / 提示词 / 输出）
             │
             ├── HTTP 节点 ──► inn-api（FastAPI，只做存储与检索）
             │                    │
             │                    └── MySQL 协议 ──► seekdb（账本 / 传闻 / 台词库）
             │
             └── LLM 节点 ──► DeepSeek（OpenAI-API-compatible 插件）
```

| 组成 | 在本项目中的职责 | 不负责 |
| --- | --- | --- |
| **Dify** | 输入处理、意图与严重度判定、档位分支（打烊/闲聊/逐客）、提示词组装、输出呈现、异常兜底 | 不持久化、不写 SQL |
| **inn-api** | 落库、混合检索、聚合统计、玩家标识解析、参数校验；转发 PowerContext 记忆读写 | 不判定"是否恶作剧"、不算档位、不生成台词 |
| **seekdb** | 应用数据层：事件事实、仇值、向量索引、全文索引、台词库 | 不承载 Dify 元数据库（见 §7.1） |
| **PowerContext**（可选层） | 记住"这个人"：对角色的印象、关系摘要，跨会话召回后注入 prompt | 不存事件明细与数值（避免与 seekdb 双写冲突） |

**一句话分工：seekdb 记"事"，PowerContext 记"人"，Dify 决定"怎么回应"。**

### 2.1 seekdb 在应用里的四处实际作用

| 作用 | 表 | 能力 | 证据 |
| --- | --- | --- | --- |
| 事件持久化 | `inn_ledger` | 结构化 + `VECTOR(1024)` | `evidence/logs/S2_db_ledger.txt` |
| 翻旧账 | `inn_ledger` | 向量相似 + 全文命中 + 玩家过滤，**单条 SQL** | `evidence/logs/S3_sql_hybrid.txt` |
| 台词检索（语气锚点） | `inn_line` | 按当前档位（善举按 `tone=kind`）取两句原话，随记账块 `LINES=` 进 prompt | `inn_line` 60 条（5 档 × 10 个高频道具 + 10 条和解句） |
| 结算聚合 | `inn_ledger` | `COUNT/SUM/MAX` 聚合 | `evidence/logs/S6_settle.log` |

### 2.2 PowerContext 在应用里的作用（可选层）

| 环节 | 调用 | 内容 |
| --- | --- | --- |
| 建档 | `POST /v1/scopes`（幂等键 `inn:player:<player_id>`） | 一玩家一个 Scope，映射存 `inn_pc_scope` |
| 写记忆 | `POST /v1/memory/remember` | 每次记账后写一句"三娘对某人的印象：档位 + 最近一次行为 + 仇值" |
| 召回 | `POST /v1/memory/search` | 进店时召回印象，拼进上下文块 `MEMORY=` 行，随档案块进入 prompt |

未配置 `PC_BASE_URL` 时整层跳过，应用仍可运行（赛题只要求 seekdb 或 PowerContext 之一）。

---

## 3. 运行环境

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Dify | **1.17.0**（自部署，docker compose 或源码） | DSL 由该版本导出；导入需同大版本 |
| seekdb | **1.4.0.0**（OceanBase seekdb，MySQL 协议） | 本文档统一用 **2891**（作者机器上 2881 被别的实例占用；默认端口是 2881，按需改 `SEEKDB_PORT`） |
| Python | 3.12 | inn-api 运行时 |
| inn-api 依赖 | fastapi 0.115.6 / uvicorn 0.34.0 / pymysql 1.1.1 / pydantic 2.10.4 | `backend/requirements.txt` |
| 模型插件 | `langgenius/openai_api_compatible:0.0.73`（Dify Marketplace） | DSL 的 `dependencies` 已声明 |
| LLM | DeepSeek `deepseek-flash`（或任意 OpenAI 兼容端点） | 需要 **function calling** 能力（判定节点用） |
| PowerContext Server（可选） | 1.4.1（sqlite 后端即可） | 不启动也能跑；启用后提供"印象"记忆 |
| Embedding | 默认**不依赖外部服务** | `EMBEDDING_MODE=hash`（字符 n-gram 哈希向量，1024 维）；可切 `api` 模式接任意 OpenAI 兼容 embedding |
| Rerank | 未使用 | — |

> **为什么默认不用外部 Embedding**：本项目要保证"评审无需作者本地服务即可复现"，且运行环境无 GPU。
> 哈希向量对 10–40 字的短句足够区分语义簇；若评审希望用真 embedding，
> 设 `EMBEDDING_MODE=api` + `EMBEDDING_BASE_URL/API_KEY/MODEL`，并把 `EMBEDDING_DIM` 与建表维度对齐（改 `db/01_schema.sql` 后重建表）。

---

## 4. 部署步骤

### 4.1 起 seekdb

```bash
# 方式一：官方二进制（示例）
./seekdb --base-dir /path/to/seekdb_data --port 2891 --nodaemon \
  --parameter memory_budget=2G --parameter log_disk_size=2G

# 方式二：镜像 oceanbase/seekdb（Dify 官方 compose 已收录该镜像）
```

### 4.2 初始化数据

```bash
cd dify
SEEKDB_HOST=127.0.0.1 SEEKDB_PORT=2891 bash db/init.sh
```

输出应包含：`inn_player 3 / inn_ledger 12 / inn_rumor 2 / inn_line 60`（3 个演示玩家：`p_demo01` / `p_tier1` / `p_tier2`）。

### 4.3 起 inn-api

```bash
cd dify/backend
cp .env.example .env          # 按需改 seekdb 地址
uv venv .venv --python 3.12
uv pip install -r requirements.txt
bash run.sh                   # 监听 0.0.0.0:8010
curl -s http://127.0.0.1:8010/healthz
```

`healthz` 应返回 `{"status":"ok","seekdb":true,...}`。

### 4.4 导入 DSL

1. Dify 控制台 → 应用 → **导入 DSL** → 选择 `dsl/01_inn_chatflow.yml`；
2. 若提示缺少插件：先在 **设置 → 插件** 安装 `langgenius/openai_api_compatible`（Marketplace），再重新导入；
3. 导入后**重新绑定**（因为地址因部署环境而异）：
   - **四个 HTTP 节点**（读取档案 / 记账 / 生成传闻 / 结算）：把 `http://127.0.0.1:8010` 改成你实际部署地址；
   - 五个 LLM 节点 + 一个参数提取节点：选择你已配置的模型（本项目用 `deepseek-flash`）；
   - 如 inn-api 不在本机，Dify 容器需能访问该地址（Docker 部署时用宿主 IP 或 `host.docker.internal`）。
4. 点击右上角**发布**。

### 4.5 应用入口

- Dify 控制台 → 应用《记仇客栈》→ **预览/运行**；
- 或调用应用 API：`POST /v1/chat-messages`（需在应用的「访问 API」里创建 Key）。

---

### 4.6 5 分钟快速验证（环境已就绪时）

```bash
# 1) 数据
bash db/init.sh                     # → inn_player 3 / inn_ledger 12 / inn_line 60
# 2) 后端
cd backend && bash run.sh &          # :8010
curl -s localhost:8010/healthz       # → {"status":"ok","seekdb":true,...}
# 3) Dify：导入 dsl/01_inn_chatflow.yml → 绑四个 HTTP 节点地址 + 六个模型节点 → 发布
```

在应用预览里依次发送，逐条对照：

| 发什么 | 应看到 |
| --- | --- |
| `往酒坛里兑半坛水` | 记账批注 + 翻旧账（"三天前你就兑过一回井水…"） |
| `又往酒坛里兑水` | 再记一笔，仇值 76 → 92，**逐客令** |
| `打烊，结账` | 《账本长卷》：逐条念账 + 判词 |

核对数据侧：
```bash
curl -s 'localhost:8010/inn/session?player_id=p_demo01&format=block'   # 看 GRUDGE / RECENT / MEMORY / LINES
mysql -h127.0.0.1 -P2891 -uroot -e "SELECT action_text,severity FROM inn.inn_ledger WHERE player_id='p_demo01' ORDER BY id DESC LIMIT 3"
```

## 5. 配置示例（占位值）

```dotenv
# backend/.env
SEEKDB_HOST=127.0.0.1
SEEKDB_PORT=2891
SEEKDB_USER=root
SEEKDB_PASSWORD=<REPLACE_ME>
SEEKDB_DATABASE=inn
EMBEDDING_MODE=hash
EMBEDDING_DIM=1024
INN_API_PORT=8010
```

> 仓库内**不含任何真实 API Key**。模型 Key 请在 Dify 界面「模型供应商」中填写，不要写进 DSL 或本仓库。

---

## 6. 验证样例

| 编号 | 验证点 | 文件 |
| --- | --- | --- |
| S1 | 首次入店、空账本 | [samples/S1_first_visit.md](samples/S1_first_visit.md) |
| S2 | 单次恶作剧记账 | [samples/S2_prank_ledger.md](samples/S2_prank_ledger.md) |
| S3 | 翻旧账（混合检索生效） | [samples/S3_old_grudge.md](samples/S3_old_grudge.md) |
| S4 | 跨会话记忆 | [samples/S4_cross_session.md](samples/S4_cross_session.md) |
| S5 | 逐客与求原谅（条件分支） | [samples/S5_expel.md](samples/S5_expel.md) |
| S6 | 打烊结算 | [samples/S6_settle.md](samples/S6_settle.md) |
| S7 | 依赖不可用兜底 | [samples/S7_degraded.md](samples/S7_degraded.md) |
| S8 | 档位梯度（T1/T2/T3 对比） | [samples/S8_tier_gradient.md](samples/S8_tier_gradient.md) |
| S9 | PowerContext 记忆 | [samples/S9_pc_memory.md](samples/S9_pc_memory.md) |
| S10 | 和解线（善举降仇值） | [samples/S10_kindness.md](samples/S10_kindness.md) |

一键复跑并重新生成证据（需要 Dify 登录态 cookie 与 app_id，见 `tools/run_app.sh`）：

```bash
INN_APP_ID=<app_id> bash tools/collect_evidence.sh
```

实际运行输出见 [evidence/logs/](evidence/logs/)，证据索引见 [evidence/README.md](evidence/README.md)。

---

## 7. 已知限制

1. **没有代码沙箱**：部署环境非 root，`dify-sandbox` 无法运行，因此 **DSL 中不使用 Code 节点**；
   判定用「参数提取器」节点，分支用「IF/ELSE」，检索用「HTTP 节点」完成。
2. **档位映射在后端**：`grudge → tier` 是纯函数（`backend/app/rules.py`），Dify 依据 tier 做分支与提示词选择；
   若评审要求"档位判定也在 Dify"，可把 backend 返回的 `TIER` 换成在 Dify 里用 IF/ELSE 逐档比较（当前实现选择了更省 token 的方案）。
3. **PowerContext 是可选的**：`PC_BASE_URL` 为空时自动跳过记忆层；启用时若 PC 挂掉，记账与回应仍走 seekdb（3 秒超时后静默降级）。
4. **玩家标识两条路径**：显式填写 `player_id` 时跨会话记忆生效；留空时按会话 ID 生成稳定 ID（只在本会话内一致）。
5. **embedding 是哈希向量**：不追求语义泛化，只在短句层面做相似度排序；换成真 embedding 需要重建表（维度一致）。
6. **单机 demo**：inn-api 无鉴权、无并发保护，仅用于赛题演示；生产环境需要加鉴权与限流。
7. **打烊结算走 LLM**：判词由模型生成，措辞有随机性，但数值与账目来自 seekdb，不会编造事件。

### 7.1 Dify 部署数据库说明（赛题 §4.4 第 1 行）

本作品**没有**用 seekdb 承载 Dify 自身的元数据库：Dify 用 PostgreSQL/MySQL 部署，seekdb 只承担应用数据与检索。
若要把 seekdb 作为 Dify 数据库（赛题允许并需要额外提供适配说明），Dify 1.17.0 的 `DB_TYPE` 已原生支持
`seekdb` / `oceanbase`，**无需改代码**。我们做过可行性实测（独立库 `dify_meta` + 独立端口 5005）：

| 检查 | 结果 |
| --- | --- |
| `DB_TYPE=seekdb flask upgrade-db` | 成功，建表 143 张 |
| `/health` | `ok`（1.17.0） |
| `/console/api/setup` | `not_started`（连通且读到空库） |

证据：[evidence/logs/dify-on-seekdb.md](evidence/logs/dify-on-seekdb.md)。
本作品主线仍用 MySQL 承载 Dify 元数据库、seekdb 承担应用数据——这条路线作为可选扩展记录，未纳入主线验证范围。

### 7.1.1 性能实测（20 轮连打）

`evidence/logs/run-loadtest.md`：单轮端到端 **中位数 5.6s / P95 9.0s**（含 2 次 LLM 调用：意图判定 + 回应生成），
20/20 全部 succeeded；仇值按 12→100→76 走完"升级—触顶—和解"整条曲线；每轮写 1 条账本 + 1 条记忆。

### 7.1.1 全新导入演练（实测）

模拟评审从零操作（`tools/fresh-import-drill.sh`）：

| 步骤 | 结果 |
| --- | --- |
| 导入 `dsl/01_inn_chatflow.yml` 为新应用 | `status=completed` |
| 草稿图节点数 | 19（与文档一致） |
| 跑一轮「往酒坛里兑半坛水」 | `succeeded`，172 字，含翻旧账 |
| 清理 | 删除测试应用 204 |

证据：[evidence/logs/fresh-import-drill.md](evidence/logs/fresh-import-drill.md)。

### 7.1.2 依赖自愈（实测）

开发机上的看门狗（`tools/watchdog.sh`，本机开发态脚本）每 15 秒检查一次依赖；做过一次故意破坏的演练：

| 动作 | 结果 |
| --- | --- |
| `kill -9` inn-api | **2 秒**后新进程接管 |
| `kill -9` seekdb | **72 秒**后新进程接管（含 seekdb 启动约 50s），账本 20 行数据无损 |

证据：[evidence/logs/selfheal-drill.md](evidence/logs/selfheal-drill.md)。评审环境不需要这个脚本，它只是说明"依赖挂了不需要人工介入"。

### 7.2 网络与资源

- Dify 进程需能访问：inn-api（默认 8010）、模型 API（如 `api.deepseek.com`）、插件 Marketplace；
- inn-api 需能访问 seekdb（2891）；
- 资源：seekdb 建议 ≥2GB 内存预算；Dify 自身建议 ≥4GB；本机复验环境为 8GB/4 核。

---

## 8. 目录结构

```
dify/
├── README.md                 # 本文件（运行说明）
├── dsl/
│   ├── 01_inn_chatflow.yml   # 主应用 DSL（可直接导入）
│   └── README.md             # 导入顺序与重绑定清单
├── backend/                  # inn-api（FastAPI + seekdb）
│   ├── app/{main,db,embedding,rules}.py
│   ├── requirements.txt
│   ├── .env.example
│   └── run.sh
├── db/                       # 建表与 seed
│   ├── 01_schema.sql
│   ├── 02_seed_lines.sql
│   ├── 04_seed_demo.sql
│   └── init.sh
├── deploy/
│   └── bootstrap.sh          # 一键：建库 → seed → 起 inn-api → 自检
├── samples/                  # S1–S7 验证样例
├── evidence/                 # 运行证据（日志 + 索引）
├── docs/                     # 设计与进度日志
└── tools/                    # 自检 / 取证 / 看门狗
```

---

## 8.2 tools/ 里有两类脚本（请勿混淆）

| 类别 | 文件 | 用途 | 评审是否需要 |
| --- | --- | --- | --- |
| **交付类** | `db/init.sh`、`backend/run.sh`、`deploy/bootstrap.sh` | 初始化数据、启动 inn-api、一键起依赖 | 需要，步骤见 §4 |
| **开发自检类** | `compliance_check.py`、`periodic_check.sh`、`run_loadtest.py`、`package.sh`、`reset-demo.sh`、`seed_embeddings.py` | 合规自检、压测、打包、重置演示数据 | 可选，用于复核 |
| **本机开发态** | `start-local.sh`、`watchdog.sh`、`capture.mjs`、`record.mjs` | 作者机器上的进程看护与截图/录屏 | **不需要**，路径与本机绑定 |

> `start-local.sh` / `watchdog.sh` / `capture.mjs` / `record.mjs` 依赖作者机器的
> `~/dify`（Dify 部署）与 `~/dify-shot`（chromium），仅用于生产素材，不属于运行说明的一部分。

## 8.3 打包与自检脚本

```bash
bash tools/reset-demo.sh     # 恢复到"评审第一次打开"的状态（重建数据 + 清空记忆）
bash tools/package.sh        # 生成 dist/dify-submission-<日期>.zip + MANIFEST.sha256（含每个文件 sha256）
python3 tools/compliance_check.py   # 11 项合规自检
bash tools/run_loadtest.py 20       # 20 轮连打压测（输出 evidence/logs/run-loadtest.md）
```

## 8.35 开发过程记录

`docs/progress-log.md` 是按时间线整理的项目进展（每个阶段做了什么、怎么验证的）；
`docs/progress-log.raw.md` 是逐次自检的机器输出（append-only）。

## 8.36 自检项说明

11 项自检分别在验什么、怎么手工复核、失败意味着什么，见
[docs/verification.md](docs/verification.md)。

## 8.4 提交前检查清单

对照赛题 §4.1–§4.4 的逐项核对表（含每项指向的文件）见
[docs/submission-checklist.md](docs/submission-checklist.md)。

## 8.5 评审 FAQ

常见疑问（为什么不拿 seekdb 当 Dify 数据库、为什么 embedding 用哈希、为什么没有 Code 节点、
断网会怎样……）见 [docs/faq.md](docs/faq.md)。

## 9. 第三方素材与许可

- 台词、传闻、演示账本数据均为本项目原创，未复用第三方文本；
- 未复用公开工作流/代码；Dify、seekdb、插件均为官方发布版本，按各自许可证使用。

---

## 10. 提交材料对照（赛题 §4）

| 赛题要求 | 本仓库对应 | 说明 |
| --- | --- | --- |
| §4.1 Dify DSL + 用途/导入顺序 + 版本 | [dsl/01_inn_chatflow.yml](dsl/01_inn_chatflow.yml)、[dsl/README.md](dsl/README.md) | 单文件；1.17.0 导出；重导入已验证 |
| §4.1 重新绑定知识库/工具/服务地址 | [dsl/README.md](dsl/README.md) | 三处 HTTP 节点地址 + 六个模型节点 |
| §4.2 作品创意/玩法/体验/分工 | §1、§2 | |
| §4.2 运行环境与版本 | §3 | Dify 1.17.0 / seekdb 1.4.0.0 / Python 3.12 / 插件 0.0.73 |
| §4.2 完整步骤与应用入口 | §4 | |
| §4.2 外部服务、网络、资源、限制 | §7、§7.2 | |
| §4.3 验证样例 + 实际结果 + 证据 | [samples/](samples/)、[evidence/](evidence/) | S1–S7，日志为原始输出 |
| §4.4 使用 seekdb 部署 Dify（若适用） | §7.1 | **本作品不适用**，已如实声明 |
| §4.4 知识库/外部数据 | [db/](db/)、[db/init.sh](db/init.sh) | 数据全部为本项目原创，含初始化脚本 |
| §4.4 预置记忆/互动状态 | [db/04_seed_demo.sql](db/04_seed_demo.sql)、§11 | 演示玩家 `p_demo01` |
| §4.4 现成插件 | §3 版本表 | `langgenius/openai_api_compatible:0.0.73`，Marketplace |
| §4.4 自定义插件 / 自定义后端 | `backend/` | 自定义后端已附源码与启动说明；未使用自定义插件 |

## 11. 标识与数据关联（赛题 §4.4 "用户/角色/会话标识如何与工作流关联"）

| 标识 | 产生方式 | 写入位置 | 在 DSL 里的位置 |
| --- | --- | --- | --- |
| `player_id` | 玩家在 Start 节点填写；留空时后端按 `sys.conversation_id` 生成稳定 ID | `inn_player.player_id` | Start 节点变量，经 HTTP 节点透传 |
| `conversation_id` | Dify 系统变量 `sys.conversation_id` | 账本行的 `session_id` | 四个 HTTP 节点的 params/body |
| `event_id` | seekdb 自增主键 | `inn_ledger.id` | 记账响应块 `EVENT=` |
| 角色 | 固定单一 NPC「柳三娘」 | `inn_line.npc` | 各 LLM 节点的 system prompt |
| 记忆边界 | 一玩家一份账本（`WHERE player_id=?` 强制过滤） | 全部查询 | 无跨玩家读取 |

演示数据：执行 `bash db/init.sh` 后，`p_demo01` 会被预置为"住了 3 天、仇值 62（T3 报复）、7 条旧账"的状态，
评审可直接用这个 ID 体验"翻旧账"与"逐客"，无需自己刷数据。
