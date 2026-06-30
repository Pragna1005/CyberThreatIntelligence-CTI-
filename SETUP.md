# Setup Guide

Complete instructions to get the Cyber Threat Intelligence RAG system running on a **brand-new machine** — Windows, macOS, or Linux — starting from `git clone`.

---

## Table of Contents

1. [Install Prerequisites](#1-install-prerequisites)
2. [Clone the Repository](#2-clone-the-repository)
3. [Configure Environment Variables](#3-configure-environment-variables)
4. [Set Up Python Virtual Environment](#4-set-up-python-virtual-environment)
5. [Set Up Frontend](#5-set-up-frontend)
6. [Pull the Ollama LLM Model](#6-pull-the-ollama-llm-model)
7. [Run Data Ingestion](#7-run-data-ingestion)
8. [Start the Application](#8-start-the-application)
9. [Open the App](#9-open-the-app)
10. [MLOps Stack (Monitoring, Tracking, CI/CD)](#10-mlops-stack-monitoring-tracking-cicd)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Install Prerequisites

You need **Python 3.12**, **Node.js 18+**, **Git**, and **Ollama** on your machine before starting.

---

### Windows

#### Install Git
1. Download from [git-scm.com](https://git-scm.com/download/win)
2. Run the installer — keep all default options
3. Verify: open **Command Prompt** or **PowerShell** and run:
   ```powershell
   git --version
   ```

#### Install Python 3.12
1. Download from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer — **check "Add Python to PATH"** at the bottom of the first screen
3. Verify:
   ```powershell
   python --version
   ```
   Expected: `Python 3.12.x`

#### Install Node.js
1. Download the LTS release from [nodejs.org](https://nodejs.org/)
2. Run the installer with default options
3. Verify:
   ```powershell
   node --version
   npm --version
   ```

#### Install Ollama
1. Download from [ollama.com/download/windows](https://ollama.com/download/windows)
2. Run the installer — Ollama installs as a system service and starts automatically
3. Verify:
   ```powershell
   ollama --version
   ```

---

### macOS

#### Install Git
Git comes pre-installed on macOS via Xcode Command Line Tools. If missing:
```bash
xcode-select --install
```
Verify:
```bash
git --version
```

#### Install Python 3.12

**Apple Silicon (M1/M2/M3/M4):**
1. Download the **macOS 64-bit universal installer** from [python.org/downloads](https://www.python.org/downloads/)
2. Run the `.pkg` installer
3. Verify that it is native arm64 (not Rosetta):
   ```bash
   python3 --version
   file $(which python3)
   # Should show: arm64 or universal
   ```

**Intel Mac:**
1. Download from [python.org/downloads](https://www.python.org/downloads/) and run the installer
2. Verify:
   ```bash
   python3 --version
   ```

> **Important (Apple Silicon):** Do NOT use an x86 Anaconda Python running under Rosetta — PyTorch wheels for macOS arm64 are not available for it and the install will fail.

#### Install Node.js
```bash
# Using Homebrew (recommended):
brew install node

# Or download the macOS installer from nodejs.org
```
Verify:
```bash
node --version
npm --version
```

If you don't have Homebrew:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
```

#### Install Ollama
```bash
# Using Homebrew:
brew install ollama

# Or download the macOS app from ollama.com and drag it to Applications
```
Verify:
```bash
ollama --version
```

---

### Linux (Ubuntu / Debian)

#### Install Git
```bash
sudo apt update
sudo apt install -y git
git --version
```

#### Install Python 3.12
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

#### Install Node.js 18+
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
npm --version
```

#### Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

---

## 2. Clone the Repository

Open a terminal (or PowerShell on Windows) and run:

```bash
git clone https://github.com/<your-username>/CyberThreatIntelligence-CTI-.git
cd CyberThreatIntelligence-CTI-
```

> Replace `<your-username>` with your actual GitHub username or the full repo URL.

---

## 3. Configure Environment Variables

### Windows (PowerShell)
```powershell
copy .env.example .env
```

### macOS / Linux
```bash
cp .env.example .env
```

Now open `.env` in any text editor and set it to:

```env
# Leave QDRANT_URL empty to use local file storage (no Docker needed for basic setup)

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b

# Prevents the embedding model from checking HuggingFace on every startup
HF_HUB_OFFLINE=1

# Set to "true" to enable per-answer hallucination scoring (adds latency)
HALLUCINATION_SCORING=false

MLFLOW_TRACKING_URI=http://localhost:5000
```

> `HF_HUB_OFFLINE=1` uses the locally cached model after the first download, avoiding network calls on every startup.

---

## 4. Set Up Python Virtual Environment

### Windows (PowerShell)
```powershell
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

> If you get a script execution policy error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### macOS — Apple Silicon (M1/M2/M3/M4)
```bash
# Use the native arm64 Python 3.12 explicitly
arch -arm64 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### macOS — Intel
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Linux
```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> Installation will take a few minutes — it downloads PyTorch, sentence-transformers, and other ML libraries.

---

## 5. Set Up Frontend

### All Platforms
```bash
cd frontend
npm install
cd ..
```

This downloads all React/Vite dependencies into `frontend/node_modules/`. Takes 1–2 minutes on first run.

---

## 6. Pull the Ollama LLM Model

This downloads `qwen2.5:3b` (~2 GB) to your local machine. Only needed once.

### Windows (PowerShell) / macOS / Linux
```bash
ollama pull qwen2.5:3b
```

Wait for it to finish downloading. Verify it's available:
```bash
ollama list
# Should show: qwen2.5:3b
```

---

## 7. Run Data Ingestion

This embeds the CTI knowledge base (MITRE ATT&CK, ThreatFox IOCs, MSRC advisories) into the local vector database.

Make sure your virtual environment is active first.

### Windows (PowerShell)
```powershell
venv\Scripts\activate
python scripts\chunker.py
python scripts\ingest.py
```

### macOS / Linux
```bash
source venv/bin/activate
python scripts/chunker.py
python scripts/ingest.py
```

Expected output for `ingest.py`:
```
Connected to Qdrant: (local file storage)
Created collection 'cti_intel' (dim=384, cosine)
Loading embedding model: BAAI/bge-small-en-v1.5 ...

[mitre_chunks.jsonl]    ... chunks
[threatfox_chunks.jsonl] ... chunks
[security_chunks.jsonl]  ... chunks

Ingestion complete.
  Total inserted this run : 3765
  Total points in Qdrant  : 3765
```

> This only needs to be run once. The data is saved to `./qdrant_data/` locally. Re-run if you update the source data.

---

## 8. Start the Application

You need **3 terminal windows/tabs** open at the same time.

---

### Terminal 1 — Start Ollama (LLM Server)

#### Windows
Ollama runs as a background service automatically after installation.
If it's not running, open the Ollama app from the Start menu, or:
```powershell
ollama serve
```

#### macOS / Linux
```bash
ollama serve
```

Leave this running. You'll see: `Listening on 127.0.0.1:11434`

---

### Terminal 2 — Start Backend (FastAPI)

#### Windows (PowerShell)
```powershell
cd CyberThreatIntelligence-CTI-
venv\Scripts\activate
python -m uvicorn backend.main:app --reload --port 8000
```

#### macOS / Linux
```bash
cd CyberThreatIntelligence-CTI-
source venv/bin/activate
python -m uvicorn backend.main:app --reload --port 8000
```

Leave this running. You'll see: `Uvicorn running on http://127.0.0.1:8000`

---

### Terminal 3 — Start Frontend (React + Vite)

#### Windows (PowerShell)
```powershell
cd CyberThreatIntelligence-CTI-\frontend
npm run dev
```

#### macOS / Linux
```bash
cd CyberThreatIntelligence-CTI-/frontend
npm run dev
```

You'll see: `Local: http://localhost:5173/`

---

## 9. Open the App

Once all three terminals are running, open your browser:

| What | URL |
|------|-----|
| **CTI Chatbot UI** | http://localhost:5173 |
| **API Interactive Docs** | http://localhost:8000/docs |
| **Raw API** | http://localhost:8000 |

The first query after startup will take 20–60 seconds while the embedding model and LLM load into memory. Subsequent queries are much faster.

---

## 10. MLOps Stack (Monitoring, Tracking, CI/CD)

The project includes Prometheus, Grafana, and MLflow for observability. These run via **Docker Compose** alongside the core application.

### Install Docker

#### Windows
Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
After install, make sure Docker Desktop is running (check the system tray icon).

#### macOS
```bash
brew install --cask docker
```
Or download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) and drag it to Applications.
Open Docker Desktop and wait for it to start.

#### Linux (Ubuntu / Debian)
```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

Verify Docker is working:
```bash
docker --version
docker compose version
```

---

### Start the Full MLOps Stack

From the project root:

```bash
docker compose up -d
```

This starts: **Qdrant · Ollama · Backend API · Prometheus · Grafana · MLflow** as containers.

> First run will pull all Docker images (~3–5 GB total) and download the Ollama model inside the container. This can take 5–15 minutes depending on your connection.

Check that all containers are running:
```bash
docker compose ps
```

All services should show `Up` or `healthy`.

---

### When using Docker Compose — Re-run Ingestion

Since Qdrant now runs inside Docker (not local file storage), re-run ingestion pointing at the Docker Qdrant:

```bash
# Make sure your .env has:
# QDRANT_URL=http://localhost:6333

source venv/bin/activate          # Windows: venv\Scripts\activate
python scripts/chunker.py
python scripts/ingest.py
```

---

### Access the Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| CTI Bot API | http://localhost:8000 | — |
| API Docs | http://localhost:8000/docs | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | admin / admin |
| MLflow | http://localhost:5000 | — |

The **Grafana dashboard "CTI Bot — MLOps Monitoring"** is provisioned automatically on first boot. It shows:
- HTTP request rate and latency p95
- RAG pipeline duration and LLM generation duration
- Advisory freshness (hours since last ingest) with colour-coded alert thresholds
- Hallucination score trend
- Chunks retrieved per query
- Ingestion duration and chunk counts

---

### Run the Local CI/CD Pipeline

```bash
# macOS / Linux:
./mlops/ci_local.sh

# Windows (Git Bash or WSL):
bash mlops/ci_local.sh
```

This runs three steps in sequence:
1. Re-ingests the latest advisories into Qdrant
2. Checks advisory freshness and reports if the knowledge base is stale
3. Runs a smoke test verifying retrieval across all three sources

**Schedule it with cron (every 6 hours) on macOS/Linux:**
```bash
crontab -e
# Add this line (update the path to your actual project location):
0 */6 * * * /full/path/to/mlops/ci_local.sh >> ~/cti_ci.log 2>&1
```

**Schedule it on Windows (Task Scheduler):**
1. Open **Task Scheduler** → Create Basic Task
2. Set trigger: Daily, repeat every 6 hours
3. Action: Start a program → `bash` → Arguments: `/full/path/to/mlops/ci_local.sh`

---

### Advisory Freshness Check

```bash
python mlops/freshness_check.py          # print report
python mlops/freshness_check.py --alert  # exit code 1 if stale (> 24 h)
```

The Grafana freshness gauge turns **yellow at 12 h** and **red at 24 h** stale.

---

### Enable Hallucination Scoring

Disabled by default to avoid extra latency. Enable to have each answer scored for faithfulness (0.0 = hallucinated, 1.0 = fully grounded):

**Local run:**
```bash
# macOS / Linux:
HALLUCINATION_SCORING=true python -m uvicorn backend.main:app --reload --port 8000

# Windows PowerShell:
$env:HALLUCINATION_SCORING="true"
python -m uvicorn backend.main:app --reload --port 8000
```

**Docker Compose:** edit `docker-compose.yml`, find the `backend` service environment block, and set:
```yaml
- HALLUCINATION_SCORING=true
```
Then restart: `docker compose up -d backend`

---

### MLflow Experiment Tracking

Open http://localhost:5000 to see:
- **cti-ingestion** — parameters (model, batch size), metrics (total chunks, duration), one run per ingestion
- **cti-rag-queries** — parameters (model, top_k, source filter), metrics (latency, chunks retrieved, hallucination score), one run per query

---

### Stop All Docker Services

```bash
docker compose down
```

To also delete all stored data (Qdrant vectors, MLflow runs, Grafana settings):
```bash
docker compose down -v
```

---

## 11. Troubleshooting

### Common Issues — All Platforms

**"address already in use" on port 8000:**
```bash
# macOS / Linux:
pkill -f "uvicorn backend.main"

# Windows PowerShell:
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**"address already in use" on port 11434 (Ollama):**
```bash
# macOS / Linux:
pkill ollama
ollama serve

# Windows: open Task Manager → find ollama.exe → End Task → restart Ollama
```

**Frontend shows "failed to fetch" or "network error":**
- Confirm the backend is running on port 8000
- Confirm Ollama is running on port 11434
- Check that CORS is not blocked (the backend allows all origins by default)

**First query takes 60+ seconds:**
- Normal — the LLM and embedding model are loading into memory for the first time
- Subsequent queries will be much faster

**"I don't have enough information" on every query:**
- The vector database has no data — run ingestion (Step 7)
- If using Docker Compose, make sure `QDRANT_URL=http://localhost:6333` in `.env` and re-run ingestion

---

### Windows-Specific

**`pip install` fails with "Microsoft Visual C++ required":**
```powershell
# Install Visual C++ Build Tools:
winget install Microsoft.VisualStudio.2022.BuildTools
# Or download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

**`venv\Scripts\activate` gives "cannot be loaded because running scripts is disabled":**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Ollama not found after install:**
- Restart PowerShell/Command Prompt after installing Ollama
- Or add `C:\Users\<YourUser>\AppData\Local\Programs\Ollama` to your PATH

**`npm run dev` fails with EACCES or permission error:**
- Run PowerShell as Administrator, or
- Delete `frontend/node_modules` and re-run `npm install`

---

### macOS-Specific

**`pip install` fails with "torch" error on Apple Silicon:**
- Make sure you created the venv using `arch -arm64` as shown in Step 4
- The x86 Anaconda/Miniconda Python does not have PyTorch arm64 wheels

**Ollama service not running:**
```bash
# If installed via Homebrew:
brew services start ollama

# If installed via the .app:
open /Applications/Ollama.app
```

**`npm: command not found`:**
```bash
brew install node
```

---

### Linux-Specific

**`python3.12` not found:**
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv
```

**`ollama: command not found` after install:**
```bash
source ~/.bashrc
# Or restart your terminal
```

**Docker permission denied:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**Port 8000 or 11434 blocked by firewall:**
```bash
sudo ufw allow 8000
sudo ufw allow 11434
```

---

## Architecture Reference

```
Browser (localhost:5173)
    │
    ▼
Frontend — React + Vite + Tailwind
    │  HTTP POST / Server-Sent Events
    ▼
Backend — FastAPI (localhost:8000)
    │  exposes /metrics
    ├── Retriever ──► Qdrant (localhost:6333 or ./qdrant_data/)
    │                 Embedding: BAAI/bge-small-en-v1.5 (384 dims)
    │
    └── Generator ──► Ollama (localhost:11434)
                      LLM: qwen2.5:3b

MLOps Layer
    ├── Prometheus (localhost:9090)  — scrapes /metrics every 15 s
    ├── Grafana    (localhost:3001)  — dashboards over Prometheus data
    ├── MLflow     (localhost:5000)  — ingestion + RAG query tracking
    └── ci_local.sh                 — local CI: ingest → freshness → smoke test
```
