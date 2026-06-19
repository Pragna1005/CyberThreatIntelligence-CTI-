const BASE_URL = "http://localhost:8000";

async function query(endpoint, question, topK = 5) {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: question, top_k: topK }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  mitre:  (q, k) => query("/api/mitre_query",  q, k),
  cert:   (q, k) => query("/api/cert_query",   q, k),
  threat: (q, k) => query("/api/threat_query", q, k),
  chat:   (q, k) => query("/api/chat",         q, k),
};
