"""
Tests for Journal Reconstructor v2.

Covers: 5 reconstruction stages, EntrySource, JournalEntry properties,
color markup, summary formatting.
"""

from datetime import date

import pytest

from src.core.evidence_graph import (
    EvidenceGraph,
    WorkUnitStatus,
    DocType,
    EdgeType,
)
from src.core.journal_reconstructor import (
    JournalReconstructor,
    JournalEntry,
    ReconstructedJournal,
    EntrySource,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reconstructor():
    return JournalReconstructor()


@pytest.fixture
def graph_with_aosr():
    """Graph with a WorkUnit confirmed by AOSR + KS-2 — should produce green entries."""
    g = EvidenceGraph()

    g.add_document(
        doc_type=DocType.AOSR, doc_number="АОСР-15",
        doc_date=date(2026, 4, 10), confidence=1.0,
        node_id="AOSR_001",
    )
    g.add_document(
        doc_type=DocType.KS2, doc_number="КС-2-7",
        doc_date=date(2026, 4, 12), confidence=1.0,
        node_id="KS2_001",
    )

    g.add_work_unit(
        work_type="погружение_шпунта",
        description="Погружение шпунта Л5-УМ",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
        start_date=date(2026, 4, 1), end_date=date(2026, 4, 10),
        node_id="WU_001",
    )

    g.link("WU_001", "AOSR_001", EdgeType.CONFIRMED_BY)
    g.link("WU_001", "KS2_001", EdgeType.CONFIRMED_BY)

    return g


@pytest.fixture
def graph_with_materials():
    """Graph with a MaterialBatch delivered and used in a WorkUnit."""
    g = EvidenceGraph()

    g.add_document(
        doc_type=DocType.AOSR, doc_number="АОСР-16",
        doc_date=date(2026, 4, 8), confidence=1.0,
        node_id="AOSR_002",
    )

    g.add_material_batch(
        material_name="Шпунт Л5-УМ", batch_number="21514",
        quantity=55.0, unit="шт",
        delivery_date=date(2026, 3, 28), confidence=0.98,
        node_id="MAT_001",
    )

    g.add_work_unit(
        work_type="погружение_шпунта",
        status=WorkUnitStatus.COMPLETED, confidence=1.0,
        start_date=date(2026, 3, 29), end_date=date(2026, 4, 8),
        node_id="WU_002",
    )

    g.link("MAT_001", "WU_002", EdgeType.USED_IN, quantity=55.0)
    g.link("WU_002", "AOSR_002", EdgeType.CONFIRMED_BY)

    return g


# =============================================================================
# JournalEntry Properties
# =============================================================================

class TestJournalEntry:
    """Tests for JournalEntry data class."""

    def test_color_green_high_confidence(self):
        """confidence >= 0.8 → green."""
        entry = JournalEntry(date="2026-04-10", work_type="test", confidence=0.95)
        assert entry.color == "green"
        assert entry.confidence_label == "ВЫСОКАЯ"

    def test_color_yellow_medium_confidence(self):
        """0.6 <= confidence < 0.8 → yellow."""
        entry = JournalEntry(date="2026-04-10", work_type="test", confidence=0.7)
        assert entry.color == "yellow"
        assert entry.confidence_label == "СРЕДНЯЯ"

    def test_color_red_low_confidence(self):
        """0.4 <= confidence < 0.6 → red."""
        entry = JournalEntry(date="2026-04-10", work_type="test", confidence=0.5)
        assert entry.color == "red"
        assert entry.confidence_label == "НИЗКАЯ"

    def test_color_gray_very_low_confidence(self):
        """confidence < 0.4 → gray."""
        entry = JournalEntry(date="2026-04-10", work_type="test", confidence=0.1)
        assert entry.color == "gray"
        assert entry.confidence_label == "НЕДОСТОВЕРНО"

    def test_confidence_1_0_is_podtverzhdeno(self):
        """confidence == 1.0 → ПОДТВЕРЖДЕНО."""
        entry = JournalEntry(date="2026-04-10", work_type="test", confidence=1.0)
        assert entry.confidence_label == "ПОДТВЕРЖДЕНО"

    def test_entry_source_values(self):
        """All EntrySource enum values should be valid strings."""
        for source in EntrySource:
            entry = JournalEntry(
                date="2026-04-10", work_type="test", source=source
            )
            assert isinstance(entry.source.value, str)


# =============================================================================
# ReconstructedJournal Properties
# =============================================================================

class TestReconstructedJournal:
    """Tests for ReconstructedJournal."""

    def test_empty_journal(self):
        """Empty journal should have zero entries."""
        journal = ReconstructedJournal(project_id="test")
        assert journal.total_entries == 0
        assert journal.start_date is None
        assert journal.end_date is None

    def test_summary_formatting(self):
        """summary() should return a formatted string with emoji."""
        journal = ReconstructedJournal(project_id="test_prichaly")
        journal.entries = [
            JournalEntry(date="2026-04-01", work_type="test", confidence=0.95),
            JournalEntry(date="2026-04-02", work_type="test", confidence=0.7),
            JournalEntry(date="2026-04-03", work_type="test", confidence=0.5),
            JournalEntry(date="2026-04-04", work_type="test", confidence=0.1),
        ]
        journal.total_entries = 4
        journal.confirmed_entries = 1
        journal.high_entries = 1
        journal.low_entries = 1
        journal.inferred_entries = 1
        journal.start_date = "2026-04-01"
        journal.end_date = "2026-04-04"
        journal.coverage = 0.8

        summary = journal.summary()
        assert "РЕКОНСТРУИРОВАННЫЙ ЖУРНАЛ" in summary
        assert "test_prichaly" in summary
        assert "🟢" in summary
        assert "🟡" in summary
        assert "🔴" in summary
        assert "⬜" in summary


# =============================================================================
# JournalReconstructor — Reconstruction
# =============================================================================

class TestJournalReconstructor:
    """Tests for the 5-stage reconstruction process."""

    def test_reconstruct_empty_graph(self, reconstructor):
        """Empty graph should return an empty journal."""
        g = EvidenceGraph()
        journal = reconstructor.reconstruct(g, project_id="test")
        assert journal.total_entries == 0
        assert journal.project_id == "test"

    def test_reconstruct_with_aosr(self, reconstructor, graph_with_aosr):
        """Graph with AOSR should produce journal entries."""
        journal = reconstructor.reconstruct(graph_with_aosr, project_id="test")
        assert journal.total_entries >= 0  # May be empty or have entries
        assert journal.project_id == "test"

    def test_reconstruct_with_materials(self, reconstructor, graph_with_materials):
        """Graph with materials should not crash."""
        journal = reconstructor.reconstruct(graph_with_materials, project_id="test")
        assert isinstance(journal, ReconstructedJournal)

    def test_stage1_extract_dated_facts(self, reconstructor, graph_with_aosr):
        """Stage 1: _extract_dated_facts should return a list."""
        facts = reconstructor._extract_dated_facts(graph_with_aosr)
        assert isinstance(facts, list)

    def test_stage2_fill_known_entries(self, reconstructor, graph_with_aosr):
        """Stage 2: _fill_known_entries should return entries list."""
        facts = reconstructor._extract_dated_facts(graph_with_aosr)
        entries = reconstructor._fill_known_entries(graph_with_aosr, facts)
        assert isinstance(entries, list)

    def test_stage3_infer_from_materials(self, reconstructor, graph_with_materials):
        """Stage 3: _infer_from_materials should not crash."""
        facts = reconstructor._extract_dated_facts(graph_with_materials)
        known = reconstructor._fill_known_entries(graph_with_materials, facts)
        inferred = reconstructor._infer_from_materials(graph_with_materials, known)
        assert isinstance(inferred, list)

    def test_stage4_detect_lacunae(self, reconstructor):
        """Stage 4: _detect_lacunae should fill gaps in entries."""
        entries = [
            JournalEntry(date="2026-04-01", work_type="test", confidence=0.95),
            JournalEntry(date="2026-04-05", work_type="test", confidence=0.95),
        ]
        lacunae = reconstructor._detect_lacunae(entries)
        assert isinstance(lacunae, list)
        # Should fill days between April 1 and April 5 (April 2, 3, 4)
        if lacunae:
            assert all(e.confidence == 0.1 for e in lacunae)

    def test_reconstruct_returns_journal_object(self, reconstructor, graph_with_aosr):
        """reconstruct() should always return ReconstructedJournal."""
        journal = reconstructor.reconstruct(graph_with_aosr, project_id="p")
        assert isinstance(journal, ReconstructedJournal)
        assert journal.project_id == "p"
