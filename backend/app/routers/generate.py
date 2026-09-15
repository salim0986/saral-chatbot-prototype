"""
Generation router - handles session creation and content generation.
"""

import uuid
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.db import get_db
from app.models.generation import SessionCreateRequest, GenerateRequest
from app.services.rag_service import RAGService
from app.services.generation_service import GenerationService
from app.models.chunk import Chunk

router = APIRouter(tags=["Generation"])


@router.post("/sessions")
async def create_session(
    req: SessionCreateRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """Creates a new interaction session for a paper."""
    session_id = str(uuid.uuid4())
    
    # Verify paper exists
    async with db.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (req.paper_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Paper not found")

    await db.execute(
        "INSERT INTO sessions (session_id, paper_id) VALUES (?, ?)",
        (session_id, req.paper_id)
    )
    await db.commit()

    return JSONResponse(content={
        "status": "success",
        "data": {"session_id": session_id}
    })


@router.post("/sessions/{session_id}/generate")
async def generate_content(
    session_id: str,
    req: GenerateRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Generates content using RAG based on the specified audience and length.
    Increments generation version.
    """
    # 1. Verify session and get paper_id
    async with db.execute("SELECT paper_id FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        session_row = await cursor.fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify req.paper_id matches session's paper_id
        if session_row["paper_id"] != req.paper_id:
            raise HTTPException(status_code=400, detail="paper_id mismatch")

    # 2. Verify paper is ready
    async with db.execute("SELECT status FROM papers WHERE paper_id = ?", (req.paper_id,)) as cursor:
        paper_row = await cursor.fetchone()
        if not paper_row:
            raise HTTPException(status_code=404, detail="Paper not found")
        if paper_row["status"] != "ready":
            raise HTTPException(status_code=409, detail=f"Paper is {paper_row['status']}, not ready")

    # 3. Retrieve chunks (Full chronological context, bypass RAG for initial generation)
    # Cap at 30 chunks to respect the 8K context limit while capturing maximum slide coverage.
    chunks = []
    async with db.execute(
        """SELECT chunk_id, paper_id, page_number, section_title, block_index, text, contains_math, has_figure, figure_caption 
           FROM chunks 
           WHERE paper_id = ? 
           ORDER BY page_number ASC, block_index ASC LIMIT 30""", 
        (req.paper_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        for row in rows:
            chunks.append(Chunk(
                chunk_id=row["chunk_id"],
                paper_id=row["paper_id"],
                page_number=row["page_number"],
                section_title=row["section_title"],
                block_index=row["block_index"],
                text=row["text"],
                contains_math=bool(row["contains_math"]),
                has_figure=bool(row["has_figure"]),
                figure_caption=row["figure_caption"],
            ))

    if not chunks:
        raise HTTPException(status_code=500, detail="Failed to retrieve relevant context")

    # 4. Generate
    gen_svc = GenerationService()
    output = await gen_svc.generate(
        paper_id=req.paper_id,
        chunks=chunks,
        audience=req.audience,
        length=req.length,
        style=req.style,
        output_type=req.output_type
    )

    # 5. Determine new version number
    async with db.execute(
        "SELECT MAX(version) as max_v FROM generations WHERE session_id = ?", 
        (session_id,)
    ) as cursor:
        v_row = await cursor.fetchone()
        next_version = (v_row["max_v"] or 0) + 1

    # 6. Save generation
    generation_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO generations 
           (generation_id, session_id, version, audience, length, style, output_json, citation_coverage, low_confidence) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            generation_id, 
            session_id, 
            next_version, 
            req.audience.value, 
            req.length.value, 
            req.style.value, 
            output.model_dump_json(),
            output.citation_coverage,
            int(output.low_confidence)
        )
    )
    await db.commit()

    return JSONResponse(content={
        "status": "success",
        "data": {
            "generation_id": generation_id,
            "version": next_version,
            "generation": output.model_dump()
        }
    })
