"""
Tests for IDRequirementsRegistry — 344/пр compliance matrix.

Covers: work type loading, required documents, delta calculation, singleton.
"""

import pytest

from src.core.services.id_requirements import (
    IDRequirementsRegistry,
    id_requirements,
    DEFAULT_CONFIG_PATH,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def registry():
    """Fresh registry instance from default config."""
    return IDRequirementsRegistry()


# =============================================================================
# Work Types
# =============================================================================

class TestWorkTypes:
    """Tests for work type definitions."""

    def test_loads_33_work_types(self, registry):
        """Should load all 33 work types from YAML config."""
        types = registry.list_work_types()
        assert len(types) == 33, f"Expected 33 work types, got {len(types)}"

    def test_config_file_exists(self):
        """Configuration file should exist at the default path."""
        assert DEFAULT_CONFIG_PATH.exists(), f"Config not found at {DEFAULT_CONFIG_PATH}"

    def test_known_work_types_present(self, registry):
        """Key work types should be in the registry."""
        types = registry.list_work_types()
        essential = [
            "concrete",
            "metal_structures",
            "earthwork_excavation",
            "foundation_pile",
            "masonry",
        ]
        for wt in essential:
            assert wt in types, f"Missing essential work type: {wt}"

    def test_singleton_loads(self):
        """Singleton should load without errors."""
        types = id_requirements.list_work_types()
        assert len(types) == 33

    def test_list_work_types_sorted(self, registry):
        """list_work_types() should return sorted list."""
        types = registry.list_work_types()
        assert types == sorted(types)


# =============================================================================
# Required Documents
# =============================================================================

class TestRequiredDocuments:
    """Tests for required documents per work type."""

    def test_get_required_documents_returns_list(self, registry):
        """Should return a list of document dicts."""
        docs = registry.get_required_documents("concrete")
        assert isinstance(docs, list)
        assert len(docs) > 0

    def test_each_doc_has_required_fields(self, registry):
        """Each required doc should have id, name, type, required, quantity."""
        docs = registry.get_required_documents("concrete")
        for doc in docs:
            assert "id" in doc, f"Missing 'id' in {doc}"
            assert "name" in doc, f"Missing 'name' in {doc}"
            assert "type" in doc, f"Missing 'type' in {doc}"
            assert "required" in doc, f"Missing 'required' in {doc}"

    def test_aosr_is_always_required(self, registry):
        """AOSR should be in required documents for every work type."""
        for wt in registry.list_work_types():
            docs = registry.get_required_documents(wt)
            aosr_docs = [d for d in docs if d["id"] == "aosr"]
            assert len(aosr_docs) == 1, f"AOSR missing for {wt}"
            assert aosr_docs[0]["required"] is True

    def test_unknown_work_type_returns_defaults(self, registry):
        """Unknown work type should return sensible defaults."""
        docs = registry.get_required_documents("nonexistent_work")
        assert isinstance(docs, list)
        assert len(docs) > 0
        # Should still have AOSR
        assert any(d["id"] == "aosr" for d in docs)

    def test_get_work_type_trail_returns_dict(self, registry):
        """get_work_type_trail should return a dict with expected keys."""
        trail = registry.get_work_type_trail("concrete")
        assert isinstance(trail, dict)
        assert "aosr_count" in trail
        assert "special_journals" in trail

    def test_all_work_types_have_trail(self, registry):
        """Every work type should have a trail."""
        for wt in registry.list_work_types():
            trail = registry.get_work_type_trail(wt)
            assert trail is not None, f"No trail for {wt}"
            assert isinstance(trail, dict)


# =============================================================================
# Delta Calculation
# =============================================================================

class TestDeltaCalculation:
    """Tests for calculate_delta()."""

    def test_empty_present_docs(self, registry):
        """With no present docs, delta should equal total_required."""
        result = registry.calculate_delta("concrete", [])
        assert result["total_required"] > 0
        assert result["present"] == 0
        assert result["delta"] == result["total_required"]
        assert result["completeness_pct"] == 0.0

    def test_full_match_zero_delta(self, registry):
        """When all required docs are present, delta should be 0."""
        docs = registry.get_required_documents("excavation")
        all_ids = [d["id"] for d in docs if d["required"]]
        result = registry.calculate_delta("excavation", all_ids)
        assert result["delta"] == 0
        assert result["completeness_pct"] == 100.0
        assert len(result["missing"]) == 0

    def test_partial_match(self, registry):
        """Partial match should show correct delta."""
        present = ["aosr"]  # Only AOSR present
        result = registry.calculate_delta("concrete", present)
        assert result["present"] == 1
        assert result["delta"] > 0
        assert 0.0 < result["completeness_pct"] < 100.0

    def test_non_required_not_counted(self, registry):
        """Documents marked as required=False should not affect delta."""
        docs = registry.get_required_documents("concrete")
        # Get only required ones
        req_ids = [d["id"] for d in docs if d["required"]]
        all_required = registry.calculate_delta("concrete", req_ids)
        assert all_required["delta"] == 0

    def test_unknown_work_type_delta(self, registry):
        """Delta for unknown work type should still work."""
        result = registry.calculate_delta("fake_work", ["aosr"])
        assert result["total_required"] > 0


# =============================================================================
# Base Trail
# =============================================================================

class TestBaseTrail:
    """Tests for base trail (common to all work types)."""

    def test_base_trail_returns_dict(self, registry):
        """get_base_trail should return a non-empty dict."""
        base = registry.get_base_trail()
        assert isinstance(base, dict)
        assert len(base) > 0

    def test_base_trail_has_key_docs(self, registry):
        """Base trail should include key document types."""
        base = registry.get_base_trail()
        base_keys = list(base.keys())
        # Should include at minimum: OZhR, input control, executive schemes
        assert len(base_keys) >= 3, f"Base trail too small: {base_keys}"
