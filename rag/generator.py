"""
Generator: builds a grounded prompt from retrieved chunks and calls a local
Ollama model to produce a cited answer.

The prompt strictly instructs the model to:
  - Answer only from the provided context
  - Cite every source by chunk_id / technique_id / CVE / IOC
  - Say "I don't have enough information" if context is insufficient
"""

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv, find_dotenv

from rag.retriever import RetrievedChunk, retrieve, retrieve_from_uploads, retrieve_by_cve_id, encode_query
from backend.metrics import (
    RAG_LATENCY,
    LLM_LATENCY,
    CHUNKS_RETRIEVED,
    HALLUCINATION_SCORE,
)
from mlops import hallucination_scorer
from mlops.tracker import log_rag_query

load_dotenv(find_dotenv(usecwd=True))

LLM_MODEL       = os.environ.get("OLLAMA_MODEL", "qwen:7b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MAX_TOKENS      = 1024   # 4096 was the bottleneck; 1024 covers all CTI answers
TEMPERATURE     = 0.2

SYSTEM_PROMPT = """You are a Cyber Defence Threat Intelligence assistant.
You answer questions about cybersecurity threats, attack techniques, malware, \
vulnerabilities, and indicators of compromise (IOCs).

Rules:
1. Ground your answers in the provided CONTEXT records. For follow-up questions that refer to \
something you said earlier (e.g. "explain the first point", "what did you mean by that?"), \
you may also draw on the CONVERSATION HISTORY shown below — but always prefer the retrieved \
context for facts.
2. The context contains structured intelligence records. Use ALL of them to build your answer.
3. For IOC records: list the IOC value, type, malware family, confidence, and reference URL.
4. For CVE/vulnerability records: summarize the CVE ID, affected product, severity, and advisory URL.
5. For MITRE technique records: explain the technique and how it is used.
6. Always cite the chunk ID when referencing a record.
7. Only say "I don't have enough information" if the context contains zero records AND there is \
nothing relevant in the conversation history either.
8. End with a "Sources:" section listing the chunk IDs used (omit if answering purely from history).
9. If the user asks you to explain, summarize, describe, or tell them about an uploaded document \
or PDF, use ALL the provided context chunks to write a comprehensive explanation — never say you \
lack information when context records are present.
10. If the context includes web page content (Source: WebFetch), read that content carefully and \
use it to answer whatever the user is asking about that URL — summarize, extract facts, or answer \
specific questions as needed.
11. Be conversational and helpful. If the user asks a clarifying or follow-up question, engage \
naturally — you don't need to repeat retrieved context they already saw unless it helps."""

# Patterns that indicate the user is asking about an uploaded document in general terms
_DOC_META_RE = re.compile(
    r"(explain|summarize|summarise|describe|overview|tell me about|what (is|does|are)|"
    r"what('s| is) in|give me|show me|read).{0,40}"
    r"(the\s+)?(pdf|document|doc|file|uploaded|attachment|content)",
    re.IGNORECASE,
)
_DOC_REF_RE = re.compile(
    r"\b(this|the|attached|uploaded)\s+(pdf|document|doc|file)\b"
    r"|\bwhat\s+(is|does|are|did)\s+(this|it)\b"
    r"|\b(it|this)\s+(says?|talks?\s+about|mentions?|covers?|discusses?|is\s+about)\b",
    re.IGNORECASE,
)
# Short standalone meta-commands — "explain", "summarize", "what's this?", etc.
_SHORT_META_RE = re.compile(
    r"^\s*(explain(\s+it)?|summarize|summarise|describe(\s+it)?|"
    r"what'?s?\s+(this|it)(\s+about)?|what\s+does\s+it\s+(say|cover|talk|discuss)|"
    r"give\s+(me\s+)?(a\s+)?(summary|overview|explanation)|"
    r"tell\s+me\s+(about\s+)?(it|this)|overview)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _is_document_meta_query(query: str) -> bool:
    """Return True when the user is asking about the uploaded document in general terms."""
    return bool(
        _DOC_META_RE.search(query)
        or _DOC_REF_RE.search(query)
        or _SHORT_META_RE.match(query)
    )


# ── Simple document-explanation prompt (used instead of the full SYSTEM_PROMPT) ──
# qwen2.5:3b can't reliably follow 11 rules; a single direct instruction works better.

DOCUMENT_SYSTEM_PROMPT = (
    "You are a helpful document reader and summarizer.\n"
    "The user has shared a document. Read all the chunks below and write a clear, "
    "thorough explanation.\n"
    "- Write at least 3 paragraphs.\n"
    "- Cover: what the document is about, the main topics it discusses, and key takeaways.\n"
    "- Use EVERY chunk provided — do not skip any.\n"
    "- End with 'Sources:' listing the chunk IDs you used.\n"
    "- NEVER say 'I don't have enough information' when content is given — just use it."
)

# Detect when the model refuses despite having context
_REFUSAL_RE = re.compile(
    r"i\s+(don'?t|do\s+not)\s+have\s+(enough\s+)?information"
    r"|not\s+enough\s+information"
    r"|cannot\s+answer\s+(this|the\s+question)"
    r"|unable\s+to\s+(answer|provide)",
    re.IGNORECASE,
)


def _is_refusal(text: str) -> bool:
    return bool(_REFUSAL_RE.search(text))


def _fallback_from_chunks(chunks: list[RetrievedChunk]) -> str:
    """
    Last-resort answer: stitch chunk text into a readable answer when the
    model refuses despite having content. Prioritises exact CVE / upload / web
    chunks over generic KB results.
    """
    # Prefer exact/uploaded/web content over generic KB chunks
    preferred = [c for c in chunks if c.source in ("UserUpload", "WebFetch") or c.score == 1.0]
    targets = preferred if preferred else chunks
    parts: list[str] = []
    for c in targets:
        text = c.text.strip()
        if text:
            parts.append(text)
    body = "\n\n".join(parts)
    ids = ", ".join(c.chunk_id for c in targets)
    source_label = "retrieved knowledge base" if not preferred else "matched records"
    return f"Here is what was found in the {source_label}:\n\n{body}\n\nSources: {ids}"


# ── URL fetching ──────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)
_WEB_MAX_CHARS = 5000  # characters of page text to include per URL
_SPA_THRESHOLD = 200   # pages with fewer extracted chars are treated as JS SPAs

# MSRC vulnerability URL pattern — extract CVE ID for direct KB lookup
_MSRC_CVE_RE = re.compile(
    r'msrc\.microsoft\.com/update-guide/[^/\s]+/vulnerability/(CVE-[\d-]+)',
    re.IGNORECASE,
)
# Generic CVE ID in any URL
_CVE_IN_URL_RE = re.compile(r'(CVE-\d{4}-\d+)', re.IGNORECASE)


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter that skips script/style tags."""

    _SKIP = {"script", "style", "head", "noscript", "nav", "footer"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if not self._depth:
            t = data.strip()
            if t:
                self._parts.append(t)

    def text(self) -> str:
        return " ".join(self._parts)


def _fetch_url_text(url: str) -> str | None:
    """
    Fetch *url* and return cleaned plain text, or None if fetching fails hard.

    JavaScript-rendered SPAs (e.g. MSRC update guide) return almost no text after
    HTML stripping. When that happens we return an informative message so the LLM
    knows the page couldn't be read and can tell the user what to do instead.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CTIBot/1.0 (cyber threat intelligence assistant)"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(_WEB_MAX_CHARS * 6).decode("utf-8", errors="ignore")

        if "html" in content_type.lower():
            stripper = _HTMLStripper()
            stripper.feed(raw)
            text = stripper.text()
        else:
            text = raw

        text = re.sub(r"\s{3,}", "  ", text).strip()
        text = text[:_WEB_MAX_CHARS]

        # Sparse text means a JavaScript SPA — return a descriptive message instead of None
        if len(text) < _SPA_THRESHOLD:
            cve_match = _CVE_IN_URL_RE.search(url)
            cve_hint = (
                f" The URL contains CVE ID: {cve_match.group(1).upper()}."
                " The knowledge base has been searched for this specific CVE."
                if cve_match else ""
            )
            return (
                f"[Note: The page at {url} is a JavaScript-rendered application that "
                f"cannot be read by a plain HTTP request.{cve_hint}]"
            )

        return text or None
    except Exception as exc:
        return f"[Note: Could not fetch {url} — {type(exc).__name__}]"


def _fetch_query_urls(query: str) -> list[RetrievedChunk]:
    """
    Find all http/https URLs in *query*, fetch their content, and return
    each as a synthetic RetrievedChunk with source='WebFetch'.
    SPA/fetch-failure messages are included so the LLM can inform the user.
    """
    urls = _URL_RE.findall(query)
    chunks: list[RetrievedChunk] = []
    for url in urls:
        text = _fetch_url_text(url)
        if text:
            chunks.append(RetrievedChunk(
                chunk_id=f"web:{url[:100]}",
                source="WebFetch",
                text=f"[Fetched from {url}]\n\n{text}",
                score=1.0,
                metadata={"url": url},
            ))
    return chunks


def _cve_ids_from_urls(query: str) -> list[str]:
    """
    Extract CVE IDs embedded in MSRC or other vulnerability-tracker URLs.
    Returns upper-cased CVE IDs like ['CVE-2026-45648'].
    """
    ids: list[str] = []
    for m in _MSRC_CVE_RE.finditer(query):
        ids.append(m.group(1).upper())
    # Also catch bare CVE IDs that appear directly in any URL in the query
    for url in _URL_RE.findall(query):
        for m in _CVE_IN_URL_RE.finditer(url):
            cve = m.group(1).upper()
            if cve not in ids:
                ids.append(cve)
    return ids


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


def _build_history_block(history: list[dict]) -> str:
    """Format a list of {role, content} turns into a readable history section."""
    lines = []
    for turn in history:
        label = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{label}: {turn['content']}")
    return "\n".join(lines)


def _build_user_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
    has_uploads: bool = False,
    has_web: bool = False,
) -> str:
    context = _build_context_block(chunks)

    history_section = ""
    if history:
        history_section = f"\nCONVERSATION HISTORY:\n{_build_history_block(history)}\n"

    notes: list[str] = []
    if has_web:
        notes.append(
            "Web page content has been fetched and included above (Source: WebFetch). "
            "Use it to answer the user's question about that URL."
        )
    if has_uploads:
        notes.append(
            "The context also contains chunks from the user's uploaded document(s). "
            "If the user is asking for an explanation or summary, use all chunks to provide one."
        )
    extra = ("\nNote: " + " ".join(notes)) if notes else ""

    return f"""CONTEXT:
{context}{history_section}
CURRENT QUESTION: {query}{extra}

Answer based on the context and conversation history above. Cite sources by their chunk ID."""


@dataclass
class RAGResponse:
    answer:   str
    sources:  list[dict]   # [{chunk_id, source, score, text_preview}]
    query:    str
    model:    str


def _retrieve_all(
    query: str,
    top_k: int,
    source_filter: str | None,
    upload_ids: list[str] | None,
) -> tuple[list[RetrievedChunk], list[RetrievedChunk], bool]:
    """
    Run all retrieval steps and return (all_chunks, upload_chunks, prompt_query).
    Encodes the query embedding once and reuses it across retrieve calls.
    """
    # Encode once — reused for both KB and upload retrieval when queries match
    kb_vector = encode_query(query)

    web_chunks = _fetch_query_urls(query)

    cve_chunks: list[RetrievedChunk] = []
    for cve_id in _cve_ids_from_urls(query):
        cve_chunks.extend(retrieve_by_cve_id(cve_id))

    kb_chunks = retrieve(query, top_k=top_k, source_filter=source_filter, vector=kb_vector)

    upload_chunks: list[RetrievedChunk] = []
    if upload_ids:
        if _is_document_meta_query(query):
            retrieval_query = "main content introduction summary key points overview"
            upload_vector = encode_query(retrieval_query)
        else:
            retrieval_query = query
            upload_vector = kb_vector  # reuse — same query, no re-encode needed
        upload_chunks = retrieve_from_uploads(retrieval_query, upload_ids, top_k_per_upload=6, vector=upload_vector)

    seen_ids: set[str] = set()
    chunks: list[RetrievedChunk] = []
    for c in web_chunks + cve_chunks + upload_chunks + kb_chunks:
        if c.chunk_id not in seen_ids:
            seen_ids.add(c.chunk_id)
            chunks.append(c)

    return chunks, upload_chunks, bool(web_chunks)


def _build_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    upload_chunks: list[RetrievedChunk],
    has_web: bool,
    upload_ids: list[str] | None,
    history: list[dict] | None,
) -> str:
    is_doc_explain = _is_document_meta_query(query) and bool(upload_chunks)
    if is_doc_explain:
        doc_text = "\n\n".join(
            f"[Chunk {i + 1} — ID: {c.chunk_id}]:\n{c.text}"
            for i, c in enumerate(upload_chunks)
        )
        return (
            f"{DOCUMENT_SYSTEM_PROMPT}\n\n"
            f"DOCUMENT CHUNKS:\n{doc_text}\n\n"
            f"USER REQUEST: {query}\n\n"
            f"Write your explanation now:"
        )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"{_build_user_prompt(query, chunks, history=history or [], has_uploads=bool(upload_ids), has_web=has_web)}"
    )


