# CyberThreatIntelligence-CTI-

A RAG-powered (Retrieval-Augmented Generation) Cyber Defence Threat Intelligence chatbot. It lets security analysts ask natural language questions about cybersecurity threats and get grounded, cited answers pulled from three intelligence sources. The system runs entirely locally using open-source tools — no cloud LLM API costs.

---

## Architecture Overview

```
User (Browser)
     ↓
  Frontend  (React + Vite + Tailwind)
     ↓  HTTP / SSE
  Backend   (FastAPI + Python)
     ↓            ↓
  Qdrant       Ollama
(Vector DB)   (Local LLM)
     ↑
  Embedding Model (BAAI/bge-small-en-v1.5)
     ↑
  Three Knowledge Sources:
    - MITRE ATT&CK
    - ThreatFox IOCs
    - MSRC Security Advisories
```

---

## Data Sources (The Knowledge Base)

Located in `json_data/` and processed into `chunks/`:

### 1. MITRE ATT&CK (`mitre_rag_documents.jsonl`)
- The industry-standard framework of adversary **tactics, techniques, and sub-techniques** (e.g., T1566 - Phishing, T1055 - Process Injection).
- Used to answer: *"What techniques are used in ransomware attacks?"*

### 2. ThreatFox (`threatfox_sample.jsonl`)
- Live **Indicators of Compromise (IOCs)** — malicious IPs, URLs, domains, file hashes.
- Each record has: IOC value, type (ip:port, url, domain, sha256), malware family, confidence level, tags.
- Used to answer: *"Show me Emotet malware indicators"*

### 3. MSRC Security Updates (`security_updates.jsonl`)
- **Microsoft Security Response Center** CVE advisories — CVE IDs, affected products, CVSS scores, exploitability, mitigation availability.
- Used to answer: *"What are critical Windows vulnerabilities?"*

---

## Data Pipeline

### Step 1 — Chunking (`scripts/chunker.py`)
Converts raw JSONL records into uniform chunk objects. Each chunk has:
- `chunk_id` — unique identifier (e.g., `mitre_T1566_0`)
- `source` — "MITRE", "ThreatFox", or "MSRC"
- `text` — human-readable sentence built from the record fields (what gets embedded)
- `metadata` — structured fields for filtering and display

Strategy:
- MITRE docs: split by 400 words with 50-word overlap if long
- ThreatFox & MSRC: one record = one chunk (already atomic)

### Step 2 — Ingestion (`scripts/ingest.py`)
Reads chunk files, generates vector embeddings using **BAAI/bge-small-en-v1.5**, and upserts into **Qdrant**:
- Point IDs are **deterministic** (MD5 of chunk_id) — re-running is safe/idempotent
- Payload indexes created on `source`, `ioc_type`, `severity`, `malware`, `technique_id` for fast filtered search
- After ingestion, writes a **freshness timestamp** to `mlops/last_ingested.json`

---

## Backend (`backend/`)

Built with **FastAPI** (`backend/main.py`). Exposes these API endpoints:

| Endpoint | Description |
|---|---|
| `POST /api/mitre_query` | Query MITRE ATT&CK techniques only |
| `POST /api/cert_query` | Query MSRC/CERT advisories only |
| `POST /api/threat_query` | Query ThreatFox IOCs only |
| `POST /api/chat` | Unified search across ALL sources |
| `POST /api/chat/stream` | Same but streams tokens via SSE |
| `POST /api/upload` | Upload a PDF/DOCX/TXT for ad-hoc querying |
| `DELETE /api/upload/{id}` | Remove an uploaded document |
| `GET /api/uploads` | List indexed uploads |
| `GET /metrics` | Prometheus metrics scrape endpoint |

### Routers
- `backend/routers/mitre.py` — MITRE-only queries
- `backend/routers/cert.py` — MSRC-only queries
- `backend/routers/threats.py` — ThreatFox-only queries
- `backend/routers/chat.py` — Unified chat (supports conversation history + streaming SSE)
- `backend/routers/upload.py` — File upload → auto-chunked → embedded → stored in Qdrant

