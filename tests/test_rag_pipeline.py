"""
ASD v12.0 — Tests for Package 3: Parser, Document Repository, RAG Pipeline.

Tests cover:
  - File type detection
  - StreamingParser: batch mode, checkpoint/resume
  - ParsedChunk and ParseResult data classes
  - Document auto-classification
  - RAG context formatting (unit tests, no DB required)
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from src.core.parser_engine import (
    StreamingParser,
    detect_file_type,
    FileType,
    ParseMethod,
    ParsedChunk,
    ParseResult,
    Checkpoint,
)


# =============================================================================
# File Type Detection
# =============================================================================

class TestFileTypeDetection:
    """detect_file_type: расширения и magic bytes."""

    def test_pdf_extension(self):
        assert detect_file_type("document.pdf") == FileType.PDF
        assert detect_file_type("path/to/file.PDF") == FileType.PDF

    def test_docx_extension(self):
        assert detect_file_type("contract.docx") == FileType.DOCX

    def test_xlsx_extension(self):
        assert detect_file_type("estimate.xlsx") == FileType.XLSX
        assert detect_file_type("old.xls") == FileType.XLSX

    def test_image_extensions(self):
        assert detect_file_type("scan.png") == FileType.IMAGE
        assert detect_file_type("photo.jpg") == FileType.IMAGE
        assert detect_file_type("photo.jpeg") == FileType.IMAGE
        assert detect_file_type("scan.tiff") == FileType.IMAGE
        assert detect_file_type("scan.tif") == FileType.IMAGE
        assert detect_file_type("img.bmp") == FileType.IMAGE

    def test_dwg_extension(self):
        assert detect_file_type("drawing.dwg") == FileType.DWG

    def test_unknown_extension(self):
        assert detect_file_type("data.bin") == FileType.UNKNOWN
        assert detect_file_type("file") == FileType.UNKNOWN

    def test_magic_bytes_pdf(self):
        """Проверка реального PDF по magic bytes."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as f:
            f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
            path = f.name
        try:
            assert detect_file_type(path) == FileType.PDF
        finally:
            os.unlink(path)

    def test_magic_bytes_png(self):
        with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            path = f.name
        try:
            assert detect_file_type(path) == FileType.IMAGE
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        assert detect_file_type("/nonexistent/file.xyz") == FileType.UNKNOWN


# =============================================================================
# ParsedChunk & ParseResult
# =============================================================================

class TestParsedChunk:
    """ParsedChunk: создание, поля, confidence."""

    def test_defaults(self):
        c = ParsedChunk(content="Hello")
        assert c.content == "Hello"
        assert c.page == 1
        assert c.method == ParseMethod.PYMFIT_TEXT.value
        assert c.confidence == 1.0
        assert not c.ocr_fallback

    def test_ocr_marker(self):
        c = ParsedChunk(content="Scanned", ocr_fallback=True, confidence=0.7)
        assert c.ocr_fallback
        assert c.confidence == 0.7

    def test_metadata(self):
        c = ParsedChunk(
            content="Test",
            metadata={"source": "scan.pdf", "dpi": 150},
        )
        assert c.metadata["source"] == "scan.pdf"


class TestParseResult:
    """ParseResult: агрегация чанков."""

    def test_success_flag(self):
        r = ParseResult(
            file_path="test.pdf",
            file_type=FileType.PDF,
            chunks=[ParsedChunk(content="OK")],
            total_pages=1,
            total_chars=2,
            methods_used=["pymupdf_text"],
            duration_sec=0.5,
        )
        assert r.success
        assert r.full_text == "OK"

    def test_with_errors(self):
        r = ParseResult(
            file_path="bad.pdf",
            file_type=FileType.PDF,
            chunks=[],
            total_pages=0,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            errors=["Corrupt file"],
        )
        assert not r.success
        assert len(r.errors) == 1

    def test_full_text_multipage(self):
        r = ParseResult(
            file_path="multi.pdf",
            file_type=FileType.PDF,
            chunks=[
                ParsedChunk(content="Page 1 text", page=1),
                ParsedChunk(content="Page 2 text", page=2),
            ],
            total_pages=2,
            total_chars=23,
            methods_used=["pymupdf_text"],
            duration_sec=1.0,
        )
        assert "Page 1 text" in r.full_text
        assert "Page 2 text" in r.full_text
        assert "PAGE BREAK" in r.full_text


