import React from 'react';

interface Result {
  ref: number;
  id: string;
  document: string | null;
  metadata: any;
  distance: number | null;
}

interface Props {
  results: Result[];
  mode: string;
}

export function ResultList({ results, mode }: Props) {
  if (!results.length) {
    return <p className="muted">没有命中结果。可以尝试降低 Top-K、换关键词，或确认索引已刷新。</p>;
  }
  return (
    <ol className="results">
      {results.map((r) => (
        <li key={r.id} className="result">
          <div className="result-head">
            <span className="rank">#{r.ref}</span>
            <span className="doc-title">{r.metadata?.title || r.id}</span>
            <span className="muted small">
              {r.metadata?.docId} · 块 {r.metadata?.chunkIndex}
              {r.distance != null ? ` · ${mode === 'vector' ? '距离' : '分数'} ${Number(r.distance).toFixed(4)}` : ''}
            </span>
          </div>
          <p className="snippet">{r.document}</p>
          <div className="result-foot muted small">id: {r.id} · 来源 {r.metadata?.source || '-'}</div>
        </li>
      ))}
    </ol>
  );
}
