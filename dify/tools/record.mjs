#!/usr/bin/env node
/**
 * 录制《记仇客栈》的完整演示视频（webm）。
 *
 * 用法：
 *   PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
 *   node record.mjs <app_id> [out_dir]
 *
 * 产物：<out_dir>/demo-inn.webm（Playwright 的 recordVideo），
 * 若本机有 ffmpeg 会顺带转 mp4。
 */

import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const PW = process.env.PLAYWRIGHT_MODULE || 'playwright';
const { chromium } = await import(PW);

const APP_ID = process.argv[2] || process.env.INN_APP_ID;
const OUT = process.argv[3] || '/home/ice/dify-project/dify/evidence/recordings';
const BASE = process.env.DIFY_BASE || 'http://localhost:3000';
const CHROME = process.env.CHROME_PATH || '/home/ice/dify-shot/chromium/chrome-linux/chrome';

if (!APP_ID) {
  console.error('缺少 app_id');
  process.exit(1);
}
fs.mkdirSync(OUT, { recursive: true });
const log = (...a) => console.log(`[${new Date().toISOString().slice(11, 19)}]`, ...a);

const HIDE = `
  [class*="styles-module__toolbar"],
  [class*="styles-module__drawCanvas"],
  [class*="styles-module__fixedMarkersLayer"],
  [class*="styles-module__markersLayer"],
  code-inspector-component { display: none !important; }
`;

const browser = await chromium.launch({
  headless: true,
  executablePath: CHROME,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--lang=zh-CN'],
});
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  locale: 'zh-CN',
  timezoneId: 'Asia/Shanghai',
  recordVideo: { dir: OUT, size: { width: 1280, height: 800 } },
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
}, HIDE);

async function hideIssues() {
  try {
    const loc = page.getByText(/^\s*\d+\s*Issues?\s*$/i).first();
    if (await loc.count()) {
      await loc.evaluate((el) => {
        let n = el;
        for (let i = 0; i < 4 && n; i += 1) {
          n.style.display = 'none';
          n = n.parentElement || n.getRootNode?.()?.host || null;
        }
      });
    }
  } catch {}
}

// 1. 登录
await page.goto(`${BASE}/signin`, { waitUntil: 'domcontentloaded', timeout: 240000 });
await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 240000 });
await hideIssues();
await page.waitForTimeout(2500);
await page.fill('input[type="email"], input[name="email"]', process.env.DIFY_EMAIL || 'admin@inn.local');
await page.fill('input[type="password"], input[name="password"]', process.env.DIFY_PASS || 'InnAdmin123!');
await page.waitForTimeout(1200);
await page.click('button[type="submit"]');
log('logged in');
await page.waitForTimeout(8000);

// 2. 画布（停留展示结构）
await page.goto(`${BASE}/app/${APP_ID}/workflow`, { waitUntil: 'domcontentloaded', timeout: 240000 });
await page.waitForTimeout(16000);
await hideIssues();
await page.waitForTimeout(4000);
log('canvas shown');

// 3. 预览抽屉 + 三轮对话
await page.getByRole('button', { name: /预览|Preview/ }).first().click({ timeout: 30000 });
await page.waitForTimeout(10000);
await hideIssues();

const box = page.locator('textarea, [contenteditable="true"]').first();
async function say(text, waitMs = 16000) {
  await box.waitFor({ timeout: 60000 });
  await box.click();
  await box.fill(text).catch(async () => page.keyboard.type(text, { delay: 30 }));
  await page.waitForTimeout(800);
  await page.keyboard.press('Enter');
  log('sent:', text);
  await page.waitForTimeout(waitMs);
}

await say('往酒坛里兑半坛水');
await say('又往酒坛里兑水');
await say('打烊，结账', 20000);

// 4. 收尾（滚动到长卷顶部，停留 2s）
await page.mouse.wheel(0, -600).catch(() => {});
await page.waitForTimeout(2500);

const video = page.video();
await ctx.close();   // 关闭后视频才落盘
await browser.close();

const raw = await video.path();
const target = path.join(OUT, 'demo-inn.webm');
fs.renameSync(raw, target);
log('video:', target, `${(fs.statSync(target).size / 1024 / 1024).toFixed(1)} MB`);

// 5. 可选转 mp4
const ffmpeg = process.env.FFMPEG_PATH || '/home/ice/.cache/ms-playwright/ffmpeg-1010/ffmpeg-linux';
if (fs.existsSync(ffmpeg)) {
  const mp4 = path.join(OUT, 'demo-inn.mp4');
  try {
    execFileSync(ffmpeg, ['-y', '-i', target, '-vf', 'scale=1280:-2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '28', mp4], { stdio: 'ignore' });
    log('mp4:', mp4, `${(fs.statSync(mp4).size / 1024 / 1024).toFixed(1)} MB`);
  } catch (e) {
    log('mp4 转换失败（保留 webm）：', String(e).slice(0, 120));
  }
}
