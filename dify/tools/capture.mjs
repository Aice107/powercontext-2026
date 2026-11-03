#!/usr/bin/env node
/**
 * 用无头 Chromium 抓 Dify 控制台与《记仇客栈》的界面截图。
 *
 * 用法：
 *   PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
 *   node capture.mjs <app_id> [out_dir]
 *
 * 说明：
 * - 本机 chromium 是手动下载的（npmmirror 的 playwright build），用 CHROME_PATH 指定；
 * - 开发模式页面会挂一个设计标注浮层（styles-module__toolbar 等），截图前用 CSS 隐藏；
 * - 页面按需编译，首次访问可能要等 1~2 分钟，超时都放大到 4 分钟。
 */

import fs from 'node:fs';
import path from 'node:path';

const PW = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(PW);

const APP_ID = process.argv[2] || process.env.INN_APP_ID;
const OUT = process.argv[3] || process.env.OUT_DIR || '/home/ice/dify-project/dify/evidence/screenshots';
const BASE = process.env.DIFY_BASE || 'http://localhost:3000';
const EMAIL = process.env.DIFY_EMAIL || 'admin@inn.local';
const PASS = process.env.DIFY_PASS || 'InnAdmin123!';
const CHROME = process.env.CHROME_PATH || '/home/ice/dify-shot/chromium/chrome-linux/chrome';

if (!APP_ID) {
  console.error('缺少 app_id');
  process.exit(1);
}
fs.mkdirSync(OUT, { recursive: true });
const log = (...a) => console.log(`[${new Date().toISOString().slice(11, 19)}]`, ...a);

const HIDE_CSS = `
  [class*="styles-module__toolbar"],
  [class*="styles-module__drawCanvas"],
  [class*="styles-module__fixedMarkersLayer"],
  [class*="styles-module__markersLayer"],
  [class*="agentation"],
  [id*="react-scan"] { display: none !important; }
`;

const browser = await chromium.launch({
  headless: true,
  executablePath: CHROME,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--lang=zh-CN'],
});
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  locale: 'zh-CN',
  timezoneId: 'Asia/Shanghai',
});
const page = await ctx.newPage();
await page.addInitScript((css) => {
  const add = () => {
    const s = document.createElement('style');
    s.textContent = css;
    document.head?.appendChild(s);
  };
  if (document.head) add();
  else document.addEventListener('DOMContentLoaded', add);
}, HIDE_CSS);

async function shot(name) {
  await page.addStyleTag({ content: HIDE_CSS }).catch(() => {});
  await page.screenshot({ path: path.join(OUT, name) });
  log('saved', name);
}

await page.goto(`${BASE}/signin`, { waitUntil: 'domcontentloaded', timeout: 240000 });
await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 240000 });
await page.waitForTimeout(1500);
await shot('01-signin.png');

await page.fill('input[type="email"], input[name="email"]', EMAIL);
await page.fill('input[type="password"], input[name="password"]', PASS);
await page.click('button[type="submit"]');
log('login submitted');
await page.waitForURL((u) => !String(u).includes('/signin'), { timeout: 120000 }).catch(() => {});
await page.waitForTimeout(6000);
log('url after login:', page.url());

await page.goto(`${BASE}/apps`, { waitUntil: 'domcontentloaded', timeout: 240000 });
await page.waitForTimeout(8000);
await shot('02-app-list.png');

await page.goto(`${BASE}/app/${APP_ID}/workflow`, { waitUntil: 'domcontentloaded', timeout: 240000 });
await page.waitForTimeout(18000);
await shot('03-canvas.png');

// 4b. 在画布上点「预览」，打开调试对话抽屉（比 /chat 路由轻，不用编译整站）
try {
  await page.getByRole('button', { name: /预览|Preview/ }).first().click({ timeout: 30000 });
  log('opened preview drawer');
  await page.waitForTimeout(12000);
  await shot('04-chat-open.png');
} catch (e) {
  log('预览按钮未找到，回退到 /chat 路由：', e.message.slice(0, 120));
  await page.goto(`${BASE}/chat/${APP_ID}`, { waitUntil: 'domcontentloaded', timeout: 240000 });
  await page.waitForTimeout(15000);
  await shot('04-chat-open.png');
}

async function send(text, file) {
  const box = page.locator('textarea, [contenteditable="true"]').first();
  await box.waitFor({ timeout: 60000 });
  await box.click();
  await box.fill(text).catch(async () => {
    await page.keyboard.type(text, { delay: 20 });
  });
  await page.keyboard.press('Enter');
  log('sent:', text);
  await page.waitForTimeout(20000);
  await shot(file);
}

try {
  await send('往酒坛里兑半坛水', '05-chat-prank.png');
  await send('又往酒坛里兑水', '06-chat-old-grudge.png');
  await send('打烊，结账', '07-chat-settle.png');
} catch (e) {
  log('对话流程失败：', e.message.slice(0, 200));
}

await browser.close();
log('done ->', OUT);
