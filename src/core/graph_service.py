"""
ASD v12.0 — Forensic Knowledge Graph (NetworkX).

Два режима графа:
  Тактика (сопровождение):   Project → Event → AgentResult
  Стратегия (восстановление): Scan → Document → Certificate → Batch → InputControl → AOSR

Узлы:   Document, Normative_Act, Project, Event, AgentResult,
        Material, Certificate, Batch, AOSR, InputControlRecord, Supplier, TTN, Scan
Рёбра:  REFERENCES, BELONGS_TO, USES, COVERS, SHIPPED_BY, RECEIVED_IN,
        GENERATED, VERIFIES, PROVENANCE
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class NodeType(str, Enum):
    DOCUMENT = "Document"
    NORMATIVE_ACT = "Normative_Act"
    PROJECT = "Project"
    EVENT = "Event"
    AGENT_RESULT = "AgentResult"
    MATERIAL = "Material"
    CERTIFICATE = "Certificate"
    BATCH = "Batch"
    AOSR = "AOSR"
    INPUT_CONTROL = "InputControlRecord"
    SUPPLIER = "Supplier"
    TTN = "TTN"
    SCAN = "Scan"


class EdgeType(str, Enum):
    REFERENCES = "REFERENCES"       # Общая ссылка между документами
    BELONGS_TO = "BELONGS_TO"       # Сертификат → Партия
    USES = "USES"                   # АОСР → Сертификат (с quantity на ребре)
    COVERS = "COVERS"               # Партия → Материал
    SHIPPED_BY = "SHIPPED_BY"       # Партия → Поставщик
    RECEIVED_IN = "RECEIVED_IN"     # Партия → Входной контроль
    GENERATED = "GENERATED"         # Скан → Документ (provenance)
    VERIFIES = "VERIFIES"           # Входной контроль → Сертификат
    PROVENANCE = "PROVENANCE"       # Документ → Скан (обратная связь)


class ForensicSeverity(str, Enum):
    CRITICAL = "critical"   # Блокирующее нарушение (подлог, фальсификация)
    HIGH = "high"           # Серьёзное расхождение
    MEDIUM = "medium"       # Потенциальная проблема
    INFO = "info"           # Информационное сообщение


# =============================================================================
# Forensic Finding
# =============================================================================

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
    # Шаблон для расширения:
    # "Наименование": {
    #     "obsolete": True,
    #     "replaced_by": "...",
    #     "reason": "...",
    #     "gost_old": "...",
    #     "gost_new": "...",
    # },
}


# =============================================================================
# GraphService — Forensic Knowledge Graph
# =============================================================================

class GraphService:
    """
    Граф знаний ASD v12.0 — NetworkX DiGraph с forensic-проверками.

    Поддерживает:
      - Тактический режим: Project → Event → AgentResult
      - Стратегический режим: Scan → Document → Certificate → Batch → AOSR
      - Forensic-проверки: batch coverage, certificate reuse, input control trace
      - Валидацию спецификаций материалов (obsolete/wrong spec)
    """

    def __init__(self):
        self.graph_dir = settings.graphs_path
        self.graph_path = self.graph_dir / "knowledge_graph.gpickle"
        self.graph = self._load_or_create_graph()

    # =========================================================================
    # Persistence
    # =========================================================================

    def _load_or_create_graph(self) -> nx.DiGraph:
        """Загружает граф с диска или создаёт новый."""
        if self.graph_path.exists():
            try:
                with open(self.graph_path, "rb") as f:
                    g = pickle.load(f)
                    logger.info("Graph loaded: %d nodes, %d edges", g.number_of_nodes(), g.number_of_edges())
                    return g
            except Exception as e:
                logger.error("Error loading graph: %s. Creating a new one.", e)
        return nx.DiGraph()

    def save_graph(self):
        """Сохраняет текущее состояние графа на диск."""
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        with open(self.graph_path, "wb") as f:
            pickle.dump(self.graph, f)

    # =========================================================================
    # Legacy API (backward compatible)
    # =========================================================================

    def add_document(self, doc_id: str, metadata: Dict[str, Any]):
        """Добавляет узел-документ (устаревший API, совместимость)."""
        self.graph.add_node(doc_id, type=NodeType.DOCUMENT.value, **metadata)
        self.save_graph()

    def add_normative_act(self, act_id: str, title: str):
        """Добавляет узел нормативного акта."""
        self.graph.add_node(act_id, type=NodeType.NORMATIVE_ACT.value, title=title)
        self.save_graph()

    def add_reference(self, source_id: str, target_id: str, context: str = ""):
        """Добавляет связь REFERENCES между узлами."""
        if self.graph.has_node(source_id) and self.graph.has_node(target_id):
            self.graph.add_edge(source_id, target_id, relation=EdgeType.REFERENCES.value, context=context)
            self.save_graph()
        else:
            logger.warning("Failed to add edge %s -> %s. Nodes must exist.", source_id, target_id)

    def get_related_nodes(self, node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        """BFS-поиск связанных узлов."""
        if not self.graph.has_node(node_id):
            return []
        related = []
        try:
            for u, v in nx.bfs_edges(self.graph, source=node_id, depth_limit=depth):
                node_data = dict(self.graph.nodes[v])
                related.append({"id": v, "data": node_data})
        except Exception as e:
            logger.warning("BFS traversal error from %s: %s", node_id, e)
        return related

    # =========================================================================
    # Node Factory — единая точка создания узлов
    # =========================================================================

    def _add_node(self, node_id: str, node_type: NodeType, **attrs) -> None:
        """Добавить узел с типом и атрибутами."""
        self.graph.add_node(node_id, type=node_type.value, added_at=datetime.now().isoformat(), **attrs)
        self.save_graph()

    # =========================================================================
    # Material Nodes
    # =========================================================================

    def add_material(
        self,
        material_id: str,
        name: str,
        gost: str = "",
        unit: str = "",
        category: str = "",
        market_price_per_unit: float = 0.0,
    ) -> None:
        """Добавить узел материала."""
        self._add_node(
            material_id, NodeType.MATERIAL,
            name=name, gost=gost, unit=unit,
            category=category, market_price=market_price_per_unit,
        )

    # =========================================================================
    # Supplier Nodes
    # =========================================================================

    def add_supplier(
        self,
        supplier_id: str,
        name: str,
        inn: str = "",
        region: str = "",
        rating: int = 0,
    ) -> None:
        """Добавить узел поставщика."""
        self._add_node(
            supplier_id, NodeType.SUPPLIER,
            name=name, inn=inn, region=region, rating=rating,
        )

    # =========================================================================
    # Batch Nodes
    # =========================================================================

    def add_batch(
        self,
        batch_id: str,
        material_name: str,
        total_quantity: float,
        unit: str = "т",
        supplier_name: str = "",
        delivery_date: str = "",
    ) -> None:
        """Добавить узел партии поставки."""
        self._add_node(
            batch_id, NodeType.BATCH,
            material_name=material_name, total_quantity=total_quantity,
            unit=unit, supplier_name=supplier_name, delivery_date=delivery_date,
        )

    def link_batch_to_material(self, batch_id: str, material_id: str) -> None:
        """Связать партию с материалом (COVERS)."""
        if self._edge_ok(batch_id, material_id):
            self.graph.add_edge(batch_id, material_id, relation=EdgeType.COVERS.value)
            self.save_graph()

    def link_batch_to_supplier(self, batch_id: str, supplier_id: str) -> None:
        """Связать партию с поставщиком (SHIPPED_BY)."""
        if self._edge_ok(batch_id, supplier_id):
            self.graph.add_edge(batch_id, supplier_id, relation=EdgeType.SHIPPED_BY.value)
            self.save_graph()

    # =========================================================================
    # Certificate Nodes
    # =========================================================================

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
    ) -> None:
        """Добавить узел сертификата качества."""
        self._add_node(
            cert_id, NodeType.CERTIFICATE,
            material_name=material_name, batch_number=batch_number,
            batch_size=batch_size, unit=unit,
            supplier=supplier, issue_date=issue_date, gost=gost,
        )

    def link_certificate_to_batch(self, cert_id: str, batch_id: str) -> None:
        """Связать сертификат с партией (BELONGS_TO)."""
        if self._edge_ok(cert_id, batch_id):
            self.graph.add_edge(cert_id, batch_id, relation=EdgeType.BELONGS_TO.value)
            self.save_graph()

    # =========================================================================
    # AOSR Nodes
    # =========================================================================

    def add_aosr(
        self,
        aosr_id: str,
        work_type: str = "",
        description: str = "",
        date: str = "",
        project_id: str = "",
    ) -> None:
        """Добавить узел АОСР."""
        self._add_node(
            aosr_id, NodeType.AOSR,
            work_type=work_type, description=description,
            date=date, project_id=project_id,
        )

    def link_aosr_to_certificate(
        self, aosr_id: str, cert_id: str, quantity_used: float
    ) -> None:
        """
        Связать АОСР с сертификатом (USES) — ключевое ребро для forensic-проверок.

        Args:
            aosr_id: идентификатор АОСР
            cert_id: идентификатор сертификата
            quantity_used: количество материала по данному АОСР (из сертификата)
        """
        if self._edge_ok(aosr_id, cert_id):
            self.graph.add_edge(
                aosr_id, cert_id,
                relation=EdgeType.USES.value,
                quantity=quantity_used,
            )
            self.save_graph()

    # =========================================================================
    # Input Control Nodes
    # =========================================================================

    def add_input_control(
        self,
        record_id: str,
        cert_id: str = "",
        inspector: str = "",
        date: str = "",
        material_name: str = "",
        quantity_received: float = 0.0,
        unit: str = "",
        result: str = "",  # "принято", "отклонено", "условно принято"
    ) -> None:
        """Добавить запись входного контроля (ЖВК)."""
        self._add_node(
            record_id, NodeType.INPUT_CONTROL,
            cert_id=cert_id, inspector=inspector, date=date,
            material_name=material_name, quantity_received=quantity_received,
            unit=unit, result=result,
        )

    def link_input_control_to_batch(self, ic_id: str, batch_id: str) -> None:
        """Связать входной контроль с партией (RECEIVED_IN)."""
        if self._edge_ok(ic_id, batch_id):
            self.graph.add_edge(ic_id, batch_id, relation=EdgeType.RECEIVED_IN.value)
            self.save_graph()

    # =========================================================================
    # TTN Nodes
    # =========================================================================

    def add_ttn(
        self,
        ttn_id: str,
        supplier: str = "",
        date: str = "",
        material_list: str = "",
    ) -> None:
        """Добавить узел товарно-транспортной накладной."""
        self._add_node(
            ttn_id, NodeType.TTN,
            supplier=supplier, date=date, material_list=material_list,
        )

    # =========================================================================
    # Scan Nodes (provenance)
    # =========================================================================

    def add_scan(self, scan_id: str, file_path: str, page: int = 0, source: str = "") -> None:
        """Добавить узел скана — источник происхождения документа."""
        self._add_node(scan_id, NodeType.SCAN, file_path=file_path, page=page, source=source)

    def link_document_to_scan(self, doc_id: str, scan_id: str) -> None:
        """Связать документ с исходным сканом (PROVENANCE)."""
        if self._edge_ok(doc_id, scan_id):
            self.graph.add_edge(doc_id, scan_id, relation=EdgeType.PROVENANCE.value)
            self.save_graph()

    # =========================================================================
    # Helpers
    # =========================================================================

    def _edge_ok(self, src: str, dst: str) -> bool:
        """Проверить существование узлов для ребра."""
        ok = self.graph.has_node(src) and self.graph.has_node(dst)
        if not ok:
            logger.warning("Cannot add edge %s -> %s: nodes missing.", src, dst)
        return ok

    def _get_edge_attr(self, src: str, dst: str, attr: str, default: Any = 0.0) -> Any:
        """Безопасно получить атрибут ребра."""
        try:
            return self.graph.edges[src, dst].get(attr, default)
        except KeyError:
            return default

    # =========================================================================
    # Traversal Helpers
    # =========================================================================

    def get_certificates_for_aosr(self, aosr_id: str) -> List[Dict[str, Any]]:
        """
        Получить все сертификаты, использованные в данном АОСР.

        Returns:
            [{cert_id, material_name, batch_size, quantity_used, ...}, ...]
        """
        if not self.graph.has_node(aosr_id):
            return []

        certs = []
        for _, cert_id, edge_data in self.graph.out_edges(aosr_id, data=True):
            if edge_data.get("relation") == EdgeType.USES.value:
                cert_node = dict(self.graph.nodes[cert_id])
                cert_node["cert_id"] = cert_id
                cert_node["quantity_used"] = edge_data.get("quantity", 0.0)
                certs.append(cert_node)
        return certs

    def get_aosrs_for_certificate(self, cert_id: str) -> List[Dict[str, Any]]:
        """
        Получить все АОСР, ссылающиеся на данный сертификат.

        Returns:
            [{aosr_id, work_type, quantity_used, ...}, ...]
        """
        if not self.graph.has_node(cert_id):
            return []

        aosrs = []
        for aosr_id, _, edge_data in self.graph.in_edges(cert_id, data=True):
            if edge_data.get("relation") == EdgeType.USES.value:
                aosr_node = dict(self.graph.nodes[aosr_id])
                aosr_node["aosr_id"] = aosr_id
                aosr_node["quantity_used"] = edge_data.get("quantity", 0.0)
                aosrs.append(aosr_node)
        return aosrs

    def get_full_provenance_chain(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Пройти цепочку происхождения: документ → скан → файл.

        Возвращает цепочку узлов PROVENANCE до исходного скана.
        """
        if not self.graph.has_node(node_id):
            return []

        chain = [{"id": node_id, "data": dict(self.graph.nodes[node_id])}]
        current = node_id
        while True:
            found = False
            for _, target, edge_data in self.graph.out_edges(current, data=True):
                if edge_data.get("relation") in (EdgeType.PROVENANCE.value, EdgeType.GENERATED.value):
                    chain.append({"id": target, "data": dict(self.graph.nodes[target])})
                    current = target
                    found = True
                    break
            if not found:
                break
        return chain

    def has_input_control_path(self, cert_id: str) -> bool:
        """
        Проверить: есть ли путь от сертификата до записи входного контроля?

        Путь: Certificate → (BELONGS_TO) → Batch → (RECEIVED_IN) → InputControl
        """
        if not self.graph.has_node(cert_id):
            return False
        # Ищем входной контроль через Batch
        for _, batch_id, edge_data in self.graph.out_edges(cert_id, data=True):
            if edge_data.get("relation") == EdgeType.BELONGS_TO.value:
                for _, ic_id, ic_edge in self.graph.out_edges(batch_id, data=True):
                    if ic_edge.get("relation") == EdgeType.RECEIVED_IN.value:
                        return True
        return False

    def get_input_control_chain(self, cert_id: str) -> List[Dict[str, Any]]:
        """
        Получить цепочку входного контроля для сертификата.

        Certificate → Batch → InputControl → (если есть) Supplier
        """
        chain = []
        if not self.graph.has_node(cert_id):
            return chain

        chain.append({"id": cert_id, "data": dict(self.graph.nodes[cert_id])})
        for _, batch_id, edge_data in self.graph.out_edges(cert_id, data=True):
            if edge_data.get("relation") == EdgeType.BELONGS_TO.value:
                chain.append({"id": batch_id, "data": dict(self.graph.nodes[batch_id])})
                for _, ic_id, ic_edge in self.graph.out_edges(batch_id, data=True):
                    if ic_edge.get("relation") == EdgeType.RECEIVED_IN.value:
                        chain.append({"id": ic_id, "data": dict(self.graph.nodes[ic_id])})
                break
        return chain

    # =========================================================================
    # Forensic Checks — rule-based, no LLM
    # =========================================================================

    def check_batch_coverage(self, cert_id: str) -> List[ForensicFinding]:
        """
        Проверка покрытия партии сертификата.

        Σ quantity_used (по всем АОСР, ссылающимся на сертификат) ≤ batch_size.

        Выявляет: использование материала сверх объёма сертифицированной партии.
        Причина: подлог (ксерокопия сертификата), ошибка ПТО, отсутствие входного контроля.
        """
        findings: List[ForensicFinding] = []

        if not self.graph.has_node(cert_id):
            findings.append(ForensicFinding(
                check_name="batch_coverage",
                severity=ForensicSeverity.INFO,
                description=f"Сертификат {cert_id} не найден в графе.",
                recommendation="Добавьте сертификат через add_certificate().",
            ))
            return findings

        cert_node = self.graph.nodes[cert_id]
        batch_size = float(cert_node.get("batch_size", 0))
        material = cert_node.get("material_name", "неизвестный материал")
        batch_num = cert_node.get("batch_number", "?")

        if batch_size <= 0:
            findings.append(ForensicFinding(
                check_name="batch_coverage",
                severity=ForensicSeverity.HIGH,
                description=(
                    f"Сертификат {cert_id} ({material}, партия №{batch_num}): "
                    f"не указан размер партии. Невозможно проверить покрытие."
                ),
                recommendation="Укажите batch_size в сертификате.",
            ))
            return findings

        # Суммируем usage по всем АОСР
        total_used = 0.0
        affected_aosrs: List[str] = []
        for _, _, edge_data in self.graph.in_edges(cert_id, data=True):
            if edge_data.get("relation") == EdgeType.USES.value:
                qty = float(edge_data.get("quantity", 0))
                total_used += qty

        # Собираем ID АОСР
        for aosr_id, _, edge_data in self.graph.in_edges(cert_id, data=True):
            if edge_data.get("relation") == EdgeType.USES.value:
                affected_aosrs.append(aosr_id)

        if total_used > batch_size:
            excess = total_used - batch_size
            excess_pct = (excess / batch_size * 100) if batch_size > 0 else 0
            findings.append(ForensicFinding(
                check_name="batch_coverage",
                severity=ForensicSeverity.CRITICAL,
                description=(
                    f"⚠️ КРИТИЧЕСКОЕ НЕСООТВЕТСТВИЕ: сертификат {cert_id} "
                    f"({material}, партия №{batch_num}) покрывает {batch_size}, "
                    f"но по {len(affected_aosrs)} АОСР использовано {total_used:.1f} "
                    f"(превышение на {excess:.1f}, +{excess_pct:.0f}%). "
                    f"Сертификат не может подтверждать качество всего объёма. "
                    f"Вероятные причины: подлог (ксерокопия сертификата от другой партии), "
                    f"отсутствие входного контроля, ошибка комплектации ИД."
                ),
                node_ids=[cert_id] + affected_aosrs,
                recommendation=(
                    f"1. Запросить у поставщика сертификаты на весь объём ({total_used:.1f}). "
                    f"2. Поднять ЖВК (журнал входного контроля) — проверить фактическое поступление. "
                    f"3. При невозможности — оформлять АОСР только на подтверждённый объём ({batch_size}). "
                    f"4. На оставшиеся {excess:.1f} — отдельный акт с новым сертификатом."
                ),
            ))
        elif len(affected_aosrs) >= 2 and total_used == batch_size:
            # Полное покрытие — ОК, но всё равно отмечаем повторное использование
            findings.append(ForensicFinding(
                check_name="batch_coverage",
                severity=ForensicSeverity.INFO,
                description=(
                    f"Сертификат {cert_id} ({material}) использован в {len(affected_aosrs)} АОСР "
                    f"на общий объём {total_used:.1f} из {batch_size}. Покрытие полное."
                ),
                node_ids=[cert_id] + affected_aosrs,
                recommendation="Убедиться в наличии входного контроля по каждой поставке.",
            ))

        return findings

    def check_certificate_reuse(self) -> List[ForensicFinding]:
        """
        Проверить сертификаты, использованные в 2+ АОСР без входного контроля.

        Выявляет: потенциальный подлог — один сертификат подкладывается
        к нескольким актам, но записи входного контроля отсутствуют.
        """
        findings: List[ForensicFinding] = []

        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get("type") != NodeType.CERTIFICATE.value:
                continue

            aosrs = self.get_aosrs_for_certificate(node_id)
            if len(aosrs) < 2:
                continue

            has_ic = self.has_input_control_path(node_id)
            if has_ic:
                continue

            total_used = sum(a.get("quantity_used", 0) for a in aosrs)
            findings.append(ForensicFinding(
                check_name="certificate_reuse",
                severity=ForensicSeverity.HIGH,
                description=(
                    f"⚠️ Сертификат {node_id} ({node_data.get('material_name', '?')}) "
                    f"использован в {len(aosrs)} АОСР (общий объём {total_used:.1f}), "
                    f"но НЕ привязан к записи входного контроля. "
                    f"Невозможно подтвердить, что материал фактически поступил на объект. "
                    f"Риск: сертификат может быть ксерокопией от другой партии/объекта."
                ),
                node_ids=[node_id] + [a.get("aosr_id", "") for a in aosrs],
                recommendation=(
                    "1. Поднять ЖВК — проверить даты и номера партий. "
                    "2. Сверить номер партии сертификата с ТТН/УПД. "
                    "3. При отсутствии ЖВК — оформить акт входного контроля задним числом "
                    "(если есть ТТН) или запросить дубликаты сертификатов у поставщика."
                ),
            ))

        return findings

    def check_input_control_trace(self, cert_id: str) -> List[ForensicFinding]:
        """
        Проверить traceability конкретного сертификата.

        Certificate → Batch → InputControl
        """
        findings: List[ForensicFinding] = []

        if not self.graph.has_node(cert_id):
            findings.append(ForensicFinding(
                check_name="input_control_trace",
                severity=ForensicSeverity.INFO,
                description=f"Сертификат {cert_id} не найден в графе.",
            ))
            return findings

        chain = self.get_input_control_chain(cert_id)

        # Проверка: есть ли связь с Batch
        has_batch = any(
            self._get_edge_attr(cert_id, n["id"], "relation") == EdgeType.BELONGS_TO.value
            for n in chain[1:] if n["id"] != cert_id
        ) if len(chain) > 1 else False

        has_ic = len(chain) >= 3

        if not has_batch and not has_ic:
            findings.append(ForensicFinding(
                check_name="input_control_trace",
                severity=ForensicSeverity.HIGH,
                description=(
                    f"Сертификат {cert_id} не привязан ни к партии, ни к входному контролю. "
                    f"Документ «висит в воздухе» — происхождение материала не подтверждено."
                ),
                recommendation="Добавьте Batch и InputControlRecord через add_batch() + link_*().",
            ))
        elif has_batch and not has_ic:
            findings.append(ForensicFinding(
                check_name="input_control_trace",
                severity=ForensicSeverity.MEDIUM,
                description=(
                    f"Сертификат {cert_id} привязан к партии, но запись входного контроля отсутствует. "
                    f"Материал мог поступить на объект без проверки качества."
                ),
                recommendation="Добавьте InputControlRecord через add_input_control().",
            ))

        return findings

    def check_orphan_certificates(self) -> List[ForensicFinding]:
        """
        Найти все сертификаты, не привязанные к входному контролю (orphan).

        Используется при инвентаризации: показывает сертификаты, которые есть в деле,
        но их невозможно привязать к фактическим поставкам.
        """
        findings: List[ForensicFinding] = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") != NodeType.CERTIFICATE.value:
                continue
            if not self.has_input_control_path(node_id):
                findings.append(ForensicFinding(
                    check_name="orphan_certificates",
                    severity=ForensicSeverity.MEDIUM,
                    description=f"Сертификат-сирота: {node_id} ({data.get('material_name', '?')})",
                    node_ids=[node_id],
                    recommendation="Привяжите к Batch → InputControl или пометьте как недостоверный.",
                ))
        return findings

    def check_document_provenance(self, doc_id: str) -> List[ForensicFinding]:
        """
        Проверить: имеет ли документ цепочку происхождения до исходного скана/файла.

        Для forensic-режима критично: каждый сгенерированный документ должен ссылаться
        на исходные данные (скан, файл), из которых он получен.
        """
        chain = self.get_full_provenance_chain(doc_id)
        findings: List[ForensicFinding] = []
        if len(chain) <= 1:
            findings.append(ForensicFinding(
                check_name="document_provenance",
                severity=ForensicSeverity.MEDIUM,
                description=f"Документ {doc_id} не имеет цепочки происхождения до исходного скана.",
                recommendation="Добавьте связь PROVENANCE: link_document_to_scan(doc_id, scan_id).",
            ))
        return findings

    # =========================================================================
    # Material Spec Validation
    # =========================================================================

    def validate_material_spec(self, material_name: str) -> List[ForensicFinding]:
        """
        Проверить спецификацию материала на известные проблемы:
          - Снят с производства (obsolete)
          - Неверная марка (геометрия не совпадает с современным аналогом)
          - Требуется Б/У обоснование

        Использует OBSOLETE_MATERIALS — словарь известных проблемных материалов.
        """
        findings: List[ForensicFinding] = []

        # Прямое совпадение
        if material_name in OBSOLETE_MATERIALS:
            info = OBSOLETE_MATERIALS[material_name]
            findings.append(ForensicFinding(
                check_name="material_spec_validation",
                severity=ForensicSeverity.CRITICAL,
                description=(
                    f"⚠️ МАТЕРИАЛ СНЯТ С ПРОИЗВОДСТВА: «{material_name}». {info['reason']}"
                ),
                node_ids=[],
                recommendation=(
                    f"Замена: {info['replaced_by']} ({info['gost_new']}). "
                    f"Если проектом предусмотрен именно {material_name} — "
                    f"необходимо обоснование применения Б/У материала с экспертизой "
                    f"остаточного сечения и согласование с заказчиком/авторским надзором."
                ),
            ))

        # Нечёткий поиск: «Шпунт Л5» в поле name любого obsolete-материала
        for obsolete_name, info in OBSOLETE_MATERIALS.items():
            if obsolete_name.lower() in material_name.lower() and material_name != obsolete_name:
                findings.append(ForensicFinding(
                    check_name="material_spec_validation",
                    severity=ForensicSeverity.HIGH,
                    description=(
                        f"⚠️ Возможна опечатка в спецификации: «{material_name}». "
                        f"Ближайшее совпадение: «{obsolete_name}» — {info['reason']}"
                    ),
                    recommendation=f"Уточните марку материала. Возможно, имеется в виду {info['replaced_by']}.",
                ))

        return findings

    # =========================================================================
    # Audit All — полный forensic-прогон для Auditor
    # =========================================================================

    def run_all_forensic_checks(self) -> List[ForensicFinding]:
        """
        Запустить все forensic-проверки по графу.

        Используется Агентом-Аудитором (Стройконтроль) для полного аудита
        документации объекта. Возвращает объединённый список находок.
        """
        all_findings: List[ForensicFinding] = []

        # 1. Проверка покрытия партий для всех сертификатов
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.CERTIFICATE.value:
                all_findings.extend(self.check_batch_coverage(node_id))

        # 2. Повторное использование сертификатов без входного контроля
        all_findings.extend(self.check_certificate_reuse())

        # 3. Сертификаты-сироты
        all_findings.extend(self.check_orphan_certificates())

        # 4. Проверка provenance для всех документов
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == NodeType.DOCUMENT.value:
                all_findings.extend(self.check_document_provenance(node_id))

        # Сортировка: CRITICAL → HIGH → MEDIUM → INFO
        severity_order = {
            ForensicSeverity.CRITICAL: 0,
            ForensicSeverity.HIGH: 1,
            ForensicSeverity.MEDIUM: 2,
            ForensicSeverity.INFO: 3,
        }
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 99))

        return all_findings

    # =========================================================================
    # Graph Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Статистика графа для мониторинга."""
        node_types: Dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            t = data.get("type", "unknown")
            node_types[t] = node_types.get(t, 0) + 1

        edge_types: Dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            r = data.get("relation", "unknown")
            edge_types[r] = edge_types.get(r, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
            "graph_path": str(self.graph_path),
        }


# =============================================================================
# Singleton
# =============================================================================

graph_service = GraphService()
