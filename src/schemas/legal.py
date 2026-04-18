"""
ASD v11.0 — Legal Schemas.

Pydantic models for legal agent input/output validation.
Updated for 2024-2025 regulatory framework + MLX-only architecture.
Matches the format defined in agents/legal/prompt.md.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class LegalSeverity(str, Enum):
    """Уровень серьёзности юридического риска."""
    CRITICAL = "critical"  # Обязательное исправление
    HIGH = "high"          # Настоятельная рекомендация
    MEDIUM = "medium"      # Обратить внимание
    LOW = "low"            # Информационно


class LegalFindingCategory(str, Enum):
    """Категория юридического замечания."""
    COMPLIANCE = "compliance"     # Нарушение ФЗ/норм
    RISK = "risk"                 # Риск для субподрядчика
    AMBIGUITY = "ambiguity"       # Неоднозначная формулировка
    OMISSION = "omission"         # Отсутствие нужного пункта
    TRAP = "trap"                 # Известная ловушка из БЛС
    REGULATORY = "regulatory"     # Устаревшая или неверная нормативная ссылка


class LegalVerdict(str, Enum):
    """Итоговый вердикт юридической экспертизы."""
    APPROVED = "approved"                       # Договор в порядке
    APPROVED_WITH_COMMENTS = "approved_with_comments"  # Можно подписать с оговорками
    REJECTED = "rejected"                       # Подписывать нельзя


class ReviewType(str, Enum):
    """Тип юридического рассмотрения."""
    CONTRACT = "contract"       # Договор/контракт
    TENDER = "tender"           # Тендерная документация
    COMPLIANCE = "compliance"   # Проверка соответствия нормативке
    ID_CHECK = "id_check"       # Проверка состава ИД (исполнительной документации)


# =============================================================================
# БЛС (База Ловушек Субподрядчика) Models
# =============================================================================

class BLCEntry(BaseModel):
    """Запись в Базе Ловушек Субподрядчика."""
    id: Optional[int] = None
    title: str = Field(description="Краткое название ловушки")
    description: str = Field(description="Полное описание ловушки и почему опасно")
    source: str = Field(description="Источник (ФЗ, судебная практика, практика субподрядчиков)")
    mitigation: str = Field(description="Рекомендация по защите")
    work_types: List[str] = Field(
        default_factory=list,
        description="Типы работ, к которым применима ловушка "
                    "(бетонные, земляные, сварочные, монтажные, шпунтовые, общестроительные)"
    )
    legal_basis: str = Field(
        default="",
        description="Нормативная база (ФЗ-44 ст. ..., ГК РФ ст. ...)"
    )
    severity: LegalSeverity = Field(
        default=LegalSeverity.HIGH,
        description="Типичная серьёзность ловушки"
    )
    created_at: Optional[datetime] = None


class BLCTrapExtraction(BaseModel):
    """Результат извлечения ловушки из текста (для пополнения БЛС)."""
    is_trap: bool = Field(description="Является ли текст описанием ловушки")
    title: Optional[str] = Field(default=None, description="Краткое название")
    description: Optional[str] = Field(default=None, description="Полное описание")
    court_cases: List[str] = Field(
        default_factory=list,
        description="Упомянутые судебные дела"
    )
    mitigation: Optional[str] = Field(default=None, description="Рекомендация по защите")


# =============================================================================
# Core Analysis Models
# =============================================================================

class LegalFinding(BaseModel):
    """
    Одно юридическое замечание / ловушка.
    """
    category: LegalFindingCategory = Field(
        description="Категория замечания"
    )
    severity: LegalSeverity = Field(
        description="Уровень серьёзности"
    )
    clause_ref: str = Field(
        description="Ссылка на пункт договора (например, 'п. 4.2 Договора')"
    )
    legal_basis: str = Field(
        description="Нормативная база (например, 'ФЗ-44 ст. 34 ч. 6')"
    )
    issue: str = Field(
        description="Описание проблемы"
    )
    recommendation: str = Field(
        description="Рекомендация по исправлению"
    )
    auto_fixable: bool = Field(
        default=False,
        description="Можно ли автоматически предложить редакцию пункта"
    )
    blc_match: Optional[str] = Field(
        default=None,
        description="ID совпадения из БЛС (если найдена известная ловушка)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "category": "risk",
                "severity": "high",
                "clause_ref": "п. 5.3 Договора",
                "legal_basis": "ФЗ-44 ст. 34 ч. 6",
                "issue": "Неустойка заказчика не установлена",
                "recommendation": "Добавить пени 1/300 ставки ЦБ за просрочку оплаты",
                "auto_fixable": False,
                "blc_match": None,
            }
        }


# =============================================================================
# Request / Response Models
# =============================================================================

class LegalAnalysisRequest(BaseModel):
    """
    Запрос на юридическую экспертизу.
    """
    document_id: Optional[int] = Field(
        default=None,
        description="ID документа в БД (если уже загружен)"
    )
    document_text: Optional[str] = Field(
        default=None,
        description="Текст документа для анализа (если не загружен в БД)"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Путь к файлу документа (PDF/DOCX)"
    )
    review_type: ReviewType = Field(
        default=ReviewType.CONTRACT,
        description="Тип рассмотрения"
    )
    project_id: Optional[int] = Field(
        default=None,
        description="ID проекта"
    )
    work_type: Optional[str] = Field(
        default=None,
        description="Тип работ для контекстного анализа "
                    "(бетонные, земляные, сварочные, монтажные, шпунтовые, общестроительные)"
    )
    chunk_size: int = Field(
        default=6000,
        description="Размер чанка для Map-Reduce (в символах)"
    )
    chunk_overlap: int = Field(
        default=300,
        description="Перекрытие между чанками"
    )


class LegalAnalysisResult(BaseModel):
    """
    Результат юридической экспертизы.
    """
    document_ref: Optional[str] = Field(
        default=None,
        description="Ссылка на анализируемый документ"
    )
    review_type: ReviewType = Field(
        description="Тип рассмотрения"
    )
    findings: List[LegalFinding] = Field(
        default_factory=list,
        description="Список найденных рисков/ловушек"
    )
    normative_refs: List[str] = Field(
        default_factory=list,
        description="Список нормативных ссылок, проверенных в документе"
    )
    contradictions: List[str] = Field(
        default_factory=list,
        description="Внутренние противоречия в документе"
    )
    verdict: LegalVerdict = Field(
        description="Итоговый вердикт"
    )
    summary: str = Field(
        description="Краткое заключение на 2-3 предложения"
    )
    analysis_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Метаданные анализа (длительность, модель, кол-во чанков)"
    )

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == LegalSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == LegalSeverity.HIGH)

    @property
    def total_risks(self) -> int:
        return len(self.findings)


class ContractUploadResult(BaseModel):
    """
    Результат загрузки и парсинга контракта.
    """
    status: str = "success"
    file_path: str
    chunks_extracted: int = Field(
        description="Количество извлечённых текстовых фрагментов"
    )
    total_chars: int = Field(
        default=0,
        description="Общее количество символов в документе"
    )
    message: str = "Document parsed and ready for analysis."
