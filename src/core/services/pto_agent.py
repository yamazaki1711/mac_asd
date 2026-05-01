"""
ASD v12.0 — PTO Agent (Производственно-технический отдел).

Полноценный агент ПТО на основе Пособия по ИД (Щербаков, 2026):
  1. Инвентаризация — классификация документов по 13 позициям 344/пр
  2. Верификация шлейфа АОСР — ВОР → ИС → сертификаты → протоколы
  3. Проверка перекрёстных связей — даты, объёмы, соответствие проекту
  4. Completeness Report — дельта относительно эталона

Источники:
  - Приказ Минстроя №344/пр (состав ИД)
  - СП 543.1325800.2024 Приложение А (перечень по видам работ)
  - ПП РФ №468 (правила приёмки скрытых работ)
  - ГОСТ Р 51872-2024 (исполнительные схемы)
  - Пособие по ИД, Выпуск №2, гл. 4-5

Usage:
    from src.core.services.pto_agent import pto_agent

    report = await pto_agent.inventory(project_id=1, documents=docs)
    trail = await pto_agent.verify_trail(aosr_id=42)
    delta = await pto_agent.completeness_delta(project_id=1, work_type="фундаменты_монолитные")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.agents.skills.pto.work_spec import (
    WorkType,
    WORK_TYPE_CATEGORIES,
    WORK_JOURNALS,
    WORK_HIDDEN_ACTS,
    COMMON_REGULATIONS,
    COMMON_JOURNAL_OJR,
    COMMON_JOURNAL_JVK,
    COMMON_ACT_AOSR,
    COMMON_ACT_AOOUK,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Document Classification — 13 позиций 344/пр
# =============================================================================

class ID344Category(str, Enum):
    """13 позиций состава ИД по Приказу Минстроя №344/пр."""
    ACT_GRO = "act_gro"                       # 1. Акт ГРО
    ACT_AXES = "act_axes"                      # 2. Акт разбивки осей
    ACT_AOSR = "act_aosr"                      # 3. АОСР (скрытые работы)
    ACT_AOOK = "act_aook"                      # 4. АООК (ответственные конструкции)
    ACT_AOUSITO = "act_aousito"                # 5. АОУСИТО (участки сетей)
    REMARKS = "remarks"                        # 6. Замечания застройщика/стройконтроля
    WORK_DRAWINGS = "work_drawings"            # 7. Рабочие чертежи с надписями
    IGS = "igs"                                # 8. Исполнительные геодезические схемы
    IS_RESULT = "is_result"                    # 9. Исполнительные схемы результатов
    TEST_ACTS = "test_acts"                    # 10. Акты испытаний
    LAB_RESULTS = "lab_results"                # 11. Лабораторные заключения
    INPUT_CONTROL = "input_control"            # 12. Входной контроль (ЖВК + сертификаты)
    JOURNALS = "journals"                      # 13. ОЖР + специальные журналы


# Mapping: doc_type from DocumentRepository → ID344Category
DOC_TYPE_TO_344: Dict[str, ID344Category] = {
    "KS2": ID344Category.ACT_AOSR,
    "KS3": ID344Category.ACT_AOSR,
    "AOSR": ID344Category.ACT_AOSR,
    "AOOK": ID344Category.ACT_AOOK,
    "AOUSITO": ID344Category.ACT_AOUSITO,
    "VOR": ID344Category.ACT_AOSR,          # ВОР — приложение к АОСР
    "Smeta": ID344Category.ACT_AOSR,        # Смета — приложение
    "Contract": ID344Category.WORK_DRAWINGS, # Договор — косвенно
    "Certificate": ID344Category.INPUT_CONTROL,
    "OZHR": ID344Category.JOURNALS,
    "Drawing": ID344Category.WORK_DRAWINGS,
    "IGS": ID344Category.IGS,
    "IS": ID344Category.IS_RESULT,
    "PPR": ID344Category.WORK_DRAWINGS,
    "Scheme": ID344Category.IGS,
    "TestAct": ID344Category.TEST_ACTS,
    "LabReport": ID344Category.LAB_RESULTS,
    "QualityDoc": ID344Category.INPUT_CONTROL,
}


# =============================================================================
# Data Classes
# =============================================================================

class DocStatus(str, Enum):
    PRESENT = "present"          # Документ найден
    MISSING = "missing"          # Отсутствует
    INCOMPLETE = "incomplete"    # Есть, но не хватает данных
    STALE = "stale"              # Устарел (версия/дата)
    PENDING = "pending"          # Ожидается (ещё не оформлен)


@dataclass
class TrailItem:
    """Один элемент шлейфа к АОСР."""
    item_type: str               # "vor", "is_scheme", "certificate", "test_protocol"...
    name: str                    # Человеческое название
    mandatory: bool = True
    status: DocStatus = DocStatus.PENDING
    doc_ref: Optional[str] = None  # Ссылка на документ (ID или путь)
    notes: str = ""


@dataclass
class AOSRTrail:
    """Полный шлейф документов к одному АОСР."""
    aosr_id: str
    aosr_name: str               # Наименование скрытой работы
    work_type: str
    items: List[TrailItem] = field(default_factory=list)
    cross_check_errors: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        mandatory = [i for i in self.items if i.mandatory]
        return all(i.status == DocStatus.PRESENT for i in mandatory)

    @property
    def missing_mandatory(self) -> List[TrailItem]:
        return [i for i in self.items if i.mandatory and i.status != DocStatus.PRESENT]


@dataclass
class CompletenessGap:
    """Разрыв в комплекте ИД."""
    category: ID344Category
    description: str
    severity: str  # "critical", "high", "medium"
    required_count: int = 1
    present_count: int = 0


@dataclass
class CompReport:
    """Отчёт о полноте ИД."""
    project_id: int
    work_types: List[str]
    total_positions: int          # Всего позиций по 344/пр
    covered_positions: int        # Закрыто позиций
    gaps: List[CompletenessGap] = field(default_factory=list)
    aosr_trails: List[AOSRTrail] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def completeness_pct(self) -> float:
        if self.total_positions == 0:
            return 0.0
        return round(self.covered_positions / self.total_positions * 100, 1)

    @property
    def critical_gaps(self) -> List[CompletenessGap]:
        return [g for g in self.gaps if g.severity == "critical"]


# =============================================================================
# PTO Agent
# =============================================================================

class PTOAgent:
    """
    Агент ПТО ASD v12.0.

    Задачи:
      - Инвентаризация: классифицировать документы по матрице 344/пр
      - Верификация шлейфа АОСР: проверить полный комплект документов к акту
      - Перекрёстный анализ: даты, объёмы, соответствие проекту
      - Отчёт о полноте: дельта между эталоном и фактом
    """

    def __init__(self, llm_engine=None):
        from src.core.llm_engine import llm_engine as _llm
        self._llm = llm_engine or _llm

    # =========================================================================
    # 1. Инвентаризация — классификация документов
    # =========================================================================

    def classify_document(self, doc_type: str) -> ID344Category:
        """Классифицировать тип документа по матрице 344/пр."""
        return DOC_TYPE_TO_344.get(doc_type, ID344Category.WORK_DRAWINGS)

    def build_completeness_matrix(self, work_types: List[str]) -> Dict[ID344Category, int]:
        """
        Построить матрицу полноты: сколько документов каждого типа требуется.

        На основе:
          - 13 позиций 344/пр (обязательный минимум)
          - Перечень АОСР из work_spec.py для каждого вида работ
          - Специальные журналы для каждого вида работ
        """
        matrix: Dict[ID344Category, int] = {
            ID344Category.ACT_GRO: 1,
            ID344Category.ACT_AXES: 1,
            ID344Category.ACT_AOSR: 0,        # Считаем ниже
            ID344Category.ACT_AOOK: 0,         # Считаем ниже
            ID344Category.ACT_AOUSITO: 0,
            ID344Category.REMARKS: 1,           # Минимум 1 комплект
            ID344Category.WORK_DRAWINGS: 1,
            ID344Category.IGS: 0,               # Считаем ниже
            ID344Category.IS_RESULT: 0,         # Считаем ниже
            ID344Category.TEST_ACTS: 0,
            ID344Category.LAB_RESULTS: 0,
            ID344Category.INPUT_CONTROL: 1,
            ID344Category.JOURNALS: 1,
        }

        # Считаем АОСР, АООК, ИГС, ИС по видам работ
        for wt_code in work_types:
            try:
                wt = WorkType(wt_code)
            except ValueError:
                continue

            # АОСР
            acts = WORK_HIDDEN_ACTS.get(wt, [])
            mandatory_acts = [a for a in acts if a.get("mandatory", True)]
            matrix[ID344Category.ACT_AOSR] += len(mandatory_acts)

            # АООК: минимум 1 на вид работ (кроме земляных)
            if wt not in (WorkType.EARTHWORK_EXCAVATION, WorkType.EARTHWORK_BACKFILL):
                matrix[ID344Category.ACT_AOOK] += 1

            # ИГС + ИС: по 1 схеме на каждый АОСР
            matrix[ID344Category.IGS] += len(mandatory_acts)
            matrix[ID344Category.IS_RESULT] += len(mandatory_acts)

        return matrix

    def get_required_aosr_list(self, work_type: str) -> List[Dict[str, Any]]:
        """Получить перечень обязательных АОСР для вида работ."""
        try:
            wt = WorkType(work_type)
        except ValueError:
            return []

        acts = WORK_HIDDEN_ACTS.get(wt, [])
        return [
            {
                "name": a["name"],
                "mandatory": a.get("mandatory", True),
                "conditional": a.get("conditional", ""),
                "note": a.get("note", ""),
            }
            for a in acts
        ]

    def get_required_journals(self, work_type: str) -> List[Dict[str, Any]]:
        """Получить перечень журналов для вида работ."""
        try:
            wt = WorkType(work_type)
        except ValueError:
            return []

        journals = WORK_JOURNALS.get(wt, [])
        return [
            {
                "name": j["name"],
                "form": j.get("form", ""),
                "mandatory": j.get("mandatory", True),
                "conditional": j.get("conditional", ""),
            }
            for j in journals
        ]

    # =========================================================================
    # 2. Верификация шлейфа АОСР
    # =========================================================================

    def build_aosr_trail(self, aosr_name: str, work_type: str = "") -> AOSRTrail:
        """
        Построить эталонный шлейф документов для одного АОСР.

        Шлейф (из Пособия, раздел 4.4):
          1. ВОР (ведомость объёмов работ) — необязательна, но заказчик требует
          2. Исполнительная схема (геодезическая + результатов)
          3. Документы качества на материалы (паспорт + сертификат/декларация)
          4. Протоколы испытаний (если применимо)
          5. Уведомление о приёмке (за 3 рабочих дня)
          6. Фотоотчёт (рекомендуется)
        """
        items = [
            TrailItem(
                item_type="vor",
                name="Ведомость объёмов работ (ВОР)",
                mandatory=False,
                notes="Необязательна по 344/пр, но заказчик часто требует (Пособие п. 5.5)",
            ),
            TrailItem(
                item_type="is_geodetic",
                name="Исполнительная геодезическая схема (ИГС)",
                mandatory=True,
                notes="ГОСТ Р 51872-2024. Фиксирует фактическое положение конструкций.",
            ),
            TrailItem(
                item_type="is_result",
                name="Исполнительная схема результатов работ",
                mandatory=True,
                notes="ГОСТ Р 51872-2024. Отражает отступления от проекта.",
            ),
            TrailItem(
                item_type="quality_docs",
                name="Документы качества на материалы",
                mandatory=True,
                notes="Паспорт качества + сертификат/декларация соответствия (ПП РФ №2425). "
                      "При необходимости: пожарный сертификат, свидетельство госрегистрации.",
            ),
            TrailItem(
                item_type="test_protocols",
                name="Протоколы испытаний",
                mandatory=False,
                notes="Для бетона: протокол прочности (7 сут). Для сварки: контроль швов. "
                      "Для грунтов: уплотнение. Обязательность зависит от вида работ.",
            ),
            TrailItem(
                item_type="notification",
                name="Уведомление о приёмке",
                mandatory=True,
                notes="ПП РФ №468 п. 11: не позднее чем за 3 рабочих дня.",
            ),
            TrailItem(
                item_type="photo_report",
                name="Фотоотчёт выполнения работ",
                mandatory=False,
                notes="Рекомендуется. Фото не заменяет акт, но помогает при спорах.",
            ),
        ]

        return AOSRTrail(
            aosr_id=f"AOSR_{hash(aosr_name) % 10000:04d}",
            aosr_name=aosr_name,
            work_type=work_type,
            items=items,
        )

    def verify_trail_completeness(
        self, trail: AOSRTrail, available_docs: List[str]
    ) -> AOSRTrail:
        """
        Проверить фактическое наличие документов шлейфа.

        Args:
            trail: эталонный шлейф
            available_docs: список ID/имён фактически имеющихся документов

        Returns:
            Обновлённый AOSRTrail с проставленными статусами
        """
        docs_lower = [d.lower() for d in available_docs]

        for item in trail.items:
            # Эвристический поиск
            found = False
            search_terms = {
                "vor": ["вор", "ведомость", "vor"],
                "is_geodetic": ["игс", "геодезическ", "исполнительн.*схем"],
                "is_result": ["ис_", "схема результат", "исполнительн.*результат"],
                "quality_docs": ["сертификат", "паспорт", "декларац", "качеств"],
                "test_protocols": ["протокол", "испытан", "test"],
                "notification": ["уведомлен", "приёмк", "приемк"],
                "photo_report": ["фото", "photo"],
            }

            terms = search_terms.get(item.item_type, [])
            for term in terms:
                if any(term in d for d in docs_lower):
                    found = True
                    break

            item.status = DocStatus.PRESENT if found else DocStatus.MISSING
            if not found and not item.mandatory:
                item.status = DocStatus.PENDING  # Необязательные — pending, не missing

        return trail

    # =========================================================================
    # 3. Перекрёстный анализ (Cross-Check)
    # =========================================================================

    def cross_check_aosr(self, trail: AOSRTrail, context: Dict[str, Any]) -> List[str]:
        """
        Перекрёстная проверка АОСР:
          - Даты: АОСР дата ≥ дата протокола испытаний
          - Объёмы: ВОР ↔ АОСР ↔ КС-2
          - Материалы: АОСР п. 3 ↔ документы качества

        Args:
            trail: шлейф АОСР
            context: dict с данными для проверки (даты, объёмы, материалы)

        Returns:
            Список ошибок перекрёстной проверки
        """
        errors = []

        # Проверка дат
        aosr_date = context.get("aosr_date")
        test_date = context.get("test_protocol_date")
        if aosr_date and test_date:
            if aosr_date < test_date:
                errors.append(
                    f"Дата АОСР ({aosr_date}) раньше даты протокола испытаний "
                    f"({test_date}). АОСР должен быть подписан ПОСЛЕ получения протокола."
                )

        # Проверка: дата выполнения работ vs дата документа качества
        work_date = context.get("work_date")
        quality_date = context.get("quality_doc_date")
        if work_date and quality_date:
            if quality_date > work_date:
                errors.append(
                    f"Дата документа качества ({quality_date}) позже даты выполнения "
                    f"работ ({work_date}). Материал должен быть принят до использования."
                )

        # Проверка объёмов (если ВОР и КС-2 переданы)
        vor_volume = context.get("vor_volume")
        ks2_volume = context.get("ks2_volume")
        if vor_volume and ks2_volume:
            diff_pct = abs(vor_volume - ks2_volume) / max(vor_volume, 1) * 100
            if diff_pct > 5:
                errors.append(
                    f"Расхождение объёмов: ВОР = {vor_volume}, "
                    f"КС-2 = {ks2_volume} (разница {diff_pct:.1f}%)"
                )

        # Проверка материалов
        aosr_materials = context.get("aosr_materials", [])
        cert_materials = context.get("cert_materials", [])
        for mat in aosr_materials:
            if mat not in cert_materials:
                errors.append(
                    f"Материал '{mat}' указан в АОСР п. 3, "
                    f"но документ качества не найден"
                )

        return errors

    # =========================================================================
    # 4. Completeness Report
    # =========================================================================

    async def generate_completeness_report(
        self,
        project_id: int,
        work_types: List[str],
        available_docs: Optional[List[Dict[str, Any]]] = None,
    ) -> CompReport:
        """
        Сгенерировать полный отчёт о комплектности ИД.

        Args:
            project_id: ID проекта
            work_types: список видов работ
            available_docs: список имеющихся документов [{doc_type, doc_id, name}, ...]

        Returns:
            CompReport с дельтой и списком разрывов
        """
        matrix = self.build_completeness_matrix(work_types)

        # Считаем имеющиеся документы по категориям
        present: Dict[ID344Category, int] = {cat: 0 for cat in ID344Category}
        if available_docs:
            for doc in available_docs:
                doc_type = doc.get("doc_type", "unknown")
                cat = self.classify_document(doc_type)
                present[cat] += 1

        # Вычисляем разрывы
        gaps: List[CompletenessGap] = []
        total = 0
        covered = 0

        for cat in ID344Category:
            required = matrix[cat]
            have = present[cat]
            total += required
            covered += min(have, required)

            if required > 0 and have < required:
                severity = "critical" if required > 1 and have == 0 else "high"
                if have > 0 and have >= required * 0.5:
                    severity = "medium"

                gaps.append(CompletenessGap(
                    category=cat,
                    description=f"{cat.value}: требуется {required}, имеется {have}",
                    severity=severity,
                    required_count=required,
                    present_count=have,
                ))

        # Строим шлейфы АОСР
        trails: List[AOSRTrail] = []
        for wt in work_types:
            aosr_list = self.get_required_aosr_list(wt)
            for aosr in aosr_list:
                if aosr.get("mandatory", True):
                    trail = self.build_aosr_trail(aosr["name"], wt)
                    trails.append(trail)

        return CompReport(
            project_id=project_id,
            work_types=work_types,
            total_positions=total,
            covered_positions=covered,
            gaps=gaps,
            aosr_trails=trails,
        )

    def format_report(self, report: CompReport) -> str:
        """Форматировать отчёт в читаемый текст."""
        lines = [
            f"╔══════════════════════════════════════════════════════╗",
            f"║  ОТЧЁТ О КОМПЛЕКТНОСТИ ИД — проект #{report.project_id}",
            f"╠══════════════════════════════════════════════════════╣",
            f"║  Виды работ: {', '.join(report.work_types)}",
            f"║  Полнота: {report.completeness_pct}% ({report.covered_positions}/{report.total_positions})",
            f"║  Критических разрывов: {len(report.critical_gaps)}",
            f"║  Всего разрывов: {len(report.gaps)}",
            f"║  АОСР в реестре: {len(report.aosr_trails)}",
            f"╚══════════════════════════════════════════════════════╝",
            "",
        ]

        if report.critical_gaps:
            lines.append("🔴 КРИТИЧЕСКИЕ РАЗРЫВЫ:")
            for g in report.critical_gaps:
                lines.append(f"  ✗ {g.description}")
            lines.append("")

        if report.gaps:
            lines.append("🟡 ВСЕ РАЗРЫВЫ:")
            for g in report.gaps:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(g.severity, "⚪")
                lines.append(f"  {icon} [{g.severity}] {g.description}")

        return "\n".join(lines)

    # =========================================================================
    # 5. Нормативная справка
    # =========================================================================

    def get_regulations(self) -> List[Dict[str, str]]:
        """Получить список действующих нормативных документов."""
        return COMMON_REGULATIONS

    def get_work_type_help(self, work_type: str) -> str:
        """Получить справку по виду работ."""
        try:
            wt = WorkType(work_type)
        except ValueError:
            return f"Неизвестный вид работ: {work_type}"

        acts = self.get_required_aosr_list(work_type)
        journals = self.get_required_journals(work_type)

        lines = [f"Вид работ: {wt.value}", ""]

        lines.append("Обязательные АОСР:")
        for a in acts:
            if a["mandatory"]:
                lines.append(f"  • {a['name']}")

        lines.append("\nОбязательные журналы:")
        for j in journals:
            if j["mandatory"]:
                lines.append(f"  • {j['name']} ({j.get('form', '')})")

        return "\n".join(lines)


# Синглтон
pto_agent = PTOAgent()
