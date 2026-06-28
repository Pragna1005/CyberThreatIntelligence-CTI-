"""
Shared Pydantic schemas for all API request/response bodies.
"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")
    upload_ids: list[str] = Field(default=[], description="IDs of user-uploaded documents to include in context")


class SourceItem(BaseModel):
    chunk_id:     str
    source:       str
    score:        float
    text_preview: str
    url:          str = ""


class QueryResponse(BaseModel):
    query:   str
    answer:  str
    sources: list[SourceItem]
    model:   str
