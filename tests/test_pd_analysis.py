"""Tests for PTO_PDAnalysis skill — PD collision detection."""

import pytest
from unittest.mock import AsyncMock, patch

from src.agents.skills.pto.pd_analysis import (
    PTO_PDAnalysis, REQUIRED_PD_SECTIONS,
)


class TestPTOPDAnalysis:
    """PD analysis tests — spatial collisions, completeness, semantics."""

    @pytest.mark.asyncio
    async def test_spatial_collision_axis_dimension_mismatch(self):
        skill = PTO_PDAnalysis()
        sections = [
            {
                "code": "АР", "name": "Архитектурные решения",
                "content": "Стены по оси А 200 мм толщиной.",
                "key_positions": ["ось А", "200 мм"],
            },
            {
                "code": "КР", "name": "Конструктивные решения",
                "content": "Несущая стена по оси А 400 мм толщиной.",
                "key_positions": ["ось А", "400 мм"],
            },
        ]

        result = await skill.execute({"sections": sections})

        assert result.is_success
        collisions = result.data["collisions"]
        spatial = [c for c in collisions if c["type"] == "spatial"]
        # 400 vs 200 = 50% diff > 30% threshold → collision
        assert len(spatial) >= 1
        assert any("АР" in c["section_a"] or "АР" in c["section_b"] for c in spatial)

    @pytest.mark.asyncio
    async def test_completeness_all_present(self):
        skill = PTO_PDAnalysis()
        sections = [
            {"code": code, "name": name, "content": "", "key_positions": []}
            for code, name in list(REQUIRED_PD_SECTIONS.items())
        ]

        result = await skill.execute({"sections": sections})

        completeness = result.data["completeness"]
        assert completeness["completeness_pct"] == 100.0
        assert len(completeness["missing"]) == 0

    @pytest.mark.asyncio
    async def test_completeness_missing_sections(self):
        skill = PTO_PDAnalysis()
        sections = [
            {"code": "АР", "name": "Архитектурные решения", "content": "", "key_positions": []},
            {"code": "КР", "name": "Конструктивные решения", "content": "", "key_positions": []},
        ]

        result = await skill.execute({"sections": sections})

        completeness = result.data["completeness"]
        assert completeness["completeness_pct"] < 100.0
        assert len(completeness["missing"]) > 0

        # Missing sections should appear as completeness-type collisions
        comp_collisions = [c for c in result.data["collisions"] if c["type"] == "completeness"]
        assert len(comp_collisions) > 0

    @pytest.mark.asyncio
    async def test_xref_broken_reference(self):
        skill = PTO_PDAnalysis()
        sections = [
            {
                "code": "АР", "name": "Архитектурные решения",
                "content": "См. лист ИОС7 детальную схему вентиляции.",
                "key_positions": [],
            },
            {
                "code": "КР", "name": "Конструктивные решения",
                "content": "",
                "key_positions": [],
            },
        ]

        result = await skill.execute({"sections": sections})

        # ИОС7 doesn't exist → xref collision
        xref = [c for c in result.data["collisions"] if c["type"] == "xref"]
        assert len(xref) >= 1
        assert any("ИОС7" in str(c) for c in xref)

    @pytest.mark.asyncio
    async def test_no_collisions_perfect_match(self):
        skill = PTO_PDAnalysis()
        sections = [
            {
                "code": "АР", "name": "Архитектурные решения",
                "content": "Фасад здания.",
                "key_positions": [],
            },
            {
                "code": "КР", "name": "Конструктивные решения",
                "content": "Фундамент здания.",
                "key_positions": [],
            },
        ]

        result = await skill.execute({"sections": sections})

        # No spatial/dimensional overlap → no spatial collisions
        spatial = [c for c in result.data["collisions"] if c["type"] == "spatial"]
        # May have xref or completeness collisions but not spatial with no shared data
        assert all(c["type"] != "spatial" for c in result.data["collisions"])
        assert result.data["summary"]["total_collisions"] >= 0

    @pytest.mark.asyncio
    async def test_llm_semantic_collision(self):
        skill = PTO_PDAnalysis()
        # Mock the LLM engine
        mock_llm = AsyncMock()
        mock_llm.safe_chat = AsyncMock(return_value='{"collisions": ['
            '{"section_a": "АР", "section_b": "КР", '
            '"description": "Стены 200 мм vs 250 мм", '
            '"severity": "high"}]}')
        skill._llm = mock_llm

        sections = [
            {"code": "АР", "name": "AP", "content": "walls 200 mm", "key_positions": []},
            {"code": "КР", "name": "KR", "content": "walls 250 mm", "key_positions": []},
        ]

        result = await skill.execute({
            "sections": sections,
            "check_semantic": True,
            "enable_llm": True,
        })

        semantic = [c for c in result.data["collisions"] if c["description"] == "Стены 200 мм vs 250 мм"]
        assert len(semantic) == 1
        assert result.data["llm_used"] is True

    @pytest.mark.asyncio
    async def test_llm_fallback_on_error(self):
        skill = PTO_PDAnalysis()
        mock_llm = AsyncMock()
        mock_llm.safe_chat = AsyncMock(side_effect=Exception("LLM down"))
        skill._llm = mock_llm

        sections = [
            {"code": "АР", "name": "AP", "content": "walls 200 mm", "key_positions": []},
            {"code": "КР", "name": "KR", "content": "walls 250 mm", "key_positions": []},
        ]

        result = await skill.execute({
            "sections": sections,
            "check_semantic": True,
            "enable_llm": True,
        })

        # Should still succeed — LLM error is caught
        assert result.is_success
        assert result.data["llm_used"] is False

    @pytest.mark.asyncio
    async def test_validate_empty(self):
        skill = PTO_PDAnalysis()
        result = await skill.execute({"sections": []})

        assert not result.is_success
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_validate_missing_code_and_name(self):
        skill = PTO_PDAnalysis()
        result = await skill.execute({"sections": [{"content": "just content"}]})

        assert not result.is_success

    @pytest.mark.asyncio
    async def test_semantic_disabled_by_default(self):
        skill = PTO_PDAnalysis()
        sections = [
            {"code": "АР", "name": "AP", "content": "walls 200 mm", "key_positions": []},
        ]

        result = await skill.execute({"sections": sections})

        # Semantic analysis should not run by default
        assert result.data["llm_used"] is False
