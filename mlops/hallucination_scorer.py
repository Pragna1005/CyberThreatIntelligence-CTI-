"""
Hallucination risk scorer.

Calls the local Ollama model with a faithfulness prompt to evaluate
whether the generated answer is grounded in the retrieved context.

Returns a score in [0.0, 1.0] where 1.0 = fully grounded.
Disabled by default (HALLUCINATION_SCORING=true to enable) because it
adds a second Ollama call after every RAG query.
"""

import os
import re

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen:7b")
ENABLED = os.environ.get("HALLUCINATION_SCORING", "false").lower() == "true"

_SCORE_RE = re.compile(r"\b([0-9]|10)\b")

_PROMPT = """\
You are a faithfulness evaluator for a Cyber Threat Intelligence RAG system.

RETRIEVED CONTEXT:
{context}

GENERATED ANSWER:
{answer}

Score the answer 0–10:
  10 = every claim is directly supported by the context above
   5 = roughly half the claims are supported
   0 = the answer contradicts or ignores the context entirely

Reply with a single integer (0–10) and nothing else."""


def score(answer: str, context_chunks: list[str]) -> float | None:
    """
    Return a faithfulness score in [0.0, 1.0], or None if scoring is
    disabled or the Ollama call fails.
    """
    if not ENABLED or not answer or not context_chunks:
        return None

    context_text = "\n\n".join(c[:300] for c in context_chunks[:5])
    prompt = _PROMPT.format(context=context_text, answer=answer[:800])

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 4, "temperature": 0.0},
            },
            timeout=30,
        )
        if not resp.ok:
            return None

        raw = resp.json().get("response", "").strip()
        m = _SCORE_RE.search(raw)
        if m:
            return round(int(m.group(1)) / 10.0, 2)
    except Exception:
        pass

    return None
