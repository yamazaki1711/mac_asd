"""
ASD v13.0 — Project Loader (нулевой слой Evidence Graph).

Первый шаг ASD на любом объекте: парсинг проектной документации (ПД/РД)
и построение планового дерева работ в Evidence Graph.

ПД/РД есть всегда — кто-то же спроектировал объект. ProjectLoader извлекает:
  - WorkUnit'ы (ЧТО строим) из спецификаций и ведомостей — status=PLANNED
  - Volume на каждый WorkUnit из ВОР
  - Location-иерархию из генплана
  - TEMPORAL_BEFORE из ПОС/ППР/календарного плана
  - MaterialBatch (ожидаемые поставки) из сметы/спецификаций
  - Ожидаемые документы (сертификаты, акты) из требований к качеству

После загрузки граф содержит ПОЛНЫЙ план работ. Дальше:
  - Сопровождение: агенты переводят PLANNED → IN_PROGRESS → COMPLETED
  - Антикризис: Inference Engine сопоставляет план с уликами

Usage:
    from src.core.project_loader import project_loader, ProjectSpec

    spec = ProjectSpec(
        name="Шпунтовое ограждение",
        work_items=[...],  # программно
    )
    summary = project_loader.load(evidence_graph, spec)

    # Или из папки ПД:
    summary = project_loader.load_from_folder(evidence_graph, "/path/to/PD")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class WorkItem:
    """Одна строка из ведомости объёмов работ / спецификации."""
    name: str                        # "Погружение шпунта Л5-УМ"
    work_type: str                   # "погружение_шпунта" (ключ для typical_rates)
    quantity: float                  # 100
    unit: str                        # "шт"
    location: str = ""               # "Захватка 1" / "Ось А-Г"
    depends_on: List[str] = field(default_factory=list)  # имена предшествующих работ
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    gost: str = ""                   # "ГОСТ Р 53629-2009"
    material: str = ""               # "Шпунт Ларсена Л5-УМ"
    material_quantity: float = 0.0   # ожидаемое количество материала
    material_unit: str = ""
    expected_documents: List[str] = field(default_factory=list)
    # ["АОСР", "Сертификат на шпунт", "Акт испытаний", "Исполнительная схема"]


@dataclass
class ProjectSpec:
    """Спецификация проекта — программное описание ПД."""
    name: str                        # "Шпунтовое ограждение ЛОС"
    code: str = ""                   # Шифр проекта
    work_items: List[WorkItem] = field(default_factory=list)
    locations: List[Dict[str, Any]] = field(default_factory=list)
    # locations: [{"name": "Площадка", "children": [{"name": "Захватка 1"}, ...]}]
    suppliers: List[Dict[str, str]] = field(default_factory=list)
    # suppliers: [{"name": "ЕВРАЗ", "role": "supplier"}]
    normative_docs: List[str] = field(default_factory=list)
    # ["ГОСТ Р 53629-2009", "СП 543.1325800.2024", "344/пр"]


# =============================================================================
# Project Loader
# =============================================================================

class ProjectLoader:
    """
    Загрузчик проектной документации в Evidence Graph.

    Создаёт плановый baseline: все WorkUnit'ы, их объёмы, локации,
    зависимости, ожидаемые материалы и документы.
    """

    def load(self, graph, spec: ProjectSpec) -> Dict[str, Any]:
        """
        Загрузить проект в Evidence Graph.

        Args:
            graph: EvidenceGraph instance
            spec: ProjectSpec с work_items, locations, suppliers

        Returns:
            {"work_units": N, "volumes": N, "locations": N, ...}
        """
        from src.core.evidence_graph import (
            WorkUnitStatus, FactSource, DocType, DocStatus,
            EdgeType, VolumeSource, PersonRole,
        )

        stats = {
            "work_units": 0,
            "volumes": 0,
            "locations": 0,
            "material_batches": 0,
            "temporal_edges": 0,
            "expected_documents": 0,
            "suppliers": 0,
        }

        # ── 1. Locations (из генплана) ─────────────────────────────────
        loc_ids: Dict[str, str] = {}  # name → node_id
        for loc in spec.locations:
            loc_id = self._build_location_tree(graph, loc, parent_id=None)
            self._collect_location_ids(graph, loc_id, loc_ids)
        stats["locations"] = len(loc_ids)

        # ── 2. Suppliers ─────────────────────────────────────────────
        supplier_ids: Dict[str, str] = {}
        for sup in spec.suppliers:
            sid = graph.add_person(
                name=sup["name"],
                role=PersonRole.SUPPLIER,
                organization=sup.get("org", sup["name"]),
            )
            supplier_ids[sup["name"]] = sid
            stats["suppliers"] += 1

        # ── 3. WorkItems → WorkUnit'ы + Volume + зависимости ────────
        wu_ids: Dict[str, str] = {}  # item.name → node_id

        # Первый проход: создаём все WorkUnit'ы
        for item in spec.work_items:
            loc_id = loc_ids.get(item.location) if item.location else None

            wu_id = graph.add_work_unit(
                work_type=item.work_type,
                description=f"{item.name} — {item.quantity} {item.unit}",
                status=WorkUnitStatus.PLANNED,
                confidence=1.0,
                source=FactSource.AGENT,
                volume=item.quantity,
                unit=item.unit,
                location_id=loc_id,
                planned_start=item.planned_start,
                planned_end=item.planned_end,
            )
            wu_ids[item.name] = wu_id
            stats["work_units"] += 1

            # Volume node
            graph.add_volume(
                value=item.quantity,
                unit=item.unit,
                source=VolumeSource.PROJECT,
                work_unit_id=wu_id,
                confidence=1.0,
            )
            stats["volumes"] += 1

            # MaterialBatch (если указан материал)
            if item.material and item.material_quantity > 0:
                supplier_id = None
                for sname, sid in supplier_ids.items():
                    supplier_id = sid
                    break

                batch_id = graph.add_material_batch(
                    material_name=item.material,
                    batch_number="",
                    quantity=item.material_quantity,
                    unit=item.material_unit or item.unit,
                    gost=item.gost or None,
                    confidence=1.0,
                )
                graph.link(batch_id, wu_id, EdgeType.USED_IN,
                          confidence=1.0, quantity=item.material_quantity)
                if supplier_id:
                    graph.link(batch_id, supplier_id, EdgeType.SUPPLIED_BY)
                stats["material_batches"] += 1

            # Expected documents (сертификаты, АОСР, акты, схемы)
            for doc_desc in item.expected_documents:
                doc_type = self._guess_doc_type(doc_desc)
                doc_id = graph.add_document(
                    doc_type=doc_type,
                    content_summary=f"Ожидаемый: {doc_desc} для {item.name}",
                    confidence=1.0,
                    status=DocStatus.REFERENCED,  # Пока не предоставлен
                    work_unit_id=wu_id,
                )
                stats["expected_documents"] += 1

        # Второй проход: TEMPORAL_BEFORE связи
        for item in spec.work_items:
            wu_id = wu_ids[item.name]
            for dep_name in item.depends_on:
                dep_id = wu_ids.get(dep_name)
                if dep_id:
                    graph.link(dep_id, wu_id, EdgeType.TEMPORAL_BEFORE, confidence=1.0)
                    stats["temporal_edges"] += 1

        # ── 4. Normative documents ───────────────────────────────────
        for norm in spec.normative_docs:
            graph.add_document(
                doc_type=DocType.DRAWING,
                content_summary=f"Норматив: {norm}",
                confidence=1.0,
                status=DocStatus.REFERENCED,
            )

        logger.info(
            "Project loaded: %d WUs, %d volumes, %d materials, %d temporal edges, %d expected docs",
            stats["work_units"], stats["volumes"], stats["material_batches"],
            stats["temporal_edges"], stats["expected_documents"],
        )

        return stats

    def load_from_folder(self, graph, folder: str) -> Dict[str, Any]:
        """
        Загрузить проект из папки с ПД/РД.

        Сканирует папку, составляет инвентаризацию файлов по типам
        и создаёт document-узлы в графе для найденных файлов.

        Полный парсинг содержимого (ВОР, спецификации, чертежи):
        - PDF: pdftotext + VLM для таблиц спецификаций
        - XLSX: openpyxl для ВОР и смет
        - DWG: ezdxf для извлечения блок-спецификаций

        Args:
            graph: EvidenceGraph instance
            folder: путь к папке с проектной документацией

        Returns:
            Статистика загрузки
        """
        pd_path = Path(folder)
        if not pd_path.exists():
            logger.error("PD folder not found: %s", folder)
            return {"error": "folder not found"}

        # Scan folder and inventory files
        from collections import Counter
        from src.core.evidence_graph import DocType

        suffix_map = {
            ".pdf": DocType.DRAWING,
            ".xlsx": DocType.DRAWING,
            ".xls": DocType.DRAWING,
            ".dwg": DocType.DRAWING,
            ".dxf": DocType.DRAWING,
            ".docx": DocType.DRAWING,
            ".doc": DocType.DRAWING,
            ".txt": DocType.DRAWING,
        }
        type_counts: Counter = Counter()
        files_found: List[Path] = []
        nodes_created = 0

        for ext in suffix_map:
            for f in sorted(pd_path.rglob(f"*{ext}")):
                files_found.append(f)
                type_counts[ext] += 1
        for f in sorted(pd_path.rglob("*")):
            if f.is_file() and f.suffix.lower() not in suffix_map:
                files_found.append(f)
                type_counts["other"] += 1

        if not files_found:
            logger.warning("PD folder is empty: %s", folder)
            return {"error": "no files found", "files": 0}

        # Create document nodes for all found files
        for f in files_found:
            node_id = graph.add_document(
                doc_type=DocType.DRAWING,
                content_summary=f"Файл ПД: {f.name}",
                confidence=0.9,
            )
            if node_id:
                nodes_created += 1

        summary = {
            "folder": str(pd_path),
            "files_found": len(files_found),
            "by_extension": dict(type_counts),
            "nodes_created": nodes_created,
            "message": (
                f"Просканировано {len(files_found)} файлов. "
                f"Узлы созданы. Для полного парсинга содержимого "
                f"используйте load() с ProjectSpec."
            ),
        }
        logger.info("load_from_folder: %s", summary)
        graph.save()
        return summary

    # ── Helpers ──────────────────────────────────────────────────────────

    def _build_location_tree(
        self, graph, loc: Dict[str, Any], parent_id: Optional[str] = None
    ) -> str:
        """Построить дерево локаций рекурсивно."""
        loc_id = graph.add_location(
            name=loc["name"],
            parent_id=parent_id,
            description=loc.get("description", ""),
        )
        for child in loc.get("children", []):
            self._build_location_tree(graph, child, parent_id=loc_id)
        return loc_id

    def _collect_location_ids(
        self, graph, loc_id: str, result: Dict[str, str]
    ):
        """Собрать все ID локаций в плоский словарь name→id."""
        data = graph.graph.nodes[loc_id]
        result[data["name"]] = loc_id
        for child_id in graph.graph.successors(loc_id):
            edge = graph.graph.edges.get((loc_id, child_id), {})
            if edge.get("edge_type") == "contains":
                self._collect_location_ids(graph, child_id, result)

    def _guess_doc_type(self, doc_desc: str):
        """Угадать тип документа по описанию."""
        from src.core.evidence_graph import DocType
        desc = doc_desc.lower()
        if "аоср" in desc or "акт освидетельствования" in desc:
            return DocType.AOSR
        elif "сертификат" in desc or "паспорт" in desc:
            return DocType.CERTIFICATE
        elif "исполнительная схема" in desc or "исп. схема" in desc or "ис " in desc:
            return DocType.EXECUTIVE_SCHEME
        elif "акт испытаний" in desc or "протокол испытаний" in desc:
            return DocType.PROTOCOL
        elif "журнал" in desc:
            return DocType.JOURNAL
        elif "кс-2" in desc or "акт приёмки" in desc:
            return DocType.KS2
        elif "фото" in desc:
            return DocType.PHOTO
        elif "схема" in desc:  # generic fallback
            return DocType.EXECUTIVE_SCHEME
        return DocType.UNKNOWN


# Модульный синглтон
project_loader = ProjectLoader()
