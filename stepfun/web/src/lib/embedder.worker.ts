/// <reference lib="webworker" />
// 端侧 embedding worker：Transformers.js + ONNX Runtime Web。
// 所有推理都发生在这里（浏览器），服务端不存在任何推理代码路径。
import { env, pipeline, type FeatureExtractionPipeline } from '@huggingface/transformers';

type Device = 'webgpu' | 'wasm';

interface InitMessage {
  type: 'init';
  requestId?: number;
  modelId: string;
  device: Device;
  dtype: 'q8' | 'fp16' | 'fp32';
  batchSize: number;
  threads?: number;
  localFirst?: boolean;
}

interface EmbedMessage {
  type: 'embed';
  requestId: number;
  texts: string[];
}

type Incoming = InitMessage | EmbedMessage | { type: 'reset' };

let extractor: FeatureExtractionPipeline | null = null;
let current: { modelId: string; device: Device; dtype: string } | null = null;
let batchSize = 8;

const ctx = self as unknown as DedicatedWorkerGlobalScope;

function post(message: unknown, transfer: Transferable[] = []) {
  ctx.postMessage(message, transfer);
}

function configureRuntime(threads?: number) {
  // ORT 运行时从本地 /ort/ 加载，避免依赖 CDN
  const ort = (env as any).backends?.onnx;
  if (ort?.wasm) {
    ort.wasm.wasmPaths = '/ort/';
    try {
      ort.wasm.numThreads = threads || Math.min(4, Math.max(1, navigator.hardwareConcurrency || 1));
    } catch {
      ort.wasm.numThreads = 1;
    }
    ort.wasm.proxy = false;
  }
}

function configureEnv(localFirst: boolean) {
  // 本地优先：模型文件由服务端 /models 静态提供（npm run fetch-models 下载）
  env.allowLocalModels = localFirst;
  env.localModelPath = '/models/';
  env.allowRemoteModels = !localFirst;
  if (!localFirst) env.remoteHost = 'https://hf-mirror.com';
  env.useBrowserCache = true;
}

async function load(msg: InitMessage) {
  const started = performance.now();
  const files: Record<string, number> = {};

  configureRuntime(msg.threads);
  configureEnv(msg.localFirst !== false);
  batchSize = msg.batchSize || 8;

  const progress_callback = (p: any) => {
    if (p?.status === 'progress' || p?.status === 'download') {
      if (p.file && p.total) files[p.file] = p.total;
      post({
        type: 'progress',
        stage: 'model',
        file: p.file,
        progress: p.progress ?? (p.loaded && p.total ? (p.loaded / p.total) * 100 : 0),
        loaded: p.loaded,
        total: p.total,
      });
    } else if (p?.status === 'ready') {
      post({ type: 'progress', stage: 'model', file: p.file, progress: 100 });
    }
  };

  try {
    extractor = await pipeline('feature-extraction', msg.modelId, {
      device: msg.device,
      dtype: msg.dtype,
      progress_callback,
    });
  } catch (error: any) {
    // 本地文件缺失时回退到公开镜像（推理位置不变，仍是本机计算）
    if (msg.localFirst !== false && /local|not found|404|Could not locate/i.test(String(error?.message))) {
      configureEnv(false);
      post({ type: 'progress', stage: 'model', note: '本地模型缺失，回退公开镜像下载' });
      extractor = await pipeline('feature-extraction', msg.modelId, {
        device: msg.device,
        dtype: msg.dtype,
        progress_callback,
      });
    } else {
      throw error;
    }
  }

  // 预热一次，确保 WebGPU 后端真的可执行（有些环境能建 pipeline 但算子跑不通）
  const warm = await extractor(['预热 warmup'], { pooling: 'mean', normalize: true });
  const dim = (warm as any).dims?.[1] ?? 0;
  const modelLoadMs = +(performance.now() - started).toFixed(1);
  const modelBytes = Object.values(files).reduce((a, b) => a + b, 0);
  current = { modelId: msg.modelId, device: msg.device, dtype: msg.dtype };
  post({
    type: 'ready',
    requestId: msg.requestId ?? 0,
    device: msg.device,
    dtype: msg.dtype,
    modelId: msg.modelId,
    dim,
    modelLoadMs,
    modelBytes,
    files,
  });
}

async function embedAll(texts: string[]) {
  if (!extractor) throw new Error('模型尚未加载');
  const vectors: number[][] = [];
  const batchTimes: number[] = [];
  const started = performance.now();

  for (let i = 0; i < texts.length; i += batchSize) {
    const slice = texts.slice(i, i + batchSize);
    const t0 = performance.now();
    const output = await extractor(slice, { pooling: 'mean', normalize: true });
    const list = output.tolist() as number[][];
    batchTimes.push(+(performance.now() - t0).toFixed(2));
    for (const row of list) vectors.push(row.map((v) => +v.toFixed(6)));
    post({ type: 'embed-progress', done: Math.min(i + slice.length, texts.length), total: texts.length });
  }

  const ms = +(performance.now() - started).toFixed(1);
  return { vectors, ms, batchTimes };
}

ctx.addEventListener('message', async (event: MessageEvent<Incoming>) => {
  const msg = event.data;
  try {
    if (msg.type === 'init') {
      if (extractor && current && current.modelId === msg.modelId && current.device === msg.device && current.dtype === msg.dtype) {
        post({ type: 'ready', requestId: msg.requestId ?? 0, device: msg.device, dtype: msg.dtype, modelId: msg.modelId, dim: 512, modelLoadMs: 0, reused: true });
        return;
      }
      await load(msg);
      return;
    }
    if (msg.type === 'embed') {
      const { vectors, ms, batchTimes } = await embedAll(msg.texts);
      post({
        type: 'embedded',
        requestId: msg.requestId,
        vectors,
        ms,
        batchTimes,
        count: msg.texts.length,
        chunksPerSec: +(msg.texts.length / (ms / 1000)).toFixed(2),
        device: current?.device,
        dtype: current?.dtype,
      });
      return;
    }
    if (msg.type === 'reset') {
      extractor = null;
      current = null;
      post({ type: 'reset-ok' });
    }
  } catch (error: any) {
    post({ type: 'error', requestId: (msg as any).requestId ?? 0, stage: msg.type, message: error?.message || String(error) });
  }
});
