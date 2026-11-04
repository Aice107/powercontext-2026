// seekdb 连接层：只负责连接、建库、SQL 取证。这里没有任何 embedding / 推理代码。
import { SeekdbClient, AdminClient, Schema, VectorIndexConfig, FulltextIndexConfig } from 'seekdb';
import { recordStatement } from './evidence.mjs';

export const config = {
  host: process.env.SEEKDB_HOST || '127.0.0.1',
  port: Number(process.env.SEEKDB_PORT || 2895),
  user: process.env.SEEKDB_USER || 'root',
  password: process.env.SEEKDB_PASSWORD || '',
  database: process.env.SEEKDB_DATABASE || 'stepfun_kb',
  embeddedPath: process.env.SEEKDB_PATH || '',
};

let client = null;
let ready = null;

function instrument(target, phaseHint) {
  if (!target || typeof target.execute !== 'function') return target;
  const original = target.execute.bind(target);
  target.execute = async (sql, params) => {
    const started = performance.now();
    const oneLine = String(sql).replace(/\s+/g, ' ').trim();
    try {
      const rows = await original(sql, params);
      recordStatement({
        phase: phaseHint || classify(oneLine),
        sql: oneLine.length > 2000 ? oneLine.slice(0, 2000) + '…' : oneLine,
        fullSql: oneLine,
        params: params ? params.map((p) => (typeof p === 'string' && p.length > 200 ? p.slice(0, 200) + '…' : p)) : null,
        durationMs: +(performance.now() - started).toFixed(2),
        rows: Array.isArray(rows) ? rows.length : 0,
        ok: true,
      });
      return rows;
    } catch (error) {
      recordStatement({
        phase: phaseHint || classify(oneLine),
        sql: oneLine.slice(0, 500),
        durationMs: +(performance.now() - started).toFixed(2),
        ok: false,
        error: error?.message,
      });
      throw error;
    }
  };
  return target;
}

function classify(sql) {
  const s = sql.toUpperCase();
  if (s.includes('DBMS_HYBRID_SEARCH')) return 'hybrid-search';
  if (s.startsWith('SET @SEARCH_PARM')) return 'hybrid-search';
  if (s.includes('_KEYWORD_RANK') && s.includes('_SEMANTIC_RANK')) return 'hybrid-fused';
  if (s.includes('REFRESH') || s.includes('BUILD INDEX')) return 'refresh-index';
  if (s.startsWith('SELECT') && s.includes('VECTOR')) return 'vector-search';
  return 'sql';
}

async function ensureDatabase() {
  const admin = AdminClient({ host: config.host, port: config.port, user: config.user, password: config.password });
  try {
    await admin.execute(`CREATE DATABASE IF NOT EXISTS \`${config.database}\``);
  } finally {
    await admin.close().catch(() => {});
  }
}

function buildHandle() {
  const args = config.embeddedPath
    ? { path: config.embeddedPath, database: config.database }
    : { host: config.host, port: config.port, user: config.user, password: config.password, database: config.database, charset: 'utf8mb4' };
  const facade = new SeekdbClient(args);
  // 逐层 patch：facade → delegate → internal client，确保 Collection 内部 SQL 也被取证。
  instrument(facade, null);
  const delegate = facade._delegate;
  if (delegate) {
    instrument(delegate, null);
    if (delegate._internal) instrument(delegate._internal, null);
  }
  return facade;
}

export async function getClient() {
  if (ready) return ready;
  ready = (async () => {
    if (!config.embeddedPath) {
      await ensureDatabase();
    }
    client = buildHandle();
    return client;
  })();
  return ready;
}

export function getConfigSummary() {
  return {
    host: config.host,
    port: config.port,
    database: config.database,
    mode: config.embeddedPath ? 'embedded' : 'local-server',
  };
}

export async function ping() {
  const db = await getClient();
  const rows = await db.execute('SELECT 1 AS ok, VERSION() AS version');
  return { ok: rows?.[0]?.ok === 1, version: rows?.[0]?.version };
}

export function collectionSchema(dim = 512) {
  return new Schema({
    vectorIndex: new VectorIndexConfig({ hnsw: { dimension: dim, distance: 'cosine', m: 16, ef_construction: 200 } }),
    fulltextIndex: new FulltextIndexConfig('ngram', { ngram_token_size: 2 }),
  });
}

export function collectionConfiguration(dim = 512) {
  return { dimension: dim, distance: 'cosine' };
}
