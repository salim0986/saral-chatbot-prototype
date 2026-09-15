"""
TDD - Phase 1d: Ingest API endpoint tests.
Uses conftest.py fixtures: in-memory SQLite + FastAPI dependency override.
IngestionService.process_paper is mocked to avoid real embedding/Qdrant calls.
"""

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

PDF_BYTES = b"%PDF-1.7\n%fake pdf content for unit testing"
TEX_BYTES = b"\\documentclass{article}\\begin{document}Hello\\end{document}"


@pytest.fixture
def pdf_file():
    return {"file": ("paper.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}


@pytest.fixture
def tex_file():
    return {"file": ("slides.tex", io.BytesIO(TEX_BYTES), "text/x-tex")}


class TestUploadPaper:
    """POST /api/papers - validates HTTP contract without real ingestion."""

    @patch("app.services.ingestion_service.IngestionService.process_paper", new_callable=AsyncMock)
    async def test_upload_pdf_returns_202(self, mock_process, client, pdf_file):
        resp = await client.post("/api/papers", files=pdf_file)
        assert resp.status_code == 202

    @patch("app.services.ingestion_service.IngestionService.process_paper", new_callable=AsyncMock)
    async def test_upload_returns_paper_id_in_body(self, mock_process, client, pdf_file):
        resp = await client.post("/api/papers", files=pdf_file)
        body = resp.json()
        assert body["status"] == "success"
        assert "paper_id" in body["data"]
        # paper_id must be a non-empty string (UUID)
        assert len(body["data"]["paper_id"]) > 0

    @patch("app.services.ingestion_service.IngestionService.process_paper", new_callable=AsyncMock)
    async def test_upload_tex_returns_202(self, mock_process, client, tex_file):
        resp = await client.post("/api/papers", files=tex_file)
        assert resp.status_code == 202

    @patch("app.services.ingestion_service.IngestionService.process_paper", new_callable=AsyncMock)
    async def test_upload_duplicate_returns_200(self, mock_process, client, pdf_file, test_db):
        # Pre-seed a paper with the same SHA256
        import hashlib
        sha256 = hashlib.sha256(PDF_BYTES).hexdigest()
        existing_id = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (existing_id, "paper.pdf", sha256, "ready"),
        )
        await test_db.commit()

        resp = await client.post("/api/papers", files=pdf_file)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["paper_id"] == existing_id
        assert body["data"]["duplicate"] is True

    async def test_file_over_50mb_returns_413(self, client):
        big_file = {"file": ("big.pdf", io.BytesIO(b"x" * (51 * 1024 * 1024)), "application/pdf")}
        resp = await client.post("/api/papers", files=big_file)
        assert resp.status_code == 413

    async def test_unsupported_mime_returns_415(self, client):
        bad_file = {
            "file": ("doc.docx", io.BytesIO(b"PK\x03\x04"), "application/vnd.openxmlformats")
        }
        resp = await client.post("/api/papers", files=bad_file)
        assert resp.status_code == 415


class TestGetPaperStatus:
    """GET /api/papers/{paper_id}"""

    async def test_existing_paper_returns_status(self, client, test_db):
        pid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status, chunk_count) "
            "VALUES (?,?,?,?,?)",
            (pid, "test.pdf", "abc123", "ready", 42),
        )
        await test_db.commit()

        resp = await client.get(f"/api/papers/{pid}")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ready"
        assert data["chunk_count"] == 42

    async def test_unknown_paper_returns_404(self, client):
        resp = await client.get("/api/papers/does-not-exist")
        assert resp.status_code == 404

    async def test_processing_paper_returns_correct_status(self, client, test_db):
        pid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (pid, "test.pdf", "def456", "processing"),
        )
        await test_db.commit()

        resp = await client.get(f"/api/papers/{pid}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "processing"


class TestListChunks:
    """GET /api/papers/{paper_id}/chunks"""

    async def test_returns_chunks_for_known_paper(self, client, test_db):
        pid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO papers (paper_id, filename, sha256_hash, status) VALUES (?,?,?,?)",
            (pid, "test.pdf", "ghi789", "ready"),
        )
        cid = str(uuid.uuid4())
        await test_db.execute(
            "INSERT INTO chunks (chunk_id, paper_id, page_number, section_title, "
            "block_index, text, contains_math, has_figure) VALUES (?,?,?,?,?,?,?,?)",
            (cid, pid, 1, "Introduction", 0, "Some text", 0, 0),
        )
        await test_db.commit()

        resp = await client.get(f"/api/papers/{pid}/chunks")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_id"] == cid

    async def test_unknown_paper_chunks_returns_404(self, client):
        resp = await client.get("/api/papers/nope/chunks")
        assert resp.status_code == 404
