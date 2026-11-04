// 检索层：默认混合检索由 seekdb 单条 DBMS_HYBRID_SEARCH 语句完成（含 RRF 融合）。
// 这里不做任何「两路结果客户端拼合」：只把数据库返回的排序结果原样交给前端。
import { getClient } from './db.mjs';
import { getKbRecord } from './kb.mjs';
import { listStatements } from './evidence.mjs';

async function collectionFor(kb) {
  const record = await getKbRecord(kb);
  if (!record) throw new Error(`知识库 ${kb} 不存在`);
  const db = await getClient();
  const col = await db.getCollection({ name: record.collection, embeddingFunction: null });
  return { record, col };
}

function normalize(result) {
  // SDK 返回 shape: { ids: [[...]], documents: [[...]], metadatas: [[...]], distances: [[...]] }
  const ids = result?.ids?.[0] || [];
  const documents = result?.documents?.[0] || [];
  const metadatas = result?.metadatas?.[0] || [];
  const distances = result?.distances?.[0] || [];
  return ids.map((id, i) => ({
    ref: i + 1,
    id,
    document: documents[i] ?? null,
    metadata: metadatas[i] ?? null,
    distance: distances[i] ?? null,
  }));
}

export async function search({ kb, mode = 'hybrid', query, vector, topK = 5, candidateK = 0 }) {
  const started = performance.now();
  const { record, col } = await collectionFor(kb);
  const seqBefore = listStatements(1)[0]?.seq || 0;
  const window = candidateK > 0 ? candidateK : Math.max(topK * 4, topK);

  let result;
  if (mode === 'hybrid') {
    if (!Array.isArray(vector) || vector.length === 0) throw new Error('混合检索需要查询向量');
    result = await col.hybridSearch({
      query: { whereDocument: { $contains: query }, nResults: window },
      knn: { queryEmbeddings: [vector], nResults: window },
      rank: { rrf: { rankWindowSize: 20, rankConstant: 60 } },
      nResults: topK,
      include: ['documents', 'metadatas', 'distances'],
    });
  } else if (mode === 'vector') {
    if (!Array.isArray(vector) || vector.length === 0) throw new Error('向量检索需要查询向量');
    result = await col.query({
      queryEmbeddings: [vector],
      nResults: topK,
      include: ['documents', 'metadatas', 'distances'],
    });
  } else if (mode === 'fulltext') {
    result = await col.hybridSearch({
      query: { whereDocument: { $contains: query }, nResults: topK },
      nResults: topK,
      include: ['documents', 'metadatas', 'distances'],
    });
  } else {
    throw new Error(`未知检索模式: ${mode}`);
  }

  const seekdbMs = +(performance.now() - started).toFixed(2);
  const statements = listStatements(12).filter((s) => s.seq > seqBefore);
  return {
    kb,
    collection: record.collection,
    mode,
    topK,
    candidateK: window,
    timings: { seekdbMs },
    results: normalize(result),
    // 取证：本次检索在 seekdb 中执行的语句（混合模式应包含 SET @search_parm 与 DBMS_HYBRID_SEARCH）
    statements: statements.map((s) => ({ seq: s.seq, phase: s.phase, sql: s.sql, durationMs: s.durationMs, rows: s.rows })),
  };
}

export async function vectorOnlyProbe(kb) {
  const { col } = await collectionFor(kb);
  return { kb, count: await col.count() };
}
