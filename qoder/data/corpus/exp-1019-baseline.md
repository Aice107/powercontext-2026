---
title: 实验记录 1019 基线召回评测
kind: experiment
project: vec-search
date: 2026-10-19
tags: [baseline, recall, eval]
origin: 组内评测脚本 output.log 整理
---

## 设置

语料：本课题组 214 篇论文笔记 + 实验记录，切块后共 1873 个 chunk，512 维。
查询集：手工写的 40 条问题，覆盖参数名、概念、结论三类。
索引：默认参数 M=16、ef_construction=100、ef_search=40。

## 结果

- Recall@10 = 0.79
- Recall@5 = 0.71
- MRR = 0.66
- P95 延迟 7.4ms（单机，warm）
- 空召回率 12.5%（5 条查询返回不足 3 个可用结果）

## 观察

空召回的 5 条里，有 4 条查询包含英文参数名（`ef_search`、`nprobe`）。
纯向量这一路对这些硬信号的区分度明显不足，这跟 ngram 那篇笔记里的预判一致。

## 结论

基线可用但达不到要求。两个改造方向：调 ef_search、加全文通道。
先做前者，因为不用改架构。
