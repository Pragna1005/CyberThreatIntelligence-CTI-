"""
Central Prometheus metrics registry for the CTI Bot.
Import from here so metrics are defined once and never double-registered.
"""

from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter(
    "cti_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "cti_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

RAG_LATENCY = Histogram(
    "cti_rag_duration_seconds",
    "End-to-end RAG pipeline duration in seconds",
    ["source_filter"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0],
)

LLM_LATENCY = Histogram(
    "cti_llm_duration_seconds",
    "Ollama LLM generation duration in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0],
)

CHUNKS_RETRIEVED = Histogram(
    "cti_chunks_retrieved",
    "Number of chunks retrieved per RAG query",
    buckets=[1, 2, 3, 5, 8, 10, 15, 20],
)

HALLUCINATION_SCORE = Histogram(
    "cti_hallucination_score",
    "Faithfulness score per answer (1.0=fully grounded, 0.0=hallucinated)",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

ADVISORY_FRESHNESS_HOURS = Gauge(
    "cti_advisory_freshness_hours",
    "Hours elapsed since last successful ingestion run",
)

INGESTION_DURATION = Histogram(
    "cti_ingestion_duration_seconds",
    "Total duration of a full ingestion run",
    buckets=[10, 30, 60, 120, 300, 600, 1800],
)

INGESTION_CHUNKS = Counter(
    "cti_ingestion_chunks_total",
    "Total chunks ingested, by source file",
    ["source_file"],
)
