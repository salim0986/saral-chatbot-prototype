import json
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient

from app.models.generation import GenerationOutput, OutputType, Audience, Length, Style, Slide, SourcedSentence
from app.models.refine import DeltaResponse, DiffHunk


@pytest.fixture
def mock_delta():
    return DeltaResponse(
        session_id="sess_123",
        version_from=1,
        version_to=2,
        slide_number=2,
        old_text="old",
        new_text="new",
        diff_hunks=[DiffHunk(operation="replace", text="diff")],
        reason="reason",
        provenance=["chunk-01"]
    )

@pytest.fixture
def mock_new_output():
    return GenerationOutput(
        output_type=OutputType.SPEAKER_SCRIPT,
        audience=Audience.POLICYMAKERS,
        length=Length.NINETY_SEC,
        slides=[
            Slide(slide_number=1, title="1", bullets=[], script="s1", speaker_notes="", sentences=[]),
            Slide(slide_number=2, title="2", bullets=[], script="new", speaker_notes="", sentences=[])
        ],
        citation_coverage=1.0,
        low_confidence=False
    )


class TestRefineAPI:

    @patch("app.routers.refine.ChangeTrackingService.apply_delta")
    @patch("app.routers.refine.RAGService.retrieve")
    async def test_refine_endpoint_success(self, mock_retrieve, mock_apply, client: AsyncClient, test_db):
        # 1. Setup DB state
        pid = "paper_1"
        sid = "sess_1"
        await test_db.execute("INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?, ?, ?, ?)", (pid, "test.pdf", "hash", "ready"))
        await test_db.execute("INSERT INTO sessions (session_id, paper_id) VALUES (?, ?)", (sid, pid))
        
        old_output = GenerationOutput(
            output_type=OutputType.SPEAKER_SCRIPT,
            audience=Audience.POLICYMAKERS,
            length=Length.NINETY_SEC,
            slides=[
                Slide(slide_number=1, title="1", bullets=[], script="s1", speaker_notes="", sentences=[]),
                Slide(slide_number=2, title="2", bullets=[], script="old", speaker_notes="", sentences=[])
            ],
            citation_coverage=1.0,
            low_confidence=False
        )
        
        await test_db.execute(
            """INSERT INTO generations (generation_id, session_id, version, audience, length, style, output_json, citation_coverage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("gen_1", sid, 1, Audience.POLICYMAKERS.value, Length.NINETY_SEC.value, Style.PLAIN_ENGLISH.value, old_output.model_dump_json(), 1.0)
        )
        await test_db.commit()

        # 2. Setup mocks
        from app.models.chunk import Chunk
        mock_retrieve.return_value = [Chunk(chunk_id="chunk-01", paper_id=pid, page_number=1, section_title="", block_index=0, text="test", contains_math=False, has_figure=False)]
        
        # mock_apply returns tuple (DeltaResponse, GenerationOutput)
        from app.models.refine import DeltaResponse, DiffHunk
        delta = DeltaResponse(
            session_id=sid, version_from=1, version_to=2, slide_number=2, old_text="old", new_text="new",
            diff_hunks=[DiffHunk(operation="replace", text="diff")], reason="reason", provenance=["chunk-01"]
        )
        new_output = old_output.model_copy(deep=True)
        new_output.slides[1].script = "new"
        
        mock_apply.return_value = (delta, new_output)

        # 3. Call endpoint
        req = {
            "change_instruction": "Make slide 2 less technical",
            "target_slide": 2
        }
        resp = await client.post(f"/api/sessions/{sid}/refine", json=req)

        # 4. Assert response
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["delta"]["version_to"] == 2
        assert data["delta"]["new_text"] == "new"
        assert data["new_generation"]["slides"][1]["script"] == "new"
        
        # 5. Assert DB state
        async with test_db.execute("SELECT COUNT(*) as c FROM generations WHERE session_id = ?", (sid,)) as c:
            row = await c.fetchone()
            assert row["c"] == 2 # v1 and v2

        async with test_db.execute("SELECT new_text FROM deltas WHERE session_id = ?", (sid,)) as c:
            row = await c.fetchone()
            assert row["new_text"] == "new"

    async def test_refine_empty_instruction_returns_400(self, client: AsyncClient):
        req = {
            "change_instruction": "   ",
            "target_slide": 2
        }
        resp = await client.post("/api/sessions/sess_1/refine", json=req)
        assert resp.status_code == 400
        assert "cannot be empty" in resp.json()["detail"]

    async def test_refine_missing_session_returns_404(self, client: AsyncClient):
        req = {
            "change_instruction": "fix",
            "target_slide": 2
        }
        resp = await client.post("/api/sessions/sess_missing/refine", json=req)
        assert resp.status_code == 404
        assert "No previous generation found" in resp.json()["detail"]

    @patch("app.routers.refine.RAGService.retrieve")
    async def test_refine_invalid_slide_returns_422(self, mock_retrieve, client: AsyncClient, test_db, mock_new_output):
        # Setup DB state
        pid = "paper_1"
        sid = "sess_1"
        await test_db.execute("INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?, ?, ?, ?)", (pid, "test.pdf", "hash", "ready"))
        await test_db.execute("INSERT INTO sessions (session_id, paper_id) VALUES (?, ?)", (sid, pid))
        await test_db.execute(
            """INSERT INTO generations (generation_id, session_id, version, audience, length, style, output_json, citation_coverage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("gen_1", sid, 1, Audience.POLICYMAKERS.value, Length.NINETY_SEC.value, Style.PLAIN_ENGLISH.value, mock_new_output.model_dump_json(), 1.0)
        )
        await test_db.commit()

        from app.models.chunk import Chunk
        mock_retrieve.return_value = [Chunk(chunk_id="c1", paper_id=pid, page_number=1, section_title="", block_index=0, text="t", contains_math=False, has_figure=False)]
        
        req = {
            "change_instruction": "fix",
            "target_slide": 99 # slide 99 doesn't exist
        }
        resp = await client.post("/api/sessions/sess_1/refine", json=req)
        assert resp.status_code == 422
        assert "Target slide 99 not found" in resp.json()["detail"]

    async def test_get_session_history_success(self, client: AsyncClient, test_db, mock_new_output):
        # Setup DB state
        pid = "paper_1"
        sid = "sess_1"
        await test_db.execute("INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?, ?, ?, ?)", (pid, "test.pdf", "hash", "ready"))
        await test_db.execute("INSERT INTO sessions (session_id, paper_id) VALUES (?, ?)", (sid, pid))
        
        # Version 1
        await test_db.execute(
            """INSERT INTO generations (generation_id, session_id, version, audience, length, style, output_json, citation_coverage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("gen_1", sid, 1, Audience.POLICYMAKERS.value, Length.NINETY_SEC.value, Style.PLAIN_ENGLISH.value, mock_new_output.model_dump_json(), 1.0)
        )
        # Version 2
        await test_db.execute(
            """INSERT INTO generations (generation_id, session_id, version, audience, length, style, output_json, citation_coverage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("gen_2", sid, 2, Audience.POLICYMAKERS.value, Length.NINETY_SEC.value, Style.PLAIN_ENGLISH.value, mock_new_output.model_dump_json(), 1.0)
        )
        # Delta for v1 -> v2
        await test_db.execute(
            """INSERT INTO deltas (delta_id, session_id, version_from, version_to, slide_number, old_text, new_text, diff_hunks, reason, provenance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("delta_1", sid, 1, 2, 2, "old", "new", '[]', "reason", '[]')
        )
        await test_db.commit()

        resp = await client.get("/api/sessions/sess_1/history")
        assert resp.status_code == 200
        data = resp.json()["data"]
        
        assert data["session_id"] == "sess_1"
        assert data["total_versions"] >= 1
        assert len(data["history"]) >= 1
        
        # Check that version 1 has no delta, version 2 has delta
        for item in data["history"]:
            if item["version"] == 1:
                assert item["delta"] is None
            elif item["version"] == 2:
                assert item["delta"] is not None
                assert "diff_hunks" in item["delta"]

    async def test_get_session_history_invalid_session_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/sessions/missing/history")
        assert resp.status_code == 404

    async def test_get_session_history_invalid_pagination_returns_400(self, client: AsyncClient):
        resp = await client.get("/api/sessions/sess_1/history?page=-1")
        assert resp.status_code == 400
