const BASE = '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await response.text();
  let payload: any = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { error: text };
  }
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload as T;
}

export interface KbInfo {
  name: string;
  collection: string;
  description: string;
  model: string;
  dtype: string;
  dim: number;
  chunks: number;
  docs: number;
  createdAt?: string;
}

export const api = {
  health: () => request<{ ok: boolean; seekdb: any; time: string }>('/api/health'),
  models: () => request<any>('/api/models'),
  listKbs: () => request<{ kbs: KbInfo[] }>('/api/kbs'),
  createKb: (body: { name: string; description?: string; model?: string; dtype?: string; dim?: number }) =>
    request<{ name: string; collection: string; createMs: number }>('/api/kbs', { method: 'POST', body: JSON.stringify(body) }),
  deleteKb: (name: string) => request(`/api/kbs/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  setSession: (body: { sessionId: string; kb: string }) =>
    request<{ sessionId: string; kb: string }>('/api/session', { method: 'POST', body: JSON.stringify(body) }),
  getSession: (sessionId: string) => request<{ session: any }>(`/api/session/${encodeURIComponent(sessionId)}`),
  ingest: (body: any) => request<any>('/api/ingest', { method: 'POST', body: JSON.stringify(body) }),
  refresh: (body: any) => request<any>('/api/refresh', { method: 'POST', body: JSON.stringify(body) }),
  search: (body: any) => request<any>('/api/search', { method: 'POST', body: JSON.stringify(body) }),
  evidence: (limit = 20) => request<{ statements: any[] }>(`/api/evidence?limit=${limit}`),
  saveRun: (run: any) => request<{ saved: string }>('/api/metrics', { method: 'POST', body: JSON.stringify(run) }),
  summary: () => request<any>('/api/metrics/summary'),
  docs: (kb: string) => request<{ docs: any[] }>(`/api/kbs/${encodeURIComponent(kb)}/docs`),
};
