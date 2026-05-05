"""
ASD v13.0 — Evidence Graph v2.

Единый граф доказательств для двух режимов:
  - Сопровождение: WorkUnit от агентов, confidence=1.0
  - Антикризис: WorkUnit от Inference Engine, confidence=0.4–0.85

7 типов узлов: WorkUnit, MaterialBatch, Document, Person, DateEvent, Volume, Location.
11 типов связей: USED_IN, CONFIRMED_BY, REFERENCES, TEMPORAL_BEFORE/AFTER,
                  LOCATED_AT, SUPPLIED_BY, SIGNED_BY, DERIVED_FROM, HAS_EVENT,
                  DEFINES_VOLUME, MENTIONS.

Каждый узел и ребро имеет confidence: 0.0–1.0.
Граф — NetworkX DiGraph, persistence — pickle в data/graphs/.

Usage:
    from src.core.evidence_graph import evidence_graph

    # Сопровождение
    wu = evidence_graph.add_work_unit("WU_001", work_type="погружение_шпунта",
                                       status=WorkUnitStatus.COMPLETED, confidence=1.0)
    cert = evidence_graph.add_document("DOC_CERT_001", doc_type=DocType.CERTIFICATE,
                                        confidence=1.0)
    evidence_graph.link(wu, cert, EdgeType.CONFIRMED_BY)

    # Антикризис
    wu2 = evidence_graph.add_work_unit("WU_inferred_001", work_type="бетонирование",
                                        status=WorkUnitStatus.INFERRED, confidence=0.65,
                                        source=FactSource.INFERENCE)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class WorkUnitStatus(str, Enum):
    PLANNED = "planned"          # Из графика, ещё не начата
    IN_PROGRESS = "in_progress"  # Выполняется
    COMPLETED = "completed"      # Завершена, подтверждена документально
    INFERRED = "inferred"        # Выведена из косвенных улик
    CONFIRMED = "confirmed"      # Подтверждена человеком (после INFERRED)


class FactSource(str, Enum):
    AGENT = "agent"              # Создано агентом (сопровождение)
    INFERENCE = "inference"       # Выведено inference engine
    HUMAN = "human"              # Подтверждено человеком


class DocType(str, Enum):
    AOSR = "aosr"
    CERTIFICATE = "certificate"
    PASSPORT = "passport"
    TTN = "ttn"
    TORG12 = "torg12"              # Товарная накладная ТОРГ-12
    M4 = "m4"                      # Приходный ордер М-4 (оприходование)
    M11 = "m11"                    # Требование-накладная М-11 (в производство)
    M15 = "m15"                    # Накладная М-15 (отпуск на сторону)
    M29 = "m29"                    # Акт списания М-29
    TOLLING_ACCEPT = "tolling_accept"  # Акт приёма-передачи давальческих материалов
    TOLLING_REPORT = "tolling_report"  # Отчёт об использовании давальческих материалов
    KS2 = "ks2"
    KS3 = "ks3"
    KS6A = "ks6a"
    VOR = "vor"
    CONTRACT = "contract"
    LETTER = "letter"
    PHOTO = "photo"
    JOURNAL = "journal"
    EXECUTIVE_SCHEME = "executive_scheme"
    DRAWING = "drawing"
    PROTOCOL = "protocol"
    INVOICE = "invoice"
    UPD = "upd"
    UNKNOWN = "unknown"


class EvidenceDocStatus(str, Enum):
    ORIGINAL = "original"            # Оригинал с подписями
    SCAN = "scan"                    # Скан (может быть без подписей)
    RECONSTRUCTED = "reconstructed"  # Восстановлен системой
    REFERENCED = "referenced"        # Только упомянут в другом документе


class PersonRole(str, Enum):
    PTO_ENGINEER = "pto_engineer"
    FOREMAN = "foreman"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    INSPECTOR = "inspector"
    WORKER = "worker"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    DELIVERY = "delivery"
    INSPECTION = "inspection"
    SIGNING = "signing"
    PHOTO_TAKEN = "photo_taken"
    STATEMENT = "statement"       # Показания человека
    INFERRED = "inferred"


class TimePrecision(str, Enum):
    EXACT = "exact"     # Точное время (ТТН, фото EXIF)
    DAY = "day"         # Известен день
    WEEK = "week"       # Известна неделя
    MONTH = "month"     # Известен месяц


class VolumeSource(str, Enum):
    PROJECT = "project"    # Из проектной документации
    VOR = "vor"            # Из ведомости объёмов работ
    KS2 = "ks2"            # Из акта КС-2
    INFERRED = "inferred"  # Выведено


class EdgeType(str, Enum):
    USED_IN = "used_in"                 # MaterialBatch → WorkUnit (quantity)
    CONFIRMED_BY = "confirmed_by"       # WorkUnit → Document
    REFERENCES = "references"           # Document → Document
    TEMPORAL_BEFORE = "temporal_before" # WorkUnit → WorkUnit
    TEMPORAL_AFTER = "temporal_after"   # WorkUnit → WorkUnit (обратное)
    LOCATED_AT = "located_at"           # WorkUnit → Location
    SUPPLIED_BY = "supplied_by"         # MaterialBatch → Person
    SIGNED_BY = "signed_by"             # Document → Person
    DERIVED_FROM = "derived_from"       # WorkUnit → WorkUnit (антикризис)
    HAS_EVENT = "has_event"             # WorkUnit → DateEvent
    DEFINES_VOLUME = "defines_volume"   # Volume → WorkUnit
    MENTIONS = "mentions"               # Document → MaterialBatch
    CONTAINS = "contains"               # Location → Location (иерархия)
    PART_OF = "part_of"                 # WorkUnit → WorkUnit (декомпозиция)
    ATTRIBUTED_TO = "attributed_to"     # DateEvent → Person
    # ── Движение ТМЦ ─────────────────────────────────────────────────
    SHIPPED_WITH = "shipped_with"       # MaterialBatch → Document (ТТН/ТОРГ-12)
    RECEIVED_AT = "received_at"         # MaterialBatch → Location (склад/площадка)
    ISSUED_BY = "issued_by"             # MaterialBatch → Document (М-11/М-15)
    WRITTEN_OFF_BY = "written_off_by"   # MaterialBatch → Document (М-29)
    # ── Давальческая схема ────────────────────────────────────────────
    OWNED_BY = "owned_by"               # MaterialBatch → Person (собственник)
    TOLLING_ACCEPTED = "tolling_accepted"  # MaterialBatch → Document (акт приёма-передачи)


# =============================================================================
# Confidence Helpers
# =============================================================================

def confidence_color(conf: float) -> str:
    """Цветовой код уверенности."""
    if conf >= 0.8:
        return "green"
    elif conf >= 0.6:
        return "yellow"
    elif conf >= 0.4:
        return "red"
    else:
        return "gray"


def confidence_label(conf: float) -> str:
    """Человекочитаемая метка уверенности."""
    if conf >= 1.0:
        return "ПОДТВЕРЖДЕНО"
    elif conf >= 0.8:
        return "ВЫСОКАЯ"
    elif conf >= 0.6:
        return "СРЕДНЯЯ"
    elif conf >= 0.4:
        return "НИЗКАЯ"
    else:
        return "НЕДОСТОВЕРНО"


# =============================================================================
# Forensic Finding (ported from graph_service.py — unified audit type)
# =============================================================================

class ForensicSeverity(str, Enum):
    CRITICAL = "critical"   # Блокирующее нарушение (подлог, фальсификация)
    HIGH = "high"           # Серьёзное расхождение
    MEDIUM = "medium"       # Потенциальная проблема
    INFO = "info"           # Информационное сообщение


@dataclass
class ForensicFinding:
    """Результат forensic-проверки."""
    check_name: str
    severity: ForensicSeverity
    description: str
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[Tuple[str, str]] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check_name,
            "severity": self.severity.value,
            "description": self.description,
            "affected_nodes": self.node_ids,
            "recommendation": self.recommendation,
        }


# =============================================================================
# Material Catalog — проблемные/снятые с производства материалы
# =============================================================================

OBSOLETE_MATERIALS: Dict[str, Dict[str, Any]] = {
    "Шпунт Л5": {
        "obsolete": True,
        "replaced_by": "Шпунт Ларсена Л5-УМ",
        "reason": (
            "Снят с производства. Выпускался в СССР (г. Луганск). "
            "Ширина профиля 425 мм (Л5-УМ — 400 мм). "
            "На рынке РФ доступен только Б/У. "
            "Применение Б/У шпунта на новом строительстве требует отдельного "
            "обоснования и экспертизы остаточного сечения."
        ),
        "gost_old": "ГОСТ СССР (отменён)",
        "gost_new": "ГОСТ Р 53629-2009",
        "production_status": "снят с производства (1991)",
        "geometry": {"width_mm": 425, "note": "Не совместим с Л5-УМ (400 мм) по замковому соединению"},
    },
    "Шпунт Л4": {
        "obsolete": True,
        "replaced_by": "Шпунт Ларсена Л4-УМ",
        "reason": "Снят с производства. Советский стандарт. Отсутствует на рынке РФ как новый прокат.",
        "gost_old": "ГОСТ СССР (отменён)",
        "gost_new": "ГОСТ Р 53629-2009",
        "production_status": "снят с производства (1991)",
    },
}


# =============================================================================
# Edge Attributes
# =============================================================================

@dataclass
class EdgeAttr:
    """Атрибуты на ребре графа."""
    confidence: float = 1.0
    quantity: Optional[float] = None   # Для USED_IN
    evidence: List[str] = field(default_factory=list)  # На каких документах основана связь
    notes: str = ""


# =============================================================================
# Evidence Graph
# =============================================================================

class EvidenceGraph:
    """
    Единый граф доказательств для ASD v12.0.

    NetworkX DiGraph с 7 типами узлов и confidence на каждом.
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._node_counter: Dict[str, int] = {}
        self._load_graph()

    # ── Persistence ──────────────────────────────────────────────────────

    def _graph_path(self) -> Path:
        """Путь к файлу графа."""
        gdir = settings.graphs_path
        gdir.mkdir(parents=True, exist_ok=True)
        return gdir / "evidence_graph.gml"

    def _load_graph(self) -> None:
        """Загрузить граф с диска."""
        path = self._graph_path()
        if path.exists():
            try:
                self.graph = nx.read_gml(str(path))
                logger.info("Evidence graph loaded: %d nodes, %d edges",
                           self.graph.number_of_nodes(),
                           self.graph.number_of_edges())
            except Exception as e:
                logger.warning("Failed to load graph: %s — starting fresh", e)
                self.graph = nx.DiGraph()
        else:
            logger.info("No saved graph found — starting fresh")
            self.graph = nx.DiGraph()

    def save(self) -> None:
        """Сохранить граф на диск (GML формат)."""
        import copy
        path = self._graph_path()
        try:
            # GML не принимает None — заменяем на пустую строку
            clean = nx.DiGraph()
            for nid, data in self.graph.nodes(data=True):
                clean_data = {k: (v if v is not None else "") for k, v in data.items()}
                clean.add_node(nid, **clean_data)
            for u, v, data in self.graph.edges(data=True):
                clean_data = {k: (v2 if v2 is not None else "") for k, v2 in data.items()}
                clean.add_edge(u, v, **clean_data)
            nx.write_gml(clean, str(path))
        except Exception as e:
            logger.warning("Failed to save evidence graph: %s", e)

    def clear(self) -> None:
        """Очистить граф."""
        self.graph.clear()
        self._node_counter.clear()
        self.save()

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _norm_date(d: Union[date, str, None]) -> Optional[str]:
        """Нормализовать дату: date → ISO-строка, str → как есть, None → None."""
        if d is None:
            return None
        if isinstance(d, date):
            return d.isoformat()
        return str(d)

    @staticmethod
    def _norm_datetime(d: Union[datetime, str, None]) -> Optional[str]:
        """Нормализовать datetime → ISO-строка."""
        if d is None:
            return None
        if isinstance(d, datetime):
            return d.isoformat()
        return str(d)

    # ── Node Creation ────────────────────────────────────────────────────

    def _make_node_id(self, prefix: str) -> str:
        """Сгенерировать уникальный ID узла."""
        self._node_counter[prefix] = self._node_counter.get(prefix, 0) + 1
        return f"{prefix}_{self._node_counter[prefix]:04d}"

    def add_work_unit(
        self,
        work_type: str,
        description: str = "",
        status: WorkUnitStatus = WorkUnitStatus.PLANNED,
        confidence: float = 1.0,
        source: FactSource = FactSource.AGENT,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        planned_start: Optional[date] = None,
        planned_end: Optional[date] = None,
        volume: Optional[float] = None,
        unit: str = "",
        location_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        node_id: Optional[str] = None,
    ) -> str:
        """
        Создать узел WorkUnit.

        Returns:
            node_id созданного узла
        """
        nid = node_id or self._make_node_id("WU")

        self.graph.add_node(
            nid,
            node_type="WorkUnit",
            work_type=work_type,
            description=description,
            status=status.value,
            confidence=confidence,
            source=source.value,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            planned_start=planned_start.isoformat() if planned_start else None,
            planned_end=planned_end.isoformat() if planned_end else None,
            volume=volume,
            unit=unit,
            location_id=location_id,
            parent_id=parent_id,
            depends_on=depends_on or [],
            created_at=datetime.now().isoformat(),
            confirmed_by=None,
            confirmed_at=None,
        )

        if location_id and self.graph.has_node(location_id):
            self.link(nid, location_id, EdgeType.LOCATED_AT)

        if parent_id and self.graph.has_node(parent_id):
            self.link(nid, parent_id, EdgeType.PART_OF)

        if depends_on:
            for dep_id in depends_on:
                if self.graph.has_node(dep_id):
                    self.link(dep_id, nid, EdgeType.TEMPORAL_BEFORE)

        self.save()
        logger.info("WorkUnit added: %s (%s, conf=%.2f)", nid, work_type, confidence)
        return nid

    def add_material_batch(
        self,
        material_name: str,
        batch_number: str = "",
        quantity: float = 0.0,
        unit: str = "",
        gost: Optional[str] = None,
        supplier: Optional[str] = None,
        delivery_date: Optional[date] = None,
        certificate_id: Optional[str] = None,
        ttn_id: Optional[str] = None,
        is_tolling: bool = False,
        customer_id: Optional[str] = None,
        confidence: float = 1.0,
        node_id: Optional[str] = None,
    ) -> str:
        """
        Создать узел MaterialBatch.

        Args:
            is_tolling: True если материал давальческий (собственность заказчика)
            customer_id: ID узла Person — собственник давальческого материала
        """
        nid = node_id or self._make_node_id("MB")

        self.graph.add_node(
            nid,
            node_type="MaterialBatch",
            material_name=material_name,
            batch_number=batch_number,
            quantity=quantity,
            unit=unit,
            gost=gost,
            supplier=supplier,
            delivery_date=self._norm_date(delivery_date),
            certificate_id=certificate_id,
            ttn_id=ttn_id,
            is_tolling=is_tolling,
            confidence=confidence,
        )

        if certificate_id and self.graph.has_node(certificate_id):
            self.link(nid, certificate_id, EdgeType.REFERENCES)
        if ttn_id and self.graph.has_node(ttn_id):
            self.link(nid, ttn_id, EdgeType.REFERENCES)
        if is_tolling and customer_id:
            self.link(nid, customer_id, EdgeType.OWNED_BY, confidence=1.0)

        self.save()
        return nid

    def add_document(
        self,
        doc_type: DocType,
        doc_number: str = "",
        doc_date: Optional[date] = None,
        file_path: Optional[str] = None,
        content_summary: str = "",
        signatures_present: bool = False,
        stamps_present: bool = False,
        confidence: float = 1.0,
        status: EvidenceDocStatus = EvidenceDocStatus.ORIGINAL,
        work_unit_id: Optional[str] = None,
        signed_by: Optional[List[str]] = None,
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел Document."""
        nid = node_id or self._make_node_id("DOC")

        self.graph.add_node(
            nid,
            node_type="Document",
            doc_type=doc_type.value,
            doc_number=doc_number,
            doc_date=self._norm_date(doc_date),
            file_path=file_path,
            content_summary=content_summary,
            signatures_present=signatures_present,
            stamps_present=stamps_present,
            confidence=confidence,
            status=status.value,
            work_unit_id=work_unit_id,
            signed_by=signed_by or [],
        )

        if work_unit_id and self.graph.has_node(work_unit_id):
            self.link(work_unit_id, nid, EdgeType.CONFIRMED_BY)

        if signed_by:
            for person_id in signed_by:
                if self.graph.has_node(person_id):
                    self.link(nid, person_id, EdgeType.SIGNED_BY)

        self.save()
        return nid

    def add_person(
        self,
        name: str,
        role: PersonRole = PersonRole.UNKNOWN,
        organization: str = "",
        reliability: float = 0.7,
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел Person."""
        nid = node_id or self._make_node_id("P")

        self.graph.add_node(
            nid,
            node_type="Person",
            name=name,
            role=role.value,
            organization=organization,
            reliability=reliability,
            last_contacted=None,
        )

        self.save()
        return nid

    def add_date_event(
        self,
        event_type: EventType,
        timestamp: datetime,
        description: str = "",
        precision: TimePrecision = TimePrecision.DAY,
        source_document_id: Optional[str] = None,
        source_person_id: Optional[str] = None,
        confidence: float = 1.0,
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел DateEvent."""
        nid = node_id or self._make_node_id("EVT")

        self.graph.add_node(
            nid,
            node_type="DateEvent",
            event_type=event_type.value,
            timestamp=self._norm_datetime(timestamp),
            description=description,
            precision=precision.value,
            source_document_id=source_document_id,
            source_person_id=source_person_id,
            confidence=confidence,
        )

        if source_document_id and self.graph.has_node(source_document_id):
            self.link(nid, source_document_id, EdgeType.REFERENCES)
        if source_person_id and self.graph.has_node(source_person_id):
            self.link(nid, source_person_id, EdgeType.ATTRIBUTED_TO)

        self.save()
        return nid

    def add_volume(
        self,
        value: float,
        unit: str,
        source: VolumeSource = VolumeSource.PROJECT,
        work_unit_id: Optional[str] = None,
        confidence: float = 1.0,
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел Volume."""
        nid = node_id or self._make_node_id("VOL")

        self.graph.add_node(
            nid,
            node_type="Volume",
            value=value,
            unit=unit,
            source=source.value,
            work_unit_id=work_unit_id,
            confidence=confidence,
        )

        if work_unit_id and self.graph.has_node(work_unit_id):
            self.link(nid, work_unit_id, EdgeType.DEFINES_VOLUME)

        self.save()
        return nid

    def add_location(
        self,
        name: str,
        parent_id: Optional[str] = None,
        description: str = "",
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел Location."""
        nid = node_id or self._make_node_id("LOC")

        self.graph.add_node(
            nid,
            node_type="Location",
            name=name,
            parent_id=parent_id,
            description=description,
        )

        if parent_id and self.graph.has_node(parent_id):
            self.link(nid, parent_id, EdgeType.CONTAINS)

        self.save()
        return nid

    # ── Edge Creation ────────────────────────────────────────────────────

    def link(
        self,
        from_node: str,
        to_node: str,
        edge_type: EdgeType,
        confidence: float = 1.0,
        quantity: Optional[float] = None,
        evidence: Optional[List[str]] = None,
        notes: str = "",
    ):
        """
        Создать связь между узлами.

        Args:
            from_node: исходный узел
            to_node: целевой узел
            edge_type: тип связи
            confidence: уверенность в связи (0.0–1.0)
            quantity: количество (для USED_IN)
            evidence: список документов, подтверждающих связь
        """
        if not self.graph.has_node(from_node):
            logger.warning("link: source node %s not found", from_node)
            return
        if not self.graph.has_node(to_node):
            logger.warning("link: target node %s not found", to_node)
            return

        self.graph.add_edge(
            from_node, to_node,
            edge_type=edge_type.value,
            confidence=confidence,
            quantity=quantity,
            evidence=evidence or [],
            notes=notes,
        )
        self.save()

    # ── Query Methods ────────────────────────────────────────────────────

    def get_work_units(self, status: Optional[WorkUnitStatus] = None) -> List[Dict[str, Any]]:
        """Получить все WorkUnit, опционально отфильтрованные по статусу."""
        result = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("node_type") == "WorkUnit":
                if status is None or data.get("status") == status.value:
                    result.append({"id": nid, **data})
        return result

    def get_documents(self, doc_type: Optional[DocType] = None) -> List[Dict[str, Any]]:
        """Получить все Document, опционально по типу."""
        result = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("node_type") == "Document":
                if doc_type is None or data.get("doc_type") == doc_type.value:
                    result.append({"id": nid, **data})
        return result

    def get_low_confidence_nodes(self, threshold: float = 0.6) -> List[Dict[str, Any]]:
        """
        Получить узлы с низкой уверенностью (для HITL).

        Returns:
            Список узлов с confidence < threshold, отсортированный по возрастанию
        """
        result = []
        for nid, data in self.graph.nodes(data=True):
            conf = data.get("confidence", 1.0)
            if isinstance(conf, (int, float)) and conf < threshold:
                result.append({"id": nid, **data})
        return sorted(result, key=lambda n: n.get("confidence", 0.0))

    def get_orphan_documents(self) -> List[Dict[str, Any]]:
        """Найти REFERENCED-документы без файла (упомянуты, но не предоставлены)."""
        return [
            {"id": nid, **data}
            for nid, data in self.graph.nodes(data=True)
            if data.get("node_type") == "Document"
            and data.get("status") == EvidenceDocStatus.REFERENCED.value
        ]

    def get_work_unit_chain(self, wu_id: str, depth: int = 3) -> Dict[str, Any]:
        """
        Получить цепочку связанных узлов для WorkUnit.

        Returns:
            {
                "work_unit": {...},
                "materials": [...],
                "documents": [...],
                "events": [...],
                "locations": [...],
                "predecessors": [...],
            }
        """
        if not self.graph.has_node(wu_id):
            return {}

        wu_data = dict(self.graph.nodes[wu_id])
        chain = {
            "work_unit": {"id": wu_id, **wu_data},
            "materials": [],
            "documents": [],
            "events": [],
            "locations": [],
            "predecessors": [],
            "successors": [],
        }

        # Materials used
        for pred in self.graph.predecessors(wu_id):
            pred_data = self.graph.nodes[pred]
            if pred_data.get("node_type") == "MaterialBatch":
                edge_data = self.graph.edges[pred, wu_id]
                chain["materials"].append({
                    "id": pred, **pred_data,
                    "edge_confidence": edge_data.get("confidence", 1.0),
                    "quantity": edge_data.get("quantity"),
                })

        # Documents confirming
        for succ in self.graph.successors(wu_id):
            succ_data = self.graph.nodes[succ]
            edge_data = self.graph.edges[wu_id, succ]
            etype = edge_data.get("edge_type", "")
            if etype == EdgeType.CONFIRMED_BY.value:
                chain["documents"].append({"id": succ, **succ_data})
            elif etype == EdgeType.HAS_EVENT.value:
                chain["events"].append({"id": succ, **succ_data})

        # Location
        loc_id = wu_data.get("location_id")
        if loc_id and self.graph.has_node(loc_id):
            chain["locations"].append({"id": loc_id, **self.graph.nodes[loc_id]})

        # Temporal chain
        for pred in self.graph.predecessors(wu_id):
            edge_data = self.graph.edges.get((pred, wu_id), {})
            if edge_data.get("edge_type") == EdgeType.TEMPORAL_BEFORE.value:
                chain["predecessors"].append({
                    "id": pred, **self.graph.nodes[pred],
                    "edge_confidence": edge_data.get("confidence", 1.0),
                })

        for succ in self.graph.successors(wu_id):
            edge_data = self.graph.edges.get((wu_id, succ), {})
            if edge_data.get("edge_type") == EdgeType.TEMPORAL_BEFORE.value:
                chain["successors"].append({
                    "id": succ, **self.graph.nodes[succ],
                    "edge_confidence": edge_data.get("confidence", 1.0),
                })

        return chain

    # ── Forensic Checks ──────────────────────────────────────────────────

    def check_batch_coverage(self) -> List[ForensicFinding]:
        """
        Проверка покрытия: Σ объёмов в АОСР ≤ размер партии сертификата.

        Выявляет сертификаты, где использованный объём превышает
        заявленный размер партии — признак подлога или дублирования.
        """
        findings: List[ForensicFinding] = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("node_type") != "MaterialBatch":
                continue
            batch_qty = data.get("quantity", 0)
            material = data.get("material_name", nid)
            batch_num = data.get("batch_number", "?")
            if batch_qty <= 0:
                findings.append(ForensicFinding(
                    check_name="batch_coverage",
                    severity=ForensicSeverity.HIGH,
                    description=(
                        f"MaterialBatch {nid} ({material}, партия №{batch_num}): "
                        f"не указан размер партии. Невозможно проверить покрытие."
                    ),
                    node_ids=[nid],
                    recommendation="Укажите quantity в MaterialBatch.",
                ))
                continue

            total_used = 0.0
            affected_wus: List[str] = []
            for succ in self.graph.successors(nid):
                if self.graph.nodes[succ].get("node_type") != "WorkUnit":
                    continue
                edge = self.graph.edges.get((nid, succ), {})
                qty = float(edge.get("quantity", 0))
                total_used += qty
                affected_wus.append(succ)

            if total_used > batch_qty:
                excess = total_used - batch_qty
                excess_pct = (excess / batch_qty * 100) if batch_qty > 0 else 0
                findings.append(ForensicFinding(
                    check_name="batch_coverage",
                    severity=ForensicSeverity.CRITICAL,
                    description=(
                        f"КРИТИЧЕСКОЕ НЕСООТВЕТСТВИЕ: сертификат {material} "
                        f"(партия №{batch_num}) покрывает {batch_qty}, "
                        f"но по {len(affected_wus)} WorkUnit использовано {total_used:.1f} "
                        f"(превышение на {excess:.1f}, +{excess_pct:.0f}%). "
                        f"Сертификат не может подтверждать качество всего объёма. "
                        f"Вероятные причины: подлог (ксерокопия сертификата от другой партии), "
                        f"отсутствие входного контроля, ошибка комплектации ИД."
                    ),
                    node_ids=[nid] + affected_wus,
                    recommendation=(
                        f"1. Запросить у поставщика сертификаты на весь объём ({total_used:.1f}). "
                        f"2. Поднять ЖВК (журнал входного контроля) — проверить фактическое поступление. "
                        f"3. При невозможности — оформлять АОСР только на подтверждённый объём ({batch_qty}). "
                        f"4. На оставшиеся {excess:.1f} — отдельный акт с новым сертификатом."
                    ),
                ))
            elif len(affected_wus) >= 2:
                findings.append(ForensicFinding(
                    check_name="batch_coverage",
                    severity=ForensicSeverity.INFO,
                    description=(
                        f"Сертификат {material} использован в {len(affected_wus)} WorkUnit "
                        f"на общий объём {total_used:.1f} из {batch_qty}. Покрытие полное."
                    ),
                    node_ids=[nid] + affected_wus,
                    recommendation="Убедиться в наличии входного контроля по каждой поставке.",
                ))
        return findings

    def check_orphan_certificates(self) -> List[ForensicFinding]:
        """
        Найти сертификаты без привязки к WorkUnit (осиротевшие).
        """
        orphans: List[ForensicFinding] = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("node_type") != "Document":
                continue
            if data.get("doc_type") not in (DocType.CERTIFICATE.value,
                                             DocType.PASSPORT.value):
                continue
            has_connection = any(True for _ in self.graph.predecessors(nid)) or \
                             any(True for _ in self.graph.successors(nid))
            if not has_connection:
                orphans.append(ForensicFinding(
                    check_name="orphan_certificates",
                    severity=ForensicSeverity.MEDIUM,
                    description=(
                        f"Сертификат-сирота: {nid} ({data.get('doc_number', '?')}) "
                        f"— не привязан ни к одной партии материала или работе"
                    ),
                    node_ids=[nid],
                    recommendation="Привяжите к MaterialBatch через certificate_id или удалите.",
                ))
        return orphans

    def check_certificate_reuse(self) -> List[ForensicFinding]:
        """
        Проверить сертификаты (MaterialBatch), использованные в нескольких WorkUnit.

        Один сертификат на несколько работ = риск подлога (ксерокопия).
        """
        findings: List[ForensicFinding] = []
        for nid, data in self.graph.nodes(data=True):
            if data.get("node_type") != "MaterialBatch":
                continue
            work_units: List[str] = []
            for succ in self.graph.successors(nid):
                if self.graph.nodes[succ].get("node_type") == "WorkUnit":
                    work_units.append(succ)
            if len(work_units) >= 2:
                material = data.get("material_name", nid)
                # Check if there's a document confirmation chain
                cert_id = data.get("certificate_id", "")
                findings.append(ForensicFinding(
                    check_name="certificate_reuse",
                    severity=ForensicSeverity.HIGH,
                    description=(
                        f"Сертификат на {material} использован в {len(work_units)} WorkUnit "
                        f"— риск подлога (ксерокопия сертификата) или ошибки комплектации. "
                        f"Невозможно подтвердить, что весь материал из одной партии."
                    ),
                    node_ids=[nid] + work_units,
                    recommendation=(
                        "1. Поднять ЖВК — проверить даты и номера партий. "
                        "2. Сверить номер партии сертификата с ТТН/УПД. "
                        "3. При отсутствии ЖВК — оформить акт входного контроля "
                        "(если есть ТТН) или запросить дубликаты сертификатов у поставщика."
                    ),
                ))
        return findings

    def run_all_forensic_checks(self) -> List[ForensicFinding]:
        """
        Запустить все forensic-проверки по графу.

        Используется Агентом-Аудитором (Стройконтроль) для полного аудита
        документации объекта. Возвращает объединённый список находок,
        отсортированный по критичности.

        Returns:
            List[ForensicFinding] — унифицированный тип для Auditor
        """
        all_findings: List[ForensicFinding] = []

        all_findings.extend(self.check_batch_coverage())
        all_findings.extend(self.check_certificate_reuse())
        all_findings.extend(self.check_orphan_certificates())

        # Сортировка: CRITICAL → HIGH → MEDIUM → INFO
        severity_order = {
            ForensicSeverity.CRITICAL: 0,
            ForensicSeverity.HIGH: 1,
            ForensicSeverity.MEDIUM: 2,
            ForensicSeverity.INFO: 3,
        }
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 99))

        logger.info(
            "Forensic audit complete: %d findings (%d critical, %d high, %d medium, %d info)",
            len(all_findings),
            sum(1 for f in all_findings if f.severity == ForensicSeverity.CRITICAL),
            sum(1 for f in all_findings if f.severity == ForensicSeverity.HIGH),
            sum(1 for f in all_findings if f.severity == ForensicSeverity.MEDIUM),
            sum(1 for f in all_findings if f.severity == ForensicSeverity.INFO),
        )

        return all_findings

    def run_all_forensic_checks_dict(self) -> Dict[str, Any]:
        """Legacy wrapper: возвращает Dict для обратной совместимости."""
        findings = self.run_all_forensic_checks()
        critical = [f for f in findings if f.severity == ForensicSeverity.CRITICAL]
        high = [f for f in findings if f.severity == ForensicSeverity.HIGH]
        medium = [f for f in findings if f.severity == ForensicSeverity.MEDIUM]
        return {
            "findings": [f.to_dict() for f in findings],
            "summary": {
                "total_findings": len(findings),
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "info": len(findings) - len(critical) - len(high) - len(medium),
            },
        }

    # ── Material Spec Validation ──────────────────────────────────────────

    def validate_material_spec(self, material_name: str) -> List[ForensicFinding]:
        """
        Проверить спецификацию материала на известные проблемы:
          - Снят с производства (obsolete)
          - Неверная марка (геометрия не совпадает с современным аналогом)
          - Требуется Б/У обоснование

        Использует OBSOLETE_MATERIALS — словарь известных проблемных материалов.
        """
        findings: List[ForensicFinding] = []

        if material_name in OBSOLETE_MATERIALS:
            info = OBSOLETE_MATERIALS[material_name]
            findings.append(ForensicFinding(
                check_name="material_spec_validation",
                severity=ForensicSeverity.CRITICAL,
                description=(
                    f"МАТЕРИАЛ СНЯТ С ПРОИЗВОДСТВА: «{material_name}». {info['reason']}"
                ),
                recommendation=(
                    f"Замена: {info['replaced_by']} ({info['gost_new']}). "
                    f"Если проектом предусмотрен именно {material_name} — "
                    f"необходимо обоснование применения Б/У материала с экспертизой "
                    f"остаточного сечения и согласование с заказчиком/авторским надзором."
                ),
            ))

        for obsolete_name, info in OBSOLETE_MATERIALS.items():
            if obsolete_name.lower() in material_name.lower() and material_name != obsolete_name:
                findings.append(ForensicFinding(
                    check_name="material_spec_validation",
                    severity=ForensicSeverity.HIGH,
                    description=(
                        f"Возможна опечатка в спецификации: «{material_name}». "
                        f"Ближайшее совпадение: «{obsolete_name}» — {info['reason']}"
                    ),
                    recommendation=f"Уточните марку материала. Возможно, имеется в виду {info['replaced_by']}.",
                ))

        return findings

    # ── Certificate Adapter ───────────────────────────────────────────────

    def add_certificate(
        self,
        cert_id: str,
        material_name: str,
        batch_number: str = "",
        batch_size: float = 0.0,
        unit: str = "",
        supplier: str = "",
        issue_date: str = "",
        gost: str = "",
    ) -> str:
        """
        Добавить сертификат качества в EvidenceGraph v2 модель.

        Создаёт два узла:
          - Document (DocType.CERTIFICATE) — сам документ сертификата
          - MaterialBatch — партия материала со ссылкой на документ

        Связь: MaterialBatch → Document (REFERENCES) — авто при add_material_batch.

        Args:
            cert_id: идентификатор узла (также используется как doc_number)

        Returns:
            cert_id созданного узла Document
        """
        from datetime import date as date_type
        parsed_date = None
        if issue_date:
            try:
                parsed_date = date_type.fromisoformat(issue_date)
            except (ValueError, TypeError):
                pass

        self.add_document(
            doc_type=DocType.CERTIFICATE,
            doc_number=cert_id,
            doc_date=parsed_date,
            content_summary=f"Сертификат на {material_name}, партия {batch_number}",
            confidence=1.0,
            node_id=cert_id,
        )

        mat_id = self._make_node_id("MB")
        self.add_material_batch(
            material_name=material_name,
            batch_number=batch_number,
            quantity=batch_size,
            unit=unit,
            gost=gost,
            supplier=supplier,
            certificate_id=cert_id,
            node_id=mat_id,
        )

        logger.info("Certificate added: %s → MaterialBatch %s (%s, партия %s)",
                     cert_id, mat_id, material_name, batch_number)
        return cert_id

    # ═══════════════════════════════════════════════════════════════════
    # Движение ТМЦ (Material Flow)
    # ═══════════════════════════════════════════════════════════════════

    def add_shipment(
        self,
        material_batch_id: str,
        doc_type: DocType,
        doc_number: str = "",
        doc_date: str = "",
        quantity: float = 0.0,
        unit: str = "",
        supplier: str = "",
    ) -> str:
        """
        Зафиксировать поставку материала по накладной (ТТН / ТОРГ-12).

        Создаёт Document типа TTN/TORG12 и связывает с MaterialBatch
        ребром SHIPPED_WITH.
        """
        if doc_type not in (DocType.TTN, DocType.TORG12):
            raise ValueError(f"add_shipment expects TTN or TORG12, got {doc_type}")

        doc_id = f"doc_{doc_type.value}_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=doc_type,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=0.95,  # Первичный документ — высокая уверенность
        )
        self.graph.nodes[doc_id].update({
            "quantity": quantity,
            "unit": unit,
            "supplier": supplier,
        })

        self.link(material_batch_id, doc_id, EdgeType.SHIPPED_WITH, confidence=0.95)

        logger.info("Shipment recorded: %s → MaterialBatch %s (%s %s %s)",
                     doc_number or doc_id, material_batch_id, quantity, unit, supplier)
        return doc_id

    def add_receipt(
        self,
        material_batch_id: str,
        doc_number: str = "",
        doc_date: str = "",
        location_id: str = "",
        quantity: float = 0.0,
    ) -> str:
        """
        Зафиксировать оприходование материала на склад (М-4).

        Создаёт Document типа M4, связывает с MaterialBatch ребром
        REFERENCES, и с Location ребром RECEIVED_AT.
        """
        doc_id = f"doc_m4_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=DocType.M4,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=0.95,
        )
        self.graph.nodes[doc_id]["quantity"] = quantity

        self.link(material_batch_id, doc_id, EdgeType.REFERENCES)
        if location_id:
            self.link(material_batch_id, location_id, EdgeType.RECEIVED_AT, confidence=0.95)

        logger.info("Receipt recorded: %s → MaterialBatch %s (%s ед.)",
                     doc_number or doc_id, material_batch_id, quantity)
        return doc_id

    def add_issue(
        self,
        material_batch_id: str,
        doc_type: DocType,
        doc_number: str = "",
        doc_date: str = "",
        quantity: float = 0.0,
        recipient: str = "",
    ) -> str:
        """
        Зафиксировать выдачу материала: в производство (М-11) или на сторону (М-15).

        Создаёт Document типа M11/M15 и связывает с MaterialBatch ребром ISSUED_BY.
        """
        if doc_type not in (DocType.M11, DocType.M15):
            raise ValueError(f"add_issue expects M11 or M15, got {doc_type}")

        doc_id = f"doc_{doc_type.value}_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=doc_type,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=0.95,
        )
        self.graph.nodes[doc_id].update({
            "quantity": quantity,
            "recipient": recipient,
        })

        self.link(material_batch_id, doc_id, EdgeType.ISSUED_BY, confidence=0.95)

        direction = "в производство" if doc_type == DocType.M11 else "на сторону"
        logger.info("Issue recorded: %s → MaterialBatch %s (%s ед. %s → %s)",
                     doc_number or doc_id, material_batch_id, quantity, direction, recipient)
        return doc_id

    def add_write_off(
        self,
        material_batch_id: str,
        doc_number: str = "",
        doc_date: str = "",
        quantity: float = 0.0,
        reason: str = "",
    ) -> str:
        """
        Зафиксировать списание материала (М-29).

        Создаёт Document типа M29 и связывает с MaterialBatch ребром WRITTEN_OFF_BY.
        Списание закрывает цикл движения: материал больше не числится на балансе.
        """
        doc_id = f"doc_m29_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=DocType.M29,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=0.90,
        )
        self.graph.nodes[doc_id].update({
            "quantity": quantity,
            "reason": reason,
        })

        self.link(material_batch_id, doc_id, EdgeType.WRITTEN_OFF_BY, confidence=0.90)

        logger.info("Write-off recorded: %s → MaterialBatch %s (%s ед., %s)",
                     doc_number or doc_id, material_batch_id, quantity, reason)
        return doc_id

    def get_material_chain(
        self, material_batch_id: str,
    ) -> Dict[str, Any]:
        """
        Получить полную цепочку движения материала.

        Returns:
            {material_batch, shipment, receipt, issue, write_off, location, supplier}
        """
        chain: Dict[str, Any] = {"material_batch_id": material_batch_id}

        if material_batch_id not in self.graph:
            chain["status"] = "not_found"
            return chain

        node = self.graph.nodes[material_batch_id]
        chain["material_name"] = node.get("material_name", "")
        chain["batch_number"] = node.get("batch_number", "")
        chain["status"] = "found"

        for _, target, data in self.graph.edges(material_batch_id, data=True):
            et = data.get("edge_type", "")
            target_node = self.graph.nodes.get(target, {})

            if et == EdgeType.SHIPPED_WITH:
                chain["shipment"] = {
                    "doc_id": target,
                    "doc_type": target_node.get("doc_type", ""),
                    "doc_number": target_node.get("doc_number", ""),
                    "doc_date": target_node.get("doc_date", ""),
                    "quantity": target_node.get("quantity"),
                    "supplier": target_node.get("supplier", ""),
                }
            elif et == EdgeType.RECEIVED_AT:
                chain["location"] = target_node.get("name", target)
            elif et == EdgeType.ISSUED_BY:
                chain["issue"] = {
                    "doc_id": target,
                    "doc_type": target_node.get("doc_type", ""),
                    "doc_number": target_node.get("doc_number", ""),
                    "doc_date": target_node.get("doc_date", ""),
                    "quantity": target_node.get("quantity"),
                    "recipient": target_node.get("recipient", ""),
                }
            elif et == EdgeType.WRITTEN_OFF_BY:
                chain["write_off"] = {
                    "doc_id": target,
                    "doc_number": target_node.get("doc_number", ""),
                    "doc_date": target_node.get("doc_date", ""),
                    "quantity": target_node.get("quantity"),
                    "reason": target_node.get("reason", ""),
                }
            elif et == EdgeType.SUPPLIED_BY:
                chain["supplier"] = target_node.get("name", target)
            elif et == EdgeType.REFERENCES:
                doc_type = target_node.get("doc_type", "")
                if doc_type == DocType.M4:
                    chain["receipt"] = {
                        "doc_id": target,
                        "doc_number": target_node.get("doc_number", ""),
                        "doc_date": target_node.get("doc_date", ""),
                        "quantity": target_node.get("quantity"),
                    }

        return chain

    # ═══════════════════════════════════════════════════════════════════
    # Давальческая схема (Tolling)
    # ═══════════════════════════════════════════════════════════════════

    def add_tolling_accept(
        self,
        material_batch_id: str,
        customer_id: str,
        doc_number: str = "",
        doc_date: str = "",
        quantity: float = 0.0,
        unit: str = "",
    ) -> str:
        """
        Зафиксировать приём давальческого материала от заказчика.

        Создаёт Document TOLLING_ACCEPT, связывает OWNED_BY → customer,
        TOLLING_ACCEPTED → Document.
        Материал НЕ покупался — он передан заказчиком на ответхранение и переработку.
        """
        if material_batch_id not in self.graph:
            raise ValueError(f"MaterialBatch {material_batch_id} not found")

        # Пометить как давальческий
        self.graph.nodes[material_batch_id]["is_tolling"] = True

        doc_id = f"doc_tolling_accept_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=DocType.TOLLING_ACCEPT,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=1.0,
        )
        self.graph.nodes[doc_id].update({
            "quantity": quantity,
            "unit": unit,
            "customer_id": customer_id,
        })

        # Связи: владелец + акт приёма-передачи
        if not any(t == customer_id for _, t, d in
                   self.graph.edges(material_batch_id, data=True)
                   if d.get("edge_type") == EdgeType.OWNED_BY):
            self.link(material_batch_id, customer_id, EdgeType.OWNED_BY, confidence=1.0)
        self.link(material_batch_id, doc_id, EdgeType.TOLLING_ACCEPTED, confidence=1.0)

        logger.info("Tolling material accepted: %s from %s (%s %s)",
                     material_batch_id, customer_id, quantity, unit)
        return doc_id

    def add_tolling_report(
        self,
        material_batch_id: str,
        doc_number: str = "",
        doc_date: str = "",
        quantity_used: float = 0.0,
        quantity_returned: float = 0.0,
        quantity_waste: float = 0.0,
    ) -> str:
        """
        Сформировать отчёт об использовании давальческих материалов.

        Создаёт Document TOLLING_REPORT. Заказчик утверждает отчёт —
        только после этого материал считается использованным.
        quantity_used + quantity_returned + quantity_waste = исходное quantity.
        """
        if material_batch_id not in self.graph:
            raise ValueError(f"MaterialBatch {material_batch_id} not found")

        doc_id = f"doc_tolling_report_{doc_number or self._next_seq()}"
        self.add_document(
            node_id=doc_id,
            doc_type=DocType.TOLLING_REPORT,
            doc_number=doc_number,
            doc_date=doc_date,
            confidence=0.85,  # До утверждения заказчиком
        )
        self.graph.nodes[doc_id].update({
            "quantity_used": quantity_used,
            "quantity_returned": quantity_returned,
            "quantity_waste": quantity_waste,
            "approved_by_customer": False,
        })

        self.link(material_batch_id, doc_id, EdgeType.REFERENCES)

        logger.info("Tolling report: %s → %s (used=%s, returned=%s, waste=%s)",
                     material_batch_id, doc_id, quantity_used, quantity_returned, quantity_waste)
        return doc_id

    def summary(self) -> Dict[str, Any]:
        """Сводка по графу."""
        node_counts = {}
        for _, data in self.graph.nodes(data=True):
            nt = data.get("node_type", "Unknown")
            node_counts[nt] = node_counts.get(nt, 0) + 1

        edge_counts = {}
        for _, _, data in self.graph.edges(data=True):
            et = data.get("edge_type", "unknown")
            edge_counts[et] = edge_counts.get(et, 0) + 1

        low_conf = self.get_low_confidence_nodes(0.6)
        orphans = self.get_orphan_documents()

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_counts,
            "edge_types": edge_counts,
            "low_confidence_count": len(low_conf),
            "low_confidence_items": [{"id": n["id"], "type": n.get("node_type"),
                                       "confidence": n.get("confidence", 0)}
                                      for n in low_conf[:10]],
            "orphan_documents": len(orphans),
            "orphan_items": [{"id": n["id"], "doc_type": n.get("doc_type"),
                              "doc_number": n.get("doc_number", "")}
                             for n in orphans[:10]],
        }


# Модульный синглтон
evidence_graph = EvidenceGraph()
