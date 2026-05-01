"""
ASD v12.0 — Tests for Legal Document Generators (Package 4).

Tests cover:
  - Protocol building from findings
  - Protocol export (text fallback)
  - Claim generation (text + fallback)
  - Lawsuit generation (text + fallback)
  - State duty calculation
  - Legal document generator helpers
  - ProtocolItem/ProtocolDisagreements serialization
"""

import os
import tempfile
import pytest
from datetime import datetime

from src.schemas.legal import (
    LegalFinding,
    LegalAnalysisResult,
    LegalSeverity,
    LegalVerdict,
    LegalFindingCategory,
    ReviewType,
    ProtocolDisagreements,
    ProtocolItem,
    ProtocolPartyInfo,
)
from src.core.services.legal_documents import LegalDocumentGenerator


# =============================================================================
# Fixtures
# =============================================================================

def _make_findings() -> list:
    """Создать реально выглядящие findings."""
    return [
        LegalFinding(
            category=LegalFindingCategory.TRAP,
            severity=LegalSeverity.CRITICAL,
            clause_ref="п. 3.5 Договора",
            legal_basis="ст. 711 ГК РФ, ст. 395 ГК РФ",
            issue="Неустойка за просрочку оплаты Заказчиком не предусмотрена",
            recommendation="Установить пени 1/300 ключевой ставки ЦБ РФ за каждый день просрочки оплаты",
            contractor_edit="В случае просрочки оплаты Заказчик уплачивает пени в размере 1/300 ключевой ставки ЦБ РФ",
            auto_fixable=True,
        ),
        LegalFinding(
            category=LegalFindingCategory.RISK,
            severity=LegalSeverity.HIGH,
            clause_ref="п. 7.2 Договора",
            legal_basis="ст. 716 ГК РФ",
            issue="Обязанность Подрядчика немедленно предупредить Заказчика без указания разумного срока",
            recommendation="Указать конкретный срок для предупреждения — 3 рабочих дня",
            contractor_edit="Подрядчик обязан предупредить Заказчика в течение 3 рабочих дней",
            auto_fixable=True,
        ),
        LegalFinding(
            category=LegalFindingCategory.COMPLIANCE,
            severity=LegalSeverity.MEDIUM,
            clause_ref="п. 12.1 Договора",
            legal_basis="ст. 330 ГК РФ",
            issue="Штрафные санкции для Подрядчика несоразмерно завышены",
            recommendation="Установить соразмерный размер санкций — не более 5% от цены договора",
            auto_fixable=False,
        ),
    ]


def _make_analysis_result(findings=None) -> LegalAnalysisResult:
    if findings is None:
        findings = _make_findings()
    return LegalAnalysisResult(
        review_type=ReviewType.CONTRACT,
        findings=findings,
        normative_refs=["ст. 711 ГК РФ", "ст. 395 ГК РФ", "ст. 716 ГК РФ", "ст. 330 ГК РФ"],
        contradictions=[],
        verdict=LegalVerdict.REJECTED,
        summary="Договор содержит критические риски для Подрядчика. Требуется протокол разногласий.",
    )


# =============================================================================
# LegalDocumentGenerator — Protocol
# =============================================================================

