#!/usr/bin/env node
// 基准 + 质量评测：真实 Chromium 中跑完整链路，输出
//   results/bench-<backend>-<dtype>.json   分阶段计时（首次/预热、中位数）
//   results/quality-summary.json           量化前后 Recall@5 / nDCG@10 对比
//   results/runs/*.json                    通过 /api/metrics 落盘（kind=bench）
import { chromium } from 'playwright-core';
import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const BASE = process.env.APP_URL || 'http://127.0.0.1:5177';
const RESULTS = join(ROOT, 'results');

const argOf = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.split('=')[1] : fallback;
};
const backend = argOf('backend', 'wasm');
const dtypes = argOf('dtypes', 'q8,fp16,fp32').split(',').filter(Boolean);
const repeats = Number(argOf('repeats', '3'));
const batchSize = Number(argOf('batch', '8'));
const topK = Number(argOf('topk', '5'));

function chromiumPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  for (const dir of ['chromium-1148', 'chromium-1134', 'chromium-1129']) {
    const candidate = join(cache, dir, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}

const median = (values) => {
  const arr = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!arr.length) return null;
  const mid = Math.floor(arr.length / 2);
  return arr.length % 2 ? arr[mid] : +((arr[mid - 1] + arr[mid]) / 2).toFixed(2);
};

function dcg(relevances) {
  return relevances.reduce((sum, rel, i) => sum + (rel ? 1 / Math.log2(i + 2) : 0), 0);
}

async function loadCorpus() {
  const dir = join(ROOT, 'eval', 'corpus');
  const files = (await readdir(dir)).filter((f) => f.endsWith('.md')).sort();
  const docs = [];
  for (const file of files) {
    docs.push({ name: basename(file, '.md'), text: await readFile(join(dir, file), 'utf8') });
  }
  return docs;
}

