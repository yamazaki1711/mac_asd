"""
ASD v12.0 — Legal Schemas.

Pydantic models for legal agent input/output validation.

v12.0.0 changes:
- Added LegalVerdict.DANGEROUS (3+ critical risks)
- Added LegalFinding.contractor_edit (редакция Подрядчика для протокола)
- Added ProtocolItem model (3-колоночный формат протокола разногласий)
- Added ProtocolDisagreements model (полный протокол)
- Added ProtocolPartyInfo (реквизиты сторон)
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums
# =============================================================================

class LegalSeverity(str, Enum):
    """Уровень серьёзности юридического риска."""
    CRITICAL = "critical"  # Подписание НЕДОПУСТИМО без исправления
    HIGH = "high"          # Настоятельная рекомендация исправить
    MEDIUM = "medium"      # Обратить внимание
    LOW = "low"            # Информационно


class LegalFindingCategory(str, Enum):
    """Категория юридического замечания."""
    COMPLIANCE = "compliance"     # Нарушение ФЗ/норм
    RISK = "risk"                 # Риск для Подрядчика
    AMBIGUITY = "ambiguity"       # Неоднозначная формулировка
    OMISSION = "omission"         # Отсутствие нужного пункта
    TRAP = "trap"                 # Известная ловушка из БЛС


class LegalVerdict(str, Enum):
    """Итоговый вердикт юридической экспертизы."""
    APPROVED = "approved"                               # Договор в порядке
    APPROVED_WITH_COMMENTS = "approved_with_comments"   # Можно подписать с оговорками
    REJECTED = "rejected"                               # Подписывать нельзя
    DANGEROUS = "dangerous"                             # Крайне невыгоден (3+ critical)


class ReviewType(str, Enum):
    """Тип юридического рассмотрения."""
    CONTRACT = "contract"       # Договор/контракт
    TENDER = "tender"           # Тендерная документация
    COMPLIANCE = "compliance"   # Проверка соответствия


# =============================================================================
# Protocol Models (v12.0.0)
# =============================================================================

class ProtocolPartyInfo(BaseModel):
    """
    Реквизиты стороны для протокола разногласий.
    """
    name: str = Field(description="Наименование организации")
    legal_address: Optional[str] = Field(default=None, description="Юридический адрес")
    inn: Optional[str] = Field(default=None, description="ИНН")
    representative: Optional[str] = Field(default=None, description="ФИО представителя")
    position: Optional[str] = Field(default=None, description="Должность представителя")
    basis: Optional[str] = Field(default=None, description="Основание (Устав, доверенность)")


class ProtocolItem(BaseModel):
    """
    Одна строка протокола разногласий — 3 колонки:
    | Пункт, статья | Редакция Заказчика | Редакция Подрядчика |
    """
    row_number: int = Field(description="Номер строки в протоколе")
    clause_ref: str = Field(
        description="Ссылка на пункт договора (например, 'п. 3.5 Договора')"
    )
    customer_text: str = Field(
        description="Редакция Заказчика — точная цитата из договора"
    )
    contractor_text: str = Field(
        description="Редакция Подрядчика — предлагаемый текст с обоснованием"
    )
    legal_basis: str = Field(
        description="Правовое основание: статья закона (ГК РФ, ГрК РФ и т.д.)"
    )
    severity: Optional[LegalSeverity] = Field(
        default=None,
        description="Критичность замечания"
    )
    blc_match: Optional[str] = Field(
        default=None,
        description="ID совпадения из БЛС (если ловушка известная)"
    )


# =============================================================================
# Core Finding Model
# =============================================================================

class LegalFinding(BaseModel):
    """
    Одно юридическое замечание / ловушка.

    v12.0.0: Добавлено contractor_edit — точная редакция Подрядчика
    для протокола разногласий. Каждая правка опирается на закон.
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
        description="Нормативная база (например, 'ст. 711 ГК РФ')"
    )
    issue: str = Field(
        description="Описание проблемы — почему это ловушка/ущемление"
    )
    recommendation: str = Field(
        description="Рекомендация по исправлению"
    )
    contractor_edit: Optional[str] = Field(
        default=None,
        description="Точная редакция Подрядчика для протокола разногласий"
    )
    auto_fixable: bool = Field(
        default=False,
        description="Можно ли автоматически предложить редакцию пункта"
    )
    blc_match: Optional[str] = Field(
        default=None,
        description="ID совпадения из БЛС (если найдена известная ловушка)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "trap",
                "severity": "high",
                "clause_ref": "п. 3.5 Договора",
                "legal_basis": "ст. 711 ГК РФ, ст. 395 ГК РФ",
                "issue": "Неустойка за просрочку оплаты не установлена",
                "recommendation": "Добавить пени за просрочку оплаты по ставке ЦБ РФ",
                "contractor_edit": "В случае просрочки оплаты Заказчик уплачивает пени в размере 1/300 ключевой ставки ЦБ РФ за каждый день просрочки",
                "auto_fixable": True,
                "blc_match": "payment_01",
            }
        }
    )


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

    v12.0.0: Добавлены protocol_items для генерации протокола разногласий.
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
    protocol_items: List[ProtocolItem] = Field(
        default_factory=list,
        description="Строки для протокола разногласий (3-колоночный формат)"
    )
    normative_refs: List[str] = Field(
        default_factory=list,
        description="Список нормативных ссылок"
    )
    contradictions: List[str] = Field(
        default_factory=list,
        description="Внутренние противоречия в документе"
    )
    verdict: LegalVerdict = Field(
        description="Итоговый вердикт"
    )
    summary: str = Field(
        description="Краткое заключение"
    )
    normative_validity_warnings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Предупреждения об устаревших нормах (от InvalidationEngine)"
    )
    analysis_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Метаданные анализа"
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


class ProtocolDisagreements(BaseModel):
    """
    Полный протокол разногласий к договору.

    Формат — 3 колонки:
    | Пункт, статья | Редакция Заказчика | Редакция Подрядчика |

    Каждая правка Подрядчика опирается на конкретную статью закона.
    Это заставляет даже государственного Заказчика вернуться в правовое поле.
    """
    protocol_title: str = Field(
        description="Заголовок протокола (например, 'Протокол разногласий к Договору №__')"
    )
    contract_number: Optional[str] = Field(
        default=None,
        description="Номер договора"
    )
    contract_date: Optional[str] = Field(
        default=None,
        description="Дата договора"
    )
    customer_info: ProtocolPartyInfo = Field(
        description="Реквизиты Заказчика"
    )
    contractor_info: ProtocolPartyInfo = Field(
        description="Реквизиты Подрядчика (Генподрядчика)"
    )
    items: List[ProtocolItem] = Field(
        default_factory=list,
        description="Строки протокола разногласий"
    )
    total_items: int = Field(
        default=0,
        description="Количество пунктов разногласий"
    )
    summary: Optional[str] = Field(
        default=None,
        description="Пояснительная записка к протоколу"
    )


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
