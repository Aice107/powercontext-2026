import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, type KbInfo } from './lib/api';
import { EmbedderClient, type ReadyInfo } from './lib/embedder';
import { probeBackend, type Backend, type BackendProbe } from './lib/backend';
import { chunkText, splitDocuments, slug } from './lib/chunk';
import { DTYPES, MODEL_DIM, MODEL_ID, MODEL_REMOTE_REPO, DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, DEFAULT_TOP_K, type Dtype } from './lib/model-config';
import { Header } from './components/Header';
import { ImportPanel } from './components/ImportPanel';
import { SearchPanel } from './components/SearchPanel';
import { MetricsPanel } from './components/MetricsPanel';
import { KbBar } from './components/KbBar';

export interface RunRecord {
  kind: 'import' | 'query' | 'bench';
  kb: string;
  backend: string;
  dtype: string;
  mode?: string;
  timings: Record<string, number>;
  metrics?: Record<string, number>;
  quality?: Record<string, number>;
  at: string;
}

export interface ImportResult {
  docs: number;
  chunks: number;
  timings: Record<string, number>;
  metrics: Record<string, number>;
  kb: string;
}

function newSessionId() {
  const existing = localStorage.getItem('stepfun.sessionId');
  if (existing) return existing;
  const id = `s-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
  localStorage.setItem('stepfun.sessionId', id);
  return id;
}

const URL_PARAMS = new URLSearchParams(typeof location !== 'undefined' ? location.search : '');

export default function App() {
  const [sessionId] = useState(newSessionId);
  const [health, setHealth] = useState<any>(null);
  const [kbs, setKbs] = useState<KbInfo[]>([]);
  const [activeKb, setActiveKb] = useState<string>('');
  const [probe, setProbe] = useState<BackendProbe | null>(null);
  const [ready, setReady] = useState<ReadyInfo | null>(null);
  const [booting, setBooting] = useState(false);
  const [bootError, setBootError] = useState<string>('');
  const [modelProgress, setModelProgress] = useState<{ file?: string; progress?: number } | null>(null);
  const [forceBackend, setForceBackend] = useState<'auto' | Backend>((URL_PARAMS.get('backend') as any) || 'auto');
  const [dtype, setDtype] = useState<Dtype>((URL_PARAMS.get('dtype') as Dtype) || 'q8');
  const batchFromUrl = Number(URL_PARAMS.get('batch') || 0);
  const threadsFromUrl = Number(URL_PARAMS.get('threads') || 0);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [error, setError] = useState<string>('');

  const embedderRef = useRef<EmbedderClient | null>(null);
  const initRef = useRef<Promise<ReadyInfo> | null>(null);

  // 首屏：健康检查 + 知识库列表 + 后端探测
  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(e.message));
    api.listKbs().then(({ kbs }) => {
      setKbs(kbs);
      if (kbs.length && !activeKb) selectKb(kbs[0].name);
    }).catch(() => {});
    probeBackend(forceBackend).then(setProbe);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ensureEmbedder = useCallback(async (): Promise<ReadyInfo> => {
    if (initRef.current) return initRef.current;
    initRef.current = (async () => {
      setBooting(true);
      setBootError('');
      setModelProgress(null);
      try {
        const detected = await probeBackend(forceBackend);
        setProbe(detected);
        const client = new EmbedderClient();
        client.onModelProgress = (p) => setModelProgress({ file: p.file, progress: p.progress });
        embedderRef.current = client;
        const info = await client.init({
          modelId: MODEL_ID,
          device: detected.backend,
          dtype,
          batchSize: batchFromUrl || (detected.backend === 'webgpu' ? 16 : 8),
          threads: threadsFromUrl || undefined,
          localFirst: true,
          allowFallback: forceBackend !== 'webgpu',
        });
        setReady(info);
        setModelProgress(null);
        return info;
      } catch (e: any) {
        setBootError(e.message || String(e));
        initRef.current = null;
        throw e;
      } finally {
        setBooting(false);
      }
    })();
    return initRef.current;
  }, [dtype, forceBackend, batchFromUrl, threadsFromUrl]);

  useEffect(() => {
    // 预热模型（不影响首屏交互）
    ensureEmbedder().catch(() => {});
  }, [ensureEmbedder]);

  async function selectKb(name: string) {
    setActiveKb(name);
    try {
      await api.setSession({ sessionId, kb: name });
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function refreshKbs() {
    try {
      const { kbs: list } = await api.listKbs();
      setKbs(list);
      if (!list.find((k) => k.name === activeKb) && list.length) selectKb(list[0].name);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function createKb(name: string) {
    await api.createKb({ name, description: '端侧向量化知识库', model: MODEL_ID, dtype, dim: MODEL_DIM });
    await refreshKbs();
    await selectKb(name);
  }

  async function deleteKb(name: string) {
    await api.deleteKb(name);
    if (activeKb === name) setActiveKb('');
    await refreshKbs();
  }

  const recordRun = useCallback(async (run: RunRecord) => {
    setRuns((prev) => [run, ...prev].slice(0, 20));
    try {
      await api.saveRun(run);
    } catch {
      // 指标落盘失败不影响主流程
    }
  }, []);

  /** 导入：分块 → 端侧向量化 → 写入 seekdb → 刷新索引 */
  const importText = useCallback(async (raw: string, name: string, options: { deferRefresh?: boolean } = {}): Promise<ImportResult> => {
    if (!activeKb) throw new Error('请先选择或创建知识库');
    const t0 = performance.now();
    const docs = splitDocuments(raw, name);
    const payloadChunks: any[] = [];
    let chunkCount = 0;
    const chunkStarted = performance.now();
    for (const doc of docs) {
      const chunks = chunkText(doc.text, { chunkSize: DEFAULT_CHUNK_SIZE, overlap: DEFAULT_CHUNK_OVERLAP });
      chunkCount += chunks.length;
      chunks.forEach((chunk, i) => {
        payloadChunks.push({
          id: `${doc.docId}#${i}`,
          text: chunk.text,
          metadata: {
            docId: doc.docId,
            title: doc.title,
            chunkIndex: i,
            charStart: chunk.charStart,
            charEnd: chunk.charEnd,
            kb: activeKb,
            source: name,
          },
        });
      });
    }
    const chunkMs = +(performance.now() - chunkStarted).toFixed(1);
    if (!payloadChunks.length) throw new Error('文档内容为空');

    const info = await ensureEmbedder();
    const embedStarted = performance.now();
    const embedded = await embedderRef.current!.embed(payloadChunks.map((c) => c.text));
    const embedMs = +(performance.now() - embedStarted).toFixed(1);
    const chunksWithVectors = payloadChunks.map((chunk, i) => ({ ...chunk, vector: embedded.vectors[i] }));

    const ingestStarted = performance.now();
    const ingestResult = await api.ingest({
      sessionId,
      kb: activeKb,
      chunks: chunksWithVectors,
      deferRefresh: Boolean(options.deferRefresh),
    });
    const ingestWallMs = +(performance.now() - ingestStarted).toFixed(1);
    const totalMs = +(performance.now() - t0).toFixed(1);

    const result: ImportResult = {
      docs: docs.length,
      chunks: chunkCount,
      kb: activeKb,
      timings: {
        chunkMs,
        embedMs,
        ingestWallMs,
        seekdbWriteMs: ingestResult.timings?.upsertMs ?? 0,
        refreshMs: ingestResult.timings?.refreshMs ?? 0,
        totalMs,
      },
      metrics: {
        embedChunksPerSec: +(chunkCount / (embedMs / 1000)).toFixed(2),
        batchSize: batchFromUrl || (info.device === 'webgpu' ? 16 : 8),
        threads: threadsFromUrl,
      },
    };
    await recordRun({
      kind: 'import',
      kb: activeKb,
      backend: info.device,
      dtype: info.dtype,
      timings: result.timings,
      metrics: result.metrics,
      at: new Date().toISOString(),
    });
    await refreshKbs();
    return result;
  }, [activeKb, dtype, ensureEmbedder, recordRun, sessionId]);

  /** 检索：端侧查询向量化 → seekdb 混合检索（单条 DBMS_HYBRID_SEARCH） → 渲染 */
  const runSearch = useCallback(async (query: string, mode: 'hybrid' | 'vector' | 'fulltext' = 'hybrid', topK = DEFAULT_TOP_K) => {
    if (!activeKb) throw new Error('请先选择知识库');
    const t0 = performance.now();
    const info = await ensureEmbedder();
    let vector: number[] | undefined;
    let queryEmbedMs = 0;
    if (mode !== 'fulltext') {
      const started = performance.now();
      const embedded = await embedderRef.current!.embed([query]);
      queryEmbedMs = +(performance.now() - started).toFixed(1);
      vector = embedded.vectors[0];
    }
    const response = await api.search({ sessionId, kb: activeKb, mode, query, vector, topK });
    const renderedAt = performance.now() - t0;
    const timings = {
      modelLoadMs: info.modelLoadMs,
      queryEmbedMs,
      seekdbMs: response.timings.seekdbMs,
      e2eMs: +renderedAt.toFixed(1),
    };
    await recordRun({
      kind: 'query',
      kb: activeKb,
      backend: info.device,
      dtype: info.dtype,
      mode,
      timings,
      metrics: { topK, results: response.results.length },
      at: new Date().toISOString(),
    });
    return { ...response, timings };
  }, [activeKb, ensureEmbedder, recordRun, sessionId]);

  const exportRuns = useCallback(async () => {
    const blob = new Blob([JSON.stringify(runs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stepfun-runs-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [runs]);

  // 供 Playwright 基准/评测脚本调用（与 UI 完全相同的代码路径）
  useEffect(() => {
    (window as any).__stepfun = {
      ready: () => ensureEmbedder(),
      info: () => ready,
      state: () => ({ kb: activeKb, sessionId, backend: ready?.device, dtype: ready?.dtype, probe }),
      importText,
      embed: async (texts: string[]) => {
        await ensureEmbedder();
        return embedderRef.current!.embed(texts);
      },
      search: runSearch,
      runs: () => runs,
      createKb,
      selectKb,
    };
  }, [activeKb, ready, probe, sessionId, importText, runSearch, runs, createKb, ensureEmbedder]);

  const availableDtypes = useMemo(() => Object.values(DTYPES), []);

  return (
    <div className="app">
      <Header
        health={health}
        probe={probe}
        ready={ready}
        booting={booting}
        modelProgress={modelProgress}
        forceBackend={forceBackend}
        onForceBackend={(value) => {
          setForceBackend(value);
          initRef.current = null;
          setReady(null);
        }}
        dtype={dtype}
        dtypes={availableDtypes}
        onDtype={(value) => {
          setDtype(value);
          initRef.current = null;
          setReady(null);
        }}
        error={bootError}
      />

      {error && (
        <div className="banner banner-error" role="alert">
          <strong>操作失败：</strong> {error}
          <button className="link" onClick={() => setError('')}>关闭</button>
        </div>
      )}

      {health && !health.ok && (
        <div className="banner banner-warn">
          seekdb 未就绪：{health.seekdb?.error}。请先执行 <code>bash scripts/seekdb_server.sh start</code>。
        </div>
      )}

      <div className="layout">
        <aside className="sidebar">
          <KbBar
            kbs={kbs}
            activeKb={activeKb}
            onSelect={selectKb}
            onCreate={createKb}
            onDelete={deleteKb}
          />
          <ImportPanel onImport={importText} activeKb={activeKb} disabled={!activeKb} />
          <MetricsPanel runs={runs} onExport={exportRuns} onRefreshSummary={() => {}} />
        </aside>

        <main className="main">
          <SearchPanel
            onSearch={runSearch}
            activeKb={activeKb}
            backend={ready?.device}
            dtype={ready?.dtype}
            disabled={!activeKb}
          />
        </main>
      </div>

      <footer className="footer">
        <span>端侧模型：{MODEL_ID}（{MODEL_REMOTE_REPO}）· {MODEL_DIM} 维 · 推理位置：浏览器</span>
        <span>存储与混合检索：seekdb（DBMS_HYBRID_SEARCH，RRF 融合）</span>
      </footer>
    </div>
  );
}
