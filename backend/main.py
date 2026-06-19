"""
FastAPI entry point for the Cyber Defence Threat Intelligence Bot.

Endpoints:
    POST /api/mitre_query   — MITRE ATT&CK techniques only
    POST /api/cert_query    — MSRC/CERT advisories only
    POST /api/threat_query  — ThreatFox IOC/malware only
    POST /api/chat          — Unified search across all sources

Run:
    python3 -m uvicorn backend.main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs
"""

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import mitre, cert, threats, chat

app = FastAPI(
    title="Cyber Defence Threat Intelligence Bot",
    description="RAG-powered API over MITRE ATT&CK, CERT advisories, and ThreatFox IOCs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mitre.router)
app.include_router(cert.router)
app.include_router(threats.router)
app.include_router(chat.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "CTI Bot API"}
