import React, { useRef, useState } from 'react';
import type { ImportResult } from '../App';
import { DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE } from '../lib/model-config';

interface Props {
  onImport: (text: string, name: string) => Promise<ImportResult>;
  activeKb: string;
  disabled: boolean;
}

export function ImportPanel({ onImport, activeKb, disabled }: Props) {
  const [text, setText] = useState('');
  const [name, setName] = useState('sample.md');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string>('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  async function runImport(payload: string, fileName: string) {
    setBusy(true);
    setError('');
    setResult(null);
    setProgress('分块 → 端侧向量化 → 写入 seekdb…');
    try {
      const res = await onImport(payload, fileName);
      setResult(res);
      setProgress('');
    } catch (e: any) {
      setError(e.message);
      setProgress('');
    } finally {
      setBusy(false);
    }
  }

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const content = await file.text();
    setText(content);
    setName(file.name);
    await runImport(content, file.name);
    event.target.value = '';
  }

  return (
    <section className="card">
      <h2>导入文档</h2>
      <p className="muted small">
        支持 .txt / .md；多文档可用 <code>=== 文件名 ===</code> 分隔。分块 {DEFAULT_CHUNK_SIZE} 字 / 重叠 {DEFAULT_CHUNK_OVERLAP} 字。
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="粘贴文本，或选择文件…"
        rows={7}
      />
      <div className="row">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="文档名" />
        <button className="btn" disabled={disabled || busy || !text.trim()} onClick={() => runImport(text, name)}>
          {busy ? '处理中…' : '导入并向量化'}
        </button>
      </div>
      <div className="row">
        <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" onChange={onFile} hidden />
        <button className="btn ghost" disabled={disabled || busy} onClick={() => fileRef.current?.click()}>
          选择文件
        </button>
        {!activeKb && <span className="muted small">请先选择知识库</span>}
      </div>
      {progress && <p className="muted small">{progress}</p>}
      {error && <p className="error small">{error}</p>}
      {result && (
        <div className="result-box">
          <div>
            ✅ 已写入 <strong>{result.kb}</strong>：{result.docs} 篇 / {result.chunks} 块
          </div>
          <table className="kv">
            <tbody>
              <tr><td>分块</td><td>{result.timings.chunkMs} ms</td></tr>
              <tr><td>端侧向量化</td><td>{result.timings.embedMs} ms（{result.metrics.embedChunksPerSec} 块/s）</td></tr>
              <tr><td>写入 seekdb</td><td>{result.timings.seekdbWriteMs} ms</td></tr>
              <tr><td>索引刷新</td><td>{result.timings.refreshMs} ms</td></tr>
              <tr><td>端到端</td><td>{result.timings.totalMs} ms</td></tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
