export interface Chunk {
  id: string;
  text: string;
  charStart: number;
  charEnd: number;
  chunkIndex: number;
}

/**
 * 滑窗分块：优先在段落/句子边界切开，保留 overlap 以保证跨块语义连续。
 */
export function chunkText(
  text: string,
  options: { chunkSize?: number; overlap?: number } = {},
): Chunk[] {
  const size = Math.max(80, options.chunkSize ?? 320);
  const overlap = Math.min(Math.max(0, options.overlap ?? 64), Math.floor(size / 2));
  const normalized = text.replace(/\r\n/g, '\n').trim();
  if (!normalized) return [];

  const chunks: Chunk[] = [];
  let cursor = 0;
  let index = 0;
  while (cursor < normalized.length) {
    let end = Math.min(cursor + size, normalized.length);
    if (end < normalized.length) {
      const window = normalized.slice(cursor, end);
      const cut = Math.max(
        window.lastIndexOf('\n\n'),
        window.lastIndexOf('。'),
        window.lastIndexOf('！'),
        window.lastIndexOf('？'),
        window.lastIndexOf('. '),
        window.lastIndexOf('\n'),
      );
      if (cut > size * 0.5) end = cursor + cut + 1;
    }
    const piece = normalized.slice(cursor, end).trim();
    if (piece) {
      chunks.push({ id: `chunk-${index}`, text: piece, charStart: cursor, charEnd: end, chunkIndex: index });
      index += 1;
    }
    if (end >= normalized.length) break;
    cursor = Math.max(end - overlap, cursor + 1);
  }
  return chunks;
}

export function splitDocuments(raw: string, fallbackName: string): Array<{ docId: string; title: string; text: string }> {
  // 支持 “=== 文件名 ===” 分隔多文档；否则整体作为一篇文档
  const normalized = raw.replace(/\r\n/g, '\n');
  const parts = normalized.split(/(?:^|\n)={3,}\s*(.+?)\s*={3,}\n/);
  if (parts.length > 1) {
    const docs: Array<{ docId: string; title: string; text: string }> = [];
    for (let i = 1; i < parts.length; i += 2) {
      const title = parts[i].trim();
      const body = (parts[i + 1] || '').trim();
      if (body) docs.push({ docId: slug(title) || `doc-${docs.length}`, title, text: body });
    }
    if (docs.length) return docs;
  }
  const title = fallbackName.replace(/\.[^.]+$/, '') || '未命名文档';
  return [{ docId: slug(title) || 'doc-0', title, text: raw }];
}

export function slug(value: string): string {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}
