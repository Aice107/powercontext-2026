#!/usr/bin/env node
// 优化前后对比实验（与 bench.mjs 使用同一套真实运行环境）：
//   1) 批处理：batch=1 vs batch=8 的端侧向量化吞吐
//   2) 索引刷新：每批刷新 vs 合并刷新 的总耗时与可见性
//   3) 量化：q8 / fp16 / fp32 的模型加载与吞吐（复用 bench 结果）
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
const backend = (process.argv.find((a) => a.startsWith('--backend=')) || '--backend=wasm').split('=')[1];

function chromiumPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  for (const dir of ['chromium-1148', 'chromium-1134', 'chromium-1129']) {
    const candidate = join(cache, dir, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
}

async function loadCorpus() {
  const dir = join(ROOT, 'eval', 'corpus');
  return Promise.all(
    (await readdir(dir)).filter((f) => f.endsWith('.md')).sort().map(async (file) => ({
      name: basename(file, '.md'),
      text: await readFile(join(dir, file), 'utf8'),
    })),
  );
}

const browser = await chromium.launch({
  headless: true,
  executablePath: chromiumPath(),
  args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--enable-features=Vulkan'],
});

const corpus = await loadCorpus();
const texts = corpus.map((d) => d.text);

async function openPage(batch, threads = 0) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${BASE}/?backend=${backend}&dtype=q8&batch=${batch}${threads ? `&threads=${threads}` : ''}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(window.__stepfun), null, { timeout: 90000 });
  await page.evaluate(async () => window.__stepfun.ready());
  return { context, page };
}

// 1) 线程数与批处理吞吐（2×2 矩阵）
const batchResults = [];
for (const threads of [1, 4]) {
  for (const batch of [1, 8]) {
    const { context, page } = await openPage(batch, threads);
    const runs = [];
    for (let i = 0; i < 3; i += 1) {
      const out = await page.evaluate(async (input) => window.__stepfun.embed(input), texts);
      runs.push({ ms: out.ms, chunksPerSec: out.chunksPerSec, batches: out.batchTimes.length });
    }
    const median = runs.sort((a, b) => a.ms - b.ms)[1];
    batchResults.push({ threads, batch, ...median, runs });
    console.log(`threads=${threads} batch=${batch}: ${median.ms}ms, ${median.chunksPerSec} chunks/s`);
    await context.close();
  }
}

// 2) 刷新策略：逐次刷新 vs 合并刷新
async function importAll(strategy) {
  const { context, page } = await openPage(8);
  const kb = `opt_${strategy}_${Date.now().toString(36).slice(-5)}`;
  await page.evaluate(async (name) => window.__stepfun.createKb(name), kb);
  const started = Date.now();
  for (const doc of corpus) {
    await page.evaluate(
      async ({ text, name, deferRefresh }) => window.__stepfun.importText(text, name, { deferRefresh }),
      { text: doc.text, name: doc.name, deferRefresh: strategy === 'merged' && doc !== corpus[corpus.length - 1] },
    );
  }
  const totalMs = Date.now() - started;
  const verify = await page.evaluate(async () => window.__stepfun.search('索引刷新后新文档可检索', 'hybrid', 3));
  await context.close();
  return { strategy, totalMs, visible: verify.results.length > 0, kb };
}

const perImport = await importAll('per-import');
const merged = await importAll('merged');
console.log('per-import:', perImport.totalMs, 'ms; merged:', merged.totalMs, 'ms');

const payload = {
  generatedAt: new Date().toISOString(),
  backend,
  dtype: 'q8',
  corpus: { docs: corpus.length, chars: texts.reduce((a, t) => a + t.length, 0) },
  batching: batchResults.map(({ threads, batch, ms, chunksPerSec, batches }) => ({ threads, batch, ms, chunksPerSec, batches })),
  refresh: [perImport, merged],
};
await mkdir(RESULTS, { recursive: true });
await writeFile(join(RESULTS, 'optimizations.json'), JSON.stringify(payload, null, 2));
console.log('写入 results/optimizations.json');
await browser.close();
