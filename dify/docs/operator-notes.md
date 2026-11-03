# 本机运维备注（非提交材料，供开发/演示时使用）

## 1. 当前环境端口

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| seekdb（本项目） | **2891** | 2881 被本机 `obtest_bench` 实例占用，故本项目改用 2891 |
| inn-api | 8010 | FastAPI |
| Dify API | 5001 | gunicorn |
| Dify Web | 3000 | next dev（生产构建需 >5.5GB 内存，本机 8GB 会 OOM） |
| Dify 的 MySQL | 3307 | 用户态实例，datadir `/var/tmp/dify-mysql` |
| Dify 的 Redis | 6379 | 用户态 |

## 2. 看门狗

`dify/tools/watchdog.sh` 每 15 秒检查一次，掉线自动拉起 seekdb 与 inn-api：

```bash
bash dify/tools/watchdog.sh     # 前台常驻（建议放 tmux / 独立会话）
tail -f /home/ice/dify-project/.run/watchdog.log
```

注意：seekdb 启动约 50 秒，脚本用 `pgrep -x seekdb` 判断"是否在启动中"，
避免重复拉起两个实例抢同一 datadir。

## 3. 改 DSL 的正确姿势

DSL 在 Dify 里是"草稿 + 已发布"两份。命令行改法：

```bash
# 1) 改 dify/dsl/01_inn_chatflow.yml
# 2) 覆盖导入到同一个 app（不会新建应用）
python3 - <<'PY' > /tmp/imp.json
import json
y=open('/home/ice/dify-project/dify/dsl/01_inn_chatflow.yml').read()
print(json.dumps({"mode":"yaml-content","yaml_content":y,"app_id":"<app_id>"}, ensure_ascii=False))
PY
curl -s -b ~/dify/run/cookies.txt -H "X-CSRF-Token: $(awk '$6=="csrf_token"{print $7}' ~/dify/run/cookies.txt)" \
  -H "Content-Type: application/json" -X POST http://127.0.0.1:5001/console/api/apps/imports --data-binary @/tmp/imp.json
# 3) 发布（否则 UI 里跑的还是旧版本）
curl -s ... -X POST http://127.0.0.1:5001/console/api/apps/<app_id>/workflows/publish -d '{}'
```

**改完 DSL 一定要发布**，draft 跑通不代表发布版本也更新。

## 3.5 机器重启后怎么恢复（一条命令）

本机重启会把所有进程清掉（2026-11-03 22:25 发生过一次）。恢复顺序已固化：

```bash
bash dify/tools/start-local.sh
```

它依次做：Dify 栈（MySQL/Redis/daemon/API/worker/Web）→ PowerContext → 看门狗（seekdb+inn-api）
→ 等待 2891/8010 就绪 → 重新登录 Dify 并刷新 cookie → 打印状态。
应用 ID 存在 `dify/tools/.local.env`（已 gitignore），不再依赖 `/tmp`。

## 4. 快捷命令

```bash
INN_APP_ID=<app_id> bash dify/tools/run_app.sh "往酒坛里兑水" p_demo01   # 跑一轮并打印节点输出
bash dify/db/init.sh                                                     # 重置演示数据
INN_APP_ID=<app_id> bash dify/tools/collect_evidence.sh                  # 重生成 evidence/logs
INN_APP_ID=<app_id> python3 dify/tools/compliance_check.py               # 8 项合规自检
```

## 4.5 本机有多个 seekdb 实例（重要）

这台机器上除了本项目的 `~/.seekdb` 实例，还有 `obtest_bench`（2881）、`obtest_al`（3051）等其它实例。
所以**任何"看 seekdb 在不在"的判断都必须限定本项目**：

```bash
# 正确：按 base-dir 判断
for p in $(pgrep -x seekdb); do
  tr '\0' ' ' < /proc/$p/cmdline | grep -q "dify-project/.seekdb" && echo mine=$p
done
# 错误：pgrep -x seekdb 会把别人的实例当自己人，导致永不重启
```

