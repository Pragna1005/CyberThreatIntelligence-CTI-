"""
Generator: builds a grounded prompt from retrieved chunks and calls a local
Ollama model to produce a cited answer.

The prompt strictly instructs the model to:
  - Answer only from the provided context
  - Cite every source by chunk_id / technique_id / CVE / IOC
  - Say "I don't have enough information" if context is insufficient
"""

import os
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

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
    Last-resort answer: stitch chunk text into a readable summary when the
    model refuses despite having content. Prioritises upload/web chunks.
    """
    preferred = [c for c in chunks if c.source in ("UserUpload", "WebFetch")]
    targets = preferred if preferred else chunks
    parts: list[str] = []
    for c in targets:
        text = c.text.strip()
        if text:
            parts.append(text)
    body = "\n\n".join(parts)
    ids = ", ".join(c.chunk_id for c in targets)
    return f"Here is the content from the document:\n\n{body}\n\nSources: {ids}"


# ── URL fetching ──────────────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)
_WEB_MAX_CHARS = 5000  # characters of page text to include per URL


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
    Fetch *url* and return cleaned plain text, or None if fetching fails.
    HTML is stripped; non-HTML responses (JSON, plain text) are returned as-is.
    Content is capped at _WEB_MAX_CHARS characters.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CTIBot/1.0 (cyber threat intelligence assistant)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(_WEB_MAX_CHARS * 6).decode("utf-8", errors="ignore")

        if "html" in content_type.lower():
            stripper = _HTMLStripper()
            stripper.feed(raw)
            text = stripper.text()
        else:
            text = raw

        text = re.sub(r"\s{3,}", "  ", text)  # collapse excessive whitespace
        return text[:_WEB_MAX_CHARS].strip() or None
    except Exception:
        return None


def _fetch_query_urls(query: str) -> list[RetrievedChunk]:
    """
    Find all http/https URLs in *query*, fetch their content, and return
    each as a synthetic RetrievedChunk with source='WebFetch'.
    Failures are silently skipped.
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


def generate(
    query: str,
    top_k: int = 5,
    source_filter: str | None = None,
    upload_ids: list[str] | None = None,
    history: list[dict] | None = None,
) -> RAGResponse:
    """
    Full RAG pipeline: retrieve → augment → generate.

    history is a list of {role, content} dicts representing recent conversation
    turns. It is injected into the prompt so the LLM can answer follow-up
    questions that reference previous answers.
    """
    # Fetch any URLs the user pasted into the query
    web_chunks = _fetch_query_urls(query)

    # Retrieve from the general knowledge base
    kb_chunks = retrieve(query, top_k=top_k, source_filter=source_filter)

    # Retrieve from the user's uploaded documents.
    # When the user asks a meta-question ("explain the pdf", "summarize this document") the
    # query has low semantic similarity to the actual document text, so we substitute a
    # neutral content-retrieval query that matches document body text much better.
    upload_chunks: list[RetrievedChunk] = []
    if upload_ids:
        if _is_document_meta_query(query):
            retrieval_query = "main content introduction summary key points overview"
        else:
            retrieval_query = query
        upload_chunks = retrieve_from_uploads(retrieval_query, upload_ids, top_k_per_upload=6)

    # Merge order: web → upload → kb so the most directly-referenced content appears first
    seen_ids: set[str] = set()
    chunks: list[RetrievedChunk] = []
    for c in web_chunks + upload_chunks + kb_chunks:
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

    # Use a simple, direct prompt when explaining/summarising an uploaded document.
    # The full 11-rule SYSTEM_PROMPT overloads small models (qwen2.5:3b) and causes
    # them to refuse despite having valid context.
    is_doc_explain = _is_document_meta_query(query) and bool(upload_chunks)
    if is_doc_explain:
        doc_text = "\n\n".join(
            f"[Chunk {i + 1} — ID: {c.chunk_id}]:\n{c.text}"
            for i, c in enumerate(upload_chunks)
        )
        prompt = (
            f"{DOCUMENT_SYSTEM_PROMPT}\n\n"
            f"DOCUMENT CHUNKS:\n{doc_text}\n\n"
            f"USER REQUEST: {query}\n\n"
            f"Write your explanation now:"
        )
    else:
        prompt = f"{SYSTEM_PROMPT}\n\n{_build_user_prompt(query, chunks, history=history or [], has_uploads=bool(upload_ids), has_web=bool(web_chunks))}"

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

    # Fallback: if the model still refuses despite having chunks, build the answer
    # directly from the chunk text so the user always gets something useful.
    if _is_refusal(answer) and chunks:
        answer = _fallback_from_chunks(chunks)

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
