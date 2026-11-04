#!/usr/bin/env node
// 浏览器端冒烟测试：用真实 Chromium（headless）跑通「导入 → 端侧向量化 → seekdb 写入/刷新 → 混合检索」。
// 可指定后端：--backend=auto|webgpu|wasm（通过页面上的选择框切换，等价于用户操作）。
import { chromium } from 'playwright-core';
import { launchOptions } from './lib/browser.mjs';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';

const BASE = process.env.APP_URL || 'http://127.0.0.1:5177';
const backendArg = (process.argv.find((a) => a.startsWith('--backend=')) || '--backend=auto').split('=')[1];
const headless = !process.argv.includes('--headed');

function chromiumPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  for (const dir of ['chromium-1148', 'chromium-1134', 'chromium-1129']) {
    const candidate = join(cache, dir, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
  return undefined;
}

const browser = await chromium.launch(launchOptions({ headed: !headless }));
const page = await browser.newPage();
page.on('console', (msg) => {
  const text = msg.text();
  if (/error|warn|WebGPU/i.test(text)) console.log(`[browser:${msg.type()}] ${text.slice(0, 300)}`);
});
page.on('pageerror', (error) => console.log('[pageerror]', error.message));

console.log(`打开 ${BASE} …`);
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(window.__stepfun), null, { timeout: 60000 });

const probe = await page.evaluate(() => window.__stepfun.state());
console.log('初始状态:', JSON.stringify(probe));

if (backendArg !== 'auto') {
  await page.selectOption('select', backendArg).catch(() => {});
  // 后端选择框是第一个 select（推理后端）
  await page.locator('.controls select').first().selectOption(backendArg);
}

const ready = await page.evaluate(async () => {
  const info = await window.__stepfun.ready();
  return info;
});
console.log('模型就绪:', JSON.stringify(ready));

const kbName = `smoke${Date.now().toString(36).slice(-5)}`;
const imported = await page.evaluate(async (name) => {
  const api = window.__stepfun;
  await api.createKb(name);
  const text = [
    '=== seekdb-intro.md ===',
    'seekdb 是 OceanBase 推出的嵌入式向量数据库，支持向量索引、全文索引与混合检索。',
    'DBMS_HYBRID_SEARCH 在数据库内部完成关键词召回、向量召回与 RRF 融合。',
    '=== edge-ai.md ===',
    'Transformers.js 让 ONNX 模型可以直接运行在浏览器中。',
    'WebGPU 后端利用 GPU 并行能力，WASM 后端在无 GPU 环境下保证可用。',
    'INT8 动态量化可以把模型体积压缩到 FP32 的四分之一左右。',
  ].join('\n');
  return api.importText(text, 'smoke.md');
}, kbName);
console.log('导入结果:', JSON.stringify(imported));

const queries = ['混合检索 RRF 融合', '浏览器里怎么跑 ONNX 模型'];
const searchResults = [];
for (const q of queries) {
  const result = await page.evaluate(async (query) => window.__stepfun.search(query, "hybrid", 3), q);
  searchResults.push(result);
  console.log(`检索「${q}」:`, JSON.stringify({
    ms: result.timings,
    top: result.results.map((r) => ({ id: r.id, d: r.distance, text: (r.document || '').slice(0, 40) })),
    statements: (result.statements || []).map((s) => s.phase),
  }));
}

// 刷新后可见性：新写入的文档应立即被检索到
const docVisible = searchResults.some((r) => r.results.length > 0);
console.log('索引刷新后可见:', docVisible);

await mkdir('results', { recursive: true }).catch(() => {});
await page.screenshot({ path: 'results/screenshot.png', fullPage: true }).catch(() => {});
await browser.close();

const failed = !ready?.dim || !imported?.chunks || !docVisible;
console.log(failed ? '❌ 冒烟测试失败' : '✅ 冒烟测试通过');
process.exit(failed ? 1 : 0);
