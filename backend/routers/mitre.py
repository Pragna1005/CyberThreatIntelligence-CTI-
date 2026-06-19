from fastapi import APIRouter
from backend.models import QueryRequest, QueryResponse, SourceItem
from rag.generator import generate

router = APIRouter(prefix="/api", tags=["MITRE"])


@router.post("/mitre_query", response_model=QueryResponse)
def mitre_query(req: QueryRequest):
    """
    Query MITRE ATT&CK data only.
    Returns relevant techniques, sub-techniques, and tactics with citations.
    """
    result = generate(req.query, top_k=req.top_k, source_filter="MITRE")
    return QueryResponse(
        query=result.query,
        answer=result.answer,
        sources=[SourceItem(**s) for s in result.sources],
        model=result.model,
    )
