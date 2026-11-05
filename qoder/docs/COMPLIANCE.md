# 赛题验收对照（COMPLIANCE）

逐条对照赛题文档（qd.md）的基础验收、评价维度与提交材料要求，标注本项目如何满足、证据在哪。

## 基础验收

| 验收项 | 本项目的满足方式 | 证据位置 |
| --- | --- | --- |
| 1. 网站可访问（Qoder Sites 发布，未登录可打开） | 项目网站用 Qoder Sites 发布并设为「任何人都可访问」 | 网址见 `docs/SUBMIT.md`；站点「访问统计」可核对 |
| 2. 项目能够运行 | `bash scripts/setup.sh && bash scripts/run_all.sh` 即可三服务就绪；`bash scripts/verify.sh` 一键跑通主要功能 | `docs/REPRODUCE.md`；`evidence/logs/S0~S9` |
| 3. Qoder 开发可核对 | 主要功能（后端三模块、前端四页、脚本、文档）全部由 Qoder 会话完成；开发过程记录 | `docs/QODER_LOG.md`（含对话截图与账号 UID） |
| 4. 技术结合有效 | seekdb：混合检索 SQL 可取证；PowerContext：记忆写入/召回/复用全链路留痕 | `docs/VERIFICATION.md` 样例 1~5；`docs/DIVISION-OF-LABOR.md` |

## 技术结合要求（2.2）

| 要求 | 实际作用 | 核对 |
| --- | --- | --- |
| seekdb：数据存储、查询与检索 | 知识分块的 向量+l2、ngram 全文、term/range 过滤、RRF 融合，一条 `dbms_hybrid_search` 语句完成；同时是 PowerContext 记忆的存储后端 | `evidence/logs/S2_search_semantic.json` 内嵌 sql 字段；`S5_filter_window.json` 证明过滤下推 |
| PowerContext：记忆与上下文、保存并复用 | 偏好/约束写入后跨会话语义召回（`matched_by:["text","vector"]`），并真实改变草稿版式与内容 | `S7_recall.json`；`S8_draft.md` vs `S8b_draft_no_memory.md` 对照 |

## 提交材料清单（四）

| 材料 | 状态 | 位置 |
| --- | --- | --- |
| 项目网站网址 | 已发布（个人账号，任何人可访问） | `docs/SUBMIT.md` |
| 代码仓库 | 本仓库 `qoder/` 目录，分支 `2026-competition-ecosystem` 派生 | `docs/SUBMIT.md` |
| 运行说明 | 环境、依赖版本、seekdb/PowerContext 部署接入方式、完整步骤 | `docs/REPRODUCE.md` |
| 验证样例 | 初始数据、输入、操作步骤、预期结果、技术作用记录 | `docs/VERIFICATION.md` + `evidence/logs/` |
| Qoder 开发记录 | 关键环节对话截图 + 账号 UID | `docs/QODER_LOG.md` |
| 使用效果材料（鼓励） | 见下节说明 | `docs/SUBMIT.md` |

## 关于使用效果数据的说明（如实声明）

截至提交日，本项目的使用效果材料限于：

1. **开发者自测的提效对照**：用示例语料手工整理一周组会材料约需 40~60 分钟（翻 6 份记录 + 手写出处），
   用格物生成初稿 + 人工修订约 5 分钟。该数字是作者本人在示例语料上的受控自测，样本 N=1，仅作参考；
2. **站点访问统计**：Qoder Sites 的「访问统计」页可查看访问次数与独立访客（发布后可在站点设置中核对）；
3. 未组织真实外部用户试用，**不编造使用人数与用户反馈**。

## 其他合规事项

- 所有配置示例（`deploy/powercontext.env`、`scripts/*.sh`）不含任何真实 API Key、密码或凭据；
  本地部署无需任何云端凭据，模型权重经 hf-mirror 公开下载；
- 示例语料为按真实科研工作流撰写的**合成数据**，非真实用户数据，已在 ARCHITECTURE.md 与 VERIFICATION.md 声明；
- PowerContext、seekdb 的用法均来自其官方文档与源码；对 seekdb DSL 的实测边界（range 仅数值、rrf.weights 不可用）
  在 `docs/ARCHITECTURE.md` §4/§5 如实记录。
