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
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from qdrant_client.http.exceptions import ResponseHandlingException

from backend.routers import mitre, cert, threats, chat, upload

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
app.include_router(upload.router)


@app.exception_handler(ResponseHandlingException)
def qdrant_unavailable_handler(_: Request, exc: ResponseHandlingException):
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Qdrant is unavailable. Start the vector database or set QDRANT_URL "
                "to a running instance."
            )
        },
    )


@app.exception_handler(requests.RequestException)
def ollama_unavailable_handler(_: Request, exc: requests.RequestException):
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The answer generation service is unavailable. Start Ollama or set "
                "OLLAMA_BASE_URL to a running instance."
            )
        },
    )


@app.get("/")
def health():
    return {"status": "ok", "service": "CTI Bot API"}
