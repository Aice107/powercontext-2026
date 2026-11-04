// 指标落盘：一次运行一条 JSON，便于统计中位数与复现。
import { mkdir, writeFile, readdir, readFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const RESULTS_DIR = process.env.RESULTS_DIR || join(HERE, '..', '..', 'results');
const RUNS_DIR = join(RESULTS_DIR, 'runs');

function median(values) {
  const arr = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!arr.length) return null;
  const mid = Math.floor(arr.length / 2);
  return arr.length % 2 ? arr[mid] : +((arr[mid - 1] + arr[mid]) / 2).toFixed(2);
}

export async function saveRun(run) {
  await mkdir(RUNS_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const record = { ...run, recordedAt: new Date().toISOString() };
  const file = join(RUNS_DIR, `${stamp}-${(run.kind || 'run').replace(/[^a-z0-9_-]/gi, '')}.json`);
  await writeFile(file, JSON.stringify(record, null, 2), 'utf8');
  return { file, record };
}

export async function listRuns(limit = 50) {
  await mkdir(RUNS_DIR, { recursive: true });
  const files = (await readdir(RUNS_DIR)).filter((f) => f.endsWith('.json')).sort().reverse().slice(0, limit);
  const runs = [];
  for (const file of files) {
    try {
      runs.push(JSON.parse(await readFile(join(RUNS_DIR, file), 'utf8')));
    } catch {
      // 损坏文件跳过
    }
  }
  return runs;
}

export async function summary() {
  const runs = await listRuns(500);
  const groups = new Map();
  for (const run of runs) {
    if (run.kind !== 'bench') continue;
    const key = `${run.backend || '?'}|${run.dtype || '?'}|${run.mode || 'hybrid'}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(run);
  }
  const rows = [];
  for (const [key, list] of groups.entries()) {
    const [backend, dtype, mode] = key.split('|');
    const pick = (path) => median(list.map((r) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), r)));
    rows.push({
      backend,
      dtype,
      mode,
      samples: list.length,
      modelLoadMs: pick('timings.modelLoadMs'),
      embedChunksPerSec: pick('metrics.embedChunksPerSec'),
      ingestMs: pick('timings.ingestMs'),
      refreshMs: pick('timings.refreshMs'),
      queryEmbedMs: pick('timings.queryEmbedMs'),
      seekdbMs: pick('timings.seekdbMs'),
      e2eMs: pick('timings.e2eMs'),
      recallAt5: pick('quality.recallAt5'),
      ndcgAt10: pick('quality.ndcgAt10'),
    });
  }
  return { generatedAt: new Date().toISOString(), runs: runs.length, rows };
}

export { median };
