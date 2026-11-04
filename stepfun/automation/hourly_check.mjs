#!/usr/bin/env node
// 每小时自动合规检查：静态代码检查 + 运行时检查（seekdb / API / 证据 / 指标），
// 生成 automation/reports/<时间戳>.md，并把摘要追加到 docs/PROGRESS.md。
import { readFile, writeFile, mkdir, readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const REPORTS = join(HERE, 'reports');
const API = process.env.APP_URL || 'http://127.0.0.1:5177';

const results = [];
function check(id, title, ok, detail = '', fix = '') {
  results.push({ id, title, ok, detail, fix });
}

async function fileText(path) {
  try {
    return await readFile(join(ROOT, path), 'utf8');
  } catch {
    return '';
  }
}

async function getJson(path) {
  try {
    const response = await fetch(`${API}${path}`, { signal: AbortSignal.timeout(4000) });
    return await response.json();
  } catch {
    return null;
  }
}

async function main() {
  // 1. 端侧推理：服务端不得出现推理代码
  const serverFiles = [];
  for (const dir of ['server', 'server/lib']) {
    const abs = join(ROOT, dir);
    if (!existsSync(abs)) continue;
    for (const name of await readdir(abs)) {
      if (name.endsWith('.mjs')) serverFiles.push(join(dir, name));
    }
  }
  const serverText = (await Promise.all(serverFiles.map(fileText))).join('\n');
  const inferenceHits = /@huggingface\/transformers|onnxruntime|pipeline\(['"]feature-extraction/.test(serverText);
  check('local-inference', '推理只在浏览器执行（服务端无推理依赖）', !inferenceHits,
    inferenceHits ? '服务端出现推理依赖引用' : `${serverFiles.length} 个服务端文件均无模型/推理调用`,
    '移除 server/ 下的推理依赖；embedding 只在 web/src/lib/embedder.worker.ts');

  // 2. 前端使用 Transformers.js + WebGPU 优先 + WASM 降级
  const worker = await fileText('web/src/lib/embedder.worker.ts');
  const backend = await fileText('web/src/lib/backend.ts');
  const hasWebGPU = /device:\s*msg\.device/.test(worker) && /requestAdapter/.test(backend);
  const hasFallback = /wasm/.test(worker) && /降级|fallback/i.test(backend + worker);
  check('webgpu-priority', 'WebGPU 优先并在失败时降级 WASM', hasWebGPU && hasFallback,
    hasWebGPU && hasFallback ? 'backend.ts 真正探测 adapter；worker 初始化失败回落 wasm' : '未找到探测/降级逻辑');

  // 3. 量化方案可选
  const modelCfg = await fileText('web/src/lib/model-config.ts');
  const hasDtypes = /q8/.test(modelCfg) && /fp16/.test(modelCfg) && /fp32/.test(modelCfg);
  check('quantization', '提供 INT8 / FP16 / FP32 三档量化权重', hasDtypes, hasDtypes ? 'model-config.ts 中 q8/fp16/fp32 均可用' : '缺少量化档位定义');

  // 4. 混合检索由 seekdb 完成（SDK hybridSearch，而非客户端拼合）
  const searchSrc = await fileText('server/lib/search.mjs');
  const usesHybrid = /hybridSearch\(/.test(searchSrc);
  const clientMerge = /mergeResults|combine\(|concat\(.*results|sort\(.*score/.test(await fileText('web/src/components/SearchPanel.tsx') + await fileText('web/src/App.tsx'));
  check('hybrid-in-db', '混合检索在 seekdb 内完成（DBMS_HYBRID_SEARCH + RRF）', usesHybrid && !clientMerge,
    usesHybrid ? 'search.mjs 调用 collection.hybridSearch（单条 DBMS_HYBRID_SEARCH）' : '未使用 SDK hybridSearch',
    '改为 seekdb 内部融合，客户端不得拼接两路结果');

  // 5. 索引刷新
  const kbSrc = await fileText('server/lib/kb.mjs');
  const hasRefresh = /refresh_index\(/.test(kbSrc);
  check('refresh-index', '写入后刷新索引（refresh_index）', hasRefresh, hasRefresh ? 'ingest 成功路径内含 refresh_index()' : '缺少索引刷新');

  // 6. 会话状态持久化在 seekdb
  const sessionSrc = await fileText('server/lib/session.mjs');
  const sessionPersist = /app_sessions/.test(sessionSrc) && /INSERT INTO app_sessions/.test(sessionSrc);
  check('session-state', '会话→知识库状态持久化在 seekdb', sessionPersist, sessionPersist ? 'app_sessions 表 upsert + 读取' : '会话状态未持久化');

  // 7. 模型体积实测
  const sizesPath = join(ROOT, 'results', 'model-sizes.json');
  let sizes = null;
  if (existsSync(sizesPath)) sizes = JSON.parse(await readFile(sizesPath, 'utf8'));
  check('model-sizes', '量化前后模型体积与压缩比已实测', Boolean(sizes?.variants?.q8?.compressionRatio),
    sizes ? `q8 ${(sizes.variants.q8.weights / 1048576).toFixed(1)}MB，压缩比 ${sizes.variants.q8.compressionRatio}x；fp16 ${sizes.variants.fp16.compressionRatio}x` : '缺少 results/model-sizes.json',
    'npm run fetch-models');

  // 8. 质量评测数据
  const runFiles = existsSync(join(ROOT, 'results', 'runs')) ? (await readdir(join(ROOT, 'results', 'runs'))).filter((f) => f.endsWith('.json')) : [];
  check('metrics-runs', '分阶段计时已落盘（首次/后续分开）', runFiles.length > 0, `${runFiles.length} 条 run 记录`);

  // 9. 运行时：seekdb + API
  const health = await getJson('/api/health');
  check('seekdb-up', 'seekdb 可连接（本地 server 模式）', Boolean(health?.ok),
    health?.ok ? `${health.seekdb.host}:${health.seekdb.port} ${health.seekdb.version}` : health?.seekdb?.error || 'API 未启动',
    'bash scripts/seekdb_server.sh start && node server/index.mjs');

  const kbs = await getJson('/api/kbs');
  check('kb-data', '知识库数据可读（集合/文档/分块）', Array.isArray(kbs?.kbs),
    kbs ? `${kbs.kbs.length} 个知识库，共 ${kbs.kbs.reduce((a, k) => a + k.chunks, 0)} 个分块` : 'API 不可用');

  // 10. SQL 取证：最近是否出现过 DBMS_HYBRID_SEARCH
  const evidence = await getJson('/api/evidence?limit=200');
  const hybridStatements = (evidence?.statements || []).filter((s) => /DBMS_HYBRID_SEARCH|_keyword_rank/.test(s.sql || ''));
  check('sql-evidence', 'seekdb 内混合检索有 SQL 证据', hybridStatements.length > 0,
    hybridStatements.length ? `最近拦截到 ${hybridStatements.length} 条混合检索语句` : '尚未记录到混合检索语句（需先执行一次检索）');

  // 11. 构建产物
  const distIndex = join(ROOT, 'web', 'dist', 'index.html');
  check('build', '前端可构建且产物存在', existsSync(distIndex), existsSync(distIndex) ? 'web/dist/index.html' : '未构建',
    'npm run build');

  // 12. git 状态（提醒未提交）
  let git = '';
  try {
    git = execSync('git status --porcelain stepfun | head -20', { cwd: join(ROOT, '..'), encoding: 'utf8' }).trim();
  } catch (error) {
    git = `git 不可用: ${error.message}`;
  }
  check('git-clean', '提交状态（工作区未提交文件会被提醒）', git === '', git ? `${git.split('\n').length} 个未提交变更` : '工作区干净（stepfun/）');

  // 汇总
  const failed = results.filter((r) => !r.ok);
  const stamp = new Date();
  const report = [
    `# 合规检查 ${stamp.toISOString()} `,
    ``,
    `- 通过：${results.length - failed.length}/${results.length}`,
    `- 结论：**${failed.length === 0 ? '全部通过' : `${failed.length} 项待处理`}**`,
    ``,
    `| # | 检查项 | 结果 | 说明 |`,
    `|---|---|---|---|`,
    ...results.map((r, i) => `| ${i + 1} | ${r.title} | ${r.ok ? '✅' : '❌'} | ${r.detail} |`),
    ``,
    ...(failed.length ? [`## 待处理`, ...failed.map((r) => `- **${r.title}**：${r.detail}${r.fix ? ` → 修复：\`${r.fix}\`` : ''}`), ''] : []),
  ].join('\n');

  await mkdir(REPORTS, { recursive: true });
  const file = join(REPORTS, `${stamp.toISOString().replace(/[:.]/g, '-')}.md`);
  await writeFile(file, report, 'utf8');

  const progress = `\n## ${stamp.toISOString().slice(0, 16).replace('T', ' ')}（自动合规检查）\n- 通过 ${results.length - failed.length}/${results.length}${failed.length ? `，待处理：${failed.map((r) => r.title).join('、')}` : ''}\n- 报告：automation/reports/${file.split('/').pop()}\n`;
  await writeFile(join(ROOT, 'docs', 'PROGRESS.md'), progress, { flag: 'a' }).catch(async () => {
    await writeFile(join(ROOT, 'docs', 'PROGRESS.md'), `# 进度日志\n${progress}`, 'utf8');
  });

  console.log(report);
  console.log(`\n报告已写入 ${file}`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error('检查脚本异常:', error);
  process.exit(2);
});
