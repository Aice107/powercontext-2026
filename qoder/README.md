# 格物 Gewu · 科研笔记管家与组会汇报助手

> Qoder × OceanBase 赛题「Build with Qoder——用 Qoder 做一个让学习、科研和工作更高效的项目」
> 技术结合：**seekdb**（存知识 + 混合检索）+ **PowerContext**（存"人"：偏好与进度的跨会话记忆）
> 开发方式：全程在 Qoder 中以自然语言驱动完成（开发记录见 [docs/QODER_LOG.md](docs/QODER_LOG.md)）

把论文摘录、实验记录、组会纪要、待办清单一次性导入，之后：

1. **找得到** —— seekdb 一条语句完成 向量 + 全文（ngram 中文）+ 结构化条件（课题/类型/日期窗口）的混合检索，每条结果带出处；
2. **记得住** —— PowerContext 记住你的汇报偏好与导师约束（"结论先行""每个结论挂出处""材料提前一天发"），跨会话复用；
3. **写得快** —— 一键生成组会汇报草稿：本周进展、关键数据、导师意见、下周计划，逐条挂出处，版式随记忆偏好自动变化。

**分工一句话：seekdb 记"事"，PowerContext 记"人"，格物负责把两者装配成草稿。**

## 为什么是这两个痛点

- 找笔记：课题组文档散落各处，"我明明记过 ef_search 怎么调"靠 Ctrl+F 找不回；纯向量检索对参数名、错误码这类硬信号又很迟钝——所以需要混合检索，并且要在数据库内部融合，而不是应用层拼两个列表。
- 写汇报：每周组会材料是重复劳动，而且导师的偏好（先给结论、必挂出处）每次都要靠人肉遵守——所以需要把偏好存成记忆，并在生成时真实生效。

## 快速开始（约 10 分钟）

```bash
cd qoder
bash scripts/setup.sh        # python 依赖 + 本地向量模型（hf-mirror，约 95MB，无需任何 API Key）
bash scripts/run_all.sh      # 启动 向量服务 + PowerContext Server + 主应用
bash scripts/verify.sh       # 可选：自动跑一遍验证样例，证据输出到 evidence/logs/
```

打开 <http://127.0.0.1:8712> → 「语料」页点"导入示例语料" → 「检索」页提问 → 「记忆」页写偏好 → 「组会草稿」页生成。
完整步骤与预期结果见 [docs/REPRODUCE.md](docs/REPRODUCE.md) 与 [docs/VERIFICATION.md](docs/VERIFICATION.md)。

## 三层架构

```
浏览器（web/）
   │  HTTP
   ▼
格物主应用 app/server.py（FastAPI）
   ├── seekdb（嵌入式，pylibseekdb）        知识层：分块表(向量列+全文索引+标量列)
   │      └── dbms_hybrid_search.search()  一条语句完成 向量+全文+过滤+RRF 融合
   ├── PowerContext Server（HTTP :8000）    记忆层：atomic-memory 的写入与召回
   │      └── 其存储后端 = 同一个嵌入式 seekdb（DATABASE_KIND=seekdb）
   └── 本地向量服务 app/embed_server.py     OpenAI 兼容 /v1/embeddings
          └── ONNX Runtime CPU 跑 bge-small-zh-v1.5（512 维），零云端 Key
```

细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；seekdb 与 PowerContext 各自的职责边界见 [docs/DIVISION-OF-LABOR.md](docs/DIVISION-OF-LABOR.md)。

## 目录

```
qoder/
├─ app/            主应用（server / seekdb_kb / memory / draft / embed_server / ingest / cli）
├─ web/            前端（原生 HTML/JS，无构建步骤）
├─ scripts/        setup / run_all / stop_all / verify / pc_service
├─ data/corpus/    16 篇示例语料（论文摘录、实验记录、组会纪要、待办）
├─ deploy/         PowerContext Server 环境变量（含 seekdb 后端与本地 embedding 配置）
├─ docs/           架构、复现、验证样例、合规对照、分工、开发记录
├─ evidence/       verify.sh 产生的真实运行证据（JSON 日志、SQL、草稿）
└─ tests/          SQL 转义与分块的单元测试
```

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 组件、数据流、关键设计决策（堆表、int 日期、转义） |
| [docs/DIVISION-OF-LABOR.md](docs/DIVISION-OF-LABOR.md) | seekdb 与 PowerContext 的分工与核对方法 |
| [docs/REPRODUCE.md](docs/REPRODUCE.md) | 从零到跑通的完整步骤（含端口与常见问题） |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | 验证样例：初始数据、操作步骤、预期结果 |
| [docs/COMPLIANCE.md](docs/COMPLIANCE.md) | 逐条对照赛题验收标准 → 证据位置 |
| [docs/QODER_LOG.md](docs/QODER_LOG.md) | Qoder 开发过程记录 |
| [docs/SUBMIT.md](docs/SUBMIT.md) | 提交信息：分支、commit、网站地址 |
