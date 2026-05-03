"""
ASD v12.0 — Evidence Graph v2.

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
        return gdir / "evidence_graph.pkl"

    def _load_graph(self):
        """Загрузить граф с диска."""
        path = self._graph_path()
        if path.exists():
            try:
                self.graph = nx.read_gpickle(str(path))
                logger.info("Evidence graph loaded: %d nodes, %d edges",
                           self.graph.number_of_nodes(),
                           self.graph.number_of_edges())
            except Exception as e:
                # Fallback: try GML
                gml_path = path.with_suffix('.gml')
                if gml_path.exists():
                    try:
                        self.graph = nx.read_gml(str(gml_path))
                        logger.info("Evidence graph loaded from GML: %d nodes, %d edges",
                                   self.graph.number_of_nodes(),
                                   self.graph.number_of_edges())
                    except Exception as e2:
                        logger.warning("Failed to load graph: %s / %s — starting fresh", e, e2)
                        self.graph = nx.DiGraph()
                else:
                    logger.warning("No saved graph found — starting fresh")
                    self.graph = nx.DiGraph()

    def save(self):
        """Сохранить граф на диск (GML формат)."""
        import copy
        path = self._graph_path().with_suffix('.gml')
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
            logger.debug("Failed to save graph: %s", e)

    def clear(self):
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
        confidence: float = 1.0,
        node_id: Optional[str] = None,
    ) -> str:
        """Создать узел MaterialBatch."""
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
            confidence=confidence,
        )

        if certificate_id and self.graph.has_node(certificate_id):
            self.link(nid, certificate_id, EdgeType.REFERENCES)
        if ttn_id and self.graph.has_node(ttn_id):
            self.link(nid, ttn_id, EdgeType.REFERENCES)

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
