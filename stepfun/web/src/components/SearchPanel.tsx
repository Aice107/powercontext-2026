import React, { useState } from 'react';
import { ResultList } from './ResultList';
import { DEFAULT_TOP_K } from '../lib/model-config';

type Mode = 'hybrid' | 'vector' | 'fulltext';

interface Props {
  onSearch: (query: string, mode: Mode, topK: number) => Promise<any>;
  activeKb: string;
  backend?: string;
  dtype?: string;
  disabled: boolean;
}

const MODE_LABEL: Record<Mode, string> = {
  hybrid: '混合检索（seekdb 内 RRF 融合）',
  vector: '仅向量',
  fulltext: '仅全文',
};

export function SearchPanel({ onSearch, activeKb, backend, dtype, disabled }: Props) {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<Mode>('hybrid');
  const [topK, setTopK] = useState(DEFAULT_TOP_K);
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState('');
  const [showSql, setShowSql] = useState(false);

  async function run(event?: React.FormEvent) {
    event?.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await onSearch(query, mode, topK);
      setResponse(res);
    } catch (e: any) {
      setError(e.message);
      setResponse(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card search">
      <form className="search-form" onSubmit={run}>
        <input
          className="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入问题，例如：seekdb 的混合检索如何融合向量与全文？"
        />
        <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
          {(Object.keys(MODE_LABEL) as Mode[]).map((m) => (
            <option key={m} value={m}>{MODE_LABEL[m]}</option>
          ))}
        </select>
        <select value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
          {[3, 5, 10].map((k) => <option key={k} value={k}>Top {k}</option>)}
        </select>
        <button className="btn primary" disabled={disabled || busy || !query.trim()}>
          {busy ? '检索中…' : '检索'}
        </button>
      </form>

      {error && <p className="error small">{error}</p>}

      {response && (
        <>
          <div className="search-meta">
            <span>知识库 <strong>{response.kb}</strong>（{response.kbSource === 'session' ? '会话状态' : '请求参数'}）</span>
            <span>后端 {backend === 'webgpu' ? 'WebGPU' : 'WASM'} · {(dtype || 'q8').toUpperCase()}</span>
            <span>候选窗口 {response.candidateK}</span>
            <span>seekdb {response.timings.seekdbMs} ms</span>
            <span>查询向量化 {response.timings?.queryEmbedMs ?? '-'} ms</span>
            <span>端到端 {response.timings?.e2eMs ?? '-'} ms</span>
            <button className="link" onClick={() => setShowSql((v) => !v)}>{showSql ? '隐藏 SQL 取证' : '查看 SQL 取证'}</button>
          </div>

          {showSql && (
            <div className="sql-box">
              <p className="muted small">以下语句为本次检索服务端实际发给 seekdb 的 SQL（混合模式由数据库完成融合）：</p>
              {(response.statements || []).map((s: any) => (
                <pre key={s.seq} className={s.phase === 'hybrid-search' ? 'sql hybrid' : 'sql'}>
                  <span className="sql-meta">#{s.seq} {s.phase} · {s.durationMs}ms · rows={s.rows}</span>
                  {s.sql}
                </pre>
              ))}
            </div>
          )}

          <ResultList results={response.results} mode={response.mode} />
        </>
      )}

      {!response && !error && (
        <p className="muted">
          当前知识库：<strong>{activeKb || '未选择'}</strong>。导入文档后即可检索；混合检索在 seekdb 内一次完成，
          客户端不做两路结果拼合。
        </p>
      )}
    </section>
  );
}