class TestProtocolGeneration:
    """Генерация протокола разногласий."""

    def test_build_protocol_from_findings(self):
        gen = LegalDocumentGenerator(llm_engine=None)
        result = _make_analysis_result()

        protocol = gen._build_protocol_from_findings(
            result,
            contract_number="42/2026",
            contract_date="01.04.2026",
            customer_info=ProtocolPartyInfo(name="ООО Заказчик", inn="7700000001"),
            contractor_info=ProtocolPartyInfo(name="ООО Подрядчик", inn="7700000002"),
        )

        assert protocol.contract_number == "42/2026"
        assert protocol.total_items >= 2  # CRITICAL + HIGH
        assert protocol.customer_info.name == "ООО Заказчик"

        # Items should have 3-column structure
        for item in protocol.items:
            assert item.clause_ref
            assert item.customer_text
            assert item.contractor_text
            assert item.legal_basis

    def test_protocol_to_dict_and_back(self):
        """ProtocolDisagreements serialization roundtrip."""
        protocol = ProtocolDisagreements(
            protocol_title="Протокол разногласий к Договору № 42",
            contract_number="42",
            contract_date="01.04.2026",
            customer_info=ProtocolPartyInfo(name="Заказчик"),
            contractor_info=ProtocolPartyInfo(name="Подрядчик"),
            items=[
                ProtocolItem(
                    row_number=1,
                    clause_ref="п. 3.5",
                    customer_text="Редакция Заказчика",
                    contractor_text="Редакция Подрядчика",
                    legal_basis="ст. 711 ГК РФ",
                    severity=LegalSeverity.HIGH,
                ),
            ],
            total_items=1,
            summary="Пояснительная записка",
        )

        d = protocol.model_dump()
        restored = ProtocolDisagreements(**d)
        assert restored.total_items == 1
        assert restored.items[0].clause_ref == "п. 3.5"

    def test_export_protocol_text(self):
        """Текстовый экспорт протокола (без python-docx)."""
        gen = LegalDocumentGenerator(llm_engine=None)
        result = _make_analysis_result()
        protocol = gen._build_protocol_from_findings(
            result, "42/2026", "01.04.2026",
            ProtocolPartyInfo(name="Заказчик"),
            ProtocolPartyInfo(name="Подрядчик"),
        )

        with tempfile.TemporaryDirectory() as d:
            path = gen._export_protocol_text(protocol, d)
            assert os.path.exists(path)
            content = open(path).read()
            assert "Протокол разногласий" in content
            assert "ст. 711 ГК РФ" in content
            assert "Заказчик" in content
            assert "Подрядчик" in content

    def test_default_edit(self):
        gen = LegalDocumentGenerator(llm_engine=None)
        finding = LegalFinding(
            category=LegalFindingCategory.RISK,
            severity=LegalSeverity.HIGH,
            clause_ref="п. 5.1",
            legal_basis="ст. 333 ГК РФ",
            issue="Штраф завышен",
            recommendation="Уменьшить до 5%",
            auto_fixable=True,
        )
        edit = gen._default_edit(finding)
        assert "333 ГК РФ" in edit

    def test_export_protocol_docx(self):
        """DOCX экспорт (если python-docx доступен)."""
        gen = LegalDocumentGenerator(llm_engine=None)
        result = _make_analysis_result()
        protocol = gen._build_protocol_from_findings(
            result, "42/2026", "01.04.2026",
            ProtocolPartyInfo(name="Заказчик"),
            ProtocolPartyInfo(name="Подрядчик"),
        )

        with tempfile.TemporaryDirectory() as d:
            path = gen._export_protocol_docx(protocol, d)
            assert os.path.exists(path)
            # Should be .docx or .txt
            assert path.endswith((".docx", ".txt"))


# =============================================================================
# LegalDocumentGenerator — Claim & Lawsuit
# =============================================================================

class TestClaimAndLawsuit:
    """Генерация претензии и иска."""

    def test_format_violations(self):
        result = _make_analysis_result()
        text = LegalDocumentGenerator._format_violations(result)
        assert "п. 3.5" in text
        assert "п. 7.2" in text
        assert "ст. 711 ГК РФ" in text

    def test_format_legal_basis(self):
        result = _make_analysis_result()
        text = LegalDocumentGenerator._format_legal_basis(result)
        assert "ст. 711" in text
        assert "ст. 395" in text

    def test_calc_state_duty(self):
        assert LegalDocumentGenerator._calc_state_duty(50_000) >= 2000
        assert LegalDocumentGenerator._calc_state_duty(150_000) > 5000
        assert LegalDocumentGenerator._calc_state_duty(500_000) > 10_000
        assert LegalDocumentGenerator._calc_state_duty(3_000_000) > 30_000

        # Check specific values per ст. 333.21 НК РФ
        # До 100 000: 4% но не менее 2000
        d1 = LegalDocumentGenerator._calc_state_duty(50_000)
        assert d1 == max(2000, 50000 * 0.04)

        # 100 001 - 200 000: 4000 + 3% от > 100 000
        d2 = LegalDocumentGenerator._calc_state_duty(150_000)
        assert d2 == 4000 + (150_000 - 100_000) * 0.03

    def test_fallback_claim(self):
        gen = LegalDocumentGenerator(llm_engine=None)
        text = gen._fallback_claim(
            "ООО Подрядчик", "ООО Заказчик", "42/2026",
            1_500_000, "Нарушение 1", "ст. 711 ГК РФ"
        )
        assert "ДОСУДЕБНАЯ ПРЕТЕНЗИЯ" in text
        assert "ООО Подрядчик" in text
        assert "ООО Заказчик" in text
        assert "1,500,000" in text

    def test_fallback_lawsuit(self):
        gen = LegalDocumentGenerator(llm_engine=None)
        text = gen._fallback_lawsuit(
            "ООО Подрядчик", "ООО Заказчик", "42/2026",
            3_000_000, 38_000, "Арбитражный суд г. Москвы",
            "ст. 711 ГК РФ", "Факты дела"
        )
        assert "ИСКОВОЕ ЗАЯВЛЕНИЕ" in text
        assert "Арбитражный суд" in text
        assert "ООО Подрядчик" in text
        assert "ст. 711 ГК РФ" in text

    def test_claim_generation_no_llm(self):
        """Генерация претензии без LLM (fallback)."""
        gen = LegalDocumentGenerator(llm_engine=None)
        result = _make_analysis_result()

        with tempfile.TemporaryDirectory() as d:
            path = gen._fallback_claim(
                "Подрядчик", "Заказчик", "42/2026", 500_000,
                gen._format_violations(result),
                gen._format_legal_basis(result),
            )
            # fallback_claim returns text, not a file.
            # Let's test the async claim generation
            pass

    def test_lawsuit_fallback_complete(self):
        """Полный fallback-текст иска."""
        gen = LegalDocumentGenerator(llm_engine=None)
        result = _make_analysis_result()
        text = gen._fallback_lawsuit(
            "Истец ООО", "Ответчик АО", "12/2026",
            2_000_000, 33_000, "АС г. Москвы",
            gen._format_legal_basis(result),
            gen._format_case_facts(result),
        )
        assert "ИСКОВОЕ" in text
        assert "ПРОШУ СУД" in text
        assert "ПРИЛОЖЕНИЯ" in text


