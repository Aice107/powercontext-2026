#!/usr/bin/env node
// 把 onnxruntime-web 的运行时（.mjs 装载器 + .wasm）复制到 web/public/ort/，
// 避免 Transformers.js 在离线/受限网络环境下去 CDN 拉取 ORT 运行时。
import { copyFile, mkdir, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const SRC = join(ROOT, 'node_modules', 'onnxruntime-web', 'dist');
const DEST = join(ROOT, 'web', 'public', 'ort');

async function main() {
  if (!existsSync(SRC)) {
    console.error('未找到 onnxruntime-web，请先 npm install');
    process.exit(1);
  }
  await mkdir(DEST, { recursive: true });
  const files = (await readdir(SRC)).filter((f) => /^(ort-wasm.*|ort-wasm-simd.*)\.(mjs|wasm)$/.test(f));
  for (const file of files) {
    await copyFile(join(SRC, file), join(DEST, file));
    console.log(`· ${file}`);
  }
  console.log(`ORT 运行时已复制到 web/public/ort/（${files.length} 个文件）`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
