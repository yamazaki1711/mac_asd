"""
ASD v12.0 — Chain Builder.

Строит цепочки документов из Evidence Graph v2 для каждого WorkUnit.
Проверяет полноту и согласованность документального шлейфа.

Цепочка:
    MaterialBatch → Certificate/Passport → (Входной контроль) → AOSR → KS-2

Для каждой цепочки вычисляется:
    - Статус: COMPLETE / PARTIAL / BROKEN
    - Confidence: средняя уверенность всех узлов
    - Разрывы: каких документов не хватает

Usage:
    from src.core.chain_builder import chain_builder
    
    chains = chain_builder.build_chains(evidence_graph)
    for chain in chains:
        print(chain.status, chain.confidence, chain.gaps)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════

class ChainStatus(str, Enum):
    COMPLETE = "complete"          # Все документы на месте, даты согласованы
    PARTIAL = "partial"            # Часть документов есть, но есть разрывы
    BROKEN = "broken"              # Критические разрывы — нет АОСР или сертификатов
    EMPTY = "empty"                # WorkUnit без документов вообще


class GapSeverity(str, Enum):
    CRITICAL = "critical"   # Нет АОСР — работа не освидетельствована
    HIGH = "high"           # Нет сертификата на материал
    MEDIUM = "medium"       # Нет КС-2 при наличии АОСР
    LOW = "low"             # Нет спецжурнала/исполнительной схемы


@dataclass
class ChainGap:
    """Разрыв в документальной цепочке."""
    severity: GapSeverity
    description: str
    missing_doc_type: str
    required_by: str = ""           # Какой норматив требует этот документ


@dataclass
class DocumentLink:
    """Одно звено цепочки — документ."""
    node_id: str
    doc_type: str                   # DocType value
    doc_number: str = ""
    doc_date: Optional[str] = None
    confidence: float = 1.0
    status: str = ""                # DocStatus value
    file_path: Optional[str] = None


@dataclass
class MaterialLink:
    """Звено цепочки — материал."""
    node_id: str
    material_name: str
    batch_number: str = ""
    quantity: float = 0.0
    unit: str = ""
    delivery_date: Optional[str] = None
    confidence: float = 1.0
    certificates: List[DocumentLink] = field(default_factory=list)
    passports: List[DocumentLink] = field(default_factory=list)


@dataclass
class DocumentChain:
    """
    Полная документальная цепочка для одного WorkUnit.
    
    Структура:
        WorkUnit ← MaterialBatch ← Certificate/Passport
        WorkUnit → AOSR → KS-2
    """
    work_unit_id: str
    work_type: str
    description: str = ""
    status: ChainStatus = ChainStatus.EMPTY
    confidence: float = 0.0
    
    # Звенья цепочки
    materials: List[MaterialLink] = field(default_factory=list)
    aosr_docs: List[DocumentLink] = field(default_factory=list)
    ks2_docs: List[DocumentLink] = field(default_factory=list)
    executive_schemes: List[DocumentLink] = field(default_factory=list)
    journals: List[DocumentLink] = field(default_factory=list)
    test_protocols: List[DocumentLink] = field(default_factory=list)
    
    # Разрывы
    gaps: List[ChainGap] = field(default_factory=list)
    
    # Даты
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # Цветовая метка (для UI)
    @property
    def color(self) -> str:
        if self.status == ChainStatus.COMPLETE:
            return "green"
        elif self.status == ChainStatus.PARTIAL:
            return "yellow"
        elif self.status == ChainStatus.BROKEN:
            return "red"
        return "gray"


@dataclass
class ChainReport:
    """Сводный отчёт по всем цепочкам."""
    chains: List[DocumentChain] = field(default_factory=list)
    total: int = 0
    complete: int = 0
    partial: int = 0
    broken: int = 0
    empty: int = 0
    critical_gaps: int = 0
    high_gaps: int = 0
    medium_gaps: int = 0
    low_gaps: int = 0
    overall_confidence: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Work Type → Required Documents mapping (from CORE_LOGIC_DESIGN §9)
# ═══════════════════════════════════════════════════════════════════════════

WORK_REQUIREMENTS = {
    "земляные": {
        "aosr": True, "executive_scheme": True, "certificate": False,
        "test_protocol": True, "journal": False,
        "description": "Земляные работы: АОСР + ИГС + протокол испытаний грунта"
    },
    "бетонирование": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": True, "journal": "ЖБР",
        "description": "Бетонные работы: АОСР + ИГС + протокол бетона + ЖБР"
    },
    "армирование": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": False, "journal": False,
        "description": "Армирование: АОСР + ИС + сертификаты на арматуру"
    },
    "сварка": {
        "aosr": True, "executive_scheme": False, "certificate": True,
        "test_protocol": True, "journal": "ЖСР",
        "description": "Сварка: АОСР + акт ВИК + сертификаты + ЖСР"
    },
    "гидроизоляция": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": False, "journal": False,
        "description": "Гидроизоляция: АОСР + ИС + сертификаты"
    },
    "кладка": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": True, "journal": False,
        "description": "Кладка: АОСР + ИС + протокол прочности сцепления"
    },
    "антикор": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": True, "journal": "Журнал антикор. работ",
        "description": "Антикоррозионная защита: АОСР + ИС + протокол + журнал"
    },
    "монтаж": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": False, "journal": "Журнал монтажа МК",
        "description": "Монтаж конструкций: АОСР + ИС + сертификаты + журнал монтажа"
    },
    "default": {
        "aosr": True, "executive_scheme": True, "certificate": True,
        "test_protocol": False, "journal": False,
        "description": "Общие требования: АОСР + ИС + сертификаты"
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Chain Builder
# ═══════════════════════════════════════════════════════════════════════════

class ChainBuilder:
    """
    Строитель документальных цепочек.
    
    Для каждого WorkUnit в Evidence Graph строит цепочку:
    MaterialBatch → Certificate/Passport → AOSR → KS-2
    и проверяет её полноту относительно требований по виду работ.
    """

    def __init__(self):
        self._requirements = WORK_REQUIREMENTS

    def build_chains(self, graph) -> List[DocumentChain]:
        """
        Построить цепочки для всех WorkUnit в графе.
        
        Args:
            graph: EvidenceGraph instance
        
        Returns:
            Список DocumentChain — по одной на каждый WorkUnit
        """
        from src.core.evidence_graph import (
            WorkUnitStatus, DocType, DocStatus, EdgeType
        )
        
        work_units = graph.get_work_units()
        chains = []
        
        for wu in work_units:
            chain = self._build_single_chain(graph, wu)
            chains.append(chain)
        
        # Sort: broken first, then partial, then complete
        chains.sort(key=lambda c: (
            c.status == ChainStatus.BROKEN,
            c.status == ChainStatus.PARTIAL,
            c.status == ChainStatus.EMPTY,
        ), reverse=True)
        
        return chains

    def _build_single_chain(self, graph, wu: dict) -> DocumentChain:
        """Построить цепочку для одного WorkUnit."""
        from src.core.evidence_graph import (
            DocType, DocStatus, EdgeType
        )
        
        wu_id = wu['id']
        work_type = wu.get('work_type', '')
        chain = DocumentChain(
            work_unit_id=wu_id,
            work_type=work_type,
            description=wu.get('description', ''),
            confidence=wu.get('confidence', 1.0),
            start_date=wu.get('start_date'),
            end_date=wu.get('end_date'),
        )
        
        # ── Collect materials ──────────────────────────────────────────
        for pred in graph.graph.predecessors(wu_id):
            pred_data = graph.graph.nodes[pred]
            if pred_data.get('node_type') != 'MaterialBatch':
                continue
            
            edge = graph.graph.edges.get((pred, wu_id), {})
            ml = MaterialLink(
                node_id=pred,
                material_name=pred_data.get('material_name', ''),
                batch_number=pred_data.get('batch_number', ''),
                quantity=pred_data.get('quantity', 0),
                unit=pred_data.get('unit', ''),
                delivery_date=pred_data.get('delivery_date'),
                confidence=pred_data.get('confidence', 1.0),
            )
            
            # Find certificates for this material
            cert_id = pred_data.get('certificate_id')
            if cert_id and graph.graph.has_node(cert_id):
                cert_data = graph.graph.nodes[cert_id]
                ml.certificates.append(DocumentLink(
                    node_id=cert_id,
                    doc_type=cert_data.get('doc_type', 'certificate'),
                    doc_number=cert_data.get('doc_number', ''),
                    doc_date=cert_data.get('doc_date'),
                    confidence=cert_data.get('confidence', 1.0),
                    status=cert_data.get('status', ''),
                ))
            
            chain.materials.append(ml)
        
        # ── Collect confirming documents ───────────────────────────────
        for succ in graph.graph.successors(wu_id):
            succ_data = graph.graph.nodes[succ]
            edge = graph.graph.edges.get((wu_id, succ), {})
            etype = edge.get('edge_type', '')
            
            if etype != EdgeType.CONFIRMED_BY.value:
                continue
            
            doc_type = succ_data.get('doc_type', '')
            dl = DocumentLink(
                node_id=succ,
                doc_type=doc_type,
                doc_number=succ_data.get('doc_number', ''),
                doc_date=succ_data.get('doc_date'),
                confidence=succ_data.get('confidence', 1.0),
                status=succ_data.get('status', ''),
                file_path=succ_data.get('file_path'),
            )
            
            if doc_type == DocType.AOSR.value:
                chain.aosr_docs.append(dl)
            elif doc_type == DocType.KS2.value:
                chain.ks2_docs.append(dl)
            elif doc_type == DocType.EXECUTIVE_SCHEME.value:
                chain.executive_schemes.append(dl)
            elif doc_type == DocType.JOURNAL.value:
                chain.journals.append(dl)
            elif doc_type == DocType.PROTOCOL.value:
                chain.test_protocols.append(dl)
        
        # ── Analyse gaps ───────────────────────────────────────────────
        chain.gaps = self._find_gaps(chain)
        chain.status = self._compute_status(chain)
        
        # ── Compute overall confidence ─────────────────────────────────
        confidences = [chain.confidence]
        for m in chain.materials:
            confidences.append(m.confidence)
            for c in m.certificates:
                confidences.append(c.confidence)
        for d in chain.aosr_docs + chain.ks2_docs:
            confidences.append(d.confidence)
        chain.confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return chain

    def _get_work_requirements(self, work_type: str) -> dict:
        """Определить требования к документальному шлейфу по виду работ."""
        wt_lower = work_type.lower()
        for key, req in self._requirements.items():
            if key in wt_lower:
                return req
        return self._requirements['default']

    def _find_gaps(self, chain: DocumentChain) -> List[ChainGap]:
        """Найти разрывы в документальной цепочке."""
        gaps = []
        req = self._get_work_requirements(chain.work_type)
        
        # 1. Проверка АОСР — самый критичный документ
        if req.get('aosr') and not chain.aosr_docs:
            gaps.append(ChainGap(
                severity=GapSeverity.CRITICAL,
                description=f"АОСР отсутствует для {chain.work_type}",
                missing_doc_type="aosr",
                required_by="Приказ 344/пр, прил. 3"
            ))
        elif chain.aosr_docs:
            # Проверка подписей
            for a in chain.aosr_docs:
                if a.confidence < 0.8:
                    gaps.append(ChainGap(
                        severity=GapSeverity.HIGH,
                        description=f"АОСР {a.doc_number}: низкая уверенность ({a.confidence:.2f})",
                        missing_doc_type="aosr_signatures",
                    ))
        
        # 2. Сертификаты на материалы
        if req.get('certificate') and chain.materials:
            for m in chain.materials:
                if not m.certificates:
                    gaps.append(ChainGap(
                        severity=GapSeverity.HIGH,
                        description=f"Нет сертификата на {m.material_name} (партия {m.batch_number})",
                        missing_doc_type="certificate",
                        required_by="СП 543.1325800.2024"
                    ))
        
        # 3. КС-2 — финансовый документ
        if not chain.ks2_docs and chain.aosr_docs:
            gaps.append(ChainGap(
                severity=GapSeverity.MEDIUM,
                description=f"КС-2 отсутствует при наличии АОСР ({chain.work_type})",
                missing_doc_type="ks2",
                required_by="Договор подряда"
            ))
        
        # 4. Исполнительная схема
        if req.get('executive_scheme') and not chain.executive_schemes:
            gaps.append(ChainGap(
                severity=GapSeverity.MEDIUM,
                description=f"Исполнительная схема отсутствует ({chain.work_type})",
                missing_doc_type="executive_scheme",
                required_by="ГОСТ Р 51872-2024"
            ))
        
        # 5. Протокол испытаний
        if req.get('test_protocol') and not chain.test_protocols:
            gaps.append(ChainGap(
                severity=GapSeverity.MEDIUM,
                description=f"Протокол испытаний отсутствует ({chain.work_type})",
                missing_doc_type="test_protocol",
                required_by="СП 70.13330.2012"
            ))
        
        # 6. Спецжурнал
        req_journal = req.get('journal')
        if req_journal and not chain.journals:
            gaps.append(ChainGap(
                severity=GapSeverity.LOW,
                description=f"Спецжурнал отсутствует ({req_journal})",
                missing_doc_type="journal",
                required_by="СП 70.13330.2012"
            ))
        
        return gaps

    def _compute_status(self, chain: DocumentChain) -> ChainStatus:
        """Вычислить статус цепочки по разрывам."""
        if not chain.aosr_docs and not chain.materials and not chain.ks2_docs:
            return ChainStatus.EMPTY
        
        severities = [g.severity for g in chain.gaps]
        
        if GapSeverity.CRITICAL in severities:
            return ChainStatus.BROKEN
        elif GapSeverity.HIGH in severities:
            return ChainStatus.PARTIAL
        elif GapSeverity.MEDIUM in severities or GapSeverity.LOW in severities:
            return ChainStatus.PARTIAL
        else:
            return ChainStatus.COMPLETE

    def generate_report(self, chains: List[DocumentChain]) -> ChainReport:
        """Сгенерировать сводный отчёт."""
        report = ChainReport(chains=chains, total=len(chains))
        
        for chain in chains:
            if chain.status == ChainStatus.COMPLETE:
                report.complete += 1
            elif chain.status == ChainStatus.PARTIAL:
                report.partial += 1
            elif chain.status == ChainStatus.BROKEN:
                report.broken += 1
            else:
                report.empty += 1
            
            for gap in chain.gaps:
                if gap.severity == GapSeverity.CRITICAL:
                    report.critical_gaps += 1
                elif gap.severity == GapSeverity.HIGH:
                    report.high_gaps += 1
                elif gap.severity == GapSeverity.MEDIUM:
                    report.medium_gaps += 1
                elif gap.severity == GapSeverity.LOW:
                    report.low_gaps += 1
        
        if chains:
            report.overall_confidence = sum(c.confidence for c in chains) / len(chains)
        
        return report

    def format_report(self, report: ChainReport) -> str:
        """Форматировать отчёт для вывода."""
        lines = [
            f"═══ ОТЧЁТ ЦЕПОЧЕК ДОКУМЕНТОВ ═══",
            f"Всего WorkUnit: {report.total}",
            f"  ✅ COMPLETE:  {report.complete}",
            f"  ⚠️  PARTIAL:   {report.partial}",
            f"  ❌ BROKEN:    {report.broken}",
            f"  ⬜ EMPTY:     {report.empty}",
            f"",
            f"Разрывы:",
            f"  🔴 CRITICAL: {report.critical_gaps}",
            f"  🟠 HIGH:     {report.high_gaps}",
            f"  🟡 MEDIUM:   {report.medium_gaps}",
            f"  ⚪ LOW:      {report.low_gaps}",
            f"",
            f"Общая уверенность: {report.overall_confidence:.2f}",
        ]
        
        # Детализация BROKEN цепочек
        broken = [c for c in report.chains if c.status == ChainStatus.BROKEN]
        if broken:
            lines.append(f"\nКРИТИЧЕСКИЕ ЦЕПОЧКИ ({len(broken)}):")
            for c in broken[:10]:
                lines.append(f"  [{c.work_type}] {c.description[:60]}")
                for g in c.gaps[:3]:
                    lines.append(f"    {g.severity.value}: {g.description}")
        
        return "\n".join(lines)


# Модульный синглтон
chain_builder = ChainBuilder()
