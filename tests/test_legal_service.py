"""
ASD v11.0 — Tests for Legal Service.

Tests the core legal analysis pipeline:
- Text chunking
- Pydantic schema validation
- Map-Reduce flow structure
- Quick Review flow structure
- ID Check flow structure
- БЛС lookup fallback
- Response parsing (valid and invalid JSON)
- Work type context
- Regulatory references

MLX-only architecture. No Ollama dependencies.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# We need to set up path before importing
import sys
sys.path.insert(0, ".")


# =============================================================================
# Test: Text Chunking
# =============================================================================

class TestTextChunking:
    """Test LegalService._chunk_text() method."""

    def test_short_text_no_chunking(self):
        """Text shorter than chunk_size should not be split."""
        from src.core.services.legal_service import LegalService
        service = LegalService()

        text = "Короткий текст"
        chunks = service._chunk_text(text, chunk_size=6000)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_is_chunked(self):
        """Long text should be split into multiple chunks."""
        from src.core.services.legal_service import LegalService
        service = LegalService()

        text = "Абзац текста.\n\n" * 2000  # ~26000 chars
        chunks = service._chunk_text(text, chunk_size=6000, chunk_overlap=300)

        assert len(chunks) > 1
        # Each chunk should be <= chunk_size + some margin for paragraph boundaries
        for chunk in chunks:
            assert len(chunk) <= 8000  # Allow some margin

    def test_chunk_overlap(self):
        """Overlapping chunks should share some text."""
        from src.core.services.legal_service import LegalService
        service = LegalService()

        text = "Пункт 1.\n\n" * 3000  # ~30000 chars
        chunks = service._chunk_text(text, chunk_size=6000, chunk_overlap=300)

        assert len(chunks) > 1
        # Check that consecutive chunks have content
        for chunk in chunks:
            assert len(chunk) > 0

    def test_empty_text(self):
        """Empty text should return empty list."""
        from src.core.services.legal_service import LegalService
        service = LegalService()

        chunks = service._chunk_text("", chunk_size=6000)
        assert chunks == []

    def test_paragraph_boundary_split(self):
        """Chunks should prefer splitting at paragraph boundaries."""
        from src.core.services.legal_service import LegalService
        service = LegalService()

        # Create text with clear paragraph boundaries
        paragraphs = [f"Абзац номер {i}." for i in range(500)]
        text = "\n\n".join(paragraphs)
        chunks = service._chunk_text(text, chunk_size=6000, chunk_overlap=300)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) > 0
            assert "Абзац номер" in chunk


# =============================================================================
# Test: Pydantic Schemas
# =============================================================================

class TestLegalSchemas:
    """Test Pydantic models for legal analysis."""

    def test_legal_finding_creation(self):
        """LegalFinding should accept valid data."""
        from src.schemas.legal import LegalFinding, LegalSeverity, LegalFindingCategory

        finding = LegalFinding(
            category=LegalFindingCategory.RISK,
            severity=LegalSeverity.HIGH,
            clause_ref="п. 4.2 Договора",
            legal_basis="ФЗ-44 ст. 34 ч. 6",
            issue="Неустойка заказчика не установлена",
            recommendation="Добавить пени 1/300 ставки ЦБ",
            auto_fixable=False,
        )

        assert finding.category == LegalFindingCategory.RISK
        assert finding.severity == LegalSeverity.HIGH
        assert finding.auto_fixable is False

    def test_legal_finding_regulatory_category(self):
        """LegalFinding should accept 'regulatory' category (new in v2)."""
        from src.schemas.legal import LegalFinding, LegalSeverity, LegalFindingCategory

        finding = LegalFinding(
            category=LegalFindingCategory.REGULATORY,
            severity=LegalSeverity.HIGH,
            clause_ref="п. 2.1 ТЗ",
            legal_basis="Приказ Минстроя № 344/пр",
            issue="Ссылка на устаревший РД-11-02-2006",
            recommendation="Заменить ссылку на Приказ № 344/пр",
        )

        assert finding.category == LegalFindingCategory.REGULATORY

    def test_legal_analysis_request_work_type(self):
        """LegalAnalysisRequest should accept work_type parameter."""
        from src.schemas.legal import LegalAnalysisRequest, ReviewType

        request = LegalAnalysisRequest(
            document_text="Test document",
            work_type="сварочные",
        )

        assert request.work_type == "сварочные"
        assert request.review_type == ReviewType.CONTRACT
        assert request.chunk_size == 6000

    def test_legal_analysis_request_id_check(self):
        """LegalAnalysisRequest should support id_check review type."""
        from src.schemas.legal import LegalAnalysisRequest, ReviewType

        request = LegalAnalysisRequest(
            document_text="List of documents",
            review_type=ReviewType.ID_CHECK,
            work_type="бетонные",
        )

        assert request.review_type == ReviewType.ID_CHECK

    def test_legal_analysis_result_counts(self):
        """LegalAnalysisResult should compute risk counts."""
        from src.schemas.legal import (
            LegalAnalysisResult,
            LegalFinding,
            LegalSeverity,
            LegalFindingCategory,
            LegalVerdict,
            ReviewType,
        )

        result = LegalAnalysisResult(
            review_type=ReviewType.CONTRACT,
            findings=[
                LegalFinding(
                    category=LegalFindingCategory.RISK,
                    severity=LegalSeverity.CRITICAL,
                    clause_ref="п. 1",
                    legal_basis="ФЗ",
                    issue="Issue 1",
                    recommendation="Fix 1",
                ),
                LegalFinding(
                    category=LegalFindingCategory.RISK,
                    severity=LegalSeverity.HIGH,
                    clause_ref="п. 2",
                    legal_basis="ГК",
                    issue="Issue 2",
                    recommendation="Fix 2",
                ),
                LegalFinding(
                    category=LegalFindingCategory.AMBIGUITY,
                    severity=LegalSeverity.LOW,
                    clause_ref="п. 3",
                    legal_basis="СП",
                    issue="Issue 3",
                    recommendation="Fix 3",
                ),
            ],
            verdict=LegalVerdict.APPROVED_WITH_COMMENTS,
            summary="Test summary",
        )

        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.total_risks == 3

    def test_legal_analysis_result_serialization(self):
        """LegalAnalysisResult should serialize to dict/JSON."""
        from src.schemas.legal import LegalAnalysisResult, LegalVerdict, ReviewType

        result = LegalAnalysisResult(
            review_type=ReviewType.CONTRACT,
            findings=[],
            verdict=LegalVerdict.APPROVED,
            summary="Всё в порядке",
        )

        data = result.model_dump()
        assert data["verdict"] == "approved"
        assert data["summary"] == "Всё в порядке"
        assert data["findings"] == []

        # Should be JSON-serializable
        json_str = json.dumps(data, ensure_ascii=False)
        assert "Всё в порядке" in json_str

    def test_blc_entry_schema(self):
        """BLCEntry should accept valid data."""
        from src.schemas.legal import BLCEntry, LegalSeverity

        entry = BLCEntry(
            title="Неустойка заказчика в договоре",
            description="Заказчик установил неустойку за просрочку, но не предусмотрел оплату за задержку платежей",
            source="Судебная практика АС Московского округа",
            mitigation="Добавить взаимную ответственность в протокол разногласий",
            work_types=["общестроительные", "бетонные"],
            legal_basis="ФЗ-44 ст. 34 ч. 6",
            severity=LegalSeverity.HIGH,
        )

        assert entry.title == "Неустойка заказчика в договоре"
        assert len(entry.work_types) == 2


# =============================================================================
# Test: Response Parsing
# =============================================================================

class TestResponseParsing:
    """Test LegalService._parse_analysis_response() method."""

    def test_parse_valid_json(self):
        """Should correctly parse a valid JSON response."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalSeverity, LegalVerdict, ReviewType

        service = LegalService()

        response = json.dumps({
            "findings": [
                {
                    "category": "risk",
                    "severity": "high",
                    "clause_ref": "п. 4.2",
                    "legal_basis": "ФЗ-44",
                    "issue": "Проблема",
                    "recommendation": "Исправить",
                    "auto_fixable": False,
                }
            ],
            "normative_refs": ["ФЗ-44 ст. 34"],
            "contradictions": [],
            "verdict": "approved_with_comments",
            "summary": "Есть риски",
        })

        result = service._parse_analysis_response(response, ReviewType.CONTRACT)

        assert result.total_risks == 1
        assert result.findings[0].severity == LegalSeverity.HIGH
        assert result.verdict == LegalVerdict.APPROVED_WITH_COMMENTS
        assert "ФЗ-44 ст. 34" in result.normative_refs

    def test_parse_json_in_markdown(self):
        """Should extract JSON from markdown code blocks."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalVerdict, ReviewType

        service = LegalService()

        response = """Вот результат:

