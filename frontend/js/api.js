/**
 * API client - all fetch calls to the backend.
 */
const API = {
  async get(path) {
    const res = await fetch(`/api${path}`);
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(`/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    return res.json();
  },

  async put(path, body) {
    const res = await fetch(`/api${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    return res.json();
  },

  async del(path) {
    const res = await fetch(`/api${path}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
  },

  async uploadFile(projectId, file, onProgress) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`/api/documents/upload/${projectId}`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    return res.json();
  },

  // SSE streaming for chat
  streamChat(projectId, message, onChunk, onDone, onError) {
    fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, message }),
    }).then(async (res) => {
      if (!res.ok) {
        onError(new Error(`HTTP ${res.status}`));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) { onDone(); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              onChunk(payload);
              if (payload.type === 'done') { onDone(); return; }
            } catch (e) { /* ignore parse errors */ }
          }
        }
      }
    }).catch(onError);
  },
};
