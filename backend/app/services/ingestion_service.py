"""
IngestionService - orchestrates the full parse → chunk → embed → store pipeline.
Uses lazy imports for heavy deps (Docling, subprocess) to keep app startup fast.
"""

import asyncio
import hashlib
import os
import subprocess
import tempfile
import uuid

import aiosqlite

from app.config import settings
from app.exceptions import ParseError, UnsupportedFormatError
from app.models.chunk import Chunk
from app.services.chunking_service import ChunkingService

_SUPPORTED_EXTENSIONS = {".pdf", ".tex", ".latex"}
_PDF_MAGIC = b"%PDF"


class IngestionService:
    """
    Orchestrates: detect_format → parse → chunk → embed → store.
    Background tasks call process_paper() which manages its own DB connection.
    """

    def __init__(self):
        self._chunking_service = ChunkingService()

    # ── Format detection ──────────────────────────────────────────────────────

    def detect_format(self, file_bytes: bytes, filename: str) -> str:
        """
        Identify file format from extension and magic bytes.

        Returns:
            'pdf' or 'latex'

        Raises:
            UnsupportedFormatError: if the file type is not supported.
        """
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf" or file_bytes[:4] == _PDF_MAGIC:
            return "pdf"
        if ext in (".tex", ".latex"):
            return "latex"

        raise UnsupportedFormatError(
            f"Unsupported format: {filename}. "
            f"Accepted: .pdf, .tex, .latex"
        )

    def compute_sha256(self, file_bytes: bytes) -> str:
        """Return the SHA-256 hex digest of file_bytes."""
        return hashlib.sha256(file_bytes).hexdigest()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _get_docling_converter(self):
        # We don't use docling anymore due to environment constraints.
        pass

    def parse_pdf(self, file_bytes: bytes) -> str:
        """
        Convert a PDF to Markdown using PyMuPDF4LLM.
        Provides high-accuracy layout retention (tables, multi-column) without heavy ML dependencies.
        """
        import tempfile
        import pymupdf4llm

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            markdown = pymupdf4llm.to_markdown(tmp_path)
        except Exception as e:
            raise ParseError(f"PyMuPDF4LLM failed to parse PDF: {e}")
        finally:
            os.unlink(tmp_path)

        if not markdown or not markdown.strip():
            raise ParseError("PyMuPDF4LLM produced empty output for this PDF.")

        return markdown

    def parse_latex(self, file_bytes: bytes) -> str:
        """
        Convert a LaTeX/Beamer file to Markdown using pandoc.
        Falls back to a pure-Python LaTeX stripper when pandoc is not installed.

        Raises:
            ParseError: if both pandoc and the fallback produce empty output.
        """
        import shutil
        if shutil.which("pandoc"):
            return self._parse_latex_pandoc(file_bytes)
        return self._parse_latex_fallback(file_bytes)

    def _parse_latex_pandoc(self, file_bytes: bytes) -> str:
        """Parse LaTeX via pandoc (preferred path)."""
        with tempfile.NamedTemporaryFile(suffix=".tex", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            proc = subprocess.run(
                ["pandoc", "-s", "-t", "markdown", "--wrap=none", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            os.unlink(tmp_path)

        if proc.returncode != 0:
            raise ParseError(
                f"pandoc failed (exit {proc.returncode}): {proc.stderr.strip()}"
            )

        return proc.stdout

    def _parse_latex_fallback(self, file_bytes: bytes) -> str:
        """
        Pure-Python fallback: strips LaTeX commands and extracts readable text.
        Handles Beamer frames, sections, math blocks (preserved as-is), and plain paragraphs.
        Good enough for chunking and embedding when pandoc is absent.
        """
        import re
        text = file_bytes.decode("utf-8", errors="replace")
        output_lines: list[str] = []

        # Extract sections as headings
        for m in re.finditer(r'\\(?:section|frametitle)\{([^}]+)\}', text):
            output_lines.append(f"\n## {m.group(1)}\n")

        # Extract frame environments for Beamer
        for m in re.finditer(
            r'\\begin\{frame\}(?:\{([^}]*)\})?(.*?)\\end\{frame\}',
            text, re.DOTALL
        ):
            title = m.group(1) or ""
            body = m.group(2) or ""
            if title.strip():
                output_lines.append(f"\n### {title.strip()}\n")
            output_lines.append(body)

        # If no frames found (regular article), strip preamble up to \begin{document}
        if not any("###" in l for l in output_lines):
            doc_match = re.search(r'\\begin\{document\}(.*)\\end\{document\}', text, re.DOTALL)
            raw = doc_match.group(1) if doc_match else text

            # Preserve math blocks
            math_placeholder = {}
            def _save_math(m: re.Match) -> str:
                key = f"MATHBLOCK{len(math_placeholder)}"
                math_placeholder[key] = m.group(0)
                return key
            raw = re.sub(r'\$\$.*?\$\$', _save_math, raw, flags=re.DOTALL)
            raw = re.sub(r'\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}',
                         _save_math, raw, flags=re.DOTALL)
            raw = re.sub(r'\$[^$\n]+?\$', _save_math, raw)

            # Strip LaTeX commands and environments we don't need
            raw = re.sub(r'\\(?:usepackage|documentclass|newcommand|renewcommand|setbeamer\w*|usetheme|usefonttheme|usecolortheme)\{[^}]*\}(?:\[[^\]]*\])?', '', raw)
            raw = re.sub(r'\\begin\{[^}]+\}|\\end\{[^}]+\}', '', raw)
            raw = re.sub(r'\\(?:textbf|textit|emph|text|mbox|hbox)\{([^}]+)\}', r'\1', raw)
            raw = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\{([^}]*)\}', r'\1', raw)
            raw = re.sub(r'\\[a-zA-Z]+\*?', '', raw)
            raw = re.sub(r'\{|\}', '', raw)
            raw = re.sub(r'%.*$', '', raw, flags=re.MULTILINE)  # strip comments

            # Restore math blocks
            for key, val in math_placeholder.items():
                raw = raw.replace(key, val)

            output_lines.append(raw)

        result = "\n".join(output_lines)
        # Collapse excessive blank lines
        result = re.sub(r'\n{3,}', '\n\n', result).strip()

        if not result:
            raise ParseError("LaTeX fallback extractor produced empty output.")

        return result

    # ── Full pipeline ─────────────────────────────────────────────────────────

    async def process_paper(
        self,
        file_bytes: bytes,
        filename: str,
        paper_id: str,
    ) -> None:
        """
        Full ingestion pipeline run as a background task.
        Opens its own DB connection (cannot use FastAPI DI in background tasks).
        Updates paper status in SQLite throughout.
        """
        async with aiosqlite.connect(settings.sqlite_db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")
            try:
                # 0. Detect format & presentation heuristics
                fmt = self.detect_format(file_bytes, filename)
                is_presentation = False
                if fmt == "pdf":
                    import fitz
                    try:
                        doc = fitz.open(stream=file_bytes, filetype="pdf")
                        if len(doc) > 0:
                            rect = doc[0].rect
                            if rect.width > rect.height:
                                is_presentation = True
                        doc.close()
                    except Exception:
                        pass
                
                await self._update_status(db, paper_id, "processing", is_presentation=is_presentation)

                # 1. Parse
                markdown = (
                    self.parse_pdf(file_bytes)
                    if fmt == "pdf"
                    else self.parse_latex(file_bytes)
                )

                # 2. Chunk
                chunks: list[Chunk] = self._chunking_service.chunk(markdown, paper_id)

                # 3. Embed (run in thread to avoid blocking the event loop)
                from app.services.embedding_service import EmbeddingService  # noqa: PLC0415
                from app.services.qdrant_service import QdrantService         # noqa: PLC0415

                embedding_svc = EmbeddingService()
                qdrant_svc = QdrantService()

                embedded = await asyncio.to_thread(embedding_svc.embed_chunks, chunks)

                # 4. Store in Qdrant
                await asyncio.to_thread(qdrant_svc.upsert_chunks, embedded)

                # 5. Store chunk metadata in SQLite
                await self._store_chunks(db, chunks)

                await self._update_status(
                    db, paper_id, "ready", chunk_count=len(chunks)
                )

            except Exception as exc:
                await self._update_status(
                    db, paper_id, "failed", error_msg=str(exc)
                )
                raise

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _update_status(
        self,
        db: aiosqlite.Connection,
        paper_id: str,
        status: str,
        chunk_count: int = 0,
        error_msg: str | None = None,
        is_presentation: bool | None = None,
    ) -> None:
        if is_presentation is not None:
            await db.execute(
                """UPDATE papers
                   SET status = ?, chunk_count = ?, error_msg = ?, is_presentation = ?
                   WHERE paper_id = ?""",
                (status, chunk_count, error_msg, int(is_presentation), paper_id),
            )
        else:
            await db.execute(
                """UPDATE papers
                   SET status = ?, chunk_count = ?, error_msg = ?
                   WHERE paper_id = ?""",
                (status, chunk_count, error_msg, paper_id),
            )
        await db.commit()

    async def _store_chunks(
        self, db: aiosqlite.Connection, chunks: list[Chunk]
    ) -> None:
        rows = [
            (
                c.chunk_id, c.paper_id, c.page_number, c.section_title,
                c.block_index, c.text,
                int(c.contains_math), int(c.has_figure), c.figure_caption,
            )
            for c in chunks
        ]
        await db.executemany(
            """INSERT INTO chunks
               (chunk_id, paper_id, page_number, section_title, block_index,
                text, contains_math, has_figure, figure_caption)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await db.commit()
