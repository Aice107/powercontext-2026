#!/usr/bin/env node
// 模型获取与体积实测：从公开镜像下载 bge-small-zh-v1.5 的 ONNX 权重（fp32 / fp16 / INT8），
// 统计每个权重文件的实际字节数与压缩比，写入 results/model-sizes.json。
// 模型文件仅用于浏览器端本地推理，不改变「推理发生在用户设备」这一要求。
import { mkdir, writeFile, stat, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const MODEL_ID = process.env.MODEL_ID || 'bge-small-zh-v1.5';
const REPO = process.env.MODEL_REPO || 'Xenova/bge-small-zh-v1.5';
const HOST = (process.env.HF_ENDPOINT || 'https://hf-mirror.com').replace(/\/$/, '');
const DEST = join(ROOT, 'models', MODEL_ID);

const FILES = [
  'config.json',
  'tokenizer.json',
  'tokenizer_config.json',
  'onnx/model.onnx',
  'onnx/model_fp16.onnx',
  'onnx/model_quantized.onnx',
];

async function download(pathRel) {
  const target = join(DEST, pathRel);
  if (existsSync(target)) {
    const info = await stat(target);
    if (info.size > 1024) {
      console.log(`· 已存在 ${pathRel} (${(info.size / 1024 / 1024).toFixed(2)} MB)`);
      return target;
    }
  }
  await mkdir(dirname(target), { recursive: true });
  const url = `${HOST}/${REPO}/resolve/main/${pathRel}`;
  console.log(`↓ ${url}`);
  const response = await fetch(url, { redirect: 'follow' });
  if (!response.ok) throw new Error(`下载失败 ${pathRel}: HTTP ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  await writeFile(target, buffer);
  console.log(`  → ${(buffer.length / 1024 / 1024).toFixed(2)} MB`);
  return target;
}

async function sha256(file) {
  const hash = createHash('sha256');
  hash.update(await readFile(file));
  return hash.digest('hex');
}

async function main() {
  const only = process.argv.find((a) => a.startsWith('--only='))?.split('=')[1];
  const wanted = only ? FILES.filter((f) => f.includes(only)) : FILES;
  for (const file of wanted) await download(file);

  const sizes = {};
  for (const file of FILES) {
    const target = join(DEST, file);
    if (!existsSync(target)) continue;
    sizes[file] = (await stat(target)).size;
  }

  const fp32 = sizes['onnx/model.onnx'];
  const fp16 = sizes['onnx/model_fp16.onnx'];
  const q8 = sizes['onnx/model_quantized.onnx'];
  const totalOf = (subset) => Object.entries(sizes).filter(([k]) => subset.includes(k)).reduce((a, [, v]) => a + v, 0);
  const runtimeFiles = ['config.json', 'tokenizer.json', 'tokenizer_config.json'];
  const summary = {
    modelId: MODEL_ID,
    repo: REPO,
    source: `${HOST}/${REPO}`,
    measuredAt: new Date().toISOString(),
    unit: 'bytes',
    files: sizes,
    runtimeOverheadBytes: totalOf(runtimeFiles),
    variants: {
      fp32: { weights: fp32, totalWithRuntime: fp32 + totalOf(runtimeFiles) },
      fp16: { weights: fp16, totalWithRuntime: fp16 + totalOf(runtimeFiles), compressionRatio: +(fp32 / fp16).toFixed(3) },
      q8: { weights: q8, totalWithRuntime: q8 + totalOf(runtimeFiles), compressionRatio: +(fp32 / q8).toFixed(3) },
    },
    sha256: {},
  };
  for (const file of FILES) {
    const target = join(DEST, file);
    if (existsSync(target)) summary.sha256[file] = await sha256(target);
  }

  await mkdir(join(ROOT, 'results'), { recursive: true });
  await writeFile(join(ROOT, 'results', 'model-sizes.json'), JSON.stringify(summary, null, 2));
  console.log('\n模型体积（权重）:');
  for (const [k, v] of Object.entries({ fp32, fp16, q8 })) {
    console.log(`  ${k.padEnd(5)} ${(v / 1024 / 1024).toFixed(2)} MB` + (k !== 'fp32' ? `  压缩比 ${(fp32 / v).toFixed(2)}x` : '  (基线)'));
  }
  console.log(`\n结果写入 results/model-sizes.json`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
