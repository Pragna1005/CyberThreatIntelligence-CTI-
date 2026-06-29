"""
Upload router: accepts user-uploaded files (PDF, TXT, DOCX/DOC),
extracts text, chunks + embeds it, and upserts into the existing
'cti_intel' Qdrant collection under source='UserUpload'.

The upload's chunks participate in all existing RAG queries automatically
since retrieve() searches the whole collection with no source filter.

Endpoints:
    POST   /api/upload              — ingest a file, returns upload_id + chunk_count
    DELETE /api/upload/{upload_id}  — remove the file's chunks from Qdrant
    GET    /api/uploads             — list currently indexed uploads
"""

import asyncio
import hashlib
import io
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointStruct

from rag.retriever import _get_client, _get_model, COLLECTION_NAME

VECTOR_DIM = 384  # BAAI/bge-small-en-v1.5 output dimension

router = APIRouter(prefix="/api", tags=["Upload"])

# In-memory registry: upload_id -> {upload_id, filename, chunk_count}
_uploads: dict[str, dict] = {}

CHUNK_SIZE    = 400   # words per chunk (matches chunker.py)
CHUNK_OVERLAP = 50    # word overlap between chunks
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    upload_id:   str
    filename:    str
    chunk_count: int
    message:     str


class UploadListItem(BaseModel):
    upload_id:   str
    filename:    str
    chunk_count: int


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {exc}")


def _extract_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read DOCX: {exc}")


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extract_text(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return _extract_pdf(data)
    if ext in ("doc", "docx"):
        return _extract_docx(data)
    if ext == "txt":
        return _extract_txt(data)
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type '.{ext}'. Please upload a PDF, TXT, DOC, or DOCX file.",
    )


# ── Chunking ──────────────────────────────────────────────────────────────────

def _split_chunks(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= CHUNK_SIZE:
        return [" ".join(words)]
    chunks, start = [], 0
    while start < len(words):
        end = start + CHUNK_SIZE
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _chunk_id_to_point_id(chunk_id: str) -> int:
    digest = hashlib.md5(chunk_id.encode()).hexdigest()
    return int(digest, 16) % (2 ** 53)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Ingest a user-provided file into the shared Qdrant collection.
    Uploaded chunks are immediately searchable by all RAG queries.
    """
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 20 MB.")

    text = _extract_text(file.filename or "upload.txt", data).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Could not extract any text from the file.")

    chunks = _split_chunks(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="File produced no usable text chunks.")

    upload_id = str(uuid.uuid4())
    model  = _get_model()
    client = _get_client()  # _get_client() ensures collection exists on first call

    # Run in a thread so the async event loop isn't blocked during CPU-bound encoding
    loop = asyncio.get_event_loop()
    vectors = await loop.run_in_executor(
        None,
        lambda: model.encode(chunks, normalize_embeddings=True, show_progress_bar=False).tolist(),
    )

    points = [
        PointStruct(
            id=_chunk_id_to_point_id(f"upload_{upload_id}_{idx}"),
            vector=vec,
            payload={
                "chunk_id":  f"upload_{upload_id}_{idx}",
                "source":    "UserUpload",
                "text":      chunk_text,
                "filename":  file.filename or "upload",
                "upload_id": upload_id,
            },
        )
        for idx, (chunk_text, vec) in enumerate(zip(chunks, vectors))
    ]

    client.upsert(collection_name=COLLECTION_NAME, points=points)

    _uploads[upload_id] = {
        "upload_id":   upload_id,
        "filename":    file.filename or "upload",
        "chunk_count": len(chunks),
    }

    return UploadResponse(
        upload_id=upload_id,
        filename=file.filename or "upload",
        chunk_count=len(chunks),
        message=f"Indexed {len(chunks)} chunk(s). Your queries now include this document.",
    )


@router.delete("/upload/{upload_id}")
def delete_upload(upload_id: str):
    """Remove all Qdrant chunks for the given upload."""
    if upload_id not in _uploads:
        raise HTTPException(status_code=404, detail="Upload not found.")

    client = _get_client()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="upload_id", match=MatchValue(value=upload_id))]
        ),
    )
    meta = _uploads.pop(upload_id)
    return {"message": f"Removed {meta['chunk_count']} chunk(s) for '{meta['filename']}'."}


@router.get("/uploads", response_model=list[UploadListItem])
def list_uploads():
    """List all currently indexed user uploads."""
    return list(_uploads.values())
