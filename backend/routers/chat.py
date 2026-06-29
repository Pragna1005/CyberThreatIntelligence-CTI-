from fastapi import APIRouter
from backend.models import QueryRequest, QueryResponse, SourceItem
from rag.generator import generate

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
