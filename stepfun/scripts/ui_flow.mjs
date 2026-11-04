#!/usr/bin/env node
// UI 层端到端验证：完全通过界面操作（点击、输入）完成导入与检索，并截图留证。
import { chromium } from 'playwright-core';
import { launchOptions } from './lib/browser.mjs';
import { mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const BASE = process.env.APP_URL || 'http://127.0.0.1:5177';

function chromiumPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  for (const dir of ['chromium-1148', 'chromium-1134', 'chromium-1129']) {
    const candidate = join(cache, dir, 'chrome-linux', 'chrome');
    if (existsSync(candidate)) return candidate;
  }
}

const SAMPLE = [
  '=== seekdb-notes.md ===',
  'seekdb 是 OceanBase 推出的嵌入式向量数据库，同时支持向量索引与全文索引。',
  '调用 DBMS_HYBRID_SEARCH 时，数据库会在内部完成关键词召回、向量召回与 RRF 融合，客户端只拿到最终排序。',
  '索引刷新后，新写入的文档立即可以被检索到。',
  '',
  '=== edge-inference.md ===',
  'Transformers.js 让 ONNX 模型可以直接在浏览器中运行，推理完全发生在用户设备上。',
  'WebGPU 后端利用 GPU 并行能力；当浏览器不支持 WebGPU 或拿不到适配器时，自动降级到 WASM。',
  'INT8 动态量化把 bge-small-zh-v1.5 的权重从 90 MB 压到 23 MB，压缩比接近 4 倍。',
].join('\n');

const browser = await chromium.launch(launchOptions());
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.on('pageerror', (error) => console.log('[pageerror]', error.message));

await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.app');
await page.waitForFunction(() => Boolean(window.__stepfun), null, { timeout: 90000 });
await page.evaluate(async () => window.__stepfun.ready());

const kbName = `demo${Date.now().toString(36).slice(-4)}`;
await page.fill('.kb-list ~ .row input, .card input[placeholder*="新知识库"]', kbName);
await page.click('button:has-text("创建")');
await page.waitForSelector(`.kb-item:has-text("${kbName}")`, { timeout: 30000 });
await page.click(`.kb-item:has-text("${kbName}")`);
console.log('已创建并选中知识库:', kbName);

// 通过界面的文件输入导入示例文档
await page.setInputFiles('input[type="file"]', {
  name: 'ui-flow-sample.md',
  mimeType: 'text/markdown',
  buffer: Buffer.from(SAMPLE, 'utf8'),
});
await page.waitForSelector('.result-box', { timeout: 180000 });
const importText = await page.textContent('.result-box');
console.log('导入结果:', (importText || '').replace(/\s+/g, ' ').slice(0, 160));

// 通过界面执行混合检索
await page.fill('input.query', '混合检索在数据库内部如何融合');
await page.click('button:has-text("检索")');
await page.waitForSelector('.result', { timeout: 120000 });
const resultCount = await page.locator('.result').count();
const meta = (await page.textContent('.search-meta'))?.replace(/\s+/g, ' ');
console.log('检索结果数:', resultCount);
console.log('检索信息:', meta?.slice(0, 200));

// 展开 SQL 取证并截图
await page.click('button:has-text("查看 SQL 取证")');
await page.waitForSelector('.sql-box');
const badge = (await page.textContent('.badges'))?.replace(/\s+/g, ' ');
console.log('后端徽标:', badge);

await mkdir(join(ROOT, 'results'), { recursive: true });
await page.screenshot({ path: join(ROOT, 'results', 'screenshot.png'), fullPage: true });
await page.screenshot({ path: join(ROOT, 'results', 'screenshot-viewport.png') });
await browser.close();

console.log(resultCount > 0 ? '✅ UI 流程通过（导入 → 检索 → 结果渲染）' : '❌ 未渲染结果');
process.exit(resultCount > 0 ? 0 : 1);
