# Setup Guide

Complete instructions to get the Cyber Threat Intelligence RAG system running locally from scratch.

---

## Prerequisites

Install these before starting:

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 (arm64 on Apple Silicon) | [python.org](https://www.python.org/downloads/) |
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

## Architecture Overview

```
Browser (localhost:5173)
    │
    ▼
Frontend — React + Vite
    │  HTTP POST
    ▼
Backend — FastAPI (localhost:8000)
    │
    ├── Retriever → Qdrant (local file: ./qdrant_data)
    │               Embedding model: BAAI/bge-small-en-v1.5
    │
    └── Generator → Ollama (localhost:11434)
                    LLM: qwen2.5:3b
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
