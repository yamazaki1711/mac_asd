"""
Tests for Evidence Graph v2 — node/edge creation, chain queries, summary.

Covers EvidenceGraph and ChainBuilder integration.
"""

from datetime import date

import pytest

from src.core.evidence_graph import (
    EvidenceGraph,
    WorkUnitStatus,
    FactSource,
    DocType,
    EdgeType,
    PersonRole,
    EvidenceDocStatus,
)
from src.core.chain_builder import (
    ChainBuilder,
    ChainStatus,
    GapSeverity,
    ChainReport,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def empty_graph():
    """Fresh empty graph for isolated tests."""
    g = EvidenceGraph()
    g.clear()
    return g


@pytest.fixture
def populated_graph():
    """Graph with a realistic document chain: Material -> Certificate -> AOSR -> KS-2."""
    g = EvidenceGraph()
    g.clear()

    # Certificate (must be created first so we can reference it)
    g.add_document(
        doc_type=DocType.CERTIFICATE,
        doc_number="№21514", doc_date=date(2026, 3, 25),
        confidence=0.95, signatures_present=True,
        node_id="DOC_CERT_001",
    )

    # Passport
    g.add_document(
        doc_type=DocType.PASSPORT,
        doc_number="ПС-21514", doc_date=date(2026, 3, 25),
        confidence=0.95,
        node_id="DOC_PASS_001",
    )

    # AOSR
    g.add_document(
        doc_type=DocType.AOSR,
        doc_number="АОСР-15", doc_date=date(2026, 4, 10),
        confidence=1.0, signatures_present=True,
        node_id="DOC_AOSR_001",
    )

    # KS-2
    g.add_document(
        doc_type=DocType.KS2,
        doc_number="КС-2-7", doc_date=date(2026, 4, 12),
        confidence=1.0,
        node_id="DOC_KS2_001",
    )

    # WorkUnit
    g.add_work_unit(
        work_type="погружение_шпунта",
        description="Погружение шпунта Л5-УМ на причале №9",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
        planned_start=date(2026, 4, 1), planned_end=date(2026, 4, 10),
        node_id="WU_001",
    )

    # MaterialBatch with certificate_id ref (so ChainBuilder finds the cert)
    g.add_material_batch(
        material_name="Шпунт Л5-УМ",
        batch_number="21514", quantity=55.0, unit="шт",
        delivery_date=date(2026, 3, 28), confidence=0.98,
        certificate_id="DOC_CERT_001",
        node_id="MAT_001",
    )

    # Links: MAT → WU (material used in work unit)
    g.link("MAT_001", "WU_001", EdgeType.USED_IN, quantity=55.0)
    # Links: WU → AOSR (work unit confirmed by AOSR)
    g.link("WU_001", "DOC_AOSR_001", EdgeType.CONFIRMED_BY)
    # Links: WU → KS-2
    g.link("WU_001", "DOC_KS2_001", EdgeType.CONFIRMED_BY)

    return g


# =============================================================================
# EvidenceGraph — Node Creation
# =============================================================================

class TestEvidenceGraphNodes:
    """Tests for node creation in EvidenceGraph."""

    def test_add_work_unit(self, empty_graph):
        """Should create a WorkUnit node with correct metadata."""
        nid = empty_graph.add_work_unit(
            work_type="бетонирование",
            status=WorkUnitStatus.COMPLETED, confidence=1.0,
            node_id="WU_001",
        )
        assert nid == "WU_001"
        assert "WU_001" in empty_graph.graph
        node_data = empty_graph.graph.nodes["WU_001"]
        assert node_data["node_type"] == "WorkUnit"
        assert node_data["work_type"] == "бетонирование"
        assert node_data["confidence"] == 1.0

    def test_add_material_batch(self, empty_graph):
        """Should create a MaterialBatch node."""
        nid = empty_graph.add_material_batch(
            material_name="Бетон B25",
            batch_number="42", quantity=100.0, unit="м³",
            node_id="MAT_001",
        )
        assert nid == "MAT_001"
        node_data = empty_graph.graph.nodes["MAT_001"]
        assert node_data["node_type"] == "MaterialBatch"
        assert node_data["material_name"] == "Бетон B25"
        assert node_data["quantity"] == 100.0

    def test_add_document(self, empty_graph):
        """Should create a Document node."""
        nid = empty_graph.add_document(
            doc_type=DocType.AOSR,
            doc_number="АОСР-15", confidence=0.95,
            node_id="DOC_001",
        )
        assert nid == "DOC_001"
        node_data = empty_graph.graph.nodes["DOC_001"]
        assert node_data["node_type"] == "Document"
        assert node_data["doc_type"] == DocType.AOSR
        assert node_data["confidence"] == 0.95

    def test_add_person(self, empty_graph):
        """Should create a Person node."""
        nid = empty_graph.add_person(
            name="Иванов И.И.",
            role=PersonRole.PTO_ENGINEER,
            node_id="PERS_001",
        )
        assert nid == "PERS_001"
        node_data = empty_graph.graph.nodes["PERS_001"]
        assert node_data["node_type"] == "Person"
        assert node_data["role"] == PersonRole.PTO_ENGINEER
        assert node_data["name"] == "Иванов И.И."

    def test_add_date_event(self, empty_graph):
        """Should create a DateEvent node."""
        from datetime import datetime
        from src.core.evidence_graph import EventType

        nid = empty_graph.add_date_event(
            event_type=EventType.DELIVERY,
            timestamp=datetime(2026, 4, 1),
            confidence=0.9,
            node_id="EVT_001",
        )
        assert nid == "EVT_001"
        node_data = empty_graph.graph.nodes["EVT_001"]
        assert node_data["node_type"] == "DateEvent"
        assert node_data["event_type"] == "delivery"

    def test_add_location(self, empty_graph):
        """Should create a Location node."""
        nid = empty_graph.add_location(
            name="Причал №9, захватка 1",
            description="Захватка 1 причала №9",
            node_id="LOC_001",
        )
        assert nid == "LOC_001"
        node_data = empty_graph.graph.nodes["LOC_001"]
        assert node_data["node_type"] == "Location"
        assert "Причал" in node_data["name"]


# =============================================================================
# EvidenceGraph — Edges
# =============================================================================

class TestEvidenceGraphEdges:
    """Tests for edge creation and management."""

    def test_link_nodes(self, empty_graph):
        """Should create an edge between two nodes."""
        empty_graph.add_work_unit(work_type="test", node_id="WU_001")
        empty_graph.add_document(doc_type=DocType.AOSR, node_id="DOC_001")
        empty_graph.link("DOC_001", "WU_001", EdgeType.CONFIRMED_BY)

        assert empty_graph.graph.has_edge("DOC_001", "WU_001")
        edge_data = empty_graph.graph.edges["DOC_001", "WU_001"]
        assert edge_data["edge_type"] == EdgeType.CONFIRMED_BY.value

    def test_link_with_quantity(self, empty_graph):
        """Should store quantity on USED_IN edges."""
        empty_graph.add_work_unit(work_type="test", node_id="WU_001")
        empty_graph.add_material_batch(material_name="Steel", node_id="MAT_001")
        empty_graph.link("MAT_001", "WU_001", EdgeType.USED_IN, quantity=55.0)

        edge_data = empty_graph.graph.edges["MAT_001", "WU_001"]
        assert edge_data["quantity"] == 55.0

    def test_link_nonexistent_node(self, empty_graph):
        """Linking nonexistent nodes should silently return."""
        result = empty_graph.link("FAKE_A", "FAKE_B", EdgeType.CONFIRMED_BY)
        # link() returns None implicitly
        assert result is None

    def test_has_document_for_material(self, populated_graph):
        """Certificate should be referenced by MaterialBatch via certificate_id field."""
        mat_data = populated_graph.graph.nodes["MAT_001"]
        assert mat_data.get("certificate_id") == "DOC_CERT_001"


# =============================================================================
# EvidenceGraph — Query Methods
# =============================================================================

class TestEvidenceGraphQueries:
    """Tests for querying the evidence graph."""

    def test_get_work_units(self, populated_graph):
        """Should return all WorkUnit nodes."""
        wus = populated_graph.get_work_units()
        assert len(wus) == 1
        assert wus[0]["id"] == "WU_001"

    def test_get_work_unit_chain(self, populated_graph):
        """Should return full chain for a WorkUnit."""
        chain = populated_graph.get_work_unit_chain("WU_001")
        assert len(chain["materials"]) >= 1
        assert len(chain["documents"]) >= 2  # AOSR + KS-2

    def test_get_orphan_documents(self):
        """Should find REFERENCED documents (mentioned but no file)."""
        g = EvidenceGraph()
        g.clear()
        g.add_document(
            doc_type=DocType.CERTIFICATE, node_id="DOC_REF",
            status=EvidenceDocStatus.REFERENCED,
        )
        orphans = g.get_orphan_documents()
        assert any(n["id"] == "DOC_REF" for n in orphans)

    def test_get_low_confidence_nodes(self, empty_graph):
        """Should find nodes with confidence below threshold."""
        empty_graph.add_work_unit(
            work_type="test", confidence=0.3, node_id="WU_LOW",
        )
        low = empty_graph.get_low_confidence_nodes(0.5)
        assert len(low) >= 1
        assert any(n["id"] == "WU_LOW" for n in low)

    def test_summary(self, populated_graph):
        """Summary should return counts by type."""
        summary = populated_graph.summary()
        assert summary["total_nodes"] >= 5
        assert "WorkUnit" in summary.get("node_types", {})
        assert "Document" in summary.get("node_types", {})
        assert summary["node_types"]["WorkUnit"] == 1


# =============================================================================
# ChainBuilder — Document Chains
# =============================================================================

class TestChainBuilder:
    """Tests for building and validating document chains."""

    @pytest.fixture
    def builder(self):
        return ChainBuilder()

    def test_build_chains(self, builder, populated_graph):
        """Should build a chain for each WorkUnit."""
        chains = builder.build_chains(populated_graph)
        assert len(chains) >= 1

    def test_chain_has_materials(self, builder, populated_graph):
        """Chain should include materials linked to WorkUnit."""
        chains = builder.build_chains(populated_graph)
        wu_chain = next(c for c in chains if c.work_unit_id == "WU_001")
        assert len(wu_chain.materials) >= 1
        assert wu_chain.materials[0].material_name == "Шпунт Л5-УМ"

    def test_chain_has_aosr(self, builder, populated_graph):
        """Chain should include AOSR documents."""
        chains = builder.build_chains(populated_graph)
        wu_chain = next(c for c in chains if c.work_unit_id == "WU_001")
        aosr_types = [d.doc_type for d in wu_chain.aosr_docs]
        assert "aosr" in aosr_types

    def test_chain_has_ks2(self, builder, populated_graph):
        """Chain should include KS-2 documents."""
        chains = builder.build_chains(populated_graph)
        wu_chain = next(c for c in chains if c.work_unit_id == "WU_001")
        ks2_types = [d.doc_type for d in wu_chain.ks2_docs]
        assert "ks2" in ks2_types

    def test_complete_chain_status(self, builder, populated_graph):
        """Fully linked chain should be PARTIAL (needs exec_scheme and journal to be COMPLETE)."""
        chains = builder.build_chains(populated_graph)
        wu_chain = next(c for c in chains if c.work_unit_id == "WU_001")
        # With AOSR + KS-2 + Certificate but no exec_scheme → PARTIAL
        assert wu_chain.status in (ChainStatus.PARTIAL, ChainStatus.COMPLETE)
        assert wu_chain.color in ("yellow", "green")

    def test_empty_chain_no_materials(self, builder):
        """WorkUnit without any documents should be EMPTY."""
        g = EvidenceGraph()
        g.clear()
        g.add_work_unit(
            work_type="бетонирование",
            status=WorkUnitStatus.IN_PROGRESS, confidence=0.5,
            node_id="WU_BARE",
        )
        chains = builder.build_chains(g)
        wu_chain = next(c for c in chains if c.work_unit_id == "WU_BARE")
        assert wu_chain.status == ChainStatus.EMPTY
        assert wu_chain.color == "gray"
        assert any(g.severity == GapSeverity.CRITICAL for g in wu_chain.gaps)

    def test_empty_graph_no_chains(self, builder, empty_graph):
        """Empty graph should produce no chains."""
        chains = builder.build_chains(empty_graph)
        assert len(chains) == 0


# =============================================================================
# ChainBuilder — Reports
# =============================================================================

class TestChainReport:
    """Tests for chain reports."""

    @pytest.fixture
    def builder(self):
        return ChainBuilder()

    def test_generate_report(self, builder, populated_graph):
        """Should generate a valid report."""
        chains = builder.build_chains(populated_graph)
        report = builder.generate_report(chains)
        assert isinstance(report, ChainReport)
        assert report.total >= 1
        assert report.broken == 0  # No critical gaps if AOSR is present

    def test_format_report(self, builder, populated_graph):
        """Should format a human-readable report string."""
        chains = builder.build_chains(populated_graph)
        report = builder.generate_report(chains)
        formatted = builder.format_report(report)
        assert "COMPLETE" in formatted

    def test_report_with_empty_chain(self, builder):
        """Report should count empty chains."""
        g = EvidenceGraph()
        g.clear()
        g.add_work_unit(
            work_type="бетонирование",
            status=WorkUnitStatus.IN_PROGRESS, confidence=0.5,
            node_id="WU_EMPTY",
        )
        chains = builder.build_chains(g)
        report = builder.generate_report(chains)
        assert report.empty >= 1
        assert report.critical_gaps >= 1

    def test_gap_types(self, builder):
        """Broken chain should have CRITICAL gap."""
        g = EvidenceGraph()
        g.clear()
        g.add_work_unit(
            work_type="бетонирование",
            status=WorkUnitStatus.PLANNED, confidence=0.8,
            node_id="WU_TEST",
        )
        chains = builder.build_chains(g)
        chain = chains[0]
        severities = {g.severity for g in chain.gaps}
        assert GapSeverity.CRITICAL in severities  # No AOSR = critical
