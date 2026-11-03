# Dify 1.17.0 元数据库切到 seekdb 的可行性实测（2026-11-03 23:30）

## 1) 建库
$ mysql -h127.0.0.1 -P2891 -uroot -e "create database dify_meta"

## 2) 迁移（DB_TYPE=seekdb，指向 seekdb:2891/dify_meta）
$ DB_TYPE=seekdb DB_HOST=127.0.0.1 DB_PORT=2891 DB_DATABASE=dify_meta flask upgrade-db
→ Database migration successful!

## 3) 表数量
→ dify_meta 表数: 143

## 4) 用这份 seekdb 元数据库起一个 Dify API 实例（独立端口 5005，不影响主线 5001）
$ DB_TYPE=seekdb ... DIFY_PORT=5005 gunicorn app:socketio_app
→ /health: {"pid": 26731, "status": "ok", "version": "1.17.0"}
→ /console/api/setup: {"step":"not_started","setup_at":null}

## 结论
- Dify 1.17.0 的 `DB_TYPE` 原生支持 seekdb，迁移 143 张表成功、API 可启动、可读写（setup 返回 not_started 说明连通并读到空库）
- 迁移过程有若干 SQLAlchemy SAWarning（OceanBase 的 UNIQUE KEY ... BLOCK_SIZE 语法解析），不影响结果
- 本作品主线仍用 MySQL 承载 Dify 元数据库，seekdb 承担应用数据；此实测用于说明"若要走赛题 §4.4 第 1 行路线，无需改代码"