# =============================================================================
# StreamingParser
# =============================================================================

class TestStreamingParser:
    """StreamingParser: инициализация, чекпоинты."""

    def test_init_creates_checkpoint_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = StreamingParser(checkpoint_dir=os.path.join(tmpdir, "chk"))
            assert os.path.isdir(parser._checkpoint_dir)

    def test_checkpoint_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = StreamingParser(checkpoint_dir=tmpdir)
            cp = Checkpoint(
                batch_id="abc123",
                file_index=5,
                page_number=42,
                processed_files=["f1.pdf", "f2.pdf"],
                total_files=10,
                created_at="2026-04-28T00:00:00",
            )
            parser._save_checkpoint(cp)

            loaded = parser._load_checkpoint("abc123")
            assert loaded is not None
            assert loaded.batch_id == "abc123"
            assert loaded.file_index == 5
            assert loaded.page_number == 42
            assert loaded.total_files == 10

    def test_checkpoint_clear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = StreamingParser(checkpoint_dir=tmpdir)
            cp = Checkpoint("xyz", 0, 0, [], 5, "now")
            parser._save_checkpoint(cp)
            assert parser._checkpoint_path("xyz").exists()

            parser._clear_checkpoint("xyz")
            assert not parser._checkpoint_path("xyz").exists()

    def test_load_nonexistent_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = StreamingParser(checkpoint_dir=tmpdir)
            assert parser._load_checkpoint("nonexistent") is None

    def test_make_batch_id_deterministic(self):
        parser = StreamingParser()
        files = ["a.pdf", "b.pdf", "c.docx"]
        id1 = parser._make_batch_id(files)
        id2 = parser._make_batch_id(list(reversed(files)))  # Сортировка внутри
        assert id1 == id2  # Детерминирован

    def test_file_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content for hashing")
            path = f.name
        try:
            h = StreamingParser._file_hash(path)
            assert len(h) == 16  # sha256 truncated
            # Повторный вызов даёт тот же хеш
            assert StreamingParser._file_hash(path) == h
        finally:
            os.unlink(path)

    def test_parse_file_unknown_type(self):
        """parse_file возвращает результат даже для неизвестного типа."""
        parser = StreamingParser()
        import asyncio
        async def run():
            return await parser.parse_file("/dev/null")
        result = asyncio.run(run())
        assert result.file_type == FileType.UNKNOWN
        # Должен быть хотя бы один чанк с ошибкой или unsupported
        assert len(result.chunks) >= 1


# =============================================================================
# Document Auto-Classification (from RAG Pipeline logic)
# =============================================================================