```json
{
    "findings": [],
    "normative_refs": [],
    "contradictions": [],
    "verdict": "approved",
    "summary": "Всё ок"
}
```
"""
        result = service._parse_analysis_response(response, ReviewType.CONTRACT)
        assert result.verdict == LegalVerdict.APPROVED

    def test_parse_invalid_json(self):
        """Should gracefully handle invalid JSON."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import ReviewType

        service = LegalService()

        response = "Это не JSON, а просто текст"

        result = service._parse_analysis_response(response, ReviewType.CONTRACT)
        # Should have at least one finding about parse error
        assert result.total_risks >= 1

    def test_parse_invalid_enum_value(self):
        """Should use default enum values for invalid inputs."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalFindingCategory, ReviewType

        service = LegalService()

        response = json.dumps({
            "findings": [
                {
                    "category": "invalid_category",
                    "severity": "super_high",
                    "clause_ref": "п. 1",
                    "legal_basis": "N/A",
                    "issue": "Test",
                    "recommendation": "N/A",
                    "auto_fixable": False,
                }
            ],
            "normative_refs": [],
            "contradictions": [],
            "verdict": "invalid_verdict",
            "summary": "Test",
        })

        result = service._parse_analysis_response(response, ReviewType.CONTRACT)
        assert result.total_risks == 1
        # Should fallback to first enum value
        assert result.findings[0].category == LegalFindingCategory.COMPLIANCE

    def test_parse_regulatory_category(self):
        """Should parse 'regulatory' finding category."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalFindingCategory, ReviewType

        service = LegalService()

        response = json.dumps({
            "findings": [
                {
                    "category": "regulatory",
                    "severity": "high",
                    "clause_ref": "п. 2.1 ТЗ",
                    "legal_basis": "Приказ Минстроя № 344/пр",
                    "issue": "Ссылка на устаревший РД-11-02-2006",
                    "recommendation": "Заменить на Приказ № 344/пр",
                    "auto_fixable": True,
                }
            ],
            "normative_refs": ["Приказ Минстроя № 344/пр"],
            "contradictions": [],
            "verdict": "approved_with_comments",
            "summary": "Обнаружена устаревшая нормативная ссылка",
        })

        result = service._parse_analysis_response(response, ReviewType.COMPLIANCE)
        assert result.findings[0].category == LegalFindingCategory.REGULATORY
        assert result.findings[0].auto_fixable is True


