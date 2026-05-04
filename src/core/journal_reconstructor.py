"""
ASD v12.0 — Journal Reconstructor v2.

Восстанавливает Общий Журнал Работ (ОЖР) из Evidence Graph.
Пять этапов реконструкции с цветовой разметкой уверенности.

Цвета (из evidence_graph.confidence_color):
    ≥ 0.8  — зелёный  (ПОДТВЕРЖДЕНО — АОСР, КС-2)
    ≥ 0.6  — жёлтый   (ВЫСОКАЯ — сертификаты, ТТН, фото)
    ≥ 0.4  — красный  (НИЗКАЯ — inference engine)
    < 0.4  — серый    (НЕДОСТОВЕРНО — лакуны)

Usage:
    from src.core.journal_reconstructor import journal_reconstructor
    
    journal = journal_reconstructor.reconstruct(evidence_graph)
    for entry in journal.entries:
        print(f"{entry.date} [{entry.color}] {entry.work_type}: {entry.description}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════

class EntrySource(str, Enum):
    AOSR = "aosr"                    # Из акта освидетельствования
    KS2 = "ks2"                      # Из КС-2
    CERTIFICATE = "certificate"      # Из сертификата (дата поставки)
    TTN = "ttn"                      # Из товарно-транспортной накладной
    PHOTO = "photo"                  # Из фото с меткой времени
    INFERENCE = "inference"          # Выведено Inference Engine
    HUMAN = "human"                  # Подтверждено оператором
    LACUNA = "lacuna"                # Лакуна — предположение на основе цепочки
    PROJECT = "project"              # Из проектной документации (план)


@dataclass
class JournalEntry:
    """Одна запись в реконструированном журнале."""
    date: str                        # ISO-дата (YYYY-MM-DD)
    work_type: str                   # Тип работы
    description: str = ""            # Описание
    volume: Optional[float] = None   # Объём за день
    unit: str = ""                   # Единица измерения
    confidence: float = 0.0          # 0.0–1.0
    source: EntrySource = EntrySource.LACUNA
    evidence_nodes: List[str] = field(default_factory=list)
    operators: str = ""              # Исполнители
    materials: str = ""              # Материалы
    notes: str = ""                  # Примечания
    
    @property
    def color(self) -> str:
        """Цветовой код уверенности."""
        if self.confidence >= 0.8:
            return "green"
        elif self.confidence >= 0.6:
            return "yellow"
        elif self.confidence >= 0.4:
            return "red"
        return "gray"
    
    @property
    def confidence_label(self) -> str:
        if self.confidence >= 1.0:
            return "ПОДТВЕРЖДЕНО"
        elif self.confidence >= 0.8:
            return "ВЫСОКАЯ"
        elif self.confidence >= 0.6:
            return "СРЕДНЯЯ"
        elif self.confidence >= 0.4:
            return "НИЗКАЯ"
        return "НЕДОСТОВЕРНО"


@dataclass
class ReconstructedJournal:
    """Реконструированный Общий Журнал Работ."""
    project_id: str = ""
    entries: List[JournalEntry] = field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # Статистика
    total_entries: int = 0
    confirmed_entries: int = 0       # green
    high_entries: int = 0            # yellow
    low_entries: int = 0             # red
    inferred_entries: int = 0        # gray
    coverage: float = 0.0            # % покрытия относительно плановых дат
    
    def summary(self) -> str:
        lines = [
            f"═══ РЕКОНСТРУИРОВАННЫЙ ЖУРНАЛ ═══",
            f"Проект: {self.project_id}",
            f"Период: {self.start_date} – {self.end_date}",
            f"Записей: {self.total_entries}",
            f"  🟢 ПОДТВЕРЖДЕНО: {self.confirmed_entries}",
            f"  🟡 ВЫСОКАЯ:     {self.high_entries}",
            f"  🔴 НИЗКАЯ:      {self.low_entries}",
            f"  ⬜ ЛАКУНЫ:      {self.inferred_entries}",
            f"Покрытие: {self.coverage:.0%}",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Journal Reconstructor
# ═══════════════════════════════════════════════════════════════════════════

class JournalReconstructor:
    """
    Реконструктор Общего Журнала Работ (ОЖР).
    
    5 этапов:
      1. Extract — собрать все датированные факты
      2. Fill — заполнить известные записи (АОСР, КС-2)
      3. Infer — вывести записи из поставок + типовых темпов
      4. Detect — найти лакуны в хронологии
      5. Generate — сформировать цветной журнал
    """

    def __init__(self):
        pass

    def reconstruct(self, graph, project_id: str = "") -> ReconstructedJournal:
        """
        Реконструировать ОЖР из Evidence Graph.
        
        Args:
            graph: EvidenceGraph instance
            project_id: идентификатор проекта
        
        Returns:
            ReconstructedJournal с записями и статистикой
        """
        from src.core.evidence_graph import (
            WorkUnitStatus, DocType, EdgeType, EventType,
            confidence_color, confidence_label,
        )
        
        journal = ReconstructedJournal(project_id=project_id)
        
        # ── Этап 1: Extract — собрать все датированные факты ──────────
        dated_facts = self._extract_dated_facts(graph)
        if not dated_facts:
            return journal
        
        # ── Этап 2: Fill — заполнить известные записи ─────────────────
        known_entries = self._fill_known_entries(graph, dated_facts)
        journal.entries.extend(known_entries)
        
        # ── Этап 3: Infer — вывести из поставок ───────────────────────
        inferred_entries = self._infer_from_materials(graph, known_entries)
        journal.entries.extend(inferred_entries)
        
        # ── Этап 4: Detect — найти лакуны ─────────────────────────────
        lacunae = self._detect_lacunae(journal.entries)
        journal.entries.extend(lacunae)
        
        # ── Этап 5: Generate — сортировка и статистика ────────────────
        journal.entries.sort(key=lambda e: e.date)
        
        if journal.entries:
            journal.start_date = journal.entries[0].date
            journal.end_date = journal.entries[-1].date
        
        journal.total_entries = len(journal.entries)
        journal.confirmed_entries = sum(1 for e in journal.entries if e.color == "green")
        journal.high_entries = sum(1 for e in journal.entries if e.color == "yellow")
        journal.low_entries = sum(1 for e in journal.entries if e.color == "red")
        journal.inferred_entries = sum(1 for e in journal.entries if e.color == "gray")
        
        # Покрытие: сколько дней имеют хотя бы одну запись
        if journal.start_date and journal.end_date:
            try:
                d1 = date.fromisoformat(journal.start_date)
                d2 = date.fromisoformat(journal.end_date)
                total_days = (d2 - d1).days + 1
                days_with_entries = len(set(e.date for e in journal.entries))
                journal.coverage = min(1.0, days_with_entries / total_days) if total_days > 0 else 0.0
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Coverage calculation failed: %s", e)
                journal.coverage = 0.0
        
        return journal

    # ── Private Methods ─────────────────────────────────────────────────────

    def _extract_dated_facts(self, graph) -> List[dict]:
        """Собрать все факты с датами из графа."""
        from src.core.evidence_graph import WorkUnitStatus
        
        facts = []
        
        # WorkUnits with dates
        for nid, data in graph.graph.nodes(data=True):
            if data.get('node_type') == 'WorkUnit':
                sdate = data.get('start_date')
                edate = data.get('end_date')
                if sdate or edate:
                    facts.append({
                        'date': sdate or edate,
                        'end_date': edate,
                        'type': 'work_unit',
                        'node_id': nid,
                        'work_type': data.get('work_type', ''),
                        'description': data.get('description', ''),
                        'volume': data.get('volume'),
                        'unit': data.get('unit', ''),
                        'confidence': data.get('confidence', 1.0),
                        'status': data.get('status', ''),
                    })
            
            elif data.get('node_type') == 'DateEvent':
                ts = data.get('timestamp')
                if ts:
                    facts.append({
                        'date': ts[:10] if len(ts) >= 10 else ts,
                        'end_date': None,
                        'type': 'event',
                        'node_id': nid,
                        'event_type': data.get('event_type', ''),
                        'description': data.get('description', ''),
                        'confidence': data.get('confidence', 1.0),
                    })
            
            elif data.get('node_type') == 'Document':
                ddate = data.get('doc_date')
                if ddate:
                    facts.append({
                        'date': ddate,
                        'end_date': None,
                        'type': 'document',
                        'node_id': nid,
                        'doc_type': data.get('doc_type', ''),
                        'doc_number': data.get('doc_number', ''),
                        'confidence': data.get('confidence', 1.0),
                    })
            
            elif data.get('node_type') == 'MaterialBatch':
                ddate = data.get('delivery_date')
                if ddate:
                    facts.append({
                        'date': ddate,
                        'end_date': None,
                        'type': 'material',
                        'node_id': nid,
                        'material_name': data.get('material_name', ''),
                        'quantity': data.get('quantity', 0),
                        'unit': data.get('unit', ''),
                        'confidence': data.get('confidence', 1.0),
                    })
        
        return facts

    def _fill_known_entries(self, graph, facts: List[dict]) -> List[JournalEntry]:
        """Заполнить записи из известных источников (АОСР, КС-2)."""
        from src.core.evidence_graph import DocType
        
        entries = []
        used_dates = set()
        
        # 1. АОСР — самый надёжный источник
        aosr_docs = graph.get_documents(DocType.AOSR)
        for doc in aosr_docs:
            ddate = doc.get('doc_date')
            if not ddate:
                continue
            
            wu_id = doc.get('work_unit_id')
            wu_data = {}
            if wu_id and graph.graph.has_node(wu_id):
                wu_data = dict(graph.graph.nodes[wu_id])
            
            entries.append(JournalEntry(
                date=ddate,
                work_type=wu_data.get('work_type', ''),
                description=wu_data.get('description', doc.get('content_summary', '')),
                volume=wu_data.get('volume'),
                unit=wu_data.get('unit', ''),
                confidence=0.95,
                source=EntrySource.AOSR,
                evidence_nodes=[doc['id']] + ([wu_id] if wu_id else []),
            ))
            used_dates.add(ddate)
        
        # 2. КС-2 — подтверждение объёмов
        ks2_docs = graph.get_documents(DocType.KS2)
        for doc in ks2_docs:
            ddate = doc.get('doc_date')
            if not ddate:
                continue
            
            wu_id = doc.get('work_unit_id')
            wu_data = {}
            if wu_id and graph.graph.has_node(wu_id):
                wu_data = dict(graph.graph.nodes[wu_id])
            
            # КС-2 может подтверждать ту же работу, что и АОСР — не дублируем
            if ddate in used_dates:
                continue
            
            entries.append(JournalEntry(
                date=ddate,
                work_type=wu_data.get('work_type', ''),
                description=wu_data.get('description', 'Работы по КС-2'),
                volume=wu_data.get('volume'),
                unit=wu_data.get('unit', ''),
                confidence=0.85,
                source=EntrySource.KS2,
                evidence_nodes=[doc['id']],
            ))
            used_dates.add(ddate)
        
        # 3. DateEvents с высокой уверенностью (фото, инспекции)
        for fact in facts:
            if fact['type'] == 'event' and fact.get('confidence', 0) >= 0.7:
                d = fact['date']
                if d not in used_dates:
                    entries.append(JournalEntry(
                        date=d,
                        work_type=fact.get('event_type', ''),
                        description=fact.get('description', ''),
                        confidence=fact.get('confidence', 0.7),
                        source=EntrySource.PHOTO,
                        evidence_nodes=[fact['node_id']],
                    ))
                    used_dates.add(d)
        
        return entries

    def _infer_from_materials(self, graph, known_entries: List[JournalEntry]) -> List[JournalEntry]:
        """Вывести записи из поставок материалов + типовых темпов."""
        from src.core.evidence_graph import DocType, EdgeType
        
        entries = []
        known_dates = set(e.date for e in known_entries)
        
        # Найти все MaterialBatch с датами поставки
        materials = []
        for nid, data in graph.graph.nodes(data=True):
            if data.get('node_type') == 'MaterialBatch':
                ddate = data.get('delivery_date')
                if ddate:
                    materials.append({
                        'node_id': nid,
                        'delivery_date': ddate,
                        'material_name': data.get('material_name', ''),
                        'quantity': data.get('quantity', 0.0),
                        'unit': data.get('unit', ''),
                        'confidence': data.get('confidence', 1.0),
                    })
        
        # Для каждого материала найти WorkUnit, где он использован
        for mat in materials:
            # Найти WorkUnit через USED_IN edge
            for succ in graph.graph.successors(mat['node_id']):
                succ_data = graph.graph.nodes[succ]
                if succ_data.get('node_type') != 'WorkUnit':
                    continue
                
                wu_type = succ_data.get('work_type', '')
                edge = graph.graph.edges.get((mat['node_id'], succ), {})
                edge_conf = edge.get('confidence', 1.0)
                
                # Проверить: есть ли уже АОСР для этого WorkUnit?
                # Если есть — не инферим (работа подтверждена)
                wu_end_date = succ_data.get('end_date')
                has_aosr = any(
                    e.source == EntrySource.AOSR and e.work_type == wu_type
                    for e in entries
                )
                if has_aosr:
                    continue
                
                # Вычислить даты работ: поставка + typical rate
                try:
                    from src.core.inference_engine import inference_engine
                    rate_info = inference_engine._rates.get(wu_type, 
                                inference_engine._rates.get('default', {'rate': 1, 'unit': 'ед/день'}))
                    daily_rate = rate_info.get('rate', 1)
                except (ImportError, AttributeError, KeyError, TypeError) as e:
                    logger.debug("Rate lookup failed for '%s': %s", wu_type, e)
                    daily_rate = 1
                
                qty = mat['quantity'] or 1
                work_days = max(1, int(qty / daily_rate)) if daily_rate > 0 else 1
                
                try:
                    ddate = date.fromisoformat(mat['delivery_date'])
                    start = ddate + timedelta(days=1)
                    end_date_limit = None
                    if wu_end_date:
                        end_date_limit = date.fromisoformat(wu_end_date)
                    
                    for day_offset in range(min(work_days, 30)):
                        work_date = start + timedelta(days=day_offset)
                        
                        # Не инферить дальше даты окончания WorkUnit
                        if end_date_limit and work_date > end_date_limit:
                            break
                        
                        work_date_str = work_date.isoformat()
                        if work_date_str in known_dates:
                            continue
                        
                        day_volume = qty / work_days  # Равномерно распределяем
                        
                        entries.append(JournalEntry(
                            date=work_date_str,
                            work_type=wu_type,
                            description=f"{mat['material_name']} — день {day_offset+1}/{work_days}",
                            volume=round(day_volume, 2),
                            unit=mat['unit'],
                            confidence=min(0.65, mat['confidence'] * edge_conf),
                            source=EntrySource.INFERENCE,
                            evidence_nodes=[mat['node_id'], succ],
                            materials=mat['material_name'],
                        ))
                        known_dates.add(work_date_str)
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug("Work date expansion failed for '%s': %s", mat.get('material_name', '?'), e)
        
        return entries

    def _detect_lacunae(self, entries: List[JournalEntry]) -> List[JournalEntry]:
        """Найти лакуны в хронологии и пометить их."""
        if len(entries) < 2:
            return []
        
        sorted_entries = sorted(entries, key=lambda e: e.date)
        lacunae = []
        
        for i in range(len(sorted_entries) - 1):
            try:
                d1 = date.fromisoformat(sorted_entries[i].date)
                d2 = date.fromisoformat(sorted_entries[i+1].date)
                gap = (d2 - d1).days
                
                if gap > 3:  # Разрыв > 3 дней — лакуна
                    # Заполняем каждый день лакуны
                    for day_offset in range(1, gap):
                        lacuna_date = d1 + timedelta(days=day_offset)
                        lacuna_str = lacuna_date.isoformat()
                        
                        # Контекст: что было до и после
                        prev_type = sorted_entries[i].work_type
                        next_type = sorted_entries[i+1].work_type
                        
                        lacunae.append(JournalEntry(
                            date=lacuna_str,
                            work_type=f"ЛАКУНА ({prev_type} → {next_type})",
                            description=f"Разрыв {gap} дн. между {sorted_entries[i].date} и {sorted_entries[i+1].date}",
                            confidence=0.1,  # Минимальная уверенность
                            source=EntrySource.LACUNA,
                            notes=f"Требуется уточнение у оператора. День {day_offset} из {gap}.",
                        ))
            except (ValueError, TypeError) as e:
                logger.debug("Lacuna entry creation failed: %s", e)

        return lacunae

    def format_journal_table(self, journal: ReconstructedJournal, max_entries: int = 50) -> str:
        """Форматировать журнал в таблицу для вывода."""
        color_map = {
            "green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⬜"
        }
        
        lines = [journal.summary(), "", f"{'Дата':<12} {'Статус':<6} {'Вид работ':<30} {'Объём':<12} {'Источник':<12}"]
        lines.append("-" * 80)
        
        for e in journal.entries[:max_entries]:
            icon = color_map.get(e.color, "⬜")
            vol_str = f"{e.volume} {e.unit}" if e.volume else "-"
            lines.append(
                f"{e.date:<12} {icon} {e.confidence_label:<4} "
                f"{e.work_type[:28]:<30} {vol_str:<12} {e.source.value:<12}"
            )
        
        if len(journal.entries) > max_entries:
            lines.append(f"...и ещё {len(journal.entries) - max_entries} записей")
        
        return "\n".join(lines)

    def to_json(self, journal: ReconstructedJournal) -> dict:
        """Сериализовать журнал в JSON."""
        return {
            "project_id": journal.project_id,
            "start_date": journal.start_date,
            "end_date": journal.end_date,
            "total_entries": journal.total_entries,
            "coverage": journal.coverage,
            "stats": {
                "confirmed": journal.confirmed_entries,
                "high": journal.high_entries,
                "low": journal.low_entries,
                "inferred": journal.inferred_entries,
            },
            "entries": [
                {
                    "date": e.date,
                    "work_type": e.work_type,
                    "description": e.description,
                    "volume": e.volume,
                    "unit": e.unit,
                    "confidence": e.confidence,
                    "color": e.color,
                    "source": e.source.value,
                    "evidence_nodes": e.evidence_nodes,
                }
                for e in journal.entries
            ],
        }


# Модульный синглтон
journal_reconstructor = JournalReconstructor()
