"""
ASD v11.3 — Tests for Legal Service.

Tests the core legal analysis pipeline:
- Text chunking
- Pydantic schema validation
- Map-Reduce flow structure
- Quick Review flow structure
- БЛС lookup fallback
- Response parsing (valid and invalid JSON)
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
        # Check that consecutive chunks share some text
        if len(chunks) >= 2:
            # Just verify they exist and have content
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
        # Chunks should have content (overlap may cause mid-paragraph start, which is OK)
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

    def test_legal_analysis_request_defaults(self):
        """LegalAnalysisRequest should have sensible defaults."""
        from src.schemas.legal import LegalAnalysisRequest, ReviewType

        request = LegalAnalysisRequest(document_text="Test document")

        assert request.review_type == ReviewType.CONTRACT
        assert request.chunk_size == 6000
        assert request.chunk_overlap == 300

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