---

## RAG Pipeline (`rag/`)

### Retriever (`rag/retriever.py`)

**Embedding model**: `BAAI/bge-small-en-v1.5` (384-dimensional vectors, cosine similarity)

BGE models require a special **query prefix** at query time (not at ingestion time):
> *"Represent this sentence for searching relevant passages: [your question]"*

Key functions:
- `retrieve()` — embeds query, searches Qdrant, returns top-K chunks. Supports `source_filter` to restrict to one data source.
- `retrieve_from_uploads()` — retrieves chunks from user-uploaded docs using `upload_id` filter.
- `retrieve_by_cve_id()` — exact CVE ID lookup via Qdrant scroll (bypasses semantic search for precision).
- `encode_query()` — encodes once and reuses across multiple retrieve calls.

### Generator (`rag/generator.py`)

The full RAG pipeline — retrieve → augment → generate:

1. **Multi-source retrieval**: runs all retrieval paths in sequence:
   - URL detection → fetches web page content if a URL is in the query
   - CVE ID extraction → direct KB lookup if a CVE URL is present
   - Upload retrieval → user-uploaded doc chunks
   - Standard vector search → KB chunks

2. **Prompt construction**: formats chunks into a numbered `CONTEXT` block with a strict system prompt instructing the LLM to cite chunk IDs and stay grounded. Two system prompts exist:
   - `SYSTEM_PROMPT` — the standard CTI assistant (11 rules)
   - `DOCUMENT_SYSTEM_PROMPT` — simpler prompt for "explain the PDF" queries (works better for small models)

3. **Refusal detection**: if the LLM refuses to answer despite having context, it falls back to directly showing the chunk text.

4. **Streaming**: `stream_generate()` streams Ollama tokens as Server-Sent Events for live token-by-token output.

**LLM**: `Ollama` running `qwen2.5:3b` locally (configurable via `OLLAMA_MODEL` env var).

---

## File Upload Feature

Users can upload **PDF, DOCX, or TXT** files at runtime:
- Extracted → word-chunked (400 words, 50-word overlap) → embedded → upserted into Qdrant under `source = "UserUpload"` with a unique `upload_id`
- Immediately searchable in all RAG queries
- Can be deleted via `DELETE /api/upload/{id}`
- Special detection logic handles *"explain this PDF"*-style queries

---

## Frontend (`frontend/`)

Built with **React 19 + Vite + Tailwind CSS**.

### Pages
- `ChatPage.jsx` — Unified chatbot with conversation history, streaming output, file upload
- `MitrePage.jsx` — MITRE ATT&CK-only queries
- `ThreatPage.jsx` — ThreatFox IOC queries
- `CertPage.jsx` — MSRC/CERT advisory queries

### Components
- `Navbar.jsx` — Navigation
- `SearchBar.jsx` — Input with submit
- `ResultCard.jsx` — Displays answers with source citations (renders Markdown via `react-markdown`)
- `SourceBadge.jsx` — Color-coded badges for MITRE / ThreatFox / MSRC / UserUpload sources

---

## MLOps (`mlops/`)

### MLflow Tracking (`mlops/tracker.py`)
Every RAG query is logged to **MLflow** with:
- Parameters: model name, top_k, source_filter
- Metrics: latency (seconds), chunks retrieved, hallucination score
- Artifacts: the query text

Two experiments: `cti-ingestion` (ingestion runs) and `cti-rag-queries` (every chat query).

### Hallucination Scorer (`mlops/hallucination_scorer.py`)
After every answer, a second Ollama call evaluates **faithfulness** — does the answer stay grounded in the retrieved context? Returns a score 0.0 (hallucinated) to 1.0 (fully grounded). Disabled by default; set `HALLUCINATION_SCORING=true` to enable.

