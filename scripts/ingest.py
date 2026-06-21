"""
Ingest: reads chunk files, generates embeddings, upserts into a local Qdrant instance.

Usage:
    python scripts/ingest.py              # ingest all chunk files
    python scripts/ingest.py --reset      # drop + recreate collection before ingesting
    python scripts/ingest.py --no-test    # skip smoke test after ingestion

Setup:
    Set these environment variables before running (or edit the .env file):
        QDRANT_URL     = http://localhost:6333
        QDRANT_API_KEY = optional for local Qdrant

Design:
    - Single local Qdrant collection: "cti_intel"
    - Embedding model: BAAI/bge-small-en-v1.5 (384 dims)
    - Distance metric: Cosine
    - Point IDs: deterministic integers derived from chunk_id (MD5 hash)
      so re-running is idempotent — same chunk always gets the same ID.
    - Full chunk stored as payload: chunk_id, source, text, metadata
"""

import argparse
import hashlib
import json
import os
import sys
import time

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

# Load .env if present
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COLLECTION_NAME = "cti_intel"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
VECTOR_DIM      = 384
BATCH_SIZE      = 64

# Read from environment — set in .env or export before running
QDRANT_URL      = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY  = os.environ.get("QDRANT_API_KEY", "")

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR      = os.path.join(BASE_DIR, "chunks")

CHUNK_FILES = [
    "mitre_chunks.jsonl",
    "threatfox_chunks.jsonl",
    "security_chunks.jsonl",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chunk_id_to_point_id(chunk_id: str) -> int:
    """Convert chunk_id string to a stable integer Qdrant point ID via MD5."""
    digest = hashlib.md5(chunk_id.encode()).hexdigest()
    return int(digest, 16) % (2 ** 53)


def batch(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Qdrant setup
# ---------------------------------------------------------------------------

def connect_qdrant():
    try:
        client_kwargs = {
            "url": QDRANT_URL,
            "timeout": 20,
        }
        if QDRANT_API_KEY:
            client_kwargs["api_key"] = QDRANT_API_KEY

        client = QdrantClient(**client_kwargs)
        client.get_collections()
        print(f"Connected to Qdrant: {QDRANT_URL}")
        return client
    except Exception as e:
        print(f"\nERROR: Could not connect to Qdrant at {QDRANT_URL} — {e}")
        print("Check that Qdrant is running (for example via docker compose up -d) and that QDRANT_URL is correct.")
        sys.exit(1)


def setup_collection(client: QdrantClient, reset: bool = False):
    from qdrant_client.models import PayloadSchemaType

    exists = any(
        c.name == COLLECTION_NAME
        for c in client.get_collections().collections
    )

    if exists and reset:
        client.delete_collection(COLLECTION_NAME)
        print(f"Dropped collection '{COLLECTION_NAME}'")
        exists = False

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection '{COLLECTION_NAME}' (dim={VECTOR_DIM}, cosine)")

        # Create payload indexes for fields used in filters
        for field, schema_type in [
            ("source",       PayloadSchemaType.KEYWORD),
            ("ioc_type",     PayloadSchemaType.KEYWORD),
            ("severity",     PayloadSchemaType.KEYWORD),
            ("malware",      PayloadSchemaType.KEYWORD),
            ("technique_id", PayloadSchemaType.KEYWORD),
        ]:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema_type,
            )
        print("  Payload indexes created: source, ioc_type, severity, malware, technique_id")
    else:
        info = client.get_collection(COLLECTION_NAME)
        print(f"Collection '{COLLECTION_NAME}' already exists "
              f"({info.points_count} points). Upserting into it.")


# ---------------------------------------------------------------------------
# Embedding + ingestion
# ---------------------------------------------------------------------------

def load_model():
    print(f"\nLoading embedding model: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Model loaded. Vector dim: {VECTOR_DIM}")
    return model


def ingest_file(client: QdrantClient, model: SentenceTransformer, filepath: str):
    chunks = read_jsonl(filepath)
    fname  = os.path.basename(filepath)
    total  = len(chunks)
    print(f"\n[{fname}] {total} chunks")

    inserted = 0
    t_start  = time.time()

    for b_idx, batch_chunks in enumerate(batch(chunks, BATCH_SIZE)):
        texts    = [c["text"] for c in batch_chunks]
        vectors  = model.encode(texts, show_progress_bar=False).tolist()

        points = [
            PointStruct(
                id=chunk_id_to_point_id(c["chunk_id"]),
                vector=vec,
                payload={
                    "chunk_id": c["chunk_id"],
                    "source":   c["source"],
                    "text":     c["text"],
                    **c["metadata"],
                },
            )
            for c, vec in zip(batch_chunks, vectors)
        ]

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        inserted += len(points)

        elapsed = time.time() - t_start
        rate    = inserted / elapsed if elapsed > 0 else 0
        print(f"  Batch {b_idx + 1:>3} | {inserted:>5}/{total} inserted "
              f"| {rate:.0f} chunks/s")

    print(f"  Done: {inserted} chunks in {time.time() - t_start:.1f}s")
    return inserted


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test(client: QdrantClient, model: SentenceTransformer):
    print("\n--- Smoke test (3 queries) ---")
    queries = [
        ("What techniques are used in phishing?",        None),
        ("Show me Emotet malware IOCs",                  "ThreatFox"),
        ("Critical Microsoft vulnerabilities with CVSS", "MSRC"),
    ]

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    for query, source_filter in queries:
        vec = model.encode([query])[0].tolist()

        search_filter = None
        if source_filter:
            search_filter = Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_filter))]
            )

        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            query_filter=search_filter,
            limit=2,
            with_payload=True,
        )

        print(f"\nQuery : {query}")
        for r in response.points:
            print(f"  [{r.score:.3f}] ({r.payload.get('source')}) "
                  f"{r.payload.get('text', '')[:100]}...")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="Drop and recreate the Qdrant collection before ingesting")
    parser.add_argument("--no-test", action="store_true",
                        help="Skip the smoke test after ingestion")
    args = parser.parse_args()

    client = connect_qdrant()
    setup_collection(client, reset=args.reset)
    model  = load_model()

    total_inserted = 0
    for fname in CHUNK_FILES:
        path = os.path.join(CHUNKS_DIR, fname)
        if not os.path.exists(path):
            print(f"\nWARNING: {fname} not found, skipping. Run chunker.py first.")
            continue
        total_inserted += ingest_file(client, model, path)

    info = client.get_collection(COLLECTION_NAME)
    print(f"\nIngestion complete.")
    print(f"  Total inserted this run : {total_inserted}")
    print(f"  Total points in Qdrant  : {info.points_count}")

    if not args.no_test:
        smoke_test(client, model)
