from fastapi import APIRouter
from backend.models import QueryRequest, QueryResponse, SourceItem
from rag.generator import generate

router = APIRouter(prefix="/api", tags=["ThreatFeed"])


@router.post("/threat_query", response_model=QueryResponse)
def threat_query(req: QueryRequest):
    """
    Query ThreatFox IOC/malware data only.
    Returns malware families, IOC values, and threat types with citations.
    """
    result = generate(req.query, top_k=req.top_k, source_filter="ThreatFox")
    return QueryResponse(
        query=result.query,
        answer=result.answer,
        sources=[SourceItem(**s) for s in result.sources],
        model=result.model,
    )
