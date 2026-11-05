---
title: 实验记录 1023 ef_search 扫描
kind: experiment
project: vec-search
date: 2026-10-23
tags: [hnsw, ef_search, latency]
origin: 扫描脚本记录
---

## 设置

固定语料与查询集，只改 ef_search，其余参数保持基线。

| ef_search | Recall@10 | P95 延迟 |
| ---: | ---: | ---: |
| 40 | 0.79 | 7.4ms |
| 80 | 0.86 | 11.1ms |
| 160 | 0.93 | 18.6ms |
| 320 | 0.96 | 34.2ms |

## 结论

- 召回随 ef_search 单调上升，但 160 之后边际收益明显变小。
- 延迟增长接近线性，320 这一档已经不满足线上 50ms 的整体预算（还要留出 embedding 时间）。
- 取 ef_search=160 作为当前工作点：Recall@10 = 0.93，P95 = 18.6ms。

## 遗留

那 4 条包含英文参数名的查询，在 ef_search=320 时仍然没有进入前 10。
说明这已经不是"图搜索不够深"的问题，是表示本身的问题，需要外部信号补。
下一轮上混合检索。
