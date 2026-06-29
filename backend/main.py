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

import time
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from backend.routers import mitre, cert, threats, chat, upload
from backend.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    ADVISORY_FRESHNESS_HOURS,
)
from mlops.freshness_check import read_freshness_hours

app = FastAPI(
    title="Cyber Defence Threat Intelligence Bot",
    description="RAG-powered API over MITRE ATT&CK, CERT advisories, and ThreatFox IOCs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus /metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = request.url.path
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=str(response.status_code),
    ).inc()

    return response


app.include_router(mitre.router)
app.include_router(cert.router)
app.include_router(threats.router)
app.include_router(chat.router)
app.include_router(upload.router)


@app.on_event("startup")
async def _update_freshness_gauge():
    hours = read_freshness_hours()
    if hours is not None:
        ADVISORY_FRESHNESS_HOURS.set(hours)


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


@app.exception_handler(UnexpectedResponse)
def qdrant_unexpected_handler(_: Request, exc: UnexpectedResponse):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "The vector store collection is not ready. "
                    "Upload a document or run the ingestion pipeline first."
                )
            },
        )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Qdrant error: {exc.content}"},
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
