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
    # 5. LLM-Powered Document Analysis
    # =========================================================================

    async def analyze_document_batch(
        self,
        documents: List[Dict[str, Any]],
        project_context: str = "",
    ) -> Dict[str, Any]:
        """
        Анализирует пакет документов через LLM: классификация, проверка связей, аномалии.

        Args:
            documents: [{"filename": str, "content_preview": str (первые 2000 символов), ...}]
            project_context: описание проекта для контекста

        Returns:
            {
                "classified": {filename: {"category_344": str, "doc_type": str, "confidence": float}},
                "issues": [{"doc": str, "issue": str, "severity": str}],
                "recommendations": [str],
            }
        """
        if not documents:
            return {"classified": {}, "issues": [], "recommendations": []}

        prompt = self._build_classification_prompt(documents, project_context)

        try:
            response = await self._llm.chat("pto", [
                {"role": "system", "content": (
                    "Ты — инженер ПТО строительной компании. Твоя задача — анализировать "
                    "пакет исполнительной документации на соответствие Приказу Минстроя №344/пр. "
                    "Отвечай строго в JSON-формате без markdown-обёрток."
                )},
                {"role": "user", "content": prompt},
            ], temperature=0.1)
        except Exception as e:
            logger.warning("LLM unavailable for PTO analysis: %s", e)
            return self._fallback_classify(documents)

        import json as _json
        try:
            result = _json.loads(response)
        except _json.JSONDecodeError:
            # Try to extract JSON from response
            import re as _re
            match = _re.search(r'\{[\s\S]*\}', response)
            if match:
                try:
                    result = _json.loads(match.group())
                except _json.JSONDecodeError:
                    return self._fallback_classify(documents)
            else:
                return self._fallback_classify(documents)

        return result

    def _build_classification_prompt(
        self,
        documents: List[Dict[str, Any]],
        project_context: str,
    ) -> str:
        """Строит промпт для классификации пакета документов."""
        lines = [
            "Проанализируй следующий пакет документов исполнительной документации.\n",
            "КОНТЕКСТ ПРОЕКТА:" if project_context else "",
            project_context if project_context else "",
            f"\nДОКУМЕНТЫ НА АНАЛИЗ ({len(documents)} шт.):\n",
        ]

        for i, doc in enumerate(documents, 1):
            fname = doc.get("filename", f"doc_{i}")
            content = doc.get("content_preview", doc.get("text", ""))[:2000]
            lines.append(f"--- Документ {i}: {fname} ---")
            lines.append(content[:1500])
            lines.append("")

        lines.append("""
ЗАДАЧА:
1. Классифицируй каждый документ по категории Приказа №344/пр:
   act_gro, act_axes, act_aosr, act_aook, act_aousito, remarks,
   work_drawings, igs, is_result, test_acts, lab_results, input_control, journals
2. Определи тип документа: АОСР, АООК, КС-2, КС-3, ВОР, ИГС, ИС,
   сертификат, паспорт качества, протокол испытаний, приказ, договор,
   журнал работ, чертёж, спецификация, уведомление, фотоотчёт
3. Найди проблемы:
   - Отсутствие обязательных подписей
   - Несоответствие дат (например, АОСР раньше протокола испытаний)
   - Ссылки на устаревшие формы (РД-11-02-2006 вместо Приказа №344/пр)
   - Отсутствие обязательных приложений
4. Дай рекомендации по доукомплектованию.

Верни ТОЛЬКО JSON (без markdown):
{
  "classified": {
    "имя_файла": {
      "category_344": "act_aosr",
      "doc_type": "АОСР",
      "confidence": 0.95,
      "work_type": "бетонирование фундамента",
      "has_signatures": true,
      "date_valid": true
    }
  },
  "issues": [
    {"doc": "имя_файла", "issue": "описание проблемы", "severity": "critical|high|medium|low"}
  ],
  "recommendations": ["рекомендация 1", "рекомендация 2"],
  "completeness_summary": "краткая оценка полноты пакета (1-2 предложения)"
}""")
        return "\n".join(lines)

    def _fallback_classify(
        self, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fallback-классификация без LLM (keyword-based)."""
        classified = {}
        for doc in documents:
            fname = doc.get("filename", "")
            text = (doc.get("content_preview", "") + " " + fname).lower()[:500]
            classified[fname] = {
                "category_344": "act_aosr" if "аоср" in text or "освидетельствование" in text
                else "test_acts" if "испытан" in text or "протокол" in text
                else "input_control" if "сертификат" in text or "паспорт" in text
                else "journals" if "журнал" in text
                else "work_drawings",
                "doc_type": "unknown",
                "confidence": 0.3,
                "llm_fallback": True,
            }
        return {
            "classified": classified,
            "issues": [],
            "recommendations": ["ВНИМАНИЕ: классификация выполнена без LLM (keyword-based). Точность низкая."],
            "completeness_summary": "LLM недоступен. Классификация по ключевым словам — требуется ручная проверка.",
        }

    async def verify_document_chain(
        self,
        aosr_text: str,
        related_docs: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        Проверяет цепочку документов для одного АОСР через LLM.

        Args:
            aosr_text: текст АОСР
            related_docs: [{"name": "ИГС.pdf", "text": "..."}, ...]

        Returns:
            {"valid": bool, "chain_gaps": [...], "date_conflicts": [...], "volume_mismatches": [...]}
        """
        prompt = f"""Проверь цепочку исполнительной документации.

АОСР:
{aosr_text[:3000]}

СВЯЗАННЫЕ ДОКУМЕНТЫ:
"""
        for d in related_docs:
            prompt += f"\n--- {d['name']} ---\n{d.get('text', '')[:1500]}\n"

        prompt += """
Проверь:
1. Правильность дат (АОСР должен быть ПОЗЖЕ протоколов испытаний)
2. Соответствие объёмов в АОСР и ВОР/КС-2
3. Наличие всех обязательных приложений (сертификаты, паспорта)
4. Соответствие вида работ проектным решениям
5. Ссылки на НТД — не устарели ли?

Верни JSON:
{
  "valid": true/false,
  "chain_gaps": ["отсутствует документ X"],
  "date_conflicts": ["конфликт дат между Y и Z"],
  "volume_mismatches": ["расхождение объёмов: АОСР=100м3, КС-2=95м3"],
  "outdated_refs": ["ссылка на РД-11-02-2006"],
  "overall": "краткое заключение (1-2 предложения)"
}"""

        try:
            response = await self._llm.chat("pto", [
                {"role": "system", "content": "Ты — инженер строительного контроля. Отвечай строго в JSON."},
                {"role": "user", "content": prompt},
            ], temperature=0.1)
            import json as _json
            return _json.loads(response)
        except Exception as e:
            logger.warning("LLM chain verification failed: %s", e)
            return {"valid": False, "chain_gaps": [], "date_conflicts": [],
                    "volume_mismatches": [], "error": str(e),
                    "overall": "Не удалось проверить цепочку — LLM недоступен."}

    # =========================================================================
    # 6. Нормативная справка (с проверкой актуальности)
    # =========================================================================

    def check_norms_validity(self, norm_refs: List[str]) -> List[Dict[str, Any]]:
        """
        Проверить актуальность списка нормативных ссылок через InvalidationEngine.

        Возвращает список предупреждений для устаревших/заменённых норм.
        """
        try:
            from src.core.knowledge.invalidation_engine import invalidation_engine
            results = invalidation_engine.check_validity_batch(norm_refs)
        except Exception:
            return []

        warnings = []
        for ref, status in results.items():
            if not status.get("valid", True) or status.get("warning"):
                warnings.append({
                    "norm_ref": ref,
                    "status": status.get("status", "unknown"),
                    "replaced_by": status.get("replaced_by"),
                    "warning": status.get("warning", ""),
                })
        return warnings

    def get_regulations(self) -> List[Dict[str, str]]:
        """Получить список действующих нормативных документов."""
        return COMMON_REGULATIONS

    def get_regulations_with_validity(self) -> Dict[str, Any]:
        """
        Получить список нормативных документов с проверкой актуальности.

        Returns:
            {"regulations": [...], "stale_warnings": [...]}
        """
        regs = COMMON_REGULATIONS
        refs = [r.get("code", "") for r in regs if r.get("code")]
        stale_warnings = self.check_norms_validity(refs)

        annotated = []
        for r in regs:
            entry = dict(r)
            code = r.get("code", "")
            stale = next((w for w in stale_warnings if w["norm_ref"] == code), None)
            entry["is_current"] = stale is None
            entry["stale_warning"] = stale["warning"] if stale else ""
            annotated.append(entry)

        return {
            "regulations": annotated,
            "stale_warnings": stale_warnings,
            "has_stale": len(stale_warnings) > 0,
        }

    def get_work_type_help(self, work_type: str) -> str:
        """Получить справку по виду работ (с проверкой актуальности норм)."""
        # Try WorkType enum first (work_spec.py)
        try:
            wt = WorkType(work_type)
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
        except ValueError:
            pass

        # Fallback: query idprosto knowledge base
        try:
            from src.core.knowledge.idprosto_loader import idprosto_loader
            code = idprosto_loader.resolve_work_type(work_type)
            if code:
                summary = idprosto_loader.get_work_type_summary(code)
                lines = [f"Вид работ: {summary['name']} [{code}]", ""]
                lines.append(f"Всего документов в перечне: {summary['total_docs']}")
                lines.append("")

                # Check normative refs validity
                if summary.get("normative_refs"):
                    validity = self.check_norms_validity(summary["normative_refs"][:20])
                    if validity:
                        lines.append("ПРЕДУПРЕЖДЕНИЯ ОБ АКТУАЛЬНОСТИ НОРМ:")
                        for w in validity:
                            lines.append(f"  • {w['warning']}")
                        lines.append("")

                if summary["aosr"]:
                    lines.append("Акты скрытых работ (АОСР):")
                    for a in summary["aosr"]:
                        lines.append(f"  • {a['name']}")
                if summary["aook"]:
                    lines.append("\nАкты ответственных конструкций (АООК):")
                    for a in summary["aook"]:
                        lines.append(f"  • {a['name']}")
                if summary["journals"]:
                    lines.append("\nЖурналы:")
                    for j in summary["journals"]:
                        lines.append(f"  • {j['name']} [{j.get('form', '')}]")
                if summary["test_acts"]:
                    lines.append(f"\nАкты испытаний/протоколы: {len(summary['test_acts'])} шт.")
                if summary["schemas"]:
                    lines.append(f"Исполнительные схемы: {len(summary['schemas'])} шт.")
                lines.append(f"\nНормативных ссылок: {len(summary['normative_refs'])}")
                return "\n".join(lines)
        except Exception:
            pass

        return f"Неизвестный вид работ: {work_type}"


# Синглтон
pto_agent = PTOAgent()
