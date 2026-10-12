const BASE = '/api';

async function jsonOrThrow(res, fallback) {
  let data;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail?.message || data?.detail || data?.message;
    throw new Error(typeof detail === 'string' ? detail : fallback);
  }
  return data;
}

export async function fetchSessions() {
  const res = await fetch(`${BASE}/sessions`);
  return jsonOrThrow(res, 'Unable to load conversations');
}

export async function fetchHistory(sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/history`);
  return jsonOrThrow(res, 'Unable to restore conversation history');
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { method: 'DELETE' });
  return res.json();
}

export async function updateSessionPaperScope(sessionId, paperIds) {
  const res = await fetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}/paper-scope`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paper_ids: paperIds }),
  });
  return jsonOrThrow(res, '无法保存当前论文范围');
}

export async function uploadFiles(files) {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  const res = await fetch(`${BASE}/files/upload`, { method: 'POST', body: form });
  return res.json();
}

export async function fetchFiles() {
  const res = await fetch(`${BASE}/files`);
  return res.json();
}

export function originalPdfUrl(fileId) {
  return `${BASE}/files/${encodeURIComponent(fileId)}/content`;
}

export async function deleteFile(fileId) {
  const res = await fetch(`${BASE}/files/${fileId}`, { method: 'DELETE' });
  return res.json();
}

export async function clearCollection() {
  const res = await fetch(`${BASE}/collection`, { method: 'DELETE' });
  return res.json();
}

export async function healthCheck() {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

export async function searchAcademicPapers(query, limit = 10) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  const res = await fetch(`${BASE}/discovery/search?${params}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail?.message || data.detail || 'Discovery failed');
  return data;
}

export async function discoverFromUploadedPaper(fileId, limit = 12) {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${BASE}/discovery/from-paper/${encodeURIComponent(fileId)}?${params}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Paper relationship discovery failed');
  return data;
}

export async function importArxivPaper(arxivId, title = '') {
  const res = await fetch(`${BASE}/discovery/import/arxiv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId, title }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Import failed');
  return data;
}

export async function fetchInspectionPapers() {
  const res = await fetch(`${BASE}/inspection/papers`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Knowledge inspection failed');
  return data;
}

export async function fetchPaperChunks(paperId, level = 'children', offset = 0, limit = 30) {
  const params = new URLSearchParams({ level, offset: String(offset), limit: String(limit) });
  const res = await fetch(`${BASE}/inspection/papers/${encodeURIComponent(paperId)}/chunks?${params}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Chunk inspection failed');
  return data;
}

export async function fetchSessionMemory(sessionId) {
  const res = await fetch(`${BASE}/inspection/sessions/${encodeURIComponent(sessionId)}/memory`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Memory inspection failed');
  return data;
}

export async function fetchRuntimeSettings() {
  const res = await fetch(`${BASE}/settings`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Settings unavailable');
  return data;
}

export async function updateRuntimeSettings(settings, apiKey = '', clearApiKey = false) {
  const res = await fetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...settings,
      ...(apiKey ? { api_key: apiKey } : {}),
      clear_api_key: clearApiKey,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'Settings update failed');
  return data;
}

export async function fetchLocalModels() {
  const res = await fetch(`${BASE}/settings/models/local`);
  return jsonOrThrow(res, '无法读取本地 Ollama 模型');
}

export async function testModelConnection(llm, apiKey = '') {
  const res = await fetch(`${BASE}/settings/models/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm, ...(apiKey ? { api_key: apiKey } : {}) }),
  });
  return jsonOrThrow(res, '模型连接测试失败');
}

export async function resetRuntimeSettings() {
  const res = await fetch(`${BASE}/settings`, { method: 'DELETE' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Settings reset failed');
  return data;
}

export async function reindexPaper(fileId) {
  const res = await fetch(`${BASE}/settings/papers/${encodeURIComponent(fileId)}/reindex`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Reindex failed');
  return data;
}

export async function resetSessionMemory(sessionId) {
  const res = await fetch(`${BASE}/settings/memory/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Memory reset failed');
  return data;
}

export function streamChat(query, sessionId, onEvent, paperIds = [], thinking = false) {
  const ctrl = new AbortController();

  fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId, paper_ids: paperIds, thinking }),
    signal: ctrl.signal,
  }).then(async (res) => {
    if (!res.ok) {
      let detail = `Chat request failed (${res.status})`;
      try {
        const body = await res.json();
        detail = body?.detail?.message || body?.detail || detail;
      } catch {
        // Keep the HTTP status message when the response is not JSON.
      }
      throw new Error(typeof detail === 'string' ? detail : `Chat request failed (${res.status})`);
    }
    if (!res.body) throw new Error('Chat stream is unavailable');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let completed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const lines = buf.split('\n');
      buf = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;
        const raw = trimmed.slice(5).trim();
        if (raw === '[DONE]') {
          completed = true;
          continue;
        }
        try {
          const evt = JSON.parse(raw);
          if (evt.type === 'done' || evt.type === 'error') completed = true;
          onEvent(evt);
        } catch {
          // Ignore a malformed SSE frame and continue reading the stream.
        }
      }
    }
    if (!completed) onEvent({ type: 'error', data: 'The answer stream ended before it was saved. Please retry.' });
  }).catch((err) => {
    if (err.name !== 'AbortError') {
      onEvent({ type: 'error', data: err.message });
    }
  });

  return () => ctrl.abort();
}
