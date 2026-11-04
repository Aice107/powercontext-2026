# 证据索引

本目录是"实际运行结果"的原始记录。所有文件由 `tools/collect_evidence.sh` 与手工命令生成，未经编辑。

| 编号 | 验证点 | 证据文件 | 说明 |
| --- | --- | --- | --- |
| S0 | 向量落库自检 | [logs/S0_embeddings.txt](logs/S0_embeddings.txt) | `db/init.sh` 后 12/12 账本行、2/2 传闻均有 embedding（排除"初始化时机导致无向量"） |
| S1 | 首次入店 | [logs/S1_first_visit.log](logs/S1_first_visit.log)、[logs/S1_db_after.txt](logs/S1_db_after.txt) | 新玩家建档，`events=0` |
| S2 | 记账 | [logs/S2_prank.log](logs/S2_prank.log)、[logs/S2_db_ledger.txt](logs/S2_db_ledger.txt) | 账本行 + `DELTA=12`；`vec` 列显示该行确有 `vector(1024)` |
| S3 | 翻旧账（混合检索） | [logs/S3_old_grudge.log](logs/S3_old_grudge.log)、[logs/S3_sql_hybrid.txt](logs/S3_sql_hybrid.txt) | **SQL 直接执行结果**：两条事件 `vsim=1.0000/0.8700`、`ft=3.86/9.31`，含 EXPLAIN 与索引清单 |
| S4 | 跨会话记忆 | [logs/S4_cross_session.log](logs/S4_cross_session.log)、[logs/S4_db_player.txt](logs/S4_db_player.txt) | 档案块 `62/4/3/7` 与库内一致 |
| S5 | 逐客分支 | [logs/S5_expel.log](logs/S5_expel.log)、[logs/S5_expel_nodes.txt](logs/S5_expel_nodes.txt) | 数值链 62→76→92；节点 `是否逐客 case=true → 逐客令` |
| S5b | 求原谅（同状态续跑） | [logs/S5_forgive.log](logs/S5_forgive.log)、[logs/S5_forgive_nodes.txt](logs/S5_forgive_nodes.txt) | 92→68；节点 `是否逐客 case=false → 三娘回应` |
| S5c | 账本快照 | [logs/S5_db_ledger.txt](logs/S5_db_ledger.txt) | 上述两条路径的账本行（含 grudge_after 链） |
| S6 | 打烊结算 | [logs/S6_settle.log](logs/S6_settle.log) | 《账本长卷》全文 |
| S7 | 依赖不可用兜底 | [logs/S7_degraded.log](logs/S7_degraded.log) | seekdb/inn-api 挂掉时的兜底话术 |
| S7b | PC 不可用降级 | [logs/S7b_pc_down.log](logs/S7b_pc_down.log)、[logs/S7b_pc_warnings.txt](logs/S7b_pc_warnings.txt) | PC 停 → `MEMORY=无` 仍应答；PC 起 → 记忆回来 |
| S8 | 档位梯度 | [logs/S8_tier_gradient.log](logs/S8_tier_gradient.log) | 同一句话在 T1/T2/T3 下的三种反应 |
| S9 | PowerContext 记忆 | [logs/S9_pc_memory.log](logs/S9_pc_memory.log)、[logs/S9_pc_scope.txt](logs/S9_pc_scope.txt)、[logs/S9_pc_search.json](logs/S9_pc_search.json) | Scope 映射 + 印象写入 + `search` 命中（reset-demo 后状态一致） |
| S10 | 和解线 | [logs/S10_kindness.log](logs/S10_kindness.log)、[logs/S10_db_ledger.txt](logs/S10_db_ledger.txt) | 62→38（`DELTA=-24`），库内该行为 `kindness/-3` |
| 体验路径 | 四步走 | [logs/demo-path-3min.log](logs/demo-path-3min.log) | README §1.4 的四步 |
| seekdb 作 Dify 元库 | 可行性 | [logs/dify-on-seekdb.md](logs/dify-on-seekdb.md) | 迁移 143 表 + 独立实例 /health、/setup |
| 全新导入演练 | 模拟评审 | [logs/fresh-import-drill.md](logs/fresh-import-drill.md) | 从零导入 → 19 节点 → 跑通一轮 |
| 自愈演练 | 故障恢复 | [logs/selfheal-drill.md](logs/selfheal-drill.md) | inn-api 2s / seekdb 72s 恢复，数据无损 |
| 压测 | 20 轮 | [logs/run-loadtest.md](logs/run-loadtest.md) | 20/20 成功，p50 5.6–6.3s |
| DSL | 可重导入 | [../dsl/01_inn_chatflow.yml](../dsl/01_inn_chatflow.yml) | 1.17.0 重导入 `status=completed` |

