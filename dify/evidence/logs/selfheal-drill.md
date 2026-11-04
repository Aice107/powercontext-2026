# 自愈演练 2026-11-04 12:02

对象：看门狗（tools/watchdog.sh）对 inn-api 与本项目 seekdb 的自动恢复能力

## 1. inn-api
- 杀掉 pid=6136（端口 8010）
- ✓ 2s 后被看门狗拉起

## 2. seekdb
- 杀掉 pid=18508（端口 2891，datadir=/home/ice/dify-project/.seekdb）
- ✓ 72s 后由新进程接管（18508 → 19139）

## 3. 恢复后数据可用性
- inn.inn_ledger 行数：20
- inn-api healthz：{"status":"ok","seekdb":true,"database":"inn","schema_version":"2026-11-03","powercontext":true,"embedding_mode":"hash","embedding_dim":1024}

## 结论
- **PASS**：两处故障均被看门狗自动恢复，数据无损