def _make_sources(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "chunk_id":     c.chunk_id,
            "source":       c.source,
            "score":        c.score,
            "text_preview": c.text[:120],
            "url":          _extract_url(c),
        }
        for c in chunks
    ]


def generate(
    query: str,
    top_k: int = 5,
    source_filter: str | None = None,
    upload_ids: list[str] | None = None,
    history: list[dict] | None = None,
) -> RAGResponse:
    """Full RAG pipeline: retrieve → augment → generate (blocking)."""
    rag_start = time.perf_counter()
    chunks, upload_chunks, has_web = _retrieve_all(query, top_k, source_filter, upload_ids)

    if not chunks:
        return RAGResponse(
            answer="I don't have enough information in the current knowledge base to answer this.",
            sources=[],
            query=query,
            model=LLM_MODEL,
        )

    prompt = _build_prompt(query, chunks, upload_chunks, has_web, upload_ids, history)

    llm_start = time.perf_counter()
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": MAX_TOKENS, "temperature": TEMPERATURE},
        },
        timeout=300,
    )
    LLM_LATENCY.observe(time.perf_counter() - llm_start)

    if not response.ok:
        raise requests.HTTPError(
            f"Ollama returned {response.status_code}: {response.text[:300]}",
            response=response,
        )
    answer = response.json().get("response", "").strip()

    if _is_refusal(answer) and chunks:
        answer = _fallback_from_chunks(chunks)

    rag_duration = time.perf_counter() - rag_start
    RAG_LATENCY.labels(source_filter=source_filter or "all").observe(rag_duration)
    CHUNKS_RETRIEVED.observe(len(chunks))

    h_score = hallucination_scorer.score(answer, [c.text for c in chunks])
    if h_score is not None:
        HALLUCINATION_SCORE.observe(h_score)

    log_rag_query(
        query=query,
        model=LLM_MODEL,
        top_k=top_k,
        source_filter=source_filter,
        latency_s=rag_duration,
        chunks_count=len(chunks),
        hallucination_score=h_score,
    )

    return RAGResponse(answer=answer, sources=_make_sources(chunks), query=query, model=LLM_MODEL)


