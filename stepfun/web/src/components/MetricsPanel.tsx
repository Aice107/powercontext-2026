import React from 'react';
import type { RunRecord } from '../App';

interface Props {
  runs: RunRecord[];
  onExport: () => void;
  onRefreshSummary: () => void;
}

const FIELDS: Array<{ key: string; label: string }> = [
  { key: 'modelLoadMs', label: '加载' },
  { key: 'embedMs', label: '向量化' },
  { key: 'seekdbMs', label: '检索' },
  { key: 'e2eMs', label: '端到端' },
];

export function MetricsPanel({ runs, onExport }: Props) {
  return (
    <section className="card">
      <div className="row space-between">
        <h2>性能指标</h2>
        <button className="link" onClick={onExport} disabled={!runs.length}>导出 JSON</button>
      </div>
      {runs.length === 0 && <p className="muted small">导入与检索后，这里会记录分阶段耗时（同时落盘 results/runs/）。</p>}
      <table className="kv compact">
        <thead>
          <tr>
            <th>操作</th>
            <th>后端</th>
            {FIELDS.map((f) => <th key={f.key}>{f.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {runs.slice(0, 10).map((run, index) => (
            <tr key={`${run.at}-${index}`}>
              <td>{run.kind === 'query' ? `检索${run.mode ? `(${run.mode})` : ''}` : '导入'}</td>
              <td>{run.backend === 'webgpu' ? 'GPU' : 'WASM'}/{run.dtype}</td>
              {FIELDS.map((f) => (
                <td key={f.key} title={run.timings[f.key] != null ? `${run.timings[f.key]} ms` : '未记录'}>
                  {run.timings[f.key] != null ? `${Math.round(run.timings[f.key])}` : '–'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">单位 ms。首次模型加载与预热后的请求分开记录。</p>
    </section>
  );
}
