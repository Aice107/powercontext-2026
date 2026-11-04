import React, { useState } from 'react';
import type { KbInfo } from '../lib/api';

interface Props {
  kbs: KbInfo[];
  activeKb: string;
  onSelect: (name: string) => void;
  onCreate: (name: string) => Promise<void>;
  onDelete: (name: string) => Promise<void>;
}

export function KbBar({ kbs, activeKb, onSelect, onCreate, onDelete }: Props) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function create() {
    const value = name.trim();
    if (!value) return;
    setBusy(true);
    setError('');
    try {
      await onCreate(value);
      setName('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>知识库</h2>
      <div className="kb-list">
        {kbs.length === 0 && <p className="muted">还没有知识库，先在下面创建一个。</p>}
        {kbs.map((kb) => (
          <div key={kb.name} className={`kb-item ${kb.name === activeKb ? 'active' : ''}`} onClick={() => onSelect(kb.name)}>
            <div>
              <strong>{kb.name}</strong>
              <div className="muted small">
                {kb.docs} 篇 · {kb.chunks} 块 · {kb.dim} 维
              </div>
            </div>
            <button
              className="link danger"
              title="删除知识库"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`删除知识库 ${kb.name} 及其全部向量？`)) onDelete(kb.name).catch((err) => setError(err.message));
              }}
            >
              删除
            </button>
          </div>
        ))}
      </div>
      <div className="row">
        <input
          value={name}
          placeholder="新知识库名称（英文/数字）"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && create()}
        />
        <button className="btn" disabled={busy || !name.trim()} onClick={create}>
          {busy ? '创建中…' : '创建'}
        </button>
      </div>
      {error && <p className="error small">{error}</p>}
    </section>
  );
}
