"""
TDD - Phase 2c: Generation API endpoint tests.
Tests session creation and generation endpoints.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.generation import GenerationOutput, OutputType, Audience, Length, Style, Slide, SourcedSentence


class TestSessionsAPI:
    """POST /api/sessions and POST /api/sessions/{id}/generate"""

    async def test_create_session(self, client, test_db):
        # Create paper first
        pid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (pid, "test.pdf", "abc", "ready")
        )
        await test_db.commit()

        resp = await client.post("/api/sessions", json={"paper_id": pid})
        assert resp.status_code == 200
        assert "session_id" in resp.json()["data"]

    @patch("app.routers.generate.RAGService.retrieve")
    @patch("app.routers.generate.GenerationService.generate", new_callable=AsyncMock)
    async def test_generate_endpoint_success(self, mock_generate, mock_retrieve, client, test_db):
        # Create paper and session
        pid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (pid, "test.pdf", "abc", "ready")
        )
        await test_db.execute(
            "INSERT INTO sessions (session_id, paper_id) VALUES (?,?)",
            (sid, pid)
        )
        await test_db.execute(
            "INSERT INTO chunks (chunk_id, paper_id, page_number, section_title, block_index, text, contains_math, has_figure, figure_caption) VALUES (?,?,?,?,?,?,?,?,?)",
            ("chunk-01", pid, 1, "", 0, "test", False, False, "")
        )
        await test_db.commit()

        # Mock dependencies
        from app.models.chunk import Chunk
        mock_generate.return_value = GenerationOutput(
            output_type=OutputType.SPEAKER_SCRIPT,
            audience=Audience.POLICYMAKERS,
            length=Length.NINETY_SEC,
            slides=[],
            citation_coverage=1.0,
            low_confidence=False
        )

        req = {
            "paper_id": pid,
            "audience": "policymakers",
            "length": "90s",
            "style": "plain_english",
            "output_type": "speaker_script"
        }

        resp = await client.post(f"/api/sessions/{sid}/generate", json=req)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["generation"]["audience"] == "policymakers"
        assert "version" in data # should be 1

    async def test_generate_invalid_audience_returns_422(self, client):
        req = {
            "paper_id": str(uuid.uuid4()),
            "audience": "aliens", # Invalid enum
            "length": "90s",
            "style": "plain_english",
            "output_type": "speaker_script"
        }
        resp = await client.post(f"/api/sessions/sid-123/generate", json=req)
        assert resp.status_code == 422 # FastAPI Pydantic validation error

    async def test_generate_paper_not_ready_returns_409(self, client, test_db):
        pid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (pid, "test.pdf", "abc", "processing") # Not ready
        )
        await test_db.execute(
            "INSERT INTO sessions (session_id, paper_id) VALUES (?,?)",
            (sid, pid)
        )
        await test_db.commit()

        req = {
            "paper_id": pid,
            "audience": "policymakers",
            "length": "90s",
            "style": "plain_english",
            "output_type": "speaker_script"
        }

        resp = await client.post(f"/api/sessions/{sid}/generate", json=req)
        assert resp.status_code == 409
        assert "not ready" in resp.json()["detail"].lower()
