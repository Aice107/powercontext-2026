# HNSW 向量索引参数

HNSW（Hierarchical Navigable Small World）是目前常用的近似最近邻索引。它把向量组织成多层图，查询时从高层粗粒度往下搜索，在保证召回率的同时减少距离计算次数。

关键参数包括 m 和 ef_construction。m 是每个节点的邻居数，越大图越稠密、召回越高，但内存与构建时间也越大；ef_construction 控制构建时的候选队列长度，越大索引质量越好、构建越慢。查询时还可以设置 ef_search 来平衡延迟与召回。

在 seekdb 中，可以在向量索引配置里指定 m 与 ef_construction，例如 m=16、ef_construction=200。建索引后需要在写入新数据后刷新索引，才能让新向量进入图结构。