> 所有 DB 核验文件（S0/S1_db/S2_db/S3_sql/S4_db/S5_db/S10_db）都由 `mysql -P2891` 直连产生，
> `tools/collect_evidence.sh` 结尾会校验它们**不含连接错误且非空**，否则整批作废。

## 证据是怎么产生的

```bash
# 1) 起依赖（seekdb + inn-api），见 deploy/bootstrap.sh
# 2) 逐条跑样例，输出落到本目录
INN_APP_ID=<app_id> bash tools/collect_evidence.sh
# 3) 合规自检（会校验本索引里每个链接都存在）
INN_APP_ID=<app_id> python3 tools/compliance_check.py
```

## 界面截图（screenshots/）

由无头 Chromium 自动抓取（`tools/capture.mjs`），非手工拼图：

| 文件 | 内容 |
| --- | --- |
| [screenshots/01-signin.png](screenshots/01-signin.png) | Dify 登录页（1.17.0） |
| [screenshots/02-app-list.png](screenshots/02-app-list.png) | 工作区应用列表：《记仇客栈》 |
| [screenshots/03-canvas.png](screenshots/03-canvas.png) | 编排画布：19 个节点与分支 |
| [screenshots/04-chat-open.png](screenshots/04-chat-open.png) | 应用预览抽屉：开场白与四个建议问题 |
| [screenshots/05-chat-prank.png](screenshots/05-chat-prank.png) | 第一次恶作剧：记账批注 |
| [screenshots/06-chat-old-grudge.png](screenshots/06-chat-old-grudge.png) | 第二次同类：**翻旧账**（"前天刚往酒坛里兑了半坛水…"） |
| [screenshots/07-chat-settle.png](screenshots/07-chat-settle.png) | 打烊：《账本长卷》与判词 |

> 说明：画布左上角显示"未发布"是编辑器自动保存（含节点坐标/视口）造成的 draft 与发布版差异，
> 不影响运行：发布版本确实存在（Dify 数据库 `workflows` 表有多个版本记录），预览与 API 运行均基于该应用；
> 若要做完全一致的取证，导入 DSL 后点一次「发布」即可，draft 与 published 哈希相同。

## 演示视频（recordings/）

| 文件 | 内容 | 说明 |
| --- | --- | --- |
| [recordings/demo-inn.webm](recordings/demo-inn.webm) | 登录 → 画布 → 预览抽屉三轮对话（兑水 / 再兑水 / 打烊长卷） | 无头 Chromium 屏幕录制，约 1 分 50 秒，6.3 MB |

```bash
# 重新录制
PLAYWRIGHT_MODULE=/home/ice/dify-shot/node_modules/playwright/index.mjs \
  node tools/record.mjs <app_id> evidence/recordings
```

> Playwright 自带的 ffmpeg 只编了 libvpx，没有 x264，所以产物是 webm（Chrome/Firefox/Edge 可直接播放）；
> 需要 mp4 时用系统 ffmpeg 转一次即可：`ffmpeg -i demo-inn.webm -c:v libx264 -pix_fmt yuv420p demo-inn.mp4`。

## 关于截图/录屏

`screenshots/` 与 `recordings/` 预留给评审端录屏（浏览器窗口），本仓库提交的文本日志已能独立复现结论：
每个日志包含 Dify 节点实际输出（HTTP 响应体、LLM 回答），配合 samples/ 的步骤即可逐条核对。
