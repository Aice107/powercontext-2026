// HTTP API：只做「收向量 → 写 seekdb → 查 seekdb」，没有模型推理。
import express from 'express';
import cors from 'cors';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';

import { getConfigSummary, ping } from './lib/db.mjs';
import { createKb, listKbs, deleteKb, ingest, refreshIndex, kbStats, listDocs, ensureAppTables } from './lib/kb.mjs';
import { getSession, setSession, resolveActiveKb } from './lib/session.mjs';
import { search } from './lib/search.mjs';
import { saveRun, summary, listRuns } from './lib/metrics.mjs';
import { listStatements } from './lib/evidence.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const PORT = Number(process.env.PORT || 5177);
const WEB_DIST = join(ROOT, 'web', 'dist');
const MODELS_DIR = join(ROOT, 'models');

const app = express();
app.use(cors());
// 跨源隔离：让 WASM 后端可以使用多线程（SharedArrayBuffer）
app.use((_req, res, next) => {
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  next();
});
app.use(express.json({ limit: '64mb' }));

const asyncRoute = (fn) => (req, res) => {
  Promise.resolve(fn(req, res)).catch((error) => {
    const status = /不存在|缺少|不能为空|未知/.test(error.message || '') ? 400 : 500;
    res.status(status).json({ error: error.message || String(error) });
  });
};

app.get('/api/health', asyncRoute(async (_req, res) => {
  const info = getConfigSummary();
  let ok = false;
  let version = null;
  let error = null;
  try {
    const pong = await ping();
    ok = pong.ok;
    version = pong.version;
    await ensureAppTables();
  } catch (e) {
    error = e.message;
  }
  res.json({ ok, seekdb: { ...info, version, error }, time: new Date().toISOString() });
}));

app.get('/api/kbs', asyncRoute(async (_req, res) => {
  res.json({ kbs: await listKbs() });
}));

app.post('/api/kbs', asyncRoute(async (req, res) => {
  const { name, description, model, dtype, dim } = req.body || {};
  if (!name) throw new Error('缺少 name');
  res.json(await createKb({ name, description, model, dtype, dim }));
}));

app.delete('/api/kbs/:name', asyncRoute(async (req, res) => {
  res.json(await deleteKb(req.params.name));
}));

app.get('/api/kbs/:name/stats', asyncRoute(async (req, res) => {
  res.json(await kbStats(req.params.name));
}));

app.get('/api/kbs/:name/docs', asyncRoute(async (req, res) => {
  res.json({ docs: await listDocs(req.params.name) });
}));

app.get('/api/session/:sessionId', asyncRoute(async (req, res) => {
  res.json({ session: await getSession(req.params.sessionId) });
}));

app.post('/api/session', asyncRoute(async (req, res) => {
  const { sessionId, kb } = req.body || {};
  if (!sessionId) throw new Error('缺少 sessionId');
  if (!kb) throw new Error('缺少 kb');
  res.json(await setSession({ sessionId, kb }));
}));

app.post('/api/ingest', asyncRoute(async (req, res) => {
  const { sessionId, kb, chunks, deferRefresh } = req.body || {};
  const active = await resolveActiveKb({ sessionId, kb });
  const result = await ingest({ kb: active.kb, chunks, deferRefresh: Boolean(deferRefresh) });
  res.json({ ...result, kbSource: active.source });
}));

app.post('/api/refresh', asyncRoute(async (req, res) => {
  const { sessionId, kb } = req.body || {};
  const active = await resolveActiveKb({ sessionId, kb });
  res.json(await refreshIndex(active.kb));
}));

app.post('/api/search', asyncRoute(async (req, res) => {
  const { sessionId, kb, mode, query, vector, topK, candidateK } = req.body || {};
  if (!query) throw new Error('缺少查询内容');
  const active = await resolveActiveKb({ sessionId, kb });
  const result = await search({ kb: active.kb, mode, query, vector, topK: Number(topK) || 5, candidateK: Number(candidateK) || 0 });
  res.json({ ...result, kbSource: active.source });
}));

app.get('/api/evidence', asyncRoute(async (req, res) => {
  const limit = Number(req.query.limit) || 20;
  res.json({ statements: listStatements(limit) });
}));

app.post('/api/metrics', asyncRoute(async (req, res) => {
  const saved = await saveRun(req.body || {});
  res.json({ saved: saved.file });
}));

app.get('/api/metrics/summary', asyncRoute(async (_req, res) => {
  res.json(await summary());
}));

app.get('/api/metrics/runs', asyncRoute(async (req, res) => {
  res.json({ runs: await listRuns(Number(req.query.limit) || 20) });
}));

// 模型体积实测结果（由 scripts/fetch_models.mjs 生成）
app.get('/api/models', asyncRoute(async (_req, res) => {
  const file = join(ROOT, 'results', 'model-sizes.json');
  if (!existsSync(file)) {
    res.json({ models: [], note: '先运行 npm run fetch-models' });
    return;
  }
  res.json(JSON.parse(await readFile(file, 'utf8')));
}));

// 静态资源：模型权重（本地优先）与前端构建产物
app.use('/models', express.static(MODELS_DIR, { maxAge: '1h' }));
if (existsSync(WEB_DIST)) {
  app.use(express.static(WEB_DIST));
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api/')) return next();
    res.sendFile(join(WEB_DIST, 'index.html'));
  });
}

app.use((error, _req, res, _next) => {
  res.status(500).json({ error: error.message || String(error) });
});

app.listen(PORT, () => {
  console.log(`[stepfun] API listening on http://127.0.0.1:${PORT}`);
  console.log(`[stepfun] seekdb ${JSON.stringify(getConfigSummary())}`);
  if (!existsSync(WEB_DIST)) console.log('[stepfun] web/dist 不存在：开发时请用 npm run dev（Vite 代理 /api）');
});
