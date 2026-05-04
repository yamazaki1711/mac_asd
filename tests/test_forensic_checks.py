"""
Tests for Forensic Checks in EvidenceGraph v2.

Covers: batch_coverage, orphan_certificates, certificate_reuse, run_all.
"""

from datetime import date

import pytest

from src.core.evidence_graph import EvidenceGraph, WorkUnitStatus, DocType, EdgeType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def g():
    return EvidenceGraph()


@pytest.fixture
def graph_with_overuse(g):
    """Certificate batch=55, but used=60 in AOSR → coverage violation."""
    g.add_document(
        doc_type=DocType.CERTIFICATE, doc_number="№21514",
        doc_date=date(2026, 3, 25), confidence=0.95,
        node_id="CERT_001",
    )
    g.add_material_batch(
        material_name="Шпунт Л5-УМ", batch_number="21514",
        quantity=55.0, unit="шт",
        certificate_id="CERT_001",
        node_id="MAT_001",
    )
    g.add_work_unit(
        work_type="погружение_шпунта",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
        node_id="WU_001",
    )
    # Using 60 units — exceeds batch of 55
    g.link("MAT_001", "WU_001", EdgeType.USED_IN, quantity=60.0)
    return g


@pytest.fixture
def graph_with_orphan_cert(g):
    """Certificate that is not linked to any work unit."""
    g.add_document(
        doc_type=DocType.CERTIFICATE, doc_number="ORPH-99",
        node_id="CERT_ORPHAN",
    )
    return g


@pytest.fixture
def graph_with_reuse(g):
    """One material batch used in 2 different WorkUnits."""
    g.add_document(
        doc_type=DocType.CERTIFICATE, doc_number="CERT-R1",
        node_id="CERT_R1",
    )
    g.add_material_batch(
        material_name="Арматура А500С", batch_number="B42",
        quantity=200.0, unit="тн",
        certificate_id="CERT_R1",
        node_id="MAT_R1",
    )
    g.add_work_unit(
        work_type="армирование", node_id="WU_A",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
    )
    g.add_work_unit(
        work_type="армирование", node_id="WU_B",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
    )
    g.link("MAT_R1", "WU_A", EdgeType.USED_IN, quantity=100.0)
    g.link("MAT_R1", "WU_B", EdgeType.USED_IN, quantity=100.0)
    return g


# =============================================================================
# Batch Coverage
# =============================================================================

class TestBatchCoverage:
    """Tests for check_batch_coverage()."""

    def test_overuse_detected(self, graph_with_overuse):
        """Usage (60) > batch (55) should trigger critical finding."""
        findings = graph_with_overuse.check_batch_coverage()
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        assert findings[0]["excess"] == 5.0
        assert "Шпунт" in findings[0]["material"]

    def test_no_overuse_no_finding(self, g):
        """Usage ≤ batch should produce no findings."""
        g.add_material_batch(
            material_name="Steel", quantity=100.0,
            node_id="MAT_OK",
        )
        g.add_work_unit(work_type="test", node_id="WU_OK")
        g.link("MAT_OK", "WU_OK", EdgeType.USED_IN, quantity=50.0)
        findings = g.check_batch_coverage()
        assert len(findings) == 0

    def test_empty_graph_no_findings(self, g):
        """Empty graph should produce no findings."""
        findings = g.check_batch_coverage()
        assert len(findings) == 0

    def test_zero_quantity_skipped(self, g):
        """MaterialBatch with quantity=0 should be skipped."""
        g.add_material_batch(
            material_name="Unknown", quantity=0.0,
            node_id="MAT_ZERO",
        )
        g.add_work_unit(work_type="test", node_id="WU_Z")
        g.link("MAT_ZERO", "WU_Z", EdgeType.USED_IN, quantity=999.0)
        findings = g.check_batch_coverage()
        assert len(findings) == 0


# =============================================================================
# Orphan Certificates
# =============================================================================

class TestOrphanCertificates:
    """Tests for check_orphan_certificates()."""

    def test_orphan_detected(self, graph_with_orphan_cert):
        """Unlinked certificate should be flagged."""
        orphans = graph_with_orphan_cert.check_orphan_certificates()
        assert len(orphans) == 1
        assert orphans[0]["severity"] == "medium"
        assert orphans[0]["document_id"] == "CERT_ORPHAN"

    def test_linked_certificate_not_orphan(self, g):
        """Certificate linked via certificate_id creates edge — NOT orphan."""
        g.add_document(doc_type=DocType.CERTIFICATE, node_id="CERT_LINKED")
        g.add_material_batch(
            material_name="Steel", certificate_id="CERT_LINKED",
            node_id="MAT_LINKED",
        )
        # add_material_batch creates edge MAT → CERT via REFERENCES
        orphans = g.check_orphan_certificates()
        cert_orphan = [o for o in orphans if o["document_id"] == "CERT_LINKED"]
        assert len(cert_orphan) == 0, "Linked certificate should NOT be orphan"

    def test_non_cert_documents_ignored(self, g):
        """AOSR documents should not be flagged as orphan certs."""
        g.add_document(doc_type=DocType.AOSR, node_id="AOSR_1")
        orphans = g.check_orphan_certificates()
        aosr_orphans = [o for o in orphans if o["document_id"] == "AOSR_1"]
        assert len(aosr_orphans) == 0


# =============================================================================
# Certificate Reuse
# =============================================================================

class TestCertificateReuse:
    """Tests for check_certificate_reuse()."""

    def test_reuse_detected(self, graph_with_reuse):
        """Material used in 2+ WorkUnits should trigger reuse finding."""
        findings = graph_with_reuse.check_certificate_reuse()
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert findings[0]["work_units_count"] == 2

    def test_single_use_no_finding(self, g):
        """Material used in only 1 WorkUnit — no reuse finding."""
        g.add_material_batch(
            material_name="Steel", quantity=100.0,
            node_id="MAT_SINGLE",
        )
        g.add_work_unit(work_type="test", node_id="WU_SINGLE")
        g.link("MAT_SINGLE", "WU_SINGLE", EdgeType.USED_IN, quantity=50.0)
        findings = g.check_certificate_reuse()
        assert len(findings) == 0

    def test_unused_material_no_finding(self, g):
        """Material with no WorkUnit links — no reuse finding."""
        g.add_material_batch(
            material_name="Orphan Steel", quantity=100.0,
            node_id="MAT_ORPHAN",
        )
        findings = g.check_certificate_reuse()
        assert len(findings) == 0


# =============================================================================
# run_all_forensic_checks
# =============================================================================

class TestRunAllForensicChecks:
    """Tests for run_all_forensic_checks()."""

    def test_returns_all_sections(self, g):
        """Should return batch_coverage, orphan_certificates, certificate_reuse sections."""
        result = g.run_all_forensic_checks()
        assert "batch_coverage" in result
        assert "orphan_certificates" in result
        assert "certificate_reuse" in result
        assert "summary" in result
        assert "total_findings" in result["summary"]

    def test_empty_graph_zero_findings(self, g):
        """Empty graph should have zero total findings."""
        result = g.run_all_forensic_checks()
        assert result["summary"]["total_findings"] == 0

    def test_overuse_surface_in_summary(self, graph_with_overuse):
        """batch_coverage CRITICAL should be counted in summary."""
        result = graph_with_overuse.run_all_forensic_checks()
        assert result["summary"]["critical"] >= 1

    def test_reuse_surface_in_summary(self, graph_with_reuse):
        """certificate_reuse HIGH should be counted in summary."""
        result = graph_with_reuse.run_all_forensic_checks()
        assert result["summary"]["high"] >= 1
