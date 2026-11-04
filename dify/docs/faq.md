# 评审常见问题（FAQ）

> 面向评审：这些都是"看材料时最可能卡住"的点，逐条给出结论、理由和可核对的位置。

## Q1 为什么不让 seekdb 直接当 Dify 的数据库？

**结论**：本作品让 seekdb 承担**应用数据与检索**，Dify 仍用自己的 MySQL/PostgreSQL。

- 理由：赛题 §2.2 允许"为应用提供数据存储、查询与检索能力"，并要求使用 seekdb 部署 Dify 时额外提供适配分支与部署配置；
  20 分赛题的重心是"可运行 + 好玩 + 技术结合有效"，改造 Dify 元数据库会引入上游差异和复现风险。
- 已如实声明：README §7.1 写明了这个取舍，不宣称未做的事。
- **已实测**：Dify 1.17.0 的 `DB_TYPE` 原生支持 `seekdb`（`api/configs/middleware/__init__.py`）。
  我们用一份独立库 `dify_meta` 跑了一次迁移 + 起了一个独立端口（5005）的 API 实例：

  | 检查 | 结果 |
  | --- | --- |
  | `DB_TYPE=seekdb flask upgrade-db` | `Database migration successful!`，建表 **143** 张 |
  | `/health` | `{"status":"ok","version":"1.17.0"}` |
  | `/console/api/setup` | `{"step":"not_started"}`（说明连通并读到空库） |

  证据：`evidence/logs/dify-on-seekdb.md`；可用 `tools/verify-seekdb-meta.sh` 复跑
  （注意：本机这个 seekdb 实例上 `DROP DATABASE` 会卡住并阻塞后续 DDL，脚本因此每次用唯一库名、
  清理只做 best-effort；在干净的评审环境里没有这个限制）。也就是说，若要走赛题 §4.4 第 1 行那条路线，**不需要改代码**，
  改 `DB_TYPE=seekdb` + 连接参数即可；本作品没走这条路是为了让主线复现更稳（见上文），不是做不到。

## Q2 为什么 embedding 用哈希向量，而不是 bge / OpenAI embedding？

**结论**：为了"评审无需作者本地服务即可复现"，默认 `EMBEDDING_MODE=hash`。

- 场景特点：检索对象是 10–40 字的短句（"往酒坛里兑水"），字符 unigram+bigram 哈希已能区分语义簇；
  实测跨表述命中：`往酒坛里兑水` vs `往酒坛里兑了半坛井水` → `vsim=0.96`。
- 可切换：`EMBEDDING_MODE=api` + `EMBEDDING_BASE_URL/API_KEY/MODEL` 接任意 OpenAI 兼容 embedding，
  但需要把 `db/01_schema.sql` 的 `VECTOR(1024)` 维度改成与模型一致并重建表。
- 限制已写明：README §3 与 §7.5，不追求语义泛化。

## Q3 为什么不用 Code 节点？

**结论**：部署环境非 root，`dify-sandbox`（chroot+seccomp）跑不起来，所以 DSL 里一个 Code 节点都没有。

替代方案（都在 DSL 里可查）：

| 原本想用 Code 做 | 实际做法 |
| --- | --- |
| 意图/严重度判定 | 参数提取器节点（LLM + function calling） |
| 档位判定 | 后端 `rules.py` 的纯函数，Dify 用 `contains TIER=4` 分支 |
| JSON 解析 | 后端提供 `format=block` 的 `KEY=VALUE` 文本（见 `docs/design.md` §4） |

## Q4 为什么前端是 dev 模式？

**结论**：这台 8GB 机器跑不动 `next build`（实测峰值 RSS 5.5GB，内核 OOM 杀掉）。

- 影响：首屏 60–100 秒（按需编译），之后正常；功能与生产构建一致。
- 换到 ≥16GB 的机器时：`cd web && pnpm build && pnpm start` 即可，DSL 不用改。
- 已写明：README §7.1、`docs/operator-notes.md`。

## Q5 为什么还要一个 inn-api，不把所有逻辑放进 Dify？

