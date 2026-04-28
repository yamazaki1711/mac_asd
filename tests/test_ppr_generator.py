"""
PPR Generator v0.1 — Tests.

Validates: schemas, TTK generators, section generators, orchestrator.
"""
import pytest
from datetime import date

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_input():
    from src.core.services.ppr_generator.schemas import (
        PPRInput, OrganizationInfo, DeveloperInfo,
        ScheduleData, Stage, WorkTypeItem,
    )
    return PPRInput(
        object_name="Строительство мостового перехода через р. Обь",
        project_code="2026/04-ППР",
        customer=OrganizationInfo(name="ООО «ЗаказчикСтрой»", inn="1234567890"),
        contractor=OrganizationInfo(name="ООО «Подрядчик»", inn="0987654321"),
        developer=DeveloperInfo(
            organization="ООО «Подрядчик»",
            chief_engineer="Иванов И.И.",
            developer="Петров П.П.",
            position="Инженер ПТО",
        ),
        construction_schedule=ScheduleData(
            construction_start=date(2026, 5, 1),
            construction_end=date(2026, 12, 31),
            stages=[
                Stage(name="Подготовительный", start_date=date(2026, 5, 1), end_date=date(2026, 5, 30)),
                Stage(name="Основной", start_date=date(2026, 6, 1), end_date=date(2026, 11, 30)),
            ],
            total_duration_days=244,
        ),
        work_types=[
            WorkTypeItem(code="welding", name="Сварные соединения", volume="1200 пог.м", quantity=1200, unit="пог.м"),
            WorkTypeItem(code="sheet_pile", name="Шпунтовое ограждение", volume="450 т", quantity=450, unit="т"),
            WorkTypeItem(code="concrete", name="Бетонные работы", volume="350 м³", quantity=350, unit="м³"),
            WorkTypeItem(code="earthwork", name="Земляные работы", volume="5000 м³", quantity=5000, unit="м³"),
            WorkTypeItem(code="metalwork", name="Монтаж металлоконструкций", volume="280 т", quantity=280, unit="т"),
        ],
    )


# =============================================================================
# Schema Tests
# =============================================================================

class TestSchemas:
    def test_ppr_input_creation(self, sample_input):
        assert sample_input.object_name.startswith("Строительство")
        assert len(sample_input.work_types) == 5
        assert sample_input.project_code == "2026/04-ППР"

    def test_ttk_result_structure(self):
        from src.core.services.ppr_generator.schemas import (
            TTKResult, TTKScope, TTKTechnology, TTKQuality, TTKResources,
        )
        ttk = TTKResult(
            work_type="welding",
            scope=TTKScope(work_type="welding", description="test"),
            technology=TTKTechnology(),
            quality=TTKQuality(),
            resources=TTKResources(),
        )
        assert ttk.work_type == "welding"
        assert ttk.total_labor_intensity_person_hours == 0.0


# =============================================================================
# TTK Registry Tests
# =============================================================================

class TestTTKRegistry:
    def test_registry_has_all_6_generators(self):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry

        expected = {"welding", "sheet_pile", "anticorrosion", "concrete", "earthwork", "metalwork"}
        registered = set(TTKRegistry.list_all())
        assert expected.issubset(registered), f"Missing: {expected - registered}"

    def test_registry_select_for_project(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry

        codes = [wt.code for wt in sample_input.work_types]
        generators = TTKRegistry.select_for_project(codes)
        assert len(generators) == 5  # anticorrosion not in input

    def test_registry_returns_none_for_unknown(self):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        assert TTKRegistry.get("nonexistent") is None


# =============================================================================
# TTK Generator Tests
# =============================================================================

class TestTTKGenerators:
    def test_welding_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen_cls = TTKRegistry.get("welding")
        gen = gen_cls()
        result = gen.generate(sample_input)
        assert result.work_type == "welding"
        assert len(result.technology.main_operations) >= 4
        assert result.total_labor_intensity_person_hours > 0

    def test_sheet_pile_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen = TTKRegistry.get("sheet_pile")()
        result = gen.generate(sample_input)
        assert result.work_type == "sheet_pile"
        assert len(result.quality.operational_control) > 0

    def test_anticorrosion_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen = TTKRegistry.get("anticorrosion")()
        result = gen.generate(sample_input)
        assert result.work_type == "anticorrosion"
        assert len(result.technology.main_operations) >= 8

    def test_concrete_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen = TTKRegistry.get("concrete")()
        result = gen.generate(sample_input)
        assert result.work_type == "concrete"
        assert len(result.resources.materials) > 0

    def test_earthwork_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen = TTKRegistry.get("earthwork")()
        result = gen.generate(sample_input)
        assert result.work_type == "earthwork"
        assert len(result.technology.main_operations) >= 4

    def test_metalwork_ttk_generates(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        gen = TTKRegistry.get("metalwork")()
        result = gen.generate(sample_input)
        assert result.work_type == "metalwork"
        assert len(result.quality.incoming_control) > 0


# =============================================================================
# Section Generator Tests
# =============================================================================

class TestSectionGenerators:
    @pytest.fixture
    def ttks(self, sample_input):
        from src.core.services.ppr_generator.sections.ttk_base import TTKRegistry
        codes = [wt.code for wt in sample_input.work_types]
        return [gen().generate(sample_input) for gen in TTKRegistry.select_for_project(codes)]

    def test_general_data(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_general_data
        result = generate_general_data(sample_input, ttks)
        assert result.section_id == "general_data"
        assert "1. Общие данные" in result.title
        assert len(result.content) > 100

    def test_work_organization(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_work_organization
        result = generate_work_organization(sample_input, ttks)
        assert result.section_id == "work_organization"

    def test_manpower(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_manpower
        result = generate_manpower(sample_input, ttks)
        assert result.section_id == "manpower"
        assert len(result.metadata.get("workers", [])) >= 0

    def test_machinery(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_machinery
        result = generate_machinery(sample_input, ttks)
        assert result.section_id == "machinery"

    def test_safety(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_safety
        result = generate_safety(sample_input, ttks)
        assert result.section_id == "safety"

    def test_attestation(self, sample_input, ttks):
        from src.core.services.ppr_generator.sections import generate_attestation
        result = generate_attestation(sample_input, ttks)
        assert result.section_id == "attestation"

    def test_title_page(self, sample_input):
        from src.core.services.ppr_generator.sections import generate_title_page
        result = generate_title_page(sample_input)
        assert result.section_id == "title_page"

    def test_approval_sheet(self, sample_input):
        from src.core.services.ppr_generator.sections import generate_approval_sheet
        result = generate_approval_sheet(sample_input)
        assert result.section_id == "approval_sheet"


# =============================================================================
# Orchestrator Smoke Test
# =============================================================================

class TestPPRGenerator:
    def test_full_generation(self, sample_input):
        from src.core.services.ppr_generator import PPRGenerator
        gen = PPRGenerator()
        result = gen.generate(sample_input)

        assert result.project_code == "2026/04-ППР"
        assert len(result.ttks) == 5
        assert len(result.sections) >= 10  # 8 content sections + title + approval
        assert result.stats.ttks_generated == 5
        assert result.stats.generation_time_seconds > 0
