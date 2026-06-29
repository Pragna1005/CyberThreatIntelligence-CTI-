const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function query(endpoint, question, topK = 5, uploadIds = [], history = []) {
  try {
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question, top_k: topK, upload_ids: uploadIds, history }),
    });
    if (!res.ok) {
      let message = `API error: ${res.status}`;
      try {
        const errorBody = await res.json();
        if (errorBody?.detail) message = errorBody.detail;
      } catch {
        // Keep the status-based message if the server did not return JSON.
      }
      throw new Error(message);
    }
    return res.json();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the API. Make sure the backend is running.");
    }
    throw error;
  }
}

async function uploadFile(file) {
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/api/upload`, { method: "POST", body: form });
    if (!res.ok) {
      let message = `Upload error: ${res.status}`;
      try {
        const errorBody = await res.json();
        if (errorBody?.detail) message = errorBody.detail;
      } catch { /* ignore */ }
      throw new Error(message);
    }
    return res.json();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the API. Make sure the backend is running.");
    }
    throw error;
  }
}

async function deleteUpload(uploadId) {
  try {
    const res = await fetch(`${BASE_URL}/api/upload/${uploadId}`, { method: "DELETE" });
    if (!res.ok) {
      let message = `Delete error: ${res.status}`;
      try {
        const errorBody = await res.json();
        if (errorBody?.detail) message = errorBody.detail;
      } catch { /* ignore */ }
      throw new Error(message);
    }
    return res.json();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the API. Make sure the backend is running.");
    }
    throw error;
  }
}

async function* chatStream(question, topK = 5, uploadIds = [], history = []) {
  const res = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: question, top_k: topK, upload_ids: uploadIds, history }),
  });

  if (!res.ok) {
    let message = `API error: ${res.status}`;
    try { const b = await res.json(); if (b?.detail) message = b.detail; } catch { /* ignore */ }
    throw new Error(message);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try { yield JSON.parse(line.slice(6)); } catch { /* skip malformed */ }
      }
    }
  }
}

export const api = {
  mitre:        (q, k) => query("/api/mitre_query",  q, k),
  cert:         (q, k) => query("/api/cert_query",   q, k),
  threat:       (q, k) => query("/api/threat_query", q, k),
  chat:         (q, k, uploadIds, history) => query("/api/chat", q, k, uploadIds, history),
  chatStream,
  uploadFile,
  deleteUpload,
};
