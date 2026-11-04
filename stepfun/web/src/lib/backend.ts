// 推理后端探测：优先 WebGPU（真正拿到 adapter），否则 WASM。
export type Backend = 'webgpu' | 'wasm';

export interface BackendProbe {
  backend: Backend;
  reason: string;
  adapterInfo?: string;
  hasWebGPUApi: boolean;
}

export async function probeBackend(force?: Backend | 'auto'): Promise<BackendProbe> {
  const gpu = (navigator as any).gpu;
  const hasWebGPUApi = Boolean(gpu);
  if (force === 'wasm') {
    return { backend: 'wasm', reason: '手动指定 WASM', hasWebGPUApi };
  }
  if (!hasWebGPUApi) {
    return { backend: 'wasm', reason: '浏览器无 WebGPU API，自动降级 WASM', hasWebGPUApi };
  }
  try {
    const adapter = await gpu.requestAdapter({ powerPreference: 'high-performance' });
    if (!adapter) {
      return { backend: 'wasm', reason: 'requestAdapter() 返回空（无可用 GPU 适配器），自动降级 WASM', hasWebGPUApi };
    }
    let adapterInfo = 'webkit';
    try {
      const info = adapter.info || (await adapter.requestAdapterInfo?.());
      if (info) adapterInfo = [info.vendor, info.architecture, info.device].filter(Boolean).join(' ') || 'gpu';
    } catch {
      // adapter.info 在部分浏览器不可用，忽略
    }
    if (force === 'webgpu') return { backend: 'webgpu', reason: '手动指定 WebGPU', adapterInfo, hasWebGPUApi };
    return { backend: 'webgpu', reason: 'WebGPU 适配器可用，优先使用', adapterInfo, hasWebGPUApi };
  } catch (error: any) {
    return { backend: 'wasm', reason: `WebGPU 初始化失败(${error?.message || error})，自动降级 WASM`, hasWebGPUApi };
  }
}

export async function detectWebGPU(): Promise<boolean> {
  return (await probeBackend('auto')).backend === 'webgpu';
}
