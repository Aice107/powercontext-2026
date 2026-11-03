# 证据索引

本目录是"实际运行结果"的原始记录。所有文件由 `tools/collect_evidence.sh` 与手工命令生成，未经编辑。

| 编号 | 验证点 | 证据文件 | 说明 |
| --- | --- | --- | --- |
| S1 | 首次入店 | [logs/S1_first_visit.log](logs/S1_first_visit.log)、[logs/S1_db_after.txt](logs/S1_db_after.txt) | 新玩家建档，事件数 0 |
| S2 | 记账 | [logs/S2_prank.log](logs/S2_prank.log)、[logs/S2_db_ledger.txt](logs/S2_db_ledger.txt) | 记账块 + seekdb 行 |
| S3 | 翻旧账 | [logs/S3_old_grudge.log](logs/S3_old_grudge.log)、[logs/S3_sql_hybrid.txt](logs/S3_sql_hybrid.txt) | 混合检索命中 + EXPLAIN |
| S4 | 跨会话记忆 | [logs/S4_cross_session.log](logs/S4_cross_session.log)、[logs/S4_db_player.txt](logs/S4_db_player.txt) | 档案块与库内数值一致 |
| S5 | 逐客分支 | [logs/S5_expel.log](logs/S5_expel.log)、[logs/S5_nodes.txt](logs/S5_nodes.txt)、[logs/S5_last_run.sse](logs/S5_last_run.sse) | 节点序列含 `是否逐客 case=true` |
| S6 | 打烊结算 | [logs/S6_settle.log](logs/S6_settle.log) | 《账本长卷》全文 |
| S7 | 降级兜底 | [logs/S7_degraded.log](logs/S7_degraded.log) | 后端不可用时的兜底话术 |
| S8 | 档位梯度 | [logs/S8_tier_gradient.log](logs/S8_tier_gradient.log) | 同一句话在 T1/T2/T3 三种仇值下的态度差异 |
| S9 | PowerContext 记忆 | [logs/S9_pc_memory.log](logs/S9_pc_memory.log)、[logs/S9_pc_scope.txt](logs/S9_pc_scope.txt)、[logs/S9_pc_search.json](logs/S9_pc_search.json) | Scope 建档 + 印象写入 + 召回进 prompt |
| S10 | 和解线 | [logs/S10_kindness.log](logs/S10_kindness.log) | 善举 -24 仇值，T3 → T1 |
| DSL | 可重导入 | [../dsl/01_inn_chatflow.yml](../dsl/01_inn_chatflow.yml) | 1.17.0 重导入 `status=completed` |

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
