"""
TDD - Phase 1a: Format detection & parsing tests.
Docling and pandoc are mocked - tests run without heavy dependencies.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PDF_MAGIC = b"%PDF-1.7\n%...fake pdf content for testing"
TEX_CONTENT = (FIXTURES / "sample.tex").read_bytes()


class TestFormatDetection:
    """IngestionService.detect_format() must correctly identify file types."""

    def setup_method(self):
        from app.services.ingestion_service import IngestionService
        self.svc = IngestionService()

    def test_pdf_magic_bytes_detected(self):
        assert self.svc.detect_format(PDF_MAGIC, "paper.pdf") == "pdf"

    def test_pdf_extension_detected(self):
        assert self.svc.detect_format(b"some bytes", "paper.pdf") == "pdf"

    def test_tex_extension_detected(self):
        assert self.svc.detect_format(TEX_CONTENT, "slides.tex") == "latex"

    def test_latex_extension_detected(self):
        assert self.svc.detect_format(TEX_CONTENT, "doc.latex") == "latex"

    def test_unsupported_format_raises(self):
        from app.exceptions import UnsupportedFormatError
        svc = self.svc
        with pytest.raises(UnsupportedFormatError):
            svc.detect_format(b"some bytes", "document.docx")

    def test_unsupported_format_includes_filename_in_message(self):
        from app.exceptions import UnsupportedFormatError
        with pytest.raises(UnsupportedFormatError, match="document.pptx"):
            self.svc.detect_format(b"bytes", "document.pptx")


class TestParsePDF:
    """IngestionService.parse_pdf() — PyMuPDF4LLM is mocked."""

    @patch("pymupdf4llm.to_markdown")
    def test_parse_pdf_returns_string(self, mock_to_markdown):
        mock_to_markdown.return_value = "# Title\n\nSome text."

        from app.services.ingestion_service import IngestionService
        svc = IngestionService()
        result = svc.parse_pdf(PDF_MAGIC)

        assert isinstance(result, str)
        assert len(result) > 0

    @patch("pymupdf4llm.to_markdown")
    def test_parse_pdf_raises_on_empty_output(self, mock_to_markdown):
        mock_to_markdown.return_value = ""

        from app.exceptions import ParseError
        from app.services.ingestion_service import IngestionService
        with pytest.raises(ParseError, match="empty"):
            IngestionService().parse_pdf(PDF_MAGIC)


class TestParseLaTeX:
    """IngestionService.parse_latex() - pandoc subprocess is mocked."""

    @patch("app.services.ingestion_service.subprocess.run")
    def test_parse_latex_returns_markdown(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="# Introduction\n\nSome text with $E = mc^2$.",
            stderr="",
        )
        from app.services.ingestion_service import IngestionService
        result = IngestionService().parse_latex(TEX_CONTENT)
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("app.services.ingestion_service.subprocess.run")
    def test_parse_latex_raises_on_pandoc_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="pandoc: unknown option",
        )
        from app.exceptions import ParseError
        from app.services.ingestion_service import IngestionService
        with pytest.raises(ParseError, match="pandoc"):
            IngestionService().parse_latex(TEX_CONTENT)


class TestSHA256Duplicate:
    """IngestionService.compute_sha256() must return a consistent hex digest."""

    def test_same_bytes_same_hash(self):
        from app.services.ingestion_service import IngestionService
        svc = IngestionService()
        h1 = svc.compute_sha256(b"hello world")
        h2 = svc.compute_sha256(b"hello world")
        assert h1 == h2

    def test_different_bytes_different_hash(self):
        from app.services.ingestion_service import IngestionService
        svc = IngestionService()
        assert svc.compute_sha256(b"foo") != svc.compute_sha256(b"bar")

    def test_hash_is_hex_string(self):
        from app.services.ingestion_service import IngestionService
        h = IngestionService().compute_sha256(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