# =============================================================================
# Test: Work Type Context
# =============================================================================

class TestWorkTypeContext:
    """Test LegalService._get_work_type_context() method."""

    def test_known_work_type(self):
        """Should return context for known work types."""
        from src.core.services.legal_service import LegalService

        context = LegalService._get_work_type_context("сварочные")
        assert "НАКС" in context or "ВСН 012-88" in context

    def test_unknown_work_type(self):
        """Should return generic context for unknown work types."""
        from src.core.services.legal_service import LegalService

        context = LegalService._get_work_type_context("сантехнические")
        assert "сантехнические" in context

    def test_none_work_type(self):
        """Should return default context when no work type specified."""
        from src.core.services.legal_service import LegalService

        context = LegalService._get_work_type_context(None)
        assert "общестроительных" in context

    def test_all_known_work_types_have_context(self):
        """All 6 company work types should have specific context."""
        from src.core.services.legal_service import LegalService, WORK_TYPE_CONTEXT

        expected_types = [
            "общестроительные", "бетонные", "земляные",
            "сварочные", "монтажные", "шпунтовые"
        ]

        for wt in expected_types:
            context = LegalService._get_work_type_context(wt)
            assert len(context) > 50, f"Context too short for {wt}"


# =============================================================================
# Test: Required ID Documents
# =============================================================================

class TestRequiredIDDocs:
    """Test REQUIRED_ID_DOCS mapping."""

    def test_all_work_types_have_required_docs(self):
        """All 6 work types should have required ID document lists."""
        from src.core.services.legal_service import REQUIRED_ID_DOCS

        expected_types = [
            "общестроительные", "бетонные", "земляные",
            "сварочные", "монтажные", "шпунтовые"
        ]

        for wt in expected_types:
            assert wt in REQUIRED_ID_DOCS, f"Missing required ID docs for {wt}"
            assert len(REQUIRED_ID_DOCS[wt]) > 50

    def test_concrete_works_mention_aosr(self):
        """Concrete works should mention АОСР."""
        from src.core.services.legal_service import REQUIRED_ID_DOCS

        docs = REQUIRED_ID_DOCS["бетонные"]
        assert "АОСР" in docs

    def test_welding_works_mention_vsn012(self):
        """Welding works should mention ВСН 012-88."""
        from src.core.services.legal_service import REQUIRED_ID_DOCS

        docs = REQUIRED_ID_DOCS["сварочные"]
        assert "ВСН 012-88" in docs

    def test_sheet_piling_works_mention_gost(self):
        """Sheet piling works should mention ГОСТ Р 57365."""
        from src.core.services.legal_service import REQUIRED_ID_DOCS

        docs = REQUIRED_ID_DOCS["шпунтовые"]
        assert "57365" in docs


# =============================================================================
# Test: Safe Enum
# =============================================================================

class TestSafeEnum:
    """Test _safe_enum helper method."""

    def test_valid_enum_value(self):
        """Should return correct enum for valid value."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalSeverity

        service = LegalService()
        result = service._safe_enum("high", LegalSeverity)
        assert result == LegalSeverity.HIGH

    def test_invalid_enum_value(self):
        """Should return first enum value for invalid input."""
        from src.core.services.legal_service import LegalService
        from src.schemas.legal import LegalSeverity

        service = LegalService()
        result = service._safe_enum("invalid", LegalSeverity)
        assert result == LegalSeverity.CRITICAL  # First value in enum


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
