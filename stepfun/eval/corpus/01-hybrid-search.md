# seekdb 混合检索原理

混合检索（Hybrid Search）把向量相似度检索与全文关键词检索结合起来，兼顾语义召回与精确匹配。seekdb 提供 DBMS_HYBRID_SEARCH 接口：调用方传入一个 search_parm JSON，其中 query 描述全文条件，knn 描述向量条件，rank 指定融合算法。数据库在内部先分别执行全文分支与向量分支，再按 Reciprocal Rank Fusion（RRF）把两路排名融合成一个最终分数。

RRF 的公式是 1/(k + rank)，其中 k 是 rank_constant（默认 60），rank 是各分支内的名次。融合发生在数据库引擎内部，客户端只拿到已经排好序的最终结果，因此不需要、也不应该由客户端分别取两路结果再自行拼合。

这种设计的优势是：一、减少一次网络往返；二、排序逻辑与数据在同一个事务视图内，索引更新后立即生效；三、融合参数（rank_window_size、rank_constant）可以按业务调节。
