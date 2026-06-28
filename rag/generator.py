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

from rag.retriever import RetrievedChunk, retrieve, retrieve_from_uploads

load_dotenv(find_dotenv(usecwd=True))

LLM_MODEL   = os.environ.get("OLLAMA_MODEL", "qwen:7b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MAX_TOKENS  = 4096
TEMPERATURE = 0.2          # low temp = more factual, less creative

SYSTEM_PROMPT = """You are a Cyber Defence Threat Intelligence assistant.
You answer questions about cybersecurity threats, attack techniques, malware, \
vulnerabilities, and indicators of compromise (IOCs).

Rules:
1. Answer using ONLY the provided context. Do not use outside knowledge.
2. The context contains structured intelligence records. Use ALL of them to build your answer.
3. For IOC records: list the IOC value, type, malware family, confidence, and reference URL.
4. For CVE/vulnerability records: summarize the CVE ID, affected product, severity, and advisory URL.
5. For MITRE technique records: explain the technique and how it is used.
6. Always cite the chunk ID when referencing a record.
7. Only say "I don't have enough information" if the context contains zero records.
8. End with a "Sources:" section listing the chunk IDs used."""


def _extract_url(chunk: RetrievedChunk) -> str:
    """Pull a URL from chunk metadata regardless of source type."""
    for key in ("url", "reference"):
        val = chunk.metadata.get(key)
        if val and isinstance(val, str):
            return val
    return ""


def _format_chunk_text(chunk: RetrievedChunk) -> str:
    """Convert raw chunk metadata into a readable bullet-point block for the LLM."""
    m = chunk.metadata
    url = _extract_url(chunk)

    if chunk.source == "ThreatFox":
        lines = [
            f"  - IOC Value: {m.get('ioc_value', 'N/A')}",
            f"  - Type: {m.get('ioc_type', 'N/A')}",
            f"  - Malware Family: {m.get('malware', 'Unknown')}",
            f"  - Threat Type: {m.get('threat_type', 'N/A')}",
            f"  - Confidence: {m.get('confidence_level', 'N/A')}%",
            f"  - First Seen: {m.get('first_seen_utc', 'N/A')}",
        ]
        tags = m.get("tags") or []
        if tags:
            lines.append(f"  - Tags: {', '.join(str(t) for t in tags)}")
        if url:
            lines.append(f"  - Reference URL: {url}")
        return "\n".join(lines)

    if chunk.source == "MSRC":
        lines = [
            f"  - CVE ID: {m.get('cve_id', 'N/A')}",
            f"  - Product: {m.get('product', 'N/A')}",
            f"  - Severity: {m.get('severity', 'N/A')} (score: {m.get('base_score', 'N/A')})",
            f"  - Exploitability: {m.get('exploitability', 'N/A')}",
            f"  - Mitigation Available: {'Yes' if m.get('has_mitigation') else 'No'}",
            f"  - Workaround Available: {'Yes' if m.get('has_workaround') else 'No'}",
        ]
        if m.get("cvss_vector"):
            lines.append(f"  - CVSS Vector: {m['cvss_vector']}")
        if url:
            lines.append(f"  - Advisory URL: {url}")
        return "\n".join(lines)

    # MITRE or uploaded docs — use the raw text as-is
    return chunk.text


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[{i}] Source: {chunk.source} | ID: {chunk.chunk_id}")
        lines.append(_format_chunk_text(chunk))
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
    upload_ids: list[str] | None = None,
) -> RAGResponse:
    """
    Full RAG pipeline: retrieve → augment → generate.

    When upload_ids are provided, chunks from those specific documents are
    fetched separately and merged into the context so the LLM always sees
    the uploaded content — even when the query phrasing ("explain the pdf")
    has low semantic similarity to the document text.
    """
    # Retrieve from the general knowledge base
    kb_chunks = retrieve(query, top_k=top_k, source_filter=source_filter)

    # Retrieve from the user's uploaded documents (bypasses semantic mismatch)
    upload_chunks: list[RetrievedChunk] = []
    if upload_ids:
        upload_chunks = retrieve_from_uploads(query, upload_ids, top_k_per_upload=3)

    # Merge: upload chunks go first so the LLM sees them prominently
    seen_ids: set[str] = set()
    chunks: list[RetrievedChunk] = []
    for c in upload_chunks + kb_chunks:
        if c.chunk_id not in seen_ids:
            seen_ids.add(c.chunk_id)
            chunks.append(c)

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
        timeout=300,
    )
    if not response.ok:
        raise requests.HTTPError(
            f"Ollama returned {response.status_code}: {response.text[:300]}",
            response=response,
        )
    answer = response.json().get("response", "").strip()

    sources = [
        {
            "chunk_id":     c.chunk_id,
            "source":       c.source,
            "score":        c.score,
            "text_preview": c.text[:120],
            "url":          _extract_url(c),
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
