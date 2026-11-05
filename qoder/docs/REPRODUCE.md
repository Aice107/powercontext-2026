# 运行说明（REPRODUCE）

目标环境：Linux x86_64（macOS 亦可，pylibseekdb 不支持 Windows）。全程不需要 docker、不需要任何 API Key。

## 0. 前置

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Python | ≥ 3.11 | 实测 3.12 |
| uv（推荐）或 pip | 任意 | 用于安装依赖 |
| curl / bash | - | 脚本使用 |
| 磁盘 | ≥ 1 GB | 模型约 95 MB + seekdb 数据 |

## 1. 获取代码

```bash
git clone <本仓库地址>
cd <仓库>/qoder
```

## 2. 安装依赖与模型（约 5 分钟）

```bash
bash scripts/setup.sh
```

脚本做两件事：

1. 在仓库根上建 `../.venv-app` 虚拟环境，安装：
   `powercontext[server,client,cli,seekdb]==1.5.0`、`pylibseekdb==1.4.0.post2`、`pyobvector`、`pymysql`、`fastapi`、`uvicorn`、`httpx`、`onnxruntime`、`tokenizers`、`numpy`；
2. 从 `hf-mirror.com` 下载 `Xenova/bge-small-zh-v1.5` 的 ONNX 权重与分词器到 `qoder/.data/models/bge-small-zh-v1.5-onnx/`（约 95 MB）。
   网络可直连 huggingface 时可 `HF_ENDPOINT=https://huggingface.co bash scripts/setup.sh`。

## 3. 启动三个服务

```bash
bash scripts/run_all.sh
```

| 服务 | 端口 | 就绪检查 |
| --- | --- | --- |
| 本地向量服务 | 8710 | `curl http://127.0.0.1:8710/health` |
| PowerContext Server | 8000 | `curl http://127.0.0.1:8000/health/ready`，`checks.database` 与 `checks["inference.embedding"]` 均应为 `ready` |
| 主应用 | 8712 | `curl http://127.0.0.1:8712/api/health` |

`deploy/powercontext.env` 已把 PowerContext 的存储指向嵌入式 seekdb（`DATABASE_KIND=seekdb`）、
把 embedding 指向本地向量服务（`http://127.0.0.1:8710/v1`，`DIMENSION=512`，`SEND_DIMENSIONS=false`）。

## 4. 体验主要功能

1. 打开 <http://127.0.0.1:8712>，顶部三个状态点应全绿；
2. 「语料」页 → **导入示例语料**（16 篇 → 56 个分块）；
3. 「混合检索」页 → 输入 `怎么提升召回率`（hybrid）→ 结果每条带出处；点开"查看 seekdb 取证"能看到实际执行的 `dbms_hybrid_search` 语句；
4. 「混合检索」页 → 换 `mode` 分别用 vector / fts 检索 `量化会不会掉点`，观察两路失败样本互补；
5. 「记忆」页 → 写入偏好 `组会材料要结论先行`，再召回 `导师对材料的要求`（`matched_by` 应含 `vector`，即语义召回生效）；
6. 「组会草稿」页 → 用默认窗口 2026-10-26 ~ 2026-11-01 生成草稿：抬头有"提前一天发"提醒、结论在最前、数据在进展之前、每条挂出处，附录列出记忆命中与 SQL。

一键脚本版（同样内容，输出留档到 `evidence/logs/`）：

```bash
bash scripts/verify.sh
```

## 5. 单元测试

```bash
../.venv-app/bin/python -m pytest tests/ -q    # 5 passed
```

## 6. 停止与重置

```bash
bash scripts/stop_all.sh        # 停三个服务
bash ../.venv-app/bin/python -m app.cli reset   # 仅删 seekdb 数据（模型与日志保留）
python -m app.cli reset --all   # 连模型与日志一起删（在 qoder/ 目录下执行）
```

## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| `seekdb_open failed: code=-1` | 偶发竞态，应用已内置 3 次重试；仍失败时删 `.data/seekdb` 后重试 |
| PowerContext 起动慢（约 1 分钟） | 首次建 seekdb 记忆表并跑迁移，属正常 |
| 模型下载失败 | 换 `HF_ENDPOINT=https://hf-mirror.com`（默认即镜像）重跑 setup |
| 8000 被占用 | `deploy/powercontext.env` 改 `POWERCONTEXT_SERVER_HTTP_PORT`，同时 `GEWU_PC_URL` 指向新端口 |
| `模型缺失：.../model.onnx` | 未完成 setup 第 2 步 |