### Freshness Monitor (`mlops/freshness_check.py`)
After ingestion, a timestamp is written. At startup, the backend checks how many hours ago the KB was last updated and publishes it as a Prometheus gauge (`cti_advisory_freshness_hours`). Run with `--alert` flag in CI to fail if the KB is stale.

---

## Monitoring (`monitoring/`)

### Prometheus Metrics (`backend/metrics.py`)

The backend exposes `/metrics` with these custom metrics:

| Metric | Type | What it tracks |
|---|---|---|
| `cti_http_requests_total` | Counter | Every HTTP request by method, endpoint, status |
| `cti_http_request_duration_seconds` | Histogram | API response time |
| `cti_rag_duration_seconds` | Histogram | End-to-end RAG pipeline time |
| `cti_llm_duration_seconds` | Histogram | Ollama generation time alone |
| `cti_chunks_retrieved` | Histogram | How many chunks returned per query |
| `cti_hallucination_score` | Histogram | Faithfulness score distribution |
| `cti_advisory_freshness_hours` | Gauge | Hours since last KB ingestion |

### Grafana
Pre-provisioned dashboards in `monitoring/grafana/` visualize all Prometheus metrics.

---

## Infrastructure / Deployment (`docker-compose.yml`)

The entire stack runs via `docker compose up`:

| Service | Image | Port | Role |
|---|---|---|---|
| `qdrant` | `qdrant/qdrant` | 6333/6334 | Vector database |
| `ollama` | `ollama/ollama` | 11434 | Local LLM server (auto-pulls qwen2.5:3b) |
| `backend` | Custom Dockerfile | 8000 | FastAPI app |
| `prometheus` | `prom/prometheus` | 9090 | Metrics scraping |
| `grafana` | `grafana/grafana` | 3001 | Dashboards |
| `mlflow` | `ghcr.io/mlflow/mlflow` | 5000 | Experiment tracking |

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM** | Ollama + qwen2.5:3b | Local inference, no cloud API |
| **Embeddings** | BAAI/bge-small-en-v1.5 via sentence-transformers | 384-dim dense vectors |
| **Vector DB** | Qdrant | Semantic similarity search + metadata filtering |
| **Backend** | FastAPI + Uvicorn | REST API + SSE streaming |
| **Frontend** | React 19 + Vite + Tailwind | Chat UI |
| **Monitoring** | Prometheus + Grafana | Real-time metrics dashboards |
| **Experiment Tracking** | MLflow | Log every query's latency and scores |
| **Containerization** | Docker + Docker Compose | One-command deployment |
| **Data Parsing** | pypdf, python-docx | File upload text extraction |

---

## Data Flow for a Single Query

```
User types: "What techniques does APT29 use for phishing?"
       ↓
ChatPage.jsx  →  POST /api/chat/stream
       ↓
chat.py router  →  stream_generate()
       ↓
generator.py:
  1. encode_query()        — embed the question once
  2. _fetch_query_urls()   — no URLs in query, skip
  3. retrieve()            — search Qdrant, filter=None, top_k=5
     → finds MITRE chunks about T1566, T1598, etc.
  4. Build prompt          — SYSTEM_PROMPT + CONTEXT block + QUESTION
  5. POST to Ollama        — /api/generate (stream=True)
  6. Yield tokens          — SSE → frontend shows live typing
  7. After done            — score hallucination, log to MLflow
       ↓
Browser shows: cited answer with chunk IDs as sources
```

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd CyberThreatIntelligence-CTI-

# 2. Start all services
docker compose up -d

# 3. Chunk and ingest the knowledge base (first time only)
pip install -r requirements.txt
python scripts/chunker.py
python scripts/ingest.py

# 4. Open the frontend
# http://localhost:5173  (dev)  or  http://localhost:80  (Docker)

# 5. Access supporting services
# API docs:   http://localhost:8000/docs
# MLflow:     http://localhost:5000
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001  (admin / admin)
```

See [SETUP.md](SETUP.md) for detailed setup instructions.
