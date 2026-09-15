"""
Ingestion router - handles paper upload, status polling, and chunk listing.
Full implementation replacing the Phase 0 stub.
"""

import uuid

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import get_db
from app.services.ingestion_service import IngestionService

router = APIRouter(tags=["Ingestion"])

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/x-tex",
    "application/x-latex",
    "text/plain",   # some clients send .tex as text/plain
}


@router.post("/papers")
async def upload_paper(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Upload a research paper (PDF or LaTeX/Beamer) for ingestion.

    Responses:
        202 - New paper accepted; ingestion running in background.
        200 - Duplicate detected; returns existing paper_id.
        413 - File exceeds 50 MB limit.
        415 - Unsupported MIME type.
    """
    file_bytes = await file.read()

    # Guard: file size
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {settings.max_upload_size_bytes // (1024 * 1024)} MB.",
        )

    # Guard: MIME type (also allow .tex uploaded with text/plain)
    filename = file.filename or ""
    is_tex = filename.lower().endswith((".tex", ".latex"))
    if file.content_type not in _ALLOWED_CONTENT_TYPES and not is_tex:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Accepted: PDF (.pdf), LaTeX (.tex, .latex).",
        )

    svc = IngestionService()
    sha256 = svc.compute_sha256(file_bytes)

    # Duplicate detection
    async with db.execute(
        "SELECT paper_id, status FROM papers WHERE sha256_hash = ?", (sha256,)
    ) as cursor:
        existing = await cursor.fetchone()

    if existing:
        paper_id, status = existing
        if status == "failed":
            # Reprocess previously failed uploads
            await db.execute(
                "UPDATE papers SET status = 'processing', error_msg = NULL WHERE paper_id = ?",
                (paper_id,)
            )
            await db.commit()
            background_tasks.add_task(svc.process_paper, file_bytes, filename, paper_id)
            return JSONResponse(
                status_code=202,
                content={
                    "status": "success",
                    "data": {"paper_id": paper_id, "duplicate": False},
                },
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": {"paper_id": paper_id, "duplicate": True},
                },
            )

    # New paper - create record and queue background ingestion
    paper_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
        (paper_id, filename, sha256, "processing"),
    )
    await db.commit()

    background_tasks.add_task(svc.process_paper, file_bytes, filename, paper_id)

    return JSONResponse(
        status_code=202,
        content={
            "status": "success",
            "data": {"paper_id": paper_id, "duplicate": False},
        },
    )


@router.get("/papers/{paper_id}")
async def get_paper_status(
    paper_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Poll the ingestion status of a paper.
    Status values: processing | ready | failed.
    """
    async with db.execute(
        "SELECT paper_id, status, chunk_count, error_msg, is_presentation FROM papers WHERE paper_id = ?",
        (paper_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Paper '{paper_id}' not found.")

    return {
        "status": "success",
        "data": {
            "paper_id": row["paper_id"],
            "status": row["status"],
            "chunk_count": row["chunk_count"],
            "error_msg": row["error_msg"],
            "is_presentation": bool(row["is_presentation"]),
        },
    }


@router.get("/papers/{paper_id}/chunks")
async def list_chunks(
    paper_id: str,
    page: int = 1,
    page_size: int = 20,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Paginated list of chunks for a paper. Useful for debugging and UI visualization.
    """
    # Verify paper exists
    async with db.execute(
        "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Paper '{paper_id}' not found.")

    offset = (page - 1) * page_size
    async with db.execute(
        """SELECT chunk_id, page_number, section_title, block_index,
                  text, contains_math, has_figure, figure_caption
           FROM chunks
           WHERE paper_id = ?
           ORDER BY page_number, block_index
           LIMIT ? OFFSET ?""",
        (paper_id, page_size, offset),
    ) as cursor:
        rows = await cursor.fetchall()

    return {
        "status": "success",
        "data": {
            "paper_id": paper_id,
            "page": page,
            "page_size": page_size,
            "chunks": [dict(r) for r in rows],
        },
    }