def stream_generate(
    query: str,
    top_k: int = 5,
    source_filter: str | None = None,
    upload_ids: list[str] | None = None,
    history: list[dict] | None = None,
):
    """
    Streaming RAG pipeline. Yields dicts:
      {"token": str}               — one per Ollama token
      {"done": True, "sources": list, "model": str}  — final event
    """
    rag_start = time.perf_counter()
    chunks, upload_chunks, has_web = _retrieve_all(query, top_k, source_filter, upload_ids)

    if not chunks:
        yield {
            "done": True,
            "sources": [],
            "model": LLM_MODEL,
            "answer": "I don't have enough information in the current knowledge base to answer this.",
        }
        return

    prompt = _build_prompt(query, chunks, upload_chunks, has_web, upload_ids, history)
    sources = _make_sources(chunks)

    llm_start = time.perf_counter()
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": True,
            "options": {"num_predict": MAX_TOKENS, "temperature": TEMPERATURE},
        },
        stream=True,
        timeout=300,
    )

    if not response.ok:
        raise requests.HTTPError(
            f"Ollama returned {response.status_code}: {response.text[:300]}",
            response=response,
        )

    full_answer = ""
    for line in response.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        token = data.get("response", "")
        if token:
            full_answer += token
            yield {"token": token}
        if data.get("done"):
            break

    LLM_LATENCY.observe(time.perf_counter() - llm_start)
    rag_duration = time.perf_counter() - rag_start
    RAG_LATENCY.labels(source_filter=source_filter or "all").observe(rag_duration)
    CHUNKS_RETRIEVED.observe(len(chunks))

    h_score = hallucination_scorer.score(full_answer, [c.text for c in chunks])
    if h_score is not None:
        HALLUCINATION_SCORE.observe(h_score)

    log_rag_query(
        query=query,
        model=LLM_MODEL,
        top_k=top_k,
        source_filter=source_filter,
        latency_s=rag_duration,
        chunks_count=len(chunks),
        hallucination_score=h_score,
    )

    yield {"done": True, "sources": sources, "model": LLM_MODEL}


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