class TestDocumentClassification:
    """Автоклассификация документов по имени файла и содержимому."""

    def _get_classifier(self):
        from src.core.rag_pipeline import RAGPipeline
        return RAGPipeline()

    def test_classify_ks2(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/КС-2_№1.pdf",
            file_type=FileType.PDF,
            chunks=[],
            total_pages=1,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            metadata={"filename": "КС-2_№1.pdf"},
        )
        assert pipeline._classify_document(result) == "KS2"

    def test_classify_aosr(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/АОСР_фундамент.pdf",
            file_type=FileType.PDF,
            chunks=[],
            total_pages=0,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            metadata={"filename": "АОСР_фундамент.pdf"},
        )
        assert pipeline._classify_document(result) == "AOSR"

    def test_classify_contract(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/Договор_подряда_123.docx",
            file_type=FileType.DOCX,
            chunks=[],
            total_pages=0,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            metadata={"filename": "Договор_подряда_123.docx"},
        )
        assert pipeline._classify_document(result) == "Contract"

    def test_classify_smeta_by_filename(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/ЛСР_01-01.xlsx",
            file_type=FileType.XLSX,
            chunks=[],
            total_pages=0,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            metadata={"filename": "ЛСР_01-01.xlsx"},
        )
        assert pipeline._classify_document(result) == "Smeta"

    def test_classify_smeta_by_content(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/unknown.xlsx",
            file_type=FileType.XLSX,
            chunks=[ParsedChunk(
                content="ЛОКАЛЬНЫЙ СМЕТНЫЙ РАСЧЁТ № 1\nСметная стоимость: 1 500 000 руб.",
                page=1,
            )],
            total_pages=1,
            total_chars=60,
            methods_used=[],
            duration_sec=0,
        )
        assert pipeline._classify_document(result) == "Smeta"

    def test_classify_ppr(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/ППР_монтаж.pdf",
            file_type=FileType.PDF,
            chunks=[],
            total_pages=0,
            total_chars=0,
            methods_used=[],
            duration_sec=0,
            metadata={"filename": "ППР_монтаж.pdf"},
        )
        assert pipeline._classify_document(result) == "PPR"

    def test_classify_unknown(self):
        pipeline = self._get_classifier()
        result = ParseResult(
            file_path="/data/mystery.xyz",
            file_type=FileType.PDF,
            chunks=[ParsedChunk(content="Some random text", page=1)],
            total_pages=1,
            total_chars=17,
            methods_used=[],
            duration_sec=0,
        )
        assert pipeline._classify_document(result) == "unknown"


# =============================================================================
# RAG Context Formatting
# =============================================================================

class TestRAGContextFormatting:
    """Форматирование RAG-контекста для инъекции в промпты."""

    def _get_pipeline(self):
        from src.core.rag_pipeline import RAGPipeline
        return RAGPipeline()

    def test_format_empty(self):
        pipeline = self._get_pipeline()
        result = pipeline._format_context(
            vector_results=[],
            graph_context=[],
            bls_context="",
            agent="legal",
            query="test",
        )
        assert result == ""

    def test_format_vector_results(self):
        pipeline = self._get_pipeline()
        results = [
            {
                "content": "Текст договора о неустойке...",
                "page": 5,
                "doc_id": 1,
                "filename": "contract.pdf",
                "doc_type": "Contract",
                "score": 0.123,
            }
        ]
        ctx = pipeline._format_context(
            vector_results=results,
            graph_context=[],
            bls_context="",
            agent="legal",
            query="неустойка",
        )
        assert "contract.pdf" in ctx
        assert "Contract" in ctx
        assert "неустойка" in ctx
        assert "стр. 5" in ctx

    def test_format_graph_context(self):
        pipeline = self._get_pipeline()
        graph_ctx = [
            {"id": "1", "data": {"filename": "doc1.pdf", "doc_type": "Contract"}},
            {"id": "2", "data": {"filename": "doc2.pdf", "doc_type": "AOSR"}},
        ]
        ctx = pipeline._format_context(
            vector_results=[],
            graph_context=graph_ctx,
            bls_context="",
            agent="pto",
            query="test",
        )
        assert "doc1.pdf" in ctx
        assert "doc2.pdf" in ctx

    def test_format_bls_context(self):
        pipeline = self._get_pipeline()
        ctx = pipeline._format_context(
            vector_results=[],
            graph_context=[],
            bls_context="⚠️ ЛОВУШКИ:\n  • Риск неустойки",
            agent="legal",
            query="test",
        )
        assert "ЛОВУШКИ" in ctx

    def test_format_all_combined(self):
        pipeline = self._get_pipeline()
        vector = [{"content": "Текст", "page": 1, "doc_id": 1, "filename": "f.pdf", "doc_type": "Doc", "score": 0.1}]
        graph = [{"id": "1", "data": {"filename": "f.pdf"}}]
        bls = "⚠️ TRAP"

        ctx = pipeline._format_context(vector, graph, bls, "legal", "q")
        assert "f.pdf" in ctx
        assert "TRAP" in ctx
        assert "СВЯЗАННЫЕ" in ctx or "ГРАФ" in ctx.upper()
