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
from qdrant_client.models import Distance, Filter, FieldCondition, MatchValue, MatchAny, VectorParams
from sentence_transformers import SentenceTransformer

load_dotenv(find_dotenv(usecwd=True))

COLLECTION_NAME = "cti_intel"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_TOP_K = 5
VECTOR_DIM = 384  # BAAI/bge-small-en-v1.5 output dimension

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
        _ensure_collection(_client)
    return _client


def _ensure_collection(client: QdrantClient) -> None:
    """Create the Qdrant collection if it does not already exist."""
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )


@dataclass
class RetrievedChunk:
    chunk_id:  str
    source:    str
    text:      str
    score:     float
    metadata:  dict


def encode_query(query: str) -> list[float]:
    """Embed a query string once; pass the result to retrieve/retrieve_from_uploads to avoid re-encoding."""
    return _get_model().encode(BGE_QUERY_PREFIX + query, normalize_embeddings=True).tolist()


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source_filter: Optional[str] = None,   # "MITRE" | "ThreatFox" | "MSRC"
    vector: Optional[list[float]] = None,  # pre-computed embedding; computed here if None
) -> list[RetrievedChunk]:
    """
    Embed query and return top_k most relevant chunks from Qdrant.

    Args:
        query:         Natural language question from the user.
        top_k:         Number of results to return.
        source_filter: Restrict results to one data source (optional).
        vector:        Pre-computed query embedding (avoids re-encoding when reusing same query).

    Returns:
        List of RetrievedChunk sorted by relevance score descending.
    """
    client = _get_client()

    if vector is None:
        vector = encode_query(query)

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
    vector: Optional[list[float]] = None,  # pre-computed embedding; computed here if None
) -> list[RetrievedChunk]:
    """
    Retrieve chunks from specific user-uploaded documents, filtered by upload_id.

    Used so that the user's uploaded file is always represented in the context
    regardless of whether the generic query semantically matches the document text
    (e.g. "explain the pdf" won't match the PDF content in a normal vector search).
    """
    if not upload_ids:
        return []

    client = _get_client()

    if vector is None:
        vector = encode_query(query)

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


def retrieve_by_cve_id(cve_id: str) -> list[RetrievedChunk]:
    """
    Return all chunks whose `cve_id` payload field exactly matches *cve_id*.
    Used to look up a specific CVE directly rather than relying on semantic search,
    which would return similar-but-wrong CVEs when the user provides an MSRC URL.
    """
    client = _get_client()
    records, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="cve_id", match=MatchValue(value=cve_id.upper()))]
        ),
        limit=10,
        with_payload=True,
    )
    results = []
    for point in records:
        p = point.payload
        results.append(RetrievedChunk(
            chunk_id=p.get("chunk_id", ""),
            source=p.get("source", ""),
            text=p.get("text", ""),
            score=1.0,
            metadata={k: v for k, v in p.items() if k not in ("chunk_id", "source", "text")},
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
