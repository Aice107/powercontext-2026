# 验证体系说明（10 项自检都在验什么）

> 面向评审：`tools/compliance_check.py` 每次巡检会跑下面 10 项。
> 这里写清每项**验什么、怎么手工复核、失败意味着什么**，方便你不信任脚本时自己动手。

```bash
python3 tools/compliance_check.py          # 人读
python3 tools/compliance_check.py --json   # 机读
```

---

## C1 DSL 可重导入（赛题 §4.1）

- **验什么**：把 `dsl/01_inn_chatflow.yml` 通过控制台 API 重新导入一次，返回 `status=completed*` 才算过；导入成功后会立刻把测试应用删掉。
- **手工复核**：Dify 控制台 → 应用 → 导入 DSL → 选该文件 → 应成功并在应用列表出现《记仇客栈》。
- **失败意味着**：DSL 结构不合法或依赖插件缺失（`dependencies` 里声明了 `langgenius/openai_api_compatible`）。

## C2 seekdb 承载数据（§2.2）

- **验什么**：`inn_player / inn_ledger / inn_rumor / inn_line` 四张表都在；向量索引（`vidx_*`）与全文索引（`FULLTEXT`）都存在；台词 ≥20 条。
- **手工复核**：
  ```sql
  SHOW TABLES FROM inn;
  SELECT index_name, index_type FROM information_schema.statistics WHERE table_schema='inn';
  SELECT COUNT(*) FROM inn.inn_line;
  ```
- **失败意味着**：没跑 `db/init.sh`，或建表脚本没执行完（向量索引要用 `CREATE VECTOR INDEX ... WITH (distance=cosine, type=hnsw)`，见 `db/01_schema.sql`）。

## C3 seekdb 检索生效（§2.2 "实际发挥作用"）

- **验什么**：先写一条"往酒坛里兑了半坛井水"，再写"又往酒坛里兑水"，要求返回的 `similar` 非空且带 `vsim`（向量分）或 `fulltext_hit`。
- **手工复核**：
  ```bash
  curl -s -X POST localhost:8010/inn/ledger -H 'Content-Type: application/json' \
    -d '{"player_id":"p_x","action_text":"往酒坛里兑了半坛井水","severity":2}'
  curl -s -X POST localhost:8010/inn/ledger -H 'Content-Type: application/json' \
    -d '{"player_id":"p_x","action_text":"又往酒坛里兑水","severity":1}'   # 看 similar
  ```
- **失败意味着**：向量/全文索引没建好，或 embedding 维度与 `VECTOR(1024)` 不一致。

## C4 Dify 应用可运行（§3.1-1）

- **验什么**：调 draft 工作流跑一轮"往酒坛里兑半坛水"，要求 `workflow_finished.status=succeeded` 且回答 ≥20 字。
- **手工复核**：控制台 → 应用 → 预览 → 发一句话，应看到三娘回应（不是"账本被雨打湿了"）。
- **失败意味着**：模型/地址没绑好，或 inn-api、seekdb 挂了（此时会走兜底话术，状态是 `partial-succeeded`）。

## C9 PowerContext 记忆生效（§2.2，可选层）

- **验什么**：`healthz` 里 `powercontext=true` 时，先写一条事件（自检玩家按小时轮换），再读 `/inn/session`，要求上下文块出现 `MEMORY=` 且不为"无"。
- **手工复核**：
  ```bash
  curl -s 'localhost:8010/inn/session?player_id=p_demo01&format=block' | grep MEMORY
  curl -s localhost:8090/health/ready
  ```
- **失败意味着**：PowerContext 没起或 `PC_BASE_URL` 没配。**注意**：未启用 PC 时这项会直接 PASS 并说明"未启用"（赛题只要求 seekdb 或 PC 之一）。

## C10 打包完整性（§4 提交物）

- **验什么**：把 `dify/` 打成 zip 到临时目录，检查 9 个必需文件都在，且没有 `.env` / `.local.env` / `.venv` / `__pycache__` 混进去。
- **手工复核**：`bash tools/package.sh` 然后 `unzip -l dist/*.zip`。
- **失败意味着**：打包脚本的排除规则被改坏，或必需文件被删。

## C5 运行说明完整（§4.2）

- **验什么**：`README.md` 是否覆盖七类要素——作品创意/玩法、体验方式、技术分工、运行环境、安装步骤、外部服务与网络、已知限制（按关键词集合判断）。
- **手工复核**：直接读 `README.md` §1–§7。
- **失败意味着**：运行说明缺章（赛题 §4.2 明确要求这六项 + 已知限制）。

## C6 验证样例完整（§4.3）

- **验什么**：`samples/` 至少 5 个 `S*.md`，且每份都含"初始 / 输入 / 预期 / 证据"四个关键词。
- **手工复核**：逐份读 `samples/S1..S10`，按步骤操作。
- **失败意味着**：样例缺要素，评审无法照着复现。

## C7 无真实凭证（§4.2 红线）

- **验什么**：全文扫描 `.yml/.md/.py/.sh/.sql/.json/.txt/.env`，匹配 `sk-[A-Za-z0-9]{16,}`。
- **手工复核**：`grep -rE "sk-[A-Za-z0-9]{16,}" dify/ || echo clean`。
- **失败意味着**：有真实 Key 进了仓库——必须立刻撤销并重新导出 DSL。

## C8 证据索引有效（§4.3）

- **验什么**：`evidence/README.md` 里的每个相对链接都指向真实存在的文件。
- **手工复核**：点开 `evidence/README.md` 逐个点链接。
- **失败意味着**：索引写了但文件没提交（常见于把 `*.sse` 排除了却仍在索引里引用）。

---

## 不在自检范围、但评审可能关心的

| 项 | 为什么没进自检 | 怎么看 |
| --- | --- | --- |
| UI 截图 / 录屏 | 需要浏览器，不适合每次巡检跑 | `evidence/screenshots/`、`evidence/recordings/` |
| 性能 | 20 轮压测耗时几分钟 | `evidence/logs/run-loadtest.md` |
| 自愈能力 | 要故意杀进程 | `evidence/logs/selfheal-drill.md` |
| seekdb 作 Dify 元库 | 需要独立库与端口，改动面大 | `evidence/logs/dify-on-seekdb.md` |
