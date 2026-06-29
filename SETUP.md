# Setup Guide

Complete instructions to get the Cyber Threat Intelligence RAG system running locally from scratch.

---

## Prerequisites

Install these before starting:

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12  | [python.org](https://www.python.org/downloads/) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| Ollama | Any | [ollama.com](https://ollama.com/) |

> **Apple Silicon Mac (M1/M2/M3):** Make sure you use a native arm64 Python, not an x86 Python running under Rosetta. The Python installer from python.org installs a universal binary that runs natively on arm64.

---

## 1. Clone the Repository

```bash
git clone <your-repo-url>
cd CyberThreatIntelligence-CTI-
```

---

## 2. Create the `.env` File

```bash
cp .env.example .env
```

Open `.env` and set it to:

```env
# Leave QDRANT_URL empty to use local file storage (no Docker needed)
QDRANT_URL=
QDRANT_API_KEY=

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b

HF_HUB_OFFLINE=1
```

> `HF_HUB_OFFLINE=1` prevents the embedding model from trying to reach HuggingFace on every startup — it uses the locally cached model instead.

---

## 3. Set Up Python Virtual Environment

**On Apple Silicon Mac:**
```bash
# Use the native arm64 Python 3.12
arch -arm64 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**On Linux / Intel Mac / Windows:**
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 4. Set Up Frontend

```bash
cd frontend
npm install
cd ..
```

---

## 5. Pull the Ollama Model

```bash
ollama pull qwen2.5:3b
```

This downloads the LLM used to generate answers (~2 GB). Only needed once.

---

## 6. Run Data Ingestion

This embeds the CTI knowledge base (MITRE ATT&CK, ThreatFox IOCs, MSRC advisories) and stores it locally.

```bash
source venv/bin/activate
python scripts/ingest.py
```

Expected output:
```
Loading embedding model: BAAI/bge-small-en-v1.5 ...
[mitre_chunks.jsonl] ...
[threatfox_chunks.jsonl] ...
[security_chunks.jsonl] ...
Ingestion complete.
  Total inserted this run : 3765
  Total points in Qdrant  : 3541
```

> Only needs to be run once. The data is saved to `./qdrant_data/`.

---

## 7. Run the Application

You need **3 terminal tabs** running simultaneously.

### Tab 1 — Ollama (LLM server)

```bash
ollama serve
```

Leave this running. You will see logs like `Listening on 127.0.0.1:11434`.

### Tab 2 — Backend (FastAPI)

```bash
cd CyberThreatIntelligence-CTI-
source venv/bin/activate
python -m uvicorn backend.main:app --reload --port 8000
```

Leave this running. You will see `Uvicorn running on http://127.0.0.1:8000`.

### Tab 3 — Frontend (React + Vite)

```bash
cd CyberThreatIntelligence-CTI-/frontend
npm run dev
```

---

## 8. Open the App

Open your browser and go to:

```
http://localhost:5173
```

The API docs (for testing endpoints directly) are at:

```
http://localhost:8000/docs
```

---

## 9. MLOps — Monitoring, Experiment Tracking & CI/CD

The project includes a full local MLOps stack. All services run via Docker Compose alongside the core app.

### Prerequisites

| Tool | Install |
|------|---------|
| Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/) |

---

### Start the Full Stack

```bash
docker compose up -d
```

This starts: Qdrant · Ollama · Backend API · Prometheus · Grafana · MLflow.

---

### Open the Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Backend API | http://localhost:8000 | — |
| Backend Metrics | http://localhost:8000/metrics | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | admin / admin |
| MLflow | http://localhost:5000 | — |

The Grafana dashboard **CTI Bot — MLOps Monitoring** is provisioned automatically on first boot. It shows:
- HTTP request rate and latency p95
- RAG pipeline duration and LLM generation duration
- Advisory freshness (hours since last ingest) with colour-coded alert thresholds
- Hallucination score trend
- Chunks retrieved per query
- Ingestion duration and chunk counts

---

### Run the Local CI/CD Pipeline Manually

```bash
./mlops/ci_local.sh
```

This runs three steps in sequence:
1. Re-ingests the latest advisories into Qdrant
2. Checks advisory freshness and reports if the knowledge base is stale
3. Runs a smoke test verifying retrieval across all three sources

**Schedule it with cron (every 6 hours):**
```bash
crontab -e
# Add this line:
0 */6 * * * /full/path/to/mlops/ci_local.sh >> ~/cti_ci.log 2>&1
```

---

### Advisory Freshness Check

After every ingestion, a timestamp is written to `mlops/last_ingested.json`. Run the freshness check standalone at any time:

```bash
python mlops/freshness_check.py          # print report
python mlops/freshness_check.py --alert  # exit code 1 if stale (> 24 h)
```

The Grafana freshness gauge turns **yellow at 12 h** and **red at 24 h** stale.

---

### Hallucination Scoring

Disabled by default to avoid extra latency. Enable it to have each RAG answer scored for faithfulness against its retrieved context (0.0 = hallucinated, 1.0 = fully grounded):

```bash
# When running the backend locally:
HALLUCINATION_SCORING=true python -m uvicorn backend.main:app --reload --port 8000

# When running via Docker Compose, add to the backend environment in docker-compose.yml:
#   HALLUCINATION_SCORING: "true"
```

Scores are recorded in Prometheus (`cti_hallucination_score`) and visible in the Grafana dashboard.

---

### MLflow Experiment Tracking

Every ingestion run and RAG query is logged to MLflow automatically.

Open http://localhost:5000 to see:
- **cti-ingestion** experiment — parameters (model, batch size), metrics (total chunks, duration), one run per ingestion
- **cti-rag-queries** experiment — parameters (model, top_k, source filter), metrics (latency, chunks retrieved, hallucination score), one run per query

---

## Architecture Overview

```
Browser (localhost:5173)
    │
    ▼
Frontend — React + Vite
    │  HTTP POST
    ▼
Backend — FastAPI (localhost:8000)
    │  exposes /metrics
    ├── Retriever → Qdrant (localhost:6333)
    │               Embedding model: BAAI/bge-small-en-v1.5
    │
    └── Generator → Ollama (localhost:11434)
                    LLM: qwen2.5:3b

MLOps Layer
    ├── Prometheus (localhost:9090) — scrapes /metrics every 15 s
    ├── Grafana    (localhost:3001) — dashboards over Prometheus data
    ├── MLflow     (localhost:5000) — ingestion + RAG experiment tracking
    └── ci_local.sh                — local CI/CD: ingest → freshness → smoke test
```

---

## Troubleshooting

**"address already in use" on port 8000:**
```bash
pkill -f "uvicorn backend.main"
```

**"address already in use" on port 11434 (Ollama):**
```bash
pkill -f "ollama"
ollama serve
```

**Frontend shows "failed to fetch":**
- Make sure the backend is running on port 8000
- Make sure Ollama is running on port 11434

**Frontend stuck on "Searching...":**
- The model is loading for the first time — wait 30–60 seconds
- Check the backend terminal for errors

**Ingestion fails with torch error (Apple Silicon):**
- Make sure you created the venv using `arch -arm64` as shown in Step 3
- The x86 Anaconda Python does not have PyTorch wheels for macOS arm64
