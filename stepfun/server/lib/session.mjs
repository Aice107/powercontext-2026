// 会话状态：会话 → 当前知识库，持久化在 seekdb（app_sessions），重启后仍一致。
import { getClient } from './db.mjs';
import { ensureAppTables, getKbRecord } from './kb.mjs';

export async function setSession({ sessionId, kb }) {
  await ensureAppTables();
  const record = await getKbRecord(kb);
  if (!record) throw new Error(`知识库 ${kb} 不存在`);
  const db = await getClient();
  await db.execute(
    `INSERT INTO app_sessions (session_id, active_kb) VALUES (?, ?)
     ON DUPLICATE KEY UPDATE active_kb = VALUES(active_kb)`,
    [sessionId, kb],
  );
  return { sessionId, kb, collection: record.collection };
}

export async function getSession(sessionId) {
  await ensureAppTables();
  const db = await getClient();
  const rows = (await db.execute(`SELECT session_id, active_kb, updated_at FROM app_sessions WHERE session_id = ?`, [sessionId])) || [];
  if (!rows.length) return null;
  return { sessionId: rows[0].session_id, kb: rows[0].active_kb, updatedAt: rows[0].updated_at };
}

/** 检索时以服务端会话状态为准，客户端传来的 kb 仅在被显式允许时使用。 */
export async function resolveActiveKb({ sessionId, kb }) {
  if (sessionId) {
    const session = await getSession(sessionId);
    if (session) return { kb: session.kb, source: 'session' };
  }
  if (kb) return { kb, source: 'request' };
  throw new Error('缺少 sessionId 或 kb，无法确定检索目标知识库');
}
