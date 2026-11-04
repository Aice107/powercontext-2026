# 使用 seekdb-js 创建集合与写入向量

seekdb-js 是 seekdb 的 JavaScript/TypeScript SDK，既可以连接本地 server（MySQL 协议），也可以在 Node 中以嵌入式方式打开数据目录。典型流程是：创建客户端、创建集合（Collection）、写入文档与向量、刷新索引、执行检索。

创建集合时可以指定 schema：向量索引使用 HNSW，距离度量用 cosine；全文索引使用 ngram 分析器，适合中文。集合维度必须与 embedding 模型输出一致，例如 bge-small-zh-v1.5 输出 512 维。写入使用 upsert，按主键覆盖，便于重复导入同一文档。写入完成后调用 refresh_index()，新数据才能被向量索引检索到。

混合检索调用 collection.hybridSearch({query, knn, rank})：SDK 会生成 SET @search_parm，然后通过 DBMS_HYBRID_SEARCH.GET_SQL 得到实际 SQL 并执行。
