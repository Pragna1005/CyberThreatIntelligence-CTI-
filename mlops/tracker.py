"""
MLflow tracking utilities for ingestion runs and RAG queries.
All calls are wrapped in try/except so a downed MLflow server never
breaks the actual pipeline.
"""

import os
from contextlib import contextmanager

MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
EXPERIMENT_INGESTION = "cti-ingestion"
EXPERIMENT_RAG = "cti-rag-queries"


def _get_mlflow():
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_URI)
        return mlflow
    except Exception:
        return None


@contextmanager
def ingestion_run(embedding_model: str, batch_size: int, collection: str):
    """Context manager that wraps a full ingestion run as an MLflow run."""
    mlflow = _get_mlflow()
    if mlflow is None:
        yield {}
        return

    try:
        mlflow.set_experiment(EXPERIMENT_INGESTION)
        with mlflow.start_run(run_name="ingestion") as run:
            mlflow.log_params({
                "embedding_model": embedding_model,
                "batch_size": batch_size,
                "collection": collection,
            })
            metrics: dict = {}
            yield metrics
            if metrics:
                mlflow.log_metrics(metrics)
    except Exception:
        yield {}


def log_rag_query(
    query: str,
    model: str,
    top_k: int,
    source_filter: str | None,
    latency_s: float,
    chunks_count: int,
    hallucination_score: float | None = None,
) -> None:
    """Log a single RAG query result to MLflow. Fires-and-forgets; never raises."""
    mlflow = _get_mlflow()
    if mlflow is None:
        return

    try:
        mlflow.set_experiment(EXPERIMENT_RAG)
        with mlflow.start_run(run_name="rag_query"):
            mlflow.log_params({
                "model": model,
                "top_k": top_k,
                "source_filter": source_filter or "all",
            })
            metrics = {
                "latency_seconds": round(latency_s, 3),
                "chunks_retrieved": chunks_count,
            }
            if hallucination_score is not None:
                metrics["hallucination_score"] = round(hallucination_score, 3)
            mlflow.log_metrics(metrics)
            mlflow.log_text(query[:500], "query.txt")
    except Exception:
        pass
