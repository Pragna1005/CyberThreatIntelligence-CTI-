from fastapi import APIRouter
from backend.models import QueryRequest, QueryResponse, SourceItem
from rag.generator import generate

router = APIRouter(prefix="/api", tags=["CERT"])


@router.post("/cert_query", response_model=QueryResponse)
def cert_query(req: QueryRequest):
    """
    Query MSRC/CERT advisory data only.
    Returns CVE records, severity scores, and exploitability info with citations.
    """
    result = generate(req.query, top_k=req.top_k, source_filter="MSRC")
    return QueryResponse(
        query=result.query,
        answer=result.answer,
        sources=[SourceItem(**s) for s in result.sources],
        model=result.model,
    )
