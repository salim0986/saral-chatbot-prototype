"""
Refine router - handles iterative changes to a generation.
"""

import json
import uuid
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.db import get_db
from app.models.generation import GenerationOutput
from app.models.chunk import Chunk
from app.models.refine import RefineRequest
from app.services.rag_service import RAGService
from app.services.change_tracking_service import ChangeTrackingService

router = APIRouter(tags=["Refinement"])

@router.post("/sessions/{session_id}/refine")
async def refine_generation(
    session_id: str,
    req: RefineRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Applies a change instruction to a specific slide, computing a diff and a new version.
    Saves the new version and the delta record.
    """
    if not req.change_instruction.strip():
        raise HTTPException(status_code=400, detail="change_instruction cannot be empty")

    # 1. Fetch latest generation for the session
    async with db.execute(
        "SELECT version, audience, length, style, output_json FROM generations WHERE session_id = ? ORDER BY version DESC LIMIT 1",
        (session_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No previous generation found for session")

        version_from = row["version"]
        output_json = row["output_json"]
        audience = row["audience"]
        length = row["length"]
        style = row["style"]

    old_output = GenerationOutput(**json.loads(output_json))
    version_to = version_from + 1

    # 2. Fetch paper_id for session to retrieve chunks
    async with db.execute("SELECT paper_id FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        s_row = await cursor.fetchone()
        if not s_row:
            raise HTTPException(status_code=404, detail="Session not found")
        paper_id = s_row["paper_id"]

    # 3. Retrieve chunks relevant to the change instruction
    rag_svc = RAGService()
    chunks = rag_svc.retrieve(req.change_instruction, paper_id, top_k=5)

    if not chunks:
        raise HTTPException(status_code=500, detail="Failed to retrieve relevant context")

    # 4. Apply delta
    tracker = ChangeTrackingService()
    try:
        delta, new_output = await tracker.apply_delta(
            session_id=session_id,
            version_from=version_from,
            version_to=version_to,
            old_output=old_output,
            target_slide_number=req.target_slide,
            change_instruction=req.change_instruction,
            valid_chunks=chunks
        )
    except ValueError as e:
        # Invalid slide number, etc.
        raise HTTPException(status_code=422, detail=str(e))

    # 5. Persist the delta
    delta_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO deltas 
           (delta_id, session_id, version_from, version_to, slide_number, old_text, new_text, diff_hunks, reason, provenance)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            delta_id,
            session_id,
            version_from,
            version_to,
            delta.slide_number,
            delta.old_text,
            delta.new_text,
            json.dumps([h.model_dump() for h in delta.diff_hunks]),
            delta.reason,
            json.dumps(delta.provenance)
        )
    )

    # 6. Persist the new generation
    generation_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO generations 
           (generation_id, session_id, version, audience, length, style, output_json, citation_coverage, low_confidence, change_instruction) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            generation_id, 
            session_id, 
            version_to, 
            audience, 
            length, 
            style, 
            new_output.model_dump_json(),
            new_output.citation_coverage,
            int(new_output.low_confidence),
            req.change_instruction
        )
    )
    await db.commit()

    return JSONResponse(content={
        "status": "success",
        "data": {
            "delta": delta.model_dump(),
            "new_generation": new_output.model_dump()
        }
    })

@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    page: int = 1,
    page_size: int = 20,
    db: aiosqlite.Connection = Depends(get_db)
):
    """
    Returns the paginated version history and deltas for a session.
    """
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")

    offset = (page - 1) * page_size
    
    # Verify session exists
    async with db.execute("SELECT paper_id FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
            
    # Get total count
    async with db.execute("SELECT COUNT(*) as c FROM generations WHERE session_id = ?", (session_id,)) as cursor:
        row = await cursor.fetchone()
        total = row["c"]
        
    history = []
    
    # We fetch generations ordered by version
    async with db.execute(
        "SELECT version, output_json, change_instruction FROM generations WHERE session_id = ? ORDER BY version ASC LIMIT ? OFFSET ?",
        (session_id, page_size, offset)
    ) as cursor:
        async for row in cursor:
            version = row["version"]
            
            # Fetch delta if version > 1
            delta = None
            if version > 1:
                async with db.execute(
                    "SELECT slide_number, reason, diff_hunks, old_text, new_text FROM deltas WHERE session_id = ? AND version_to = ?",
                    (session_id, version)
                ) as d_cursor:
                    d_row = await d_cursor.fetchone()
                    if d_row:
                        delta = {
                            "slide_number": d_row["slide_number"],
                            "reason": d_row["reason"],
                            "diff_hunks": json.loads(d_row["diff_hunks"]),
                            "old_text": d_row["old_text"],
                            "new_text": d_row["new_text"]
                        }
            
            history.append({
                "version": version,
                "change_instruction": row["change_instruction"],
                "generation": json.loads(row["output_json"]),
                "delta": delta
            })
            
    return JSONResponse(content={
        "status": "success",
        "data": {
            "session_id": session_id,
            "total_versions": total,
            "page": page,
            "page_size": page_size,
            "history": history
        }
    })
