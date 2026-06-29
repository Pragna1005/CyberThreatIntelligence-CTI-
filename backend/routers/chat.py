import json

import requests as _requests
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models import QueryRequest, QueryResponse, SourceItem
from rag.generator import generate, stream_generate

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat", response_model=QueryResponse)
def chat(req: QueryRequest):
    """
    Unified chatbot endpoint — searches ALL sources (MITRE + ThreatFox + MSRC).
    Best for cross-domain questions like 'Tell me about phishing threats targeting Microsoft'.
    """
    history = [{"role": m.role, "content": m.content} for m in (req.history or [])]
    result = generate(
        req.query,
        top_k=req.top_k,
        source_filter=None,
        upload_ids=req.upload_ids or None,
        history=history or None,
    )
    return QueryResponse(
        query=result.query,
        answer=result.answer,
        sources=[SourceItem(**s) for s in result.sources],
        model=result.model,
    )


@router.post("/chat/stream")
def chat_stream(req: QueryRequest):
    """
    Streaming variant of /chat. Returns Server-Sent Events:
      data: {"token": "..."}
      data: {"done": true, "sources": [...], "model": "..."}
    """
    history = [{"role": m.role, "content": m.content} for m in (req.history or [])]

    def _sse():
        try:
            for event in stream_generate(
                req.query,
                top_k=req.top_k,
                source_filter=None,
                upload_ids=req.upload_ids or None,
                history=history or None,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except _requests.RequestException:
            yield (
                f"data: {json.dumps({'error': 'The answer generation service is unavailable. '
                                              'Ollama is not ready or the model is still loading.'})}\n\n"
            )
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
