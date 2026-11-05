---
title: HNSW 图索引参数对召回率的影响
kind: paper
project: vec-search
date: 2026-09-08
tags: [hnsw, recall, index]
origin: 本人阅读笔记整理，非原文摘录
---

## 核心结论

HNSW 的召回率主要由 `ef_search`（查询时候选队列长度）决定，而不是 `M`（每个节点的出边数）。
在 100 万条 512 维向量、余弦距离的设置下，`ef_search` 从 40 提到 200，Recall@10 从 0.82 上升到 0.97，
但 P95 延迟从 6ms 涨到 21ms，近似线性。

## 建图参数

`M=16`、`ef_construction=200` 是常见的折中。把 `ef_construction` 从 100 提到 200，
建图时间翻倍，但一次性收益：同样的 `ef_search` 下 Recall@10 提升约 3~4 个点。
`M` 继续加大到 32 之后收益很小，内存占用却明显上升，不建议无脑调大。

## 与 IVF 的对比

IVF 系（如 IVF_PQ）靠 `nprobe` 控制扫描的聚类数，召回-延迟曲线在低召回区比 HNSW 陡峭，
在高召回区（>0.95）明显不如 HNSW。课题里如果目标是 Recall@10 > 0.95，基本只能走 HNSW。

## 对我课题的启发

组里现在用的是默认参数。我怀疑线上"搜不到东西"的抱怨并不是向量模型的问题，
而是 `ef_search` 太小。下一步实验应该固定语料，只扫 `ef_search`，把召回-延迟曲线画出来。
