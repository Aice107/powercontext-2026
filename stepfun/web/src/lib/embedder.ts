// Worker 客户端：负责初始化、WebGPU→WASM 自动降级与进度回调。
import type { Dtype } from './model-config';

export type Device = 'webgpu' | 'wasm';

export interface ReadyInfo {
  device: Device;
  dtype: Dtype;
  modelId: string;
  dim: number;
  modelLoadMs: number;
  modelBytes?: number;
  fallback?: string | null;
}

interface Pending {
  resolve: (value: any) => void;
  reject: (error: any) => void;
  onProgress?: (done: number, total: number) => void;
}

export class EmbedderClient {
  private worker: Worker | null = null;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private readyInfo: ReadyInfo | null = null;

  onModelProgress?: (p: { file?: string; progress?: number; loaded?: number; total?: number; note?: string }) => void;

  private ensureWorker() {
    if (this.worker) return this.worker;
    const worker = new Worker(new URL('./embedder.worker.ts', import.meta.url), { type: 'module' });
    worker.addEventListener('message', (event: MessageEvent<any>) => {
      const msg = event.data;
      if (msg.type === 'progress') {
        this.onModelProgress?.(msg);
        return;
      }
      if (msg.type === 'embed-progress') {
        for (const p of this.pending.values()) p.onProgress?.(msg.done, msg.total);
        return;
      }
      if (msg.type === 'error') {
        const first = this.pending.values().next().value as Pending | undefined;
        if (first) first.reject(new Error(msg.message));
        this.pending.clear();
        return;
      }
      if (msg.type === 'ready' || msg.type === 'embedded' || msg.type === 'reset-ok') {
        const id = msg.requestId ?? 0;
        const pending = this.pending.get(id);
        if (pending) {
          this.pending.delete(id);
          pending.resolve(msg);
        }
        return;
      }
    });
    this.worker = worker;
    return worker;
  }

  private once<T>(message: any, onProgress?: (a: number, b: number) => void): Promise<T> {
    const worker = this.ensureWorker();
    const requestId = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(requestId, { resolve: resolve as any, reject, onProgress });
      worker.postMessage({ ...message, requestId });
    });
  }

  /**
   * 初始化：先用探测出的 device；若 WebGPU 初始化/预热失败，自动降级到 WASM 并记录原因。
   */
  async init(options: {
    modelId: string;
    device: Device;
    dtype: Dtype;
    batchSize: number;
    threads?: number;
    localFirst?: boolean;
    allowFallback?: boolean;
  }): Promise<ReadyInfo> {
    try {
      const ready = await this.once<ReadyInfo>({ type: 'init', ...options });
      this.readyInfo = { ...ready };
      return this.readyInfo;
    } catch (error: any) {
      if (options.device === 'webgpu' && options.allowFallback !== false) {
        const ready = await this.once<ReadyInfo>({
          type: 'init',
          ...options,
          device: 'wasm',
          dtype: options.dtype === 'fp16' ? 'q8' : options.dtype,
        });
        this.readyInfo = { ...ready, fallback: `WebGPU 不可用（${error.message}），已自动降级 WASM` };
        return this.readyInfo;
      }
      throw error;
    }
  }

  async embed(texts: string[], onProgress?: (done: number, total: number) => void) {
    const result = await this.once<{
      vectors: number[][];
      ms: number;
      batchTimes: number[];
      count: number;
      chunksPerSec: number;
      device?: string;
      dtype?: string;
    }>({ type: 'embed', texts }, onProgress);
    return result;
  }

  get info() {
    return this.readyInfo;
  }

  terminate() {
    this.worker?.terminate();
    this.worker = null;
    this.pending.clear();
  }
}
