"""
Retriever: embeds a user query and fetches the most relevant chunks from Qdrant.

BGE models perform better with a query prefix "Represent this sentence for searching
relevant passages: " on the query side only (not during ingestion). This is applied
automatically here.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv, find_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from sentence_transformers import SentenceTransformer

load_dotenv(find_dotenv(usecwd=True))

COLLECTION_NAME = "cti_intel"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_TOP_K = 5

_model: Optional[SentenceTransformer] = None
_client: Optional[QdrantClient] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        qdrant_url = os.environ.get("QDRANT_URL", "").strip()
        api_key = os.environ.get("QDRANT_API_KEY", "").strip()
        if qdrant_url:
            client_kwargs = {"url": qdrant_url, "timeout": 20}
            if api_key:
                client_kwargs["api_key"] = api_key
            _client = QdrantClient(**client_kwargs)
        else:
            local_path = os.environ.get("QDRANT_LOCAL_PATH", "./qdrant_data")
            _client = QdrantClient(path=local_path)
    return _client


@dataclass
class RetrievedChunk:
    chunk_id:  str
    source:    str
    text:      str
    score:     float
    metadata:  dict


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source_filter: Optional[str] = None,   # "MITRE" | "ThreatFox" | "MSRC"
) -> list[RetrievedChunk]:
    """
    Embed query and return top_k most relevant chunks from Qdrant.

    Args:
        query:         Natural language question from the user.
        top_k:         Number of results to return.
        source_filter: Restrict results to one data source (optional).

    Returns:
        List of RetrievedChunk sorted by relevance score descending.
    """
    model  = _get_model()
    client = _get_client()

    prefixed_query = BGE_QUERY_PREFIX + query
    vector = model.encode(prefixed_query, normalize_embeddings=True).tolist()

    search_filter = None
    if source_filter:
        search_filter = Filter(
            must=[FieldCondition(
                key="source",
                match=MatchValue(value=source_filter),
            )]
        )

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=search_filter,
        limit=top_k,
        with_payload=True,
    )

    results = []
    for point in response.points:
        p = point.payload
        results.append(RetrievedChunk(
            chunk_id=p.get("chunk_id", ""),
            source=p.get("source", ""),
            text=p.get("text", ""),
            score=round(point.score, 4),
            metadata={k: v for k, v in p.items()
                      if k not in ("chunk_id", "source", "text")},
        ))

    return results


def retrieve_from_uploads(
    query: str,
    upload_ids: list[str],
    top_k_per_upload: int = 3,
) -> list[RetrievedChunk]:
    """
    Retrieve chunks from specific user-uploaded documents, filtered by upload_id.

    Used so that the user's uploaded file is always represented in the context
    regardless of whether the generic query semantically matches the document text
    (e.g. "explain the pdf" won't match the PDF content in a normal vector search).
    """
    if not upload_ids:
        return []

    model  = _get_model()
    client = _get_client()

    prefixed_query = BGE_QUERY_PREFIX + query
    vector = model.encode(prefixed_query, normalize_embeddings=True).tolist()

    results = []
    for uid in upload_ids:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=Filter(
                must=[FieldCondition(key="upload_id", match=MatchValue(value=uid))]
            ),
            limit=top_k_per_upload,
            with_payload=True,
        )
        for point in response.points:
            p = point.payload
            results.append(RetrievedChunk(
                chunk_id=p.get("chunk_id", ""),
                source=p.get("source", "UserUpload"),
                text=p.get("text", ""),
                score=round(point.score, 4),
                metadata={k: v for k, v in p.items()
                          if k not in ("chunk_id", "source", "text")},
            ))

    return results


if __name__ == "__main__":
    tests = [
        ("What ATT&CK techniques are used in phishing attacks?", None),
        ("Show me ClearFake malware indicators",                 "ThreatFox"),
        ("What are critical Windows vulnerabilities?",           "MSRC"),
    ]

    for query, source in tests:
        print(f"\nQuery  : {query}")
        print(f"Filter : {source or 'all sources'}")
        chunks = retrieve(query, top_k=3, source_filter=source)
        for c in chunks:
            print(f"  [{c.score}] ({c.source}) {c.text[:100]}...")
