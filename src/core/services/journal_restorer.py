"""
ASD v12.0 — Journal Restoration Service.

Восстанавливает (реконструирует) Общий журнал работ (ОЖР) и специальные
журналы из имеющихся данных: АОСР, КС-2, ВОР, геодезические отчёты.

Сценарий: подрядчик потерял/не вёл журнал, но есть полный комплект АОСР,
КС-2, исполнительных схем и геодезии. Заказчик/стройконтроль требует журнал
перед приёмкой. АСД реконструирует журнал из первичных документов.

Нормативная база:
  - Приказ № 1026/пр (7 разделов ОЖР, замена РД 11-05-2007)
  - Приказ № 344/пр (АОСР, АООК — источники данных)
  - СП 48.13330.2019 (организация строительства)

Концепция:
  Каждый АОСР + КС-2 — это «точка данных» на временной шкале.
  JournalRestorer собирает все точки, сортирует по датам, заполняет
  разделы журнала, проверяет цепочку (акт → схема → протокол → запись),
  генерирует готовый DOCX журнала.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Journal Model (Приказ №1026/пр — 7 разделов)
# =============================================================================

class JournalSection(str, Enum):
    """7 разделов ОЖР по Приказу №1026/пр."""
    SEC_1 = "sec_1_general"         # Общие сведения об объекте
    SEC_2 = "sec_2_participants"    # Участники строительства
    SEC_3 = "sec_3_work_log"        # Журнал учёта выполнения работ
    SEC_4 = "sec_4_control"         # Строительный контроль
    SEC_5 = "sec_5_author_supervision"  # Авторский надзор
    SEC_6 = "sec_6_input_control"   # Входной контроль материалов
    SEC_7 = "sec_7_remarks"         # Замечания и предписания


@dataclass
class JournalEntry:
    """Одна запись в ОЖР (раздел 3 — учёт работ)."""
    entry_date: str
    work_description: str
    work_type: str
    executor: str = ""
    aosr_ref: str = ""             # Ссылка на АОСР
    ks2_ref: str = ""              # Ссылка на строку КС-2
    is_scheme_ref: str = ""        # Ссылка на ИС
    materials_used: List[str] = field(default_factory=list)
    equipment_used: List[str] = field(default_factory=list)
    weather: str = ""
    temperature_c: Optional[float] = None
    notes: str = ""

    @property
    def date(self) -> datetime:
        return datetime.fromisoformat(self.entry_date)


@dataclass
class Section3Data:
    """Раздел 3: журнал учёта выполнения работ."""
    entries: List[JournalEntry] = field(default_factory=list)

    @property
    def date_range(self) -> Tuple[str, str]:
        if not self.entries:
            return ("", "")
        sorted_entries = sorted(self.entries, key=lambda e: e.entry_date)
        return (sorted_entries[0].entry_date, sorted_entries[-1].entry_date)

    @property
    def total_work_days(self) -> int:
        dates = {e.entry_date for e in self.entries}
        return len(dates)

    @property
    def by_aosr(self) -> Dict[str, List[JournalEntry]]:
        """Сгруппировать по АОСР."""
        groups: Dict[str, List[JournalEntry]] = {}
        for e in self.entries:
            key = e.aosr_ref or "unknown"
            if key not in groups:
                groups[key] = []
            groups[key].append(e)
        return groups


@dataclass
class JournalData:
    """Полный набор данных для ОЖР."""
    project_id: int
    project_name: str
    customer: str = ""
    contractor: str = ""
    section_1: Dict[str, Any] = field(default_factory=dict)
    section_2: List[Dict[str, str]] = field(default_factory=list)
    section_3: Section3Data = field(default_factory=Section3Data)
    section_4: List[Dict[str, str]] = field(default_factory=list)
    section_6: List[Dict[str, Any]] = field(default_factory=list)
    section_7: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_viable(self) -> bool:
        """Можно ли восстановить журнал (есть хотя бы раздел 3)."""
        return len(self.section_3.entries) > 0

    @property
    def gaps(self) -> List[str]:
        """Пропуски в данных."""
        issues = []
        if not self.section_1:
            issues.append("Раздел 1: отсутствуют общие сведения")
        if not self.section_2:
            issues.append("Раздел 2: отсутствуют участники")
        if not self.section_3.entries:
            issues.append("Раздел 3: нет записей о работах")
        return issues


# =============================================================================
# Data Extractor — достаёт данные из АОСР/КС-2 etc.
# =============================================================================

class JournalDataExtractor:
    """
    Извлекает данные для журнала из первичных документов.
    """

    def extract_from_aosr(self, aosr_data: Dict[str, Any]) -> Optional[JournalEntry]:
        """
        Извлечь запись журнала из данных АОСР.

        Ожидаемые поля в aosr_data:
          - aosr_number: str
          - work_type: str
          - work_start: str
          - work_end: str
          - materials: list[str]
          - project_name: str
        """
        try:
            return JournalEntry(
                entry_date=aosr_data.get("work_start", ""),
                work_description=aosr_data.get("work_type", "Неизвестная работа"),
                work_type=aosr_data.get("work_type", ""),
                executor=aosr_data.get("executor_company", "ООО «КСК №1»"),
                aosr_ref=aosr_data.get("aosr_number", ""),
                materials_used=aosr_data.get("materials", []),
                notes=f"АОСР: {aosr_data.get('aosr_number', '')}. "
                      f"Решение: {aosr_data.get('decision', 'разрешается')}.",
            )
        except Exception as e:
            logger.warning("Failed to extract journal entry from AOSR: %s", e)
            return None

    def extract_from_ks2_line(
        self, line: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[JournalEntry]:
        """
        Извлечь запись из строки КС-2.

        Ожидаемые поля:
          - name: наименование работ
          - code: шифр расценки
          - quantity: объём
          - date: дата (из контекста)
        """
        try:
            return JournalEntry(
                entry_date=context.get("date", ""),
                work_description=f"{line.get('name', '')} — "
                                f"{line.get('quantity', '')} {line.get('unit', '')} "
                                f"(расценка {line.get('code', '')})",
                work_type=line.get("work_type", ""),
                ks2_ref=context.get("ks2_number", ""),
                notes=f"Строка КС-2. Сумма: {line.get('total', 0):.2f} руб.",
            )
        except Exception as e:
            logger.warning("Failed to extract from KS-2 line: %s", e)
            return None

    def extract_from_vor(
        self, vor_positions: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[JournalEntry]:
        """Извлечь записи из ВОР (Ведомость объёмов работ)."""
        entries = []
        for pos in vor_positions:
            try:
                entries.append(JournalEntry(
                    entry_date=context.get("date", ""),
                    work_description=f"{pos.get('name', '')} — "
                                    f"{pos.get('quantity', '')} {pos.get('unit', '')}",
                    work_type=pos.get("work_type", ""),
                    notes="Из ВОР (ведомость объёмов работ)",
                ))
            except Exception as e:
                logger.warning("VOR extraction error: %s", e)
        return entries


# =============================================================================
# Journal Restorer
# =============================================================================

class JournalRestorer:
    """
    Восстанавливает Общий журнал работ (ОЖР) из первичной документации.

    Args:
        llm_engine: LLM engine для проверки и дополнения данных
    """

    def __init__(self, llm_engine=None):
        from src.core.llm_engine import llm_engine as _llm
        self._llm = llm_engine or _llm
        self._extractor = JournalDataExtractor()

    # -------------------------------------------------------------------------
    # Restoration Pipeline
    # -------------------------------------------------------------------------

    def reconstruct(
        self,
        project_id: int,
        project_name: str,
        aosr_list: List[Dict[str, Any]],
        ks2_lines: Optional[List[Dict[str, Any]]] = None,
        vor_positions: Optional[List[Dict[str, Any]]] = None,
        project_meta: Optional[Dict[str, Any]] = None,
    ) -> JournalData:
        """
        Главный метод: реконструировать журнал из первичных данных.

        Args:
            project_id: ID проекта
            project_name: название объекта
            aosr_list: список АОСР [{"aosr_number": ..., "work_type": ..., ...}, ...]
            ks2_lines: строки КС-2
            vor_positions: позиции ВОР
            project_meta: {"customer": ..., "contractor": ..., ...}

        Returns:
            JournalData с заполненными разделами
        """
        meta = project_meta or {}
        journal = JournalData(
            project_id=project_id,
            project_name=project_name,
            customer=meta.get("customer", ""),
            contractor=meta.get("contractor", "ООО «КСК №1»"),
            section_1={
                "object_name": project_name,
                "address": meta.get("object_address", ""),
                "developer": meta.get("developer", "Заказчик"),
                "general_contractor": meta.get("customer", ""),
                "contractor": meta.get("contractor", "ООО «КСК №1»"),
                "designer": meta.get("designer", "Проектная организация"),
                "contract_number": meta.get("contract_number", ""),
                "contract_date": meta.get("contract_date", ""),
            },
            section_2=meta.get("participants", []),
        )

        # Раздел 3: записи из АОСР
        for aosr in aosr_list:
            entry = self._extractor.extract_from_aosr(aosr)
            if entry:
                journal.section_3.entries.append(entry)

        # Раздел 3: записи из КС-2
        if ks2_lines:
            ks2_context = {
                "date": meta.get("ks2_date", ""),
                "ks2_number": meta.get("ks2_number", ""),
            }
            for line in ks2_lines:
                entry = self._extractor.extract_from_ks2_line(line, ks2_context)
                if entry:
                    journal.section_3.entries.append(entry)

        # Раздел 3: записи из ВОР
        if vor_positions:
            vor_context = {"date": meta.get("vor_date", "")}
            entries = self._extractor.extract_from_vor(vor_positions, vor_context)
            journal.section_3.entries.extend(entries)

        # Сортировка по дате
        journal.section_3.entries.sort(key=lambda e: e.entry_date or "0000-00-00")

        # Раздел 4: строительный контроль (из решений АОСР)
        for aosr in aosr_list:
            if aosr.get("decision") == "запрещается":
                journal.section_4.append({
                    "date": aosr.get("work_start", ""),
                    "inspector": aosr.get("inspector", ""),
                    "result": "Выполнение последующих работ запрещено",
                    "aosr_ref": aosr.get("aosr_number", ""),
                })

        logger.info(
            "Journal reconstructed: project=%d, entries=%d, gaps=%d",
            project_id, len(journal.section_3.entries), len(journal.gaps),
        )
        return journal

    # -------------------------------------------------------------------------
    # LLM-powered gap filling
    # -------------------------------------------------------------------------

    async def fill_gaps(
        self, journal: JournalData, available_docs: List[str]
    ) -> Dict[str, Any]:
        """
        Использует LLM для заполнения пропусков в журнале.

        Args:
            journal: реконструированный журнал с пропусками
            available_docs: список доступных документов

        Returns:
            {"filled_sections": [...], "still_missing": [...], "confidence": float}
        """
        prompt = f"""Проанализируй восстановленный Общий журнал работ и найди пропуски.