async function evaluateDtype(browser, dtype, corpus, queries) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  const open = async (query = '') => {
    await page.goto(`${BASE}/?backend=${backend}&dtype=${dtype}&batch=${batchSize}${query}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__stepfun), null, { timeout: 90000 });
    return page.evaluate(async () => window.__stepfun.ready());
  };

  const coldReady = await open();
  const reloadReady = await open();

  const kbName = `eval_${dtype}_${Date.now().toString(36).slice(-5)}`;
  await page.evaluate(async (name) => {
    await window.__stepfun.createKb(name);
  }, kbName);

  // 导入语料
  const importTimings = [];
  let totalChunks = 0;
  let embedMs = 0;
  for (const doc of corpus) {
    const result = await page.evaluate(
      async ({ text, name, deferRefresh }) => window.__stepfun.importText(text, name, { deferRefresh }),
      { ...doc, deferRefresh: doc !== corpus[corpus.length - 1] },
    );
    importTimings.push(result.timings);
    totalChunks += result.chunks;
    embedMs += result.timings.embedMs;
  }

  // 质量评测
  const quality = { hits5: 0, hits10: 0, ndcg10: 0, mrr: 0, queries: [] };
  const queryTimings = [];
  const refreshLastMs = importTimings[importTimings.length - 1]?.refreshMs ?? 0;
  for (const item of queries) {
    const runs = [];
    for (let i = 0; i < repeats; i += 1) {
      runs.push(await page.evaluate(async ({ q, k }) => window.__stepfun.search(q, 'hybrid', k), { q: item.query, k: 10 }));
    }
    const result = runs[runs.length - 1];
    const docIds = [...new Set(result.results.map((r) => r.metadata?.docId || ''))];
    const top5 = docIds.slice(0, topK);
    const top10 = docIds.slice(0, 10);
    const relevant = new Set(item.relevant);
    const hit5 = top5.some((d) => relevant.has(d)) ? 1 : 0;
    const hit10 = top10.some((d) => relevant.has(d)) ? 1 : 0;
    const relVec = top10.map((d) => (relevant.has(d) ? 1 : 0));
    const firstHit = docIds.findIndex((d) => relevant.has(d));
    quality.hits5 += hit5;
    quality.hits10 += hit10;
    const ideal = dcg(Array.from({ length: Math.min(relevant.size, 10) }, () => 1));
    quality.ndcg10 += dcg(relVec) / (ideal || 1);
    quality.mrr += firstHit >= 0 ? 1 / (firstHit + 1) : 0;
    quality.queries.push({ id: item.id, query: item.query, top5, hit5, hit10 });
    queryTimings.push(result.timings);
  }
  const n = queries.length;
  quality.recallAt5 = +(quality.hits5 / n).toFixed(4);
  quality.recallAt10 = +(quality.hits10 / n).toFixed(4);
  quality.ndcgAt10 = +(quality.ndcg10 / n).toFixed(4);
  quality.mrrAt10 = +(quality.mrr / n).toFixed(4);
  delete quality.hits5; delete quality.hits10; delete quality.ndcg10; delete quality.mrr;

  const bench = {
    kind: 'bench',
    backend,
    dtype,
    kb: kbName,
    device: coldReady.device,
    model: coldReady.modelId,
    dim: coldReady.dim,
    corpus: { docs: corpus.length, chunks: totalChunks },
    timings: {
      modelLoadColdMs: coldReady.modelLoadMs,
      modelLoadWarmMs: reloadReady.modelLoadMs,
      embedMsTotal: +embedMs.toFixed(1),
      ingestMs: median(importTimings.map((t) => t.seekdbWriteMs)),
      refreshMs: refreshLastMs,
      ingestTotalMs: +importTimings.reduce((a, t) => a + (t.totalMs || 0), 0).toFixed(1),
      queryEmbedMs: median(queryTimings.map((t) => t.queryEmbedMs)),
      seekdbMs: median(queryTimings.map((t) => t.seekdbMs)),
      e2eMs: median(queryTimings.map((t) => t.e2eMs)),
    },
    metrics: {
      embedChunksPerSec: +(totalChunks / (embedMs / 1000)).toFixed(2),
      batchSize: Number(batchSize),
    },
    quality: {
      recallAt5: quality.recallAt5,
      recallAt10: quality.recallAt10,
      ndcgAt10: quality.ndcgAt10,
      mrrAt10: quality.mrrAt10,
    },
    samples: { imports: importTimings.length, queryRepeats: repeats },
    errors,
    at: new Date().toISOString(),
  };

  await mkdir(RESULTS, { recursive: true });
  await writeFile(join(RESULTS, `bench-${backend}-${dtype}.json`), JSON.stringify({ ...bench, quality, qualityDetail: quality }, null, 2));
  await fetch(`${BASE}/api/metrics`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(bench),
  }).catch(() => {});

  await context.close();
  return { bench, quality };
}

async function main() {
  const corpus = await loadCorpus();
  const queries = JSON.parse(await readFile(join(ROOT, 'eval', 'queries.json'), 'utf8')).queries;
  const browser = await chromium.launch({
    headless: !process.argv.includes('--headed'),
    executablePath: chromiumPath(),
    args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--enable-features=Vulkan'],
  });

  const summary = [];
  for (const dtype of dtypes) {
    console.log(`\n=== ${backend} / ${dtype} ===`);
    const { bench, quality } = await evaluateDtype(browser, dtype, corpus, queries);
    console.log(JSON.stringify({ timings: bench.timings, metrics: bench.metrics, quality: bench.quality }, null, 2));
    summary.push({
      backend,
      dtype,
      batch: batchSize,
      modelBytes: null,
      timings: bench.timings,
      metrics: bench.metrics,
      quality: bench.quality,
      corpus: bench.corpus,
      errors: bench.errors.length,
    });
  }
  await browser.close();

  const file = join(RESULTS, 'quality-summary.json');
  let existing = { runs: [] };
  if (existsSync(file)) existing = JSON.parse(await readFile(file, 'utf8'));
  const filtered = (existing.runs || []).filter(
    (r) => !(r.backend === backend && dtypes.includes(r.dtype) && Number(r.batch || 8) === Number(batchSize)),
  );
  const payload = { generatedAt: new Date().toISOString(), unit: 'ms', runs: [...filtered, ...summary] };
  await writeFile(file, JSON.stringify(payload, null, 2));
  console.log(`\n写入 ${file}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
