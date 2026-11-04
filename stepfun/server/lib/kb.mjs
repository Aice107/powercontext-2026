// 知识库（= seekdb 集合）生命周期与增量写入。所有数据只落 seekdb。
import { getClient, collectionSchema, collectionConfiguration } from './db.mjs';

export const DEFAULT_DIM = 512;
const UPSERT_BATCH = 64;

function slug(name) {
  return String(name).toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 48);
}

export function collectionNameFor(kb) {
  return `kb_${slug(kb)}`;
}

let tablesReady = null;
export async function ensureAppTables() {
  if (tablesReady) return tablesReady;
  tablesReady = (async () => {
    const db = await getClient();
    await db.execute(`CREATE TABLE IF NOT EXISTS app_kbs (
      name VARCHAR(64) PRIMARY KEY,
      collection VARCHAR(128) NOT NULL,
      description VARCHAR(512),
      model VARCHAR(128),
      dtype VARCHAR(16),
      dim INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )`);
    await db.execute(`CREATE TABLE IF NOT EXISTS app_docs (
      kb VARCHAR(64) NOT NULL,
      doc_id VARCHAR(128) NOT NULL,
      title VARCHAR(512),
      chunks INT,
      chars INT,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (kb, doc_id)
    )`);
    await db.execute(`CREATE TABLE IF NOT EXISTS app_sessions (
      session_id VARCHAR(64) PRIMARY KEY,
      active_kb VARCHAR(64) NOT NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )`);
    return true;
  })();
  return tablesReady;
}

export async function createKb({ name, description = '', model = '', dtype = '', dim = DEFAULT_DIM }) {
  await ensureAppTables();
  const db = await getClient();
  const collection = collectionNameFor(name);
  if (await db.hasCollection(collection)) {
    throw new Error(`知识库 ${name} 已存在`);
  }
  const started = performance.now();
  await db.createCollection({
    name: collection,
    schema: collectionSchema(dim),
    configuration: collectionConfiguration(dim),
    embeddingFunction: null,
  });
  const createMs = +(performance.now() - started).toFixed(1);
  await db.execute(
    `INSERT INTO app_kbs (name, collection, description, model, dtype, dim) VALUES (?, ?, ?, ?, ?, ?)`,
    [name, collection, description, model, dtype, dim],
  );
  return { name, collection, createMs };
}

export async function listKbs() {
  await ensureAppTables();
  const db = await getClient();
  const rows = (await db.execute(
    `SELECT name, collection, description, model, dtype, dim, created_at, updated_at FROM app_kbs ORDER BY created_at`,
  )) || [];
  const out = [];
  for (const row of rows) {
    let chunks = 0;
    let docs = 0;
    try {
      const col = await db.getCollection({ name: row.collection, embeddingFunction: null });
      chunks = await col.count();
      const docRows = (await db.execute(`SELECT COUNT(*) AS c FROM app_docs WHERE kb = ?`, [row.name])) || [];
      docs = Number(docRows[0]?.c || 0);
    } catch {
      // 集合被外部删除时不让列表接口整体失败
    }
    out.push({
      name: row.name,
      collection: row.collection,
      description: row.description || '',
      model: row.model || '',
      dtype: row.dtype || '',
      dim: Number(row.dim || DEFAULT_DIM),
      chunks,
      docs,
      createdAt: row.created_at,
    });
  }
  return out;
}

export async function getKbRecord(kb) {
  await ensureAppTables();
  const db = await getClient();
  const rows = (await db.execute(`SELECT name, collection, description, model, dtype, dim FROM app_kbs WHERE name = ?`, [kb])) || [];
  return rows[0] || null;
}

export async function deleteKb(kb) {
  await ensureAppTables();
  const db = await getClient();
  const record = await getKbRecord(kb);
  if (!record) throw new Error(`知识库 ${kb} 不存在`);
  await db.deleteCollection(record.collection);
  await db.execute(`DELETE FROM app_docs WHERE kb = ?`, [kb]);
  await db.execute(`DELETE FROM app_kbs WHERE name = ?`, [kb]);
  return { deleted: kb };
}

async function collectionFor(kb) {
  const record = await getKbRecord(kb);
  if (!record) throw new Error(`知识库 ${kb} 不存在`);
  const db = await getClient();
  return { record, db, col: await db.getCollection({ name: record.collection, embeddingFunction: null }) };
}

