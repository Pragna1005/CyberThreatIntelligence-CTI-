"""
Generator: builds a grounded prompt from retrieved chunks and calls a local
Ollama model to produce a cited answer.

The prompt strictly instructs the model to:
  - Answer only from the provided context
  - Cite every source by chunk_id / technique_id / CVE / IOC
  - Say "I don't have enough information" if context is insufficient
"""

import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv, find_dotenv

from rag.retriever import RetrievedChunk, retrieve

load_dotenv(find_dotenv(usecwd=True))

LLM_MODEL   = os.environ.get("OLLAMA_MODEL", "qwen:7b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MAX_TOKENS  = 4096
TEMPERATURE = 0.2          # low temp = more factual, less creative

SYSTEM_PROMPT = """You are a Cyber Defence Threat Intelligence assistant.
You answer questions about cybersecurity threats, attack techniques, malware, \
vulnerabilities, and indicators of compromise (IOCs).

Rules:
1. Answer ONLY using the provided context. Do not use outside knowledge.
2. Always cite your sources using the identifiers in the context \
(e.g. T1566, CVE-2026-XXXX, IOC value).
3. If the context does not contain enough information to answer, say:
   "I don't have enough information in the current knowledge base to answer this."
4. Give thorough, detailed answers. Explain context, impact, and relevant details. Use bullet points, headers, and numbered lists where appropriate.
5. Always end with a "Sources:" section listing the chunk IDs used."""


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[{i}] Source: {chunk.source} | ID: {chunk.chunk_id} | Score: {chunk.score}")
        lines.append(chunk.text)
        lines.append("")
    return "\n".join(lines)


def _build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = _build_context_block(chunks)
    return f"""CONTEXT:
{context}

QUESTION: {query}

Answer based strictly on the context above. Cite sources by their chunk ID."""


@dataclass
class RAGResponse:
    answer:   str
    sources:  list[dict]   # [{chunk_id, source, score, text_preview}]
    query:    str
    model:    str


def generate(
    query: str,
    top_k: int = 5,
    source_filter: str | None = None,
) -> RAGResponse:
    """
    Full RAG pipeline: retrieve → augment → generate.

    Args:
        query:         User's natural language question.
        top_k:         Number of chunks to retrieve.
        source_filter: Optionally restrict retrieval to one source.

    Returns:
        RAGResponse with the answer, sources used, and metadata.
    """
    chunks = retrieve(query, top_k=top_k, source_filter=source_filter)

    if not chunks:
        return RAGResponse(
            answer="I don't have enough information in the current knowledge base to answer this.",
            sources=[],
            query=query,
            model=LLM_MODEL,
        )

    prompt = f"{SYSTEM_PROMPT}\n\n{_build_user_prompt(query, chunks)}"
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": MAX_TOKENS,
                "temperature": TEMPERATURE,
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    answer = response.json().get("response", "").strip()

    sources = [
        {
            "chunk_id":     c.chunk_id,
            "source":       c.source,
            "score":        c.score,
            "text_preview": c.text[:120],
        }
        for c in chunks
    ]

    return RAGResponse(answer=answer, sources=sources, query=query, model=LLM_MODEL)


if __name__ == "__main__":
    test_queries = [
        ("What ATT&CK techniques are used in phishing attacks?",    None),
        ("What are the latest critical Windows vulnerabilities?",    "MSRC"),
        ("Show me malware families that use URL-based delivery",     "ThreatFox"),
        ("Tell me about recent phishing threats targeting Microsoft", None),
    ]

    for query, source in test_queries:
        print("=" * 70)
        print(f"Query  : {query}")
        print(f"Filter : {source or 'all sources'}")
        result = generate(query, top_k=5, source_filter=source)
        print(f"\nAnswer :\n{result.answer}")
        print(f"\nSources ({len(result.sources)}):")
        for s in result.sources:
            print(f"  [{s['score']}] ({s['source']}) {s['chunk_id']}")
        print()
