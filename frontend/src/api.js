const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function query(endpoint, question, topK = 5) {
  try {
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question, top_k: topK }),
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

export const api = {
  mitre:        (q, k) => query("/api/mitre_query",  q, k),
  cert:         (q, k) => query("/api/cert_query",   q, k),
  threat:       (q, k) => query("/api/threat_query", q, k),
  chat:         (q, k) => query("/api/chat",         q, k),
  uploadFile,
  deleteUpload,
};
