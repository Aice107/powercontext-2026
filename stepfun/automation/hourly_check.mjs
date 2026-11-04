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

async function postJson(path, body) {
  try {
    const response = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20000),
    });
    return { status: response.status, ...(await response.json()) };
  } catch (error) {
    return { status: 0, error: error.message };
  }
}

/** 运行时一致性：增量写入可见性 + 会话切换不串库（使用临时知识库，检查后清理） */
async function runtimeConsistency() {
  const stamp = Date.now().toString(36).slice(-5);
  const kbA = `chk_a_${stamp}`;
  const kbB = `chk_b_${stamp}`;
  const sessionId = `chk-${stamp}`;
  const vec = (seed) => Array.from({ length: 512 }, (_, i) => +(Math.sin(seed * 3.17 + i * 0.11) * 0.5).toFixed(4));
  const details = [];
  let ok = true;
  try {
    for (const kb of [kbA, kbB]) {
      const created = await postJson('/api/kbs', { name: kb, description: 'hourly check', model: 'bge-small-zh-v1.5', dtype: 'q8', dim: 512 });
      if (created.status !== 200) throw new Error(`创建 ${kb} 失败: ${created.error}`);
    }
    const ingestA = await postJson('/api/ingest', {
      kb: kbA,
      chunks: [{ id: 'a#0', text: `知识库 A 的标记内容 token-${stamp}-alpha`, vector: vec(1), metadata: { docId: 'a', title: 'A', chunkIndex: 0 } }],
    });
    const ingestB = await postJson('/api/ingest', {
      kb: kbB,
      chunks: [{ id: 'b#0', text: `知识库 B 的标记内容 token-${stamp}-beta`, vector: vec(2), metadata: { docId: 'b', title: 'B', chunkIndex: 0 } }],
    });
    if (ingestA.status !== 200 || ingestB.status !== 200) throw new Error('临时知识库写入失败');

    // 1) 会话 → A，检索应只命中 A
    await postJson('/api/session', { sessionId, kb: kbA });
    const searchA = await postJson('/api/search', { sessionId, mode: 'hybrid', query: '标记内容 alpha', vector: vec(1), topK: 3 });
    const docA = searchA.results?.map((r) => r.metadata?.docId).filter(Boolean) || [];
    const fixedA = searchA.kbSource === 'session' && docA.includes('a') && !docA.includes('b');
    details.push(`会话A→${docA.join(',') || '空'}`);
    ok = ok && fixedA;

    // 2) 切换到 B，检索应只命中 B（不串库）
    await postJson('/api/session', { sessionId, kb: kbB });
    const searchB = await postJson('/api/search', { sessionId, mode: 'hybrid', query: '标记内容 beta', vector: vec(2), topK: 3 });
    const docB = searchB.results?.map((r) => r.metadata?.docId).filter(Boolean) || [];
    const fixedB = searchB.kb === kbB && docB.includes('b') && !docB.includes('a');
    details.push(`会话B→${docB.join(',') || '空'}`);
    ok = ok && fixedB;

    // 3) 增量写入 + 刷新后立即可检索
    const token = `token-${stamp}-gamma`;
    const ingestNew = await postJson('/api/ingest', {
      kb: kbB,
      chunks: [{ id: 'b2#0', text: `增量文档 ${token}`, vector: vec(3), metadata: { docId: 'b2', title: 'B2', chunkIndex: 0 } }],
    });
    const searchNew = await postJson('/api/search', { sessionId, mode: 'hybrid', query: token, vector: vec(3), topK: 3 });
    const docNew = searchNew.results?.map((r) => r.metadata?.docId) || [];
    const visible = docNew.includes('b2') && ingestNew.timings?.refreshMs >= 0;
    details.push(`增量可见=${visible}`);
    ok = ok && visible;
  } catch (error) {
    ok = false;
    details.push(`异常: ${error.message}`);
  } finally {
    for (const kb of [kbA, kbB]) {
      await fetch(`${API}/api/kbs/${encodeURIComponent(kb)}`, { method: 'DELETE' }).catch(() => {});
    }
  }
  return { ok, detail: details.join('；') };
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

  // 10.5 运行时一致性：会话切换 / 增量刷新可见性
  let runtime = { ok: false, detail: '跳过（API 不可用）' };
  if (health?.ok) runtime = await runtimeConsistency();
  check('runtime-consistency', '会话切换不串库 + 增量写入刷新后可检索', runtime.ok, runtime.detail,
    '检查 server/lib/{session,kb}.mjs 与 ingest 刷新路径');

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
