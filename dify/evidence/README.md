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
| DSL | 可重导入 | [../dsl/01_inn_chatflow.yml](../dsl/01_inn_chatflow.yml) | 1.17.0 重导入 `status=completed` |

## 证据是怎么产生的

```bash
# 1) 起依赖（seekdb + inn-api），见 deploy/bootstrap.sh
# 2) 逐条跑样例，输出落到本目录
INN_APP_ID=<app_id> bash tools/collect_evidence.sh
# 3) 合规自检（会校验本索引里每个链接都存在）
INN_APP_ID=<app_id> python3 tools/compliance_check.py
```

## 关于截图/录屏

`screenshots/` 与 `recordings/` 预留给评审端录屏（浏览器窗口），本仓库提交的文本日志已能独立复现结论：
每个日志包含 Dify 节点实际输出（HTTP 响应体、LLM 回答），配合 samples/ 的步骤即可逐条核对。