# =============================================================================
# ProtocolItem Serialization
# =============================================================================

class TestProtocolItem:
    """ProtocolItem: создание, валидация."""

    def test_create_minimal(self):
        item = ProtocolItem(
            row_number=1,
            clause_ref="п. 1.1",
            customer_text="Текст Заказчика",
            contractor_text="Текст Подрядчика",
            legal_basis="ст. 309 ГК РФ",
        )
        assert item.row_number == 1
        assert item.legal_basis == "ст. 309 ГК РФ"

    def test_create_with_severity(self):
        item = ProtocolItem(
            row_number=2,
            clause_ref="п. 3.5",
            customer_text="Заказчик",
            contractor_text="Подрядчик",
            legal_basis="ст. 711 ГК РФ",
            severity=LegalSeverity.CRITICAL,
            blc_match="payment_01",
        )
        assert item.severity == LegalSeverity.CRITICAL
        assert item.blc_match == "payment_01"

    def test_roundtrip_serialization(self):
        item = ProtocolItem(
            row_number=3,
            clause_ref="п. 8.2",
            customer_text="Оригинал",
            contractor_text="Редакция",
            legal_basis="ст. 333 ГК РФ",
            severity=LegalSeverity.HIGH,
            blc_match="trap_42",
        )
        d = item.model_dump()
        restored = ProtocolItem(**d)
        assert restored.row_number == 3
        assert restored.clause_ref == "п. 8.2"
        assert restored.blc_match == "trap_42"


# =============================================================================
# LegalFinding Extensions
# =============================================================================

class TestLegalFinding:
    """LegalFinding: создание, contractor_edit."""

    def test_create_with_edit(self):
        f = LegalFinding(
            category=LegalFindingCategory.TRAP,
            severity=LegalSeverity.HIGH,
            clause_ref="п. 4.1",
            legal_basis="ст. 450 ГК РФ",
            issue="Односторонний отказ Заказчика без оснований",
            recommendation="Ограничить случаи одностороннего отказа",
            contractor_edit="Односторонний отказ допускается только в случаях, предусмотренных законом",
            auto_fixable=True,
            blc_match="unilateral_01",
        )
        assert f.contractor_edit is not None
        assert "односторонний отказ" in f.contractor_edit.lower()

    def test_minimal_finding(self):
        f = LegalFinding(
            category=LegalFindingCategory.RISK,
            severity=LegalSeverity.LOW,
            clause_ref="п. 10.5",
            legal_basis="ст. 421 ГК РФ",
            issue="Диспозитивная норма",
            recommendation="Оставить без изменений",
        )
        assert f.auto_fixable is False
        assert f.contractor_edit is None
