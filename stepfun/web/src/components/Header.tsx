import React from 'react';
import type { ReadyInfo } from '../lib/embedder';
import type { BackendProbe } from '../lib/backend';
import type { Dtype } from '../lib/model-config';

interface Props {
  health: any;
  probe: BackendProbe | null;
  ready: ReadyInfo | null;
  booting: boolean;
  modelProgress: { file?: string; progress?: number } | null;
  forceBackend: 'auto' | 'webgpu' | 'wasm';
  onForceBackend: (value: 'auto' | 'webgpu' | 'wasm') => void;
  dtype: Dtype;
  dtypes: Array<{ id: Dtype; label: string; note: string }>;
  onDtype: (value: Dtype) => void;
  error: string;
}

export function Header({ health, probe, ready, booting, modelProgress, forceBackend, onForceBackend, dtype, dtypes, onDtype, error }: Props) {
  const backend = ready?.device || probe?.backend;
  return (
    <header className="header">
      <div className="brand">
        <div className="logo">◈</div>
        <div>
          <h1>端侧知识库</h1>
          <p>浏览器本地向量化 · seekdb 混合检索</p>
        </div>
      </div>

      <div className="badges">
        <span className={`badge ${backend === 'webgpu' ? 'badge-gpu' : 'badge-wasm'}`} title={probe?.reason || ready?.fallback || ''}>
          {booting ? '模型加载中…' : backend ? `${backend === 'webgpu' ? 'WebGPU' : 'WASM'} · ${(ready?.dtype || dtype).toUpperCase()}` : '后端探测中'}
        </span>
        {ready?.fallback && <span className="badge badge-warn" title={ready.fallback}>已降级</span>}
        <span className={`badge ${health?.ok ? 'badge-ok' : 'badge-err'}`}>
          seekdb {health?.ok ? '已连接' : '未连接'}
        </span>
        {ready?.modelLoadMs ? <span className="badge badge-muted">加载 {Math.round(ready.modelLoadMs)} ms</span> : null}
      </div>

      <div className="controls">
        <label>
          推理后端
          <select value={forceBackend} onChange={(e) => onForceBackend(e.target.value as any)}>
            <option value="auto">自动（优先 WebGPU）</option>
            <option value="webgpu">强制 WebGPU</option>
            <option value="wasm">强制 WASM</option>
          </select>
        </label>
        <label>
          量化档位
          <select value={dtype} onChange={(e) => onDtype(e.target.value as Dtype)}>
            {dtypes.map((d) => (
              <option key={d.id} value={d.id} title={d.note}>{d.label}</option>
            ))}
          </select>
        </label>
      </div>

      {modelProgress?.file && (
        <div className="model-progress" title={modelProgress.file}>
          模型 {modelProgress.file.split('/').pop()} {modelProgress.progress ? `${modelProgress.progress.toFixed(0)}%` : ''}
        </div>
      )}
      {error && <div className="header-error">{error}</div>}
    </header>
  );
}
