// SQL 证据环形缓冲区：记录服务端实际发给 seekdb 的语句。
// 用于证明「混合检索由 seekdb 完成」，而不是客户端拼合两路结果。
const MAX = 400;
const buffer = [];

export function recordStatement(entry) {
  buffer.push({ seq: buffer.length ? buffer[buffer.length - 1].seq + 1 : 1, ...entry });
  while (buffer.length > MAX) buffer.shift();
}

export function listStatements(limit = 20) {
  return buffer.slice(-limit);
}

export function statementsByPhase(phase, limit = 10) {
  return buffer.filter((s) => s.phase === phase).slice(-limit);
}

export function clearStatements() {
  buffer.length = 0;
}