**结论**：Dify 负责编排，inn-api 只做 seekdb 的读写与聚合，这样"谁在编排"是可验证的。

- 如果后端做判定：删掉 Dify 后逻辑还在，赛题"Y 承担核心流程编排"就无从证明；
- 现在的边界：后端不知道"兑水是不是恶作剧"，只接收 `severity=2`；档位、分支、提示词全在 Dify。
- 逐条对照见 `docs/division-of-labor.md`。

## Q6 已经有 seekdb 账本了，为什么还要 PowerContext？

**结论**：两者记的不是一回事，分工写在 README §2 与 `docs/division-of-labor.md` §3。

| | seekdb | PowerContext |
| --- | --- | --- |
| 记什么 | 事：时间、类型、严重度、数值 | 人：印象、关系、档位情绪 |
| 谁用 | 检索"翻旧账"、算仇值 | 进店时召回，拼进 prompt |
| 证据 | `S2/S3` 日志 | `S9` 日志（`MEMORY=` 行） |

- 赛题只要求两者之一；同时使用是为了让"她记得你这个人"不只是数值。
- PC 未配置时整层跳过，应用仍可运行（`PC_BASE_URL` 为空即降级）。

## Q7 换一个会话，她还记得我吗？

**两种入口**：

1. 玩家标识留空 → 后端按 `sys.conversation_id` 生成稳定 ID，**同一会话内**一致；
2. 玩家标识填同一个值（如 `p_demo01`）→ **跨会话**一致，这就是 S4 的验证方式。

标识规则写在 README §11；`inn_pc_scope` 表保存"玩家 → Scope"映射，重启不丢。

## Q8 被逐客之后还能玩吗？

**能，而且这是设计的一部分**：

- 逐客分支的触发条件是「`TIER=4` **且** 本次事件 `SEV` 不为负」——即**只有继续作恶才被赶**；
- 满仇值时做善举（修屋顶、赔钱、劈柴）会走正常回应，仇值按 `severity×8` 下降，可以把人"哄回来"；
- 实测：仇值 100 时修屋顶 → 76，语气从"逐客"变回"冷脸带刺"。

## Q9 数据怎么重置，评审会不会看到我跑脏的状态？

```bash
bash db/init.sh      # 重建表 + 重灌台词/传闻/演示玩家（p_demo01 仇值 62、7 条旧账）
rm -f ../.pc/pc.db   # 可选：清空 PowerContext 记忆（sqlite 后端）
```

合规自检使用 `p_check` / `p_check_pc` 专用玩家，不会污染演示玩家的状态。

## Q10 断网/依赖挂掉会怎样？

| 挂掉的组件 | 表现 | 恢复 |
| --- | --- | --- |
| seekdb | 进店节点返回 500 → Dify 走 `default-value` → 兜底话术"账本让雨打湿了" | 看门狗 90 秒内拉起 |
| inn-api | 同上 | 看门狗拉起 |
| PowerContext | 记忆层静默跳过，`MEMORY=无`，其余照常 | 重新起 `powercontext server run` |
| 模型 API | 节点报错，workflow `failed` | 恢复 Key 后重试 |

兜底表现见 `samples/S7_degraded.md` 与真实日志 `evidence/logs/S7_degraded.log`。

## Q11 仓库里有没有真实 API Key？

**没有**，可自证：

```bash
grep -rE "sk-[A-Za-z0-9]{16,}" dify/ || echo "clean"
```

- 模型 Key 存在 Dify 数据库（凭据表加密），DSL 导出用 `include_secret=false`，`dependencies` 只有插件标识；
- `backend/.env.example` 全是占位符；`.env` 与 `.local.env` 已 gitignore。

## Q12 这套东西能不能一键跑起来？

- 有 Docker 的环境：按 README §4 起 seekdb → `db/init.sh` → inn-api → 导入 DSL → 绑地址/模型，约 10 分钟；
- 本项目开发机（无 Docker、无 root）：`bash tools/start-local.sh` 一条命令拉起全部依赖（机器重启后也用这条）。