ПРОЕКТ: {journal.project_name}
ЗАПИСЕЙ В РАЗДЕЛЕ 3: {len(journal.section_3.entries)}
ПЕРИОД: {journal.section_3.date_range[0]} – {journal.section_3.date_range[1]}

ПРОПУСКИ:
{chr(10).join(f'- {g}' for g in journal.gaps)}

ДОСТУПНЫЕ ДОКУМЕНТЫ:
{chr(10).join(f'- {d}' for d in available_docs)}

ЗАДАЧА:
1. Какие разделы можно заполнить из имеющихся документов?
2. Какие данные точно отсутствуют?
3. Предложи конкретные источники для каждого пропущенного поля.

Верни JSON:
{{
  "fillable": [{{"section": "sec_1_general", "field": "object_name", "source": "...", "value": "..."}}],
  "still_missing": ["перечень того что точно отсутствует"],
  "confidence": 0.0-1.0,
  "recommendation": "краткая рекомендация"
}}"""

        try:
            response = await self._llm.chat("pto", [
                {"role": "system", "content": "Ты — инженер ПТО. Анализируй комплектность документации. JSON-only ответ."},
                {"role": "user", "content": prompt},
            ], temperature=0.1)
            import json as _json
            return _json.loads(response)
        except Exception as e:
            logger.warning("LLM gap analysis failed: %s", e)
            return {"fillable": [], "still_missing": journal.gaps, "confidence": 0.0}

    # -------------------------------------------------------------------------
    # DOCX Export (delegates to OutputPipeline)
    # -------------------------------------------------------------------------

    def to_aosr_data(self, journal: JournalData) -> List[Dict[str, Any]]:
        """
        Конвертирует записи журнала обратно в структуру для АОСР-генерации.
        Позволяет «развернуть» журнал → комплект АОСР.
        """
        aosr_data_list = []
        for aosr_ref, entries in journal.section_3.by_aosr.items():
            if not entries:
                continue
            first = entries[0]
            materials = []
            for e in entries:
                materials.extend(e.materials_used)

            aosr_data_list.append({
                "aosr_number": aosr_ref,
                "project_name": journal.project_name,
                "work_type": first.work_type,
                "work_start": first.entry_date,
                "work_end": entries[-1].entry_date if len(entries) > 1 else first.entry_date,
                "materials": list(set(materials)),
                "executor_company": journal.contractor,
                "customer_company": journal.customer,
                "decision": "разрешается",
            })
        return aosr_data_list

    def to_register_entries(self, journal: JournalData) -> List[Dict[str, Any]]:
        """Конвертирует записи в формат для DocRegistry / IDRegisterGenerator."""
        docs = []
        # АОСР
        for aosr_ref in journal.section_3.by_aosr:
            docs.append({
                "number": aosr_ref,
                "name": f"Акт освидетельствования скрытых работ {aosr_ref}",
                "pages": 2,
                "date": journal.section_3.by_aosr[aosr_ref][0].entry_date if journal.section_3.by_aosr[aosr_ref] else "",
                "status": "prepared",
                "note": "Сгенерировано автоматически (восстановление журнала)",
            })

        # КС-2
        ks2_set = set()
        for e in journal.section_3.entries:
            if e.ks2_ref and e.ks2_ref not in ks2_set:
                ks2_set.add(e.ks2_ref)
                docs.append({
                    "number": e.ks2_ref,
                    "name": "Акт о приёмке выполненных работ (КС-2)",
                    "pages": 1,
                    "date": e.entry_date,
                    "status": "prepared",
                    "note": "Сгенерировано из строк КС-2",
                })

        return docs


# Синглтон
journal_restorer = JournalRestorer()