`tools/watchdog.sh` 已按 base-dir 判断，并且用 `flock` 保证单实例（两个看门狗会抢同一 datadir）。

## 4.8 压测

```bash
cd dify && python3 tools/run_loadtest.py 20          # 20 轮连打，报告写 evidence/logs/run-loadtest.md
```

注意：压测期间若 seekdb 被 OOM 杀掉，会出现"部分轮次 partial-succeeded"（走兜底话术，不写库），
看门狗会在 90 秒内拉起；异常轮次不影响主结论，但写进报告前建议先确认 `healthz` 为 ok。

## 4.9 自检会写数据

`compliance_check.py` 的 C3/C4/C9 会真的写账本（否则无法验证检索与记忆）。为了让**演示玩家**保持初始状态
（`p_demo01` 仇值 62、7 条旧账），自检统一使用 `p_check` / `p_check_pc` 两个专用玩家；
C3 会先造一条旧账再查相似事件，所以单独跑也能通过。

## 4.95 重置与打包

```bash
bash dify/tools/reset-demo.sh     # seekdb 重建 + PowerContext 记忆清空（两者必须一起做，否则记忆与账本会打架）
bash dify/tools/package.sh        # 产物在 ../dist/：zip + MANIFEST.sha256
```

注意：清 PC 记忆要**按端口杀进程**（`ss -lntp | grep :8090`），因为 `powercontext` exec 后命令行变成
`powercontext serve`，按 `server run` 字样匹配不到。

## 5. 已知环境问题

1. **内存紧张**：本机 9.3GB + 3.8GB swap，swap 常年接近打满；Dify web dev 编译、seekdb 启动都会把内存推到临界，
   历史上出现过 seekdb/inn-api 被 OOM 连带杀死 → 看门狗会拉起，重跑 `db/init.sh` 可恢复数据。
2. **登录态过期**：`tools/*.sh` 依赖 `~/dify/run/cookies.txt`（Dify 控制台 cookie），过期后需重新登录：
   ```bash
   B64=$(printf 'InnAdmin123!' | base64)
   curl -s -c ~/dify/run/cookies.txt -X POST http://127.0.0.1:5001/console/api/login \
     -H "Content-Type: application/json" -d "{\"email\":\"admin@inn.local\",\"password\":\"$B64\",\"remember_me\":true}"
   ```
3. **不要用 `pkill -f "某个字符串"` 杀进程**：命令行里含有同一字符串时会杀掉自己（踩过两次）。
   杀端口占用用 `ss -lntp | awk '/:PORT /{print $NF}'` 取 pid；杀 seekdb 用 `pkill -x seekdb`。

## 6. 界面截图怎么生成（无需人工点）

本机没有装浏览器自动化依赖，做法是「手动下 Chromium + Playwright 驱动」：

```bash
# 一次性准备
cd ~/dify-shot
npm i playwright --registry=https://registry.npmmirror.com
curl -sSL -o chromium.zip \
  https://cdn.npmmirror.com/binaries/playwright/builds/chromium/1148/chromium-linux.zip
unzip -q chromium.zip -d chromium          # 得到 chromium/chrome-linux/chrome

# 每次抓图（Dify 需已登录过一次、应用已发布）
cd ~/dify-shot
PLAYWRIGHT_MODULE=/home/ice/dify-shot/node_modules/playwright/index.mjs \
  node /home/ice/dify-project/dify/tools/capture.mjs <app_id> \
  /home/ice/dify-project/dify/evidence/screenshots
```

要点：
- **必须用 `http://localhost:3000`**，`127.0.0.1` 会被 Next dev 的跨域策略挡掉静态资源（页面卡在 spinner）；
- 开发模式有一个设计标注浮层（`styles-module__toolbar`），脚本用 CSS 隐藏；
- 对话截图走画布右上角的「预览」抽屉（`/chat/<id>` 路由在 dev 下编译极慢，会超时）；
- `playwright install chromium` 会额外下载 headless-shell（npmmirror 没有），所以直接下 `chromium-linux.zip` 并用 `executablePath` 指定。
