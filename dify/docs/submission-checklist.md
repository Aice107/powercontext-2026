# 提交前检查清单（对照赛题 §4）

> 逐条核对，每项都指向仓库里的具体文件；打勾前请实际打开文件确认内容。最后更新：2026-11-03 23:00。

## A. §4.1 Dify DSL

- [x] DSL 文件：`dsl/01_inn_chatflow.yml`（唯一必需，19 节点 advanced-chat）
- [x] 适用版本：Dify **1.17.0**（导出 DSL `version: 0.7.0`），写在 `dsl/README.md`
- [x] 文件用途与导入顺序：`dsl/README.md` 表格（只有一个文件，顺序 1）
- [x] 重新绑定步骤：`dsl/README.md` "导入后必须重绑定的三处"（3 个 HTTP 节点地址 + 6 个模型节点）
- [x] 依赖声明：DSL `dependencies` 已含 `langgenius/openai_api_compatible:0.0.73@…`
- [x] 重导入验证：`tools/compliance_check.py` C1 每次巡检都会真导入一次（最近一次 `status=completed`）

## B. §4.2 运行说明

- [x] 作品创意/玩法/核心功能：`README.md` §1
- [x] 体验方式：`README.md` §1.4（3 分钟路径 + 演示玩家 `p_demo01`）
- [x] Dify 与指定技术的分工：`README.md` §2、`docs/division-of-labor.md`
- [x] 运行环境与软件版本：`README.md` §3（Dify 1.17.0 / seekdb 1.4.0.0 / Python 3.12 / 插件 0.0.73 / PowerContext 1.4.1）
- [x] 模型服务与配置项：`README.md` §3 + §4.4（DeepSeek `deepseek-flash`，需 function calling）
- [x] Embedding 说明：`README.md` §3（默认 hash 模式；切 api 模式的变量与维度要求）
- [x] Rerank：未使用，已注明
- [x] 完整步骤（依赖 → 导入 DSL → 初始化数据 → 启动 → 入口）：`README.md` §4
- [x] 应用入口：`README.md` §4.5（控制台预览 / 应用 API）
- [x] 外部服务获取与网络条件：`README.md` §7.2
- [x] 资源条件：`README.md` §7.2（seekdb ≥2GB、Dify ≥4GB）
- [x] 已知功能限制：`README.md` §7（7 条）+ `docs/faq.md`
- [x] 配置示例用占位值：`backend/.env.example`
- [x] 复用第三方素材：无（`README.md` §9 声明台词/数据均为原创）

## C. §4.3 验证样例与运行证据

- [x] 样例覆盖 10 组：`samples/S1`–`S10`（首次/记账/翻旧账/跨会话/逐客/求原谅/结算/降级/档位梯度/记忆/和解）
- [x] 每组含"初始状态 / 输入 / 预期 / 证据 / 恢复方法"（C6 自检会检查四个关键词）
- [x] 实际运行结果：`evidence/logs/`（17 个日志 + 1 个节点序列 + 1 个 SSE）
- [x] UI 截图 7 张：`evidence/screenshots/`
- [x] 演示录屏：`evidence/recordings/demo-inn.webm`（1 分 50 秒）
- [x] 指定技术作用记录：
  - seekdb：`logs/S2_db_ledger.txt`（行）、`logs/S3_sql_hybrid.txt`（EXPLAIN）、`logs/*.log` 里的 `SIM=`/`LINES=`
  - PowerContext：`logs/S9_pc_scope.txt`（Scope 映射）、`logs/S9_pc_search.json`（检索响应）、`logs/S9_pc_memory.log`（`MEMORY=` 行）
- [x] 连续操作的恢复方法：每组末尾都有 `bash db/init.sh`

## D. §4.4 按依赖补充的材料

| 依赖 | 材料 | 位置 |
| --- | --- | --- |
| seekdb 部署 Dify | **不适用**（本作品不让 seekdb 承载 Dify 元数据库） | `README.md` §7.1 已声明，并给出可选做法 |
| 知识库/外部数据 | 无需外部数据；台词/传闻/演示账本均随仓库交付，含初始化脚本 | `db/01_schema.sql`、`db/02_seed_lines.sql`、`db/04_seed_demo.sql`、`db/init.sh` |
| 预置记忆/互动状态 | `p_demo01`（仇值 62、7 条旧账）、`p_tier1`、`p_tier2` | `db/04_seed_demo.sql`；标识关联见 `README.md` §11 |
| 现成插件 | `langgenius/openai_api_compatible:0.0.73`（Marketplace 安装） | `README.md` §3、`dsl/README.md` |
| 自定义插件 | 未使用 | — |
| 自定义后端 | inn-api 源码 + 依赖 + 启动说明 | `backend/`（`main.py`/`db.py`/`embedding.py`/`pc.py`/`rules.py`、`requirements.txt`、`run.sh`、`.env.example`） |

## E. 红线自查

- [x] 无真实 API Key：`grep -rE "sk-[A-Za-z0-9]{16,}" dify/` 为空（C7 每次巡检复核）
- [x] 无本地绝对路径硬编码在交付物中（`tools/*.sh` 里的 `~/dify` 属"本机开发态脚本"，已在 `docs/operator-notes.md` 标注，不属赛题材料）
- [x] 不宣称未实现的能力：seekdb 部署 Dify、知识库、自定义插件都明确写"不适用/未使用"
- [x] 提交分支：`2026-competition-ecosystem`，资产在 `dify/` 目录

## F. 一条命令复核

```bash
cd dify
INN_APP_ID=<你的 app_id> python3 tools/compliance_check.py   # 11 项：DSL/数据/检索/运行/PC/打包/文档一致性/说明/样例/凭证/证据
```

当前结果：**11/11 PASS**（明细见 `docs/progress-log.raw.md`，逐项说明见 `docs/verification.md`）。
