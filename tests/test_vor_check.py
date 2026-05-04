"""Tests for PTO_VorCheck skill — VOR vs PD comparison."""

import pytest

from src.agents.skills.pto.vor_check import (
    PTO_VorCheck, Severity, DiscrepancyType,
    FUZZY_MATCH_THRESHOLD, VOLUME_TOLERANCE_PCT,
)


class TestPTOVorCheck:
    """Core comparison logic tests."""

    @pytest.mark.asyncio
    async def test_exact_match_no_discrepancies(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Устройство фундаментов ленточных", "quantity": 100, "unit": "м3"}]
        pd = [{"name": "Устройство фундаментов ленточных", "quantity": 100, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert result.is_success
        assert result.data["summary"]["total_discrepancies"] == 0
        assert len(result.data["matches"]) == 1
        assert len(result.data["missing_in_pd"]) == 0
        assert len(result.data["extra_in_vor"]) == 0

    @pytest.mark.asyncio
    async def test_volume_mismatch_critical(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Бетонирование ростверка", "quantity": 150, "unit": "м3"}]
        pd = [{"name": "Бетонирование ростверка", "quantity": 100, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        discrepancies = result.data["discrepancies"]
        assert len(discrepancies) == 1
        assert discrepancies[0]["severity"] == Severity.CRITICAL.value
        assert discrepancies[0]["type"] == DiscrepancyType.VOLUME_MISMATCH.value
        assert discrepancies[0]["diff_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_volume_mismatch_within_tolerance(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Разработка котлована", "quantity": 103, "unit": "м3"}]
        pd = [{"name": "Разработка котлована", "quantity": 100, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        discrepancies = result.data["discrepancies"]
        # 3% diff < 5% tolerance → severity LOW
        vol_disc = [d for d in discrepancies if d["type"] == DiscrepancyType.VOLUME_MISMATCH.value]
        assert len(vol_disc) == 1
        assert vol_disc[0]["severity"] == Severity.LOW.value

    @pytest.mark.asyncio
    async def test_unit_mismatch(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Щебёночная подготовка", "quantity": 1500, "unit": "м3"}]
        pd = [{"name": "Щебёночная подготовка", "quantity": 1500, "unit": "т"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        discrepancies = result.data["discrepancies"]
        unit_disc = [d for d in discrepancies if d["type"] == DiscrepancyType.UNIT_MISMATCH.value]
        assert len(unit_disc) == 1
        assert unit_disc[0]["severity"] == Severity.HIGH.value

    @pytest.mark.asyncio
    async def test_missing_in_pd(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Монтаж ограждения", "quantity": 200, "unit": "м"}]
        pd = [{"name": "Демонтаж временных сооружений", "quantity": 1, "unit": "компл"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert len(result.data["missing_in_pd"]) == 1
        assert len(result.data["extra_in_vor"]) == 1
        # The VOR item not matched in PD
        missing = result.data["discrepancies"]
        missing_types = {d["type"] for d in missing}
        assert DiscrepancyType.MISSING_IN_PD.value in missing_types
        assert DiscrepancyType.EXTRA_IN_VOR.value in missing_types

    @pytest.mark.asyncio
    async def test_fuzzy_match_near_duplicate(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Устройство фундаментов ленточных монолитных", "quantity": 120, "unit": "м3"}]
        pd = [{"name": "Фундаменты ленточные монолитные устройство", "quantity": 120, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert result.data["summary"]["total_discrepancies"] == 0
        assert len(result.data["matches"]) == 1
        assert result.data["matches"][0]["match_score"] >= FUZZY_MATCH_THRESHOLD

    @pytest.mark.asyncio
    async def test_fuzzy_match_below_threshold(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Устройство фундаментов", "quantity": 100, "unit": "м3"}]
        pd = [{"name": "Прокладка кабеля силового", "quantity": 500, "unit": "м"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        # Should not match — completely different work types
        assert len(result.data["matches"]) == 0
        assert len(result.data["missing_in_pd"]) == 1
        assert len(result.data["extra_in_vor"]) == 1

    @pytest.mark.asyncio
    async def test_empty_vor(self):
        skill = PTO_VorCheck()
        vor = []
        pd = [{"name": "Бетонирование", "quantity": 50, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert result.is_success
        assert result.data["total_vor_items"] == 0
        assert len(result.data["extra_in_vor"]) == 1
        assert len(result.warnings) >= 1

    @pytest.mark.asyncio
    async def test_empty_pd(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Бетонирование", "quantity": 50, "unit": "м3"}]
        pd = []

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert result.is_success
        assert result.data["total_pd_items"] == 0
        assert len(result.data["missing_in_pd"]) == 1
        assert len(result.warnings) >= 1

    @pytest.mark.asyncio
    async def test_custom_tolerance(self):
        skill = PTO_VorCheck()
        vor = [{"name": "Работа X", "quantity": 108, "unit": "м3"}]
        pd = [{"name": "Работа X", "quantity": 100, "unit": "м3"}]

        # Default tolerance 5% → 8% diff → HIGH
        result_default = await skill.execute({"vor_items": vor, "pd_items": pd})
        vol_disc = [d for d in result_default.data["discrepancies"]
                    if d["type"] == DiscrepancyType.VOLUME_MISMATCH.value]
        assert len(vol_disc) == 1
        assert vol_disc[0]["severity"] == Severity.HIGH.value

        # Custom tolerance 10% → 8% diff → LOW
        result_custom = await skill.execute({
            "vor_items": vor, "pd_items": pd, "volume_tolerance_pct": 10.0,
        })
        vol_disc2 = [d for d in result_custom.data["discrepancies"]
                     if d["type"] == DiscrepancyType.VOLUME_MISMATCH.value]
        assert len(vol_disc2) == 1
        assert vol_disc2[0]["severity"] == Severity.LOW.value

    @pytest.mark.asyncio
    async def test_multiple_items(self):
        skill = PTO_VorCheck()
        vor = [
            {"name": "Бетонирование фундамента", "quantity": 500, "unit": "м3"},
            {"name": "Армирование фундамента", "quantity": 50, "unit": "т"},
            {"name": "Гидроизоляция", "quantity": 200, "unit": "м2"},
        ]
        pd = [
            {"name": "Бетонирование фундамента", "quantity": 450, "unit": "м3"},
            {"name": "Армирование фундамента", "quantity": 50, "unit": "т"},
            {"name": "Гидроизоляция", "quantity": 200, "unit": "м2"},
        ]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        # 3 matches, 1 volume discrepancy (500 vs 450 = 11.1% → CRITICAL)
        assert len(result.data["matches"]) == 3
        vol_disc = [d for d in result.data["discrepancies"]
                    if d["type"] == DiscrepancyType.VOLUME_MISMATCH.value]
        assert len(vol_disc) == 1
        assert vol_disc[0]["severity"] == Severity.CRITICAL.value

    @pytest.mark.asyncio
    async def test_string_input_normalization(self):
        skill = PTO_VorCheck()
        vor = ["Устройство щебёночной подготовки"]
        pd = [{"name": "Устройство щебёночной подготовки", "quantity": 1200, "unit": "м3"}]

        result = await skill.execute({"vor_items": vor, "pd_items": pd})

        assert result.is_success
        assert len(result.data["matches"]) == 1
        # String items get quantity=0 → no volume comparison
        assert result.data["summary"]["total_discrepancies"] == 0

    @pytest.mark.asyncio
    async def test_validate_empty_both(self):
        skill = PTO_VorCheck()
        result = await skill.execute({"vor_items": [], "pd_items": []})

        assert not result.is_success
        assert result.status.value == "error"
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_validate_bad_types(self):
        skill = PTO_VorCheck()
        result = await skill.execute({"vor_items": "not_a_list", "pd_items": []})

        assert not result.is_success
        assert len(result.errors) >= 1