/**
 * 增量写入：同一 docId 重新导入时先删除旧分块，再批量 upsert，最后刷新索引。
 * @param {{kb: string, chunks: Array<{id: string, text: string, vector: number[], metadata: object}>}} input
 */
export async function ingest({ kb, chunks, deferRefresh = false }) {
  if (!Array.isArray(chunks) || chunks.length === 0) throw new Error('chunks 不能为空');
  const { record, db, col } = await collectionFor(kb);

  const byDoc = new Map();
  for (const chunk of chunks) {
    const docId = chunk.metadata?.docId || chunk.id.split('#')[0];
    if (!byDoc.has(docId)) byDoc.set(docId, []);
    byDoc.get(docId).push(chunk);
  }

  const timings = { deleteMs: 0, upsertMs: 0, refreshMs: 0 };
  let deletedChunks = 0;

  // 1) 增量语义：按文档删除旧分块，避免「旧内容残留」
  const t0 = performance.now();
  for (const docId of byDoc.keys()) {
    const rows = (await db.execute(`SELECT chunks FROM app_docs WHERE kb = ? AND doc_id = ?`, [kb, docId])) || [];
    if (rows.length) deletedChunks += Number(rows[0].chunks || 0);
    await col.delete({ where: { docId } });
  }
  timings.deleteMs = +(performance.now() - t0).toFixed(1);

  // 2) 批量 upsert（批大小可配置，失败重试一次以便观察幂等性）
  const t1 = performance.now();
  let batches = 0;
  for (let i = 0; i < chunks.length; i += UPSERT_BATCH) {
    const slice = chunks.slice(i, i + UPSERT_BATCH);
    const payload = {
      ids: slice.map((c) => c.id),
      embeddings: slice.map((c) => c.vector),
      documents: slice.map((c) => c.text),
      metadatas: slice.map((c) => c.metadata || {}),
    };
    try {
      await col.upsert(payload);
    } catch (error) {
      await col.upsert(payload);
      console.warn('[ingest] upsert retried after error:', error.message);
    }
    batches += 1;
  }
  timings.upsertMs = +(performance.now() - t1).toFixed(1);

  // 3) 索引刷新：连续导入时可用 deferRefresh 合并刷新（由调用方最后统一刷新）
  const t2 = performance.now();
  if (deferRefresh) {
    timings.refreshMs = 0;
  } else {
    await col.refresh_index();
    timings.refreshMs = +(performance.now() - t2).toFixed(1);
  }

  // 4) 文档登记（同一 kb+docId 覆盖）
  for (const [docId, docChunks] of byDoc.entries()) {
    const title = docChunks[0]?.metadata?.title || docId;
    const chars = docChunks.reduce((sum, c) => sum + (c.text?.length || 0), 0);
    await db.execute(
      `INSERT INTO app_docs (kb, doc_id, title, chunks, chars) VALUES (?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE title = VALUES(title), chunks = VALUES(chunks), chars = VALUES(chars)`,
      [kb, docId, String(title).slice(0, 500), docChunks.length, chars],
    );
  }

  const totalMs = +(performance.now() - t0).toFixed(1);
  return {
    kb,
    docs: byDoc.size,
    chunks: chunks.length,
    deletedChunks,
    batches,
    timings: { ...timings, totalMs },
    indexRefreshed: !deferRefresh,
    collection: record.collection,
  };
}

export async function refreshIndex(kb) {
  const { col } = await collectionFor(kb);
  const started = performance.now();
  await col.refresh_index();
  return { kb, refreshMs: +(performance.now() - started).toFixed(1) };
}

export async function kbStats(kb) {
  const { record, db, col } = await collectionFor(kb);
  const chunks = await col.count();
  const docRows = (await db.execute(`SELECT COUNT(*) AS c, COALESCE(SUM(chars),0) AS chars FROM app_docs WHERE kb = ?`, [kb])) || [];
  return {
    kb,
    collection: record.collection,
    chunks,
    docs: Number(docRows[0]?.c || 0),
    chars: Number(docRows[0]?.chars || 0),
    dim: Number(record.dim || DEFAULT_DIM),
  };
}

export async function listDocs(kb) {
  await ensureAppTables();
  const db = await getClient();
  return (await db.execute(
    `SELECT doc_id AS docId, title, chunks, chars, updated_at AS updatedAt FROM app_docs WHERE kb = ? ORDER BY updated_at DESC`,
    [kb],
  )) || [];
}
