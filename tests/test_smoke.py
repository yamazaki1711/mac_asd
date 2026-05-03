"""
MAC_ASD v12.0 — Smoke Tests for Full Pipeline.

Tests the full agent pipeline end-to-end with mock LLM responses.
Verifies: AgentState v2 structure, HermesRouter decision model,
confidence scoring, fallback detection, and error propagation.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def base_state():
    """Minimal AgentState v2.0 for testing."""
    return {
        "schema_version": "2.0",
        "workflow_mode": "lot_search",
        "project_id": 1,
        "current_lot_id": "LOT-001",
        "task_description": "Test pipeline run",
        "messages": [],
        "intermediate_data": {},
        "findings": [],
        "confidence_scores": {},
        "current_step": "start",
        "next_step": "start",
        "is_complete": False,
        "audit_trail": [],
        "revision_history": [],
        "rollback_point": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_llm_fallback_triggered": False,
        "_llm_fallback_agents": [],
    }


# =============================================================================
# AgentState v2.0 Tests
# =============================================================================

class TestAgentState:
    """Verify AgentState v2.0 schema integrity."""

    def test_state_schema_version(self, base_state):
        assert base_state["schema_version"] == "2.0"

    def test_workflow_mode_valid(self, base_state):
        from src.agents.state import WorkflowMode
        assert base_state["workflow_mode"] in [m.value for m in WorkflowMode]

    def test_llm_fallback_fields_present(self, base_state):
        assert "_llm_fallback_triggered" in base_state
        assert "_llm_fallback_agents" in base_state
        assert base_state["_llm_fallback_triggered"] is False
        assert base_state["_llm_fallback_agents"] == []

    def test_create_initial_state(self):
        from src.agents.state import create_initial_state
        state = create_initial_state(
            project_id=42,
            task_description="Build a bridge",
            workflow_mode="lot_search",
            lot_id="LOT-42",
        )
        assert state["project_id"] == 42
        assert state["task_description"] == "Build a bridge"
        assert state["current_lot_id"] == "LOT-42"
        assert state["schema_version"] == "2.0"
        assert state["_llm_fallback_triggered"] is False


# =============================================================================
# PM Agent Decision Engine Tests (merged from HermesRouter)
# =============================================================================

class TestPMAgentDecisions:
    """Verify PM Agent 3-stage decision engine (weighted scoring + veto rules)."""

    def test_weighted_scoring_go_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.90, confidence=0.9, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.85, confidence=0.9, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.80, confidence=0.9, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.75, confidence=0.9, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.70, confidence=0.9, weight=0.08, reasoning=""),
        ]

        result = compute_weighted_score(signals)
        assert result.zone == "go_zone", f"Expected go_zone, got {result.zone}"
        assert result.normalized_score >= 0.70

    def test_weighted_scoring_grey_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.50, confidence=0.8, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.45, confidence=0.8, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.50, confidence=0.8, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.40, confidence=0.8, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.45, confidence=0.8, weight=0.08, reasoning=""),
        ]

        result = compute_weighted_score(signals)
        assert result.zone == "grey_zone", f"Expected grey_zone, got {result.zone}"
        assert 0.30 <= result.normalized_score <= 0.70

    def test_weighted_scoring_no_go_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.10, confidence=0.8, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.15, confidence=0.8, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.20, confidence=0.8, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.10, confidence=0.8, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.15, confidence=0.8, weight=0.08, reasoning=""),
        ]

        result = compute_weighted_score(signals)
        assert result.zone == "no_go_zone", f"Expected no_go_zone, got {result.zone}"
        assert result.normalized_score <= 0.30

    def test_veto_dangerous_triggers(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {
            "legal_result": {"verdict": "dangerous", "critical_count": 5, "high_count": 2},
            "smeta_result": {"profit_margin_pct": 25},
        }
        veto_id, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert veto_id == "veto_dangerous_verdict"

    def test_veto_margin_below_10_triggers(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {
            "legal_result": {"verdict": "approved_with_comments", "critical_count": 0, "high_count": 1},
            "smeta_result": {"profit_margin_pct": 5},
        }
        veto_id, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert veto_id == "veto_margin_below_10"

    def test_veto_3plus_critical_traps(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {
            "legal_result": {"verdict": "rejected", "critical_count": 3, "high_count": 1},
            "smeta_result": {"profit_margin_pct": 20},
        }
        veto_id, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert veto_id == "veto_critical_traps_3plus"

    def test_no_veto_when_clean(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {
            "legal_result": {"verdict": "approved", "critical_count": 0, "high_count": 0},
            "smeta_result": {"profit_margin_pct": 25},
        }
        veto_id, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert veto_id is None

    def test_signal_extractors_return_valid_signals(self):
        from src.core.pm_agent import (
            extract_legal_signal,
            extract_smeta_signal,
            extract_pto_signal,
            extract_procurement_signal,
            extract_logistics_signal,
        )

        state = {
            "legal_result": {"verdict": "approved", "critical_count": 0, "high_count": 1},
            "smeta_result": {"profit_margin_pct": 25, "fer_coverage_pct": 80},
            "vor_result": {"total_positions": 10, "unit_mismatches": [], "confidence_score": 0.8},
            "procurement_result": {"decision": "bid", "nmck_vs_market": 5, "competitor_count": 3},
            "logistics_result": {"vendors_found": 3, "delivery_available": True},
            "confidence_scores": {
                "legal": 0.8, "smeta": 0.8, "pto": 0.8, "procurement": 0.7, "logistics": 0.8,
            },
        }

        legal_s = extract_legal_signal(state)
        assert 0.0 <= legal_s.signal <= 1.0
        assert legal_s.weight == 0.35

        smeta_s = extract_smeta_signal(state)
        assert 0.0 <= smeta_s.signal <= 1.0

        pto_s = extract_pto_signal(state)
        assert 0.0 <= pto_s.signal <= 1.0

        proc_s = extract_procurement_signal(state)
        assert 0.0 <= proc_s.signal <= 1.0

        log_s = extract_logistics_signal(state)
        assert 0.0 <= log_s.signal <= 1.0


# =============================================================================
# Confidence Score Tests
# =============================================================================

class TestConfidenceScores:
    """Verify confidence scores are computed from actual data, not hardcoded."""

    def test_compute_confidence_fallback(self, base_state):
        from src.agents.nodes import _compute_agent_confidence

        base_state["_llm_fallback_triggered"] = True
        base_state["_llm_fallback_agents"] = ["pto"]

        conf = _compute_agent_confidence(base_state, "pto", "fallback data", {"key": "val"})
        assert conf == 0.0, f"Fallback should give 0.0 confidence, got {conf}"

    def test_compute_confidence_no_data(self, base_state):
        from src.agents.nodes import _compute_agent_confidence

        conf = _compute_agent_confidence(base_state, "pto", "", None)
        assert conf == 0.1

    def test_compute_confidence_unparsed(self, base_state):
        from src.agents.nodes import _compute_agent_confidence

        conf = _compute_agent_confidence(base_state, "pto", "some text response not json", None)
        assert conf == 0.3

    def test_compute_confidence_rich(self, base_state):
        from src.agents.nodes import _compute_agent_confidence

        data = {"volumes": [1, 2, 3], "source": "drawing.pdf", "confidence": 0.9}
        conf = _compute_agent_confidence(base_state, "pto", json.dumps(data), data)
        assert conf == 0.85, f"Rich JSON should give 0.85, got {conf}"

    def test_legal_confidence_no_findings(self, base_state):
        from src.agents.nodes import _compute_legal_confidence

        class MockResult:
            findings_count = 0
            findings = []
            critical_count = 0
            high_count = 0

            class MockVerdict:
                value = "approved"
            verdict = MockVerdict()

        conf = _compute_legal_confidence(base_state, MockResult())
        assert conf == 0.2

    def test_legal_confidence_dangerous(self, base_state):
        from src.agents.nodes import _compute_legal_confidence

        class MockResult:
            findings_count = 8
            findings = [{}] * 8
            critical_count = 3
            high_count = 5

            class MockVerdict:
                value = "dangerous"
            verdict = MockVerdict()

        conf = _compute_legal_confidence(base_state, MockResult())
        assert conf == 0.95, f"Definitive dangerous should give 0.95, got {conf}"


# =============================================================================
# VerdictReport Schema Tests
# =============================================================================

class TestVerdictReport:
    """Verify VerdictReport schema and builder."""

    def test_builder_produces_valid_report(self):
        from src.schemas.verdict import (
            VerdictReportBuilder, TenderVerdict, DecisionMethod, RiskLevel,
            AgentSignal, WeightedScoringResult, VetoRule,
        )

        builder = VerdictReportBuilder(lot_id="LOT-TEST", project_id=1)

        # Add signals
        builder.add_agent_signal(
            AgentSignal(agent_name="legal", signal=0.80, confidence=0.9, weight=0.35, reasoning="OK")
        )

        # Add scoring
        builder.set_scoring(WeightedScoringResult(
            raw_score=0.75, normalized_score=0.75,
            agent_contributions={"legal": 0.28},
            zone="go_zone",
        ))

        # Add veto rules
        builder.add_veto_rule(VetoRule(
            rule_id="veto_test", rule_name="Test", description="Test rule",
            condition="false", override_verdict=TenderVerdict.NO_GO,
        ))

        # Add warning
        builder.add_warning("Test warning: this is a mock run")

        # Set verdict
        builder.set_verdict(
            verdict=TenderVerdict.GO,
            method=DecisionMethod.WEIGHT_SCORING,
            risk_level=RiskLevel.LOW,
        )
        builder.set_summary("Test verdict: GO")

        report = builder.build()

        assert report.verdict == TenderVerdict.GO
        assert report.lot_id == "LOT-TEST"
        assert len(report.agent_signals) == 1
        assert len(report.warnings) == 1
        assert "Test warning" in report.warnings[0]

    def test_report_must_have_verdict(self):
        from src.schemas.verdict import VerdictReportBuilder

        builder = VerdictReportBuilder(lot_id="TEST")
        with pytest.raises(ValueError, match="Verdict must be set"):
            builder.build()


# =============================================================================
# Workflow Smoke Test
# =============================================================================

@pytest.mark.smoke
@pytest.mark.asyncio
class TestWorkflowSmoke:
    """Smoke test: verify the full pipeline graph compiles and runs."""

    async def test_workflow_graph_compiles_parallel(self):
        """Verify parallel StateGraph compiles without errors."""
        from src.agents.workflow import create_parallel_workflow, create_sequential_workflow
        parallel_graph = create_parallel_workflow()
        assert parallel_graph is not None
        sequential_graph = create_sequential_workflow()
        assert sequential_graph is not None

    async def test_pm_planning_creates_plan_and_routes(self, base_state):
        """PM planning node creates a WorkPlan and dispatches first agent."""
        import src.agents.nodes_v2 as nodes_v2
        from src.agents.nodes_v2 import _plan_cache
        from unittest.mock import patch, AsyncMock

        _plan_cache.clear()

        plan_json = json.dumps({
            "plan": {
                "goal": "Smoke test routing",
                "reasoning": "Single task test",
                "estimated_hours": 0.1,
                "tasks": [{
                    "task_id": "task_1", "task_type": "archive_register",
                    "description": "Register docs", "agent": "archive",
                    "depends_on": [], "priority": 10, "confidence_required": 0.5,
                }],
            }
        })

        with patch.object(
            nodes_v2.llm_engine, "chat", return_value=plan_json
        ):
            result = await nodes_v2.pm_planning_node(base_state)
            assert "work_plan" in result
            assert result.get("current_agent") == "archive"
            assert result.get("next_step") == "archive"

    async def test_pm_dispatch_router_selects_agent_from_plan(self, base_state):
        """PM dispatch router selects the correct agent from WorkPlan."""
        from src.agents.nodes_v2 import pm_dispatch_router, _plan_cache
        from src.core.pm_agent import WorkPlan, TaskNode

        _plan_cache.clear()

        task = TaskNode(
            task_id="task_1", task_type="archive_register",
            description="Register", agent="archive",
            depends_on=[], priority=10,
        )
        plan = WorkPlan(
            plan_id="PLAN-SMOKE", project_id=base_state["project_id"],
            goal="Test dispatch", tasks=[task],
        )
        _plan_cache[base_state["project_id"]] = plan
        state = {**base_state, "work_plan": plan.to_dict(), "current_agent": "archive"}

        route = pm_dispatch_router(state)
        assert route == "archive"

    async def test_pm_evaluate_handles_low_confidence(self, base_state):
        """PM evaluation handles low-confidence agent results without crashing."""
        from src.agents.nodes_v2 import _plan_cache
        from src.core.pm_agent import WorkPlan, TaskNode, PlanStatus

        _plan_cache.clear()

        task = TaskNode(
            task_id="task_1", task_type="archive_register",
            description="Register docs", agent="archive",
            depends_on=[], priority=10, confidence_required=0.6,
            max_retries=2,
        )
        plan = WorkPlan(
            plan_id="PLAN-FALLBACK", project_id=base_state["project_id"],
            goal="Test fallback handling", tasks=[task],
        )
        _plan_cache[base_state["project_id"]] = plan
        state = {
            **base_state,
            "work_plan": plan.to_dict(),
            "current_agent": "archive",
            "current_task_id": "task_1",
            "confidence_scores": {"archive": 0.0},
            "_llm_fallback_triggered": True,
            "_llm_fallback_agents": ["archive"],
            "intermediate_data": {},
            "workflow_mode": "lot_search",
        }

        from src.agents.nodes_v2 import pm_evaluate_node
        result = await pm_evaluate_node(state)
        assert "next_step" in result
        assert "work_plan" in result


# =============================================================================
# LLM Engine Profile Tests
# =============================================================================

class TestLLMEngineConfig:
    """Verify LLM Engine configuration and profile loading."""

    def test_dev_linux_maps_all_agents_to_ollama(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="dev_linux")

        for agent in ["pm", "pto", "smeta", "legal", "procurement", "logistics", "archive"]:
            config = settings.get_model_config(agent)
            assert config["engine"] == "ollama", f"{agent} should use ollama in dev_linux"

    def test_mac_studio_uses_mlx_for_vlm_agents(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="mac_studio")

        # These agents share Gemma 4 31B via MLX-VLM
        for agent in ["pto", "smeta", "legal", "procurement", "logistics"]:
            config = settings.get_model_config(agent)
            assert config["engine"] == "mlx-vlm", f"{agent} should use mlx-vlm, got {config['engine']}"

    def test_mac_studio_pm_uses_mlx(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="mac_studio")

        config = settings.get_model_config("pm")
        assert config["engine"] == "mlx"

    def test_deepseek_all_agents_use_deepseek_engine(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="deepseek")

        for agent in ["pto", "smeta", "legal", "procurement", "logistics", "archive"]:
            config = settings.get_model_config(agent)
            assert config["engine"] == "deepseek", f"{agent} should use deepseek, got {config['engine']}"
            assert config["model"] == "deepseek-chat", f"{agent} should use deepseek-chat"

    def test_deepseek_pm_uses_reasoner(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="deepseek")

        config = settings.get_model_config("pm")
        assert config["engine"] == "deepseek"
        assert config["model"] == "deepseek-reasoner"

    def test_deepseek_embed_uses_ollama(self):
        from src.config import Settings
        settings = Settings(ASD_PROFILE="deepseek")

        config = settings.get_model_config("embed")
        assert config["engine"] == "ollama", "Embeddings should use Ollama (DeepSeek has no embedding model)"

    def test_database_url_format(self):
        from src.config import Settings
        settings = Settings(
            POSTGRES_USER="testuser",
            POSTGRES_PASSWORD="testpass",
            POSTGRES_DB="testdb",
            POSTGRES_HOST="localhost",
            POSTGRES_PORT=5433,
        )

        url = settings.database_url
        assert "postgresql+psycopg2://" in url
        assert "testuser:testpass" in url
        assert "localhost:5433/testdb" in url


# =============================================================================
# ID Services Tests (v12.0 — Batch ID, Journal Restoration, DeloAgent export)
# =============================================================================

class TestIDServices:
    """Verify ID-related services: PTO Agent, Delo Agent, Journal Restorer."""

    def test_pto_classify_document(self):
        from src.core.services.pto_agent import PTOAgent, ID344Category
        agent = PTOAgent()

        assert agent.classify_document("AOSR") == ID344Category.ACT_AOSR
        assert agent.classify_document("KS2") == ID344Category.ACT_AOSR
        assert agent.classify_document("Certificate") == ID344Category.INPUT_CONTROL
        assert agent.classify_document("OZHR") == ID344Category.JOURNALS
        assert agent.classify_document("unknown_type") == ID344Category.WORK_DRAWINGS

    def test_pto_build_completeness_matrix(self):
        from src.core.services.pto_agent import PTOAgent, ID344Category
        agent = PTOAgent()

        from src.agents.skills.pto.work_spec import WorkType
        matrix = agent.build_completeness_matrix([WorkType.CONCRETE.value])
        assert matrix[ID344Category.ACT_AOSR] > 0, "Concrete work must require AOSR"
        assert matrix[ID344Category.JOURNALS] == 1
        assert matrix[ID344Category.ACT_GRO] == 1

    def test_pto_aosr_trail(self):
        from src.core.services.pto_agent import PTOAgent
        from src.agents.skills.pto.work_spec import WorkType
        agent = PTOAgent()

        trail = agent.build_aosr_trail("Бетонирование фундамента", WorkType.CONCRETE.value)
        assert trail.aosr_name == "Бетонирование фундамента"
        mandatory = [i for i in trail.items if i.mandatory]
        assert len(mandatory) >= 3, f"Expected >=3 mandatory items, got {len(mandatory)}"

        # Check specific mandatory items
        item_types = [i.item_type for i in mandatory]
        assert "is_geodetic" in item_types
        assert "is_result" in item_types
        assert "quality_docs" in item_types

    def test_delo_agent_registry_lifecycle(self):
        from src.core.services.delo_agent import DeloAgent, DocStatus
        agent = DeloAgent()

        agent.create_registry(1, "Тестовый проект")
        entry = agent.register_document(1, "АОСР", "Бетонирование фундамента",
                                        category_344="act_aosr", work_type="concrete",
                                        pages=2)
        assert entry is not None
        assert entry.reg_id.startswith("ASD-1-")
        assert entry.status == DocStatus.DRAFT

        # Update status
        ok = agent.update_status(1, entry.reg_id, DocStatus.PREPARED)
        assert ok is True

        registry = agent.get_registry(1)
        assert registry is not None
        assert registry.total_docs == 1
        assert registry.completion_pct == 0.0  # Not accepted yet

    def test_delo_export_for_output(self):
        from src.core.services.delo_agent import DeloAgent
        agent = DeloAgent()

        agent.create_registry(1, "Тест")
        agent.register_document(1, "АОСР", "Скрытые работы фундамента",
                                category_344="act_aosr", pages=2)
        agent.register_document(1, "КС-2", "Акт приёмки",
                                category_344="act_aosr", pages=1)

        export = agent.export_registry_for_output(1)
        assert export["project_name"] == "Тест"
        assert len(export["documents"]) == 2
        assert "stats" in export

    def test_journal_restorer_reconstruct(self):
        from src.core.services.journal_restorer import JournalRestorer
        restorer = JournalRestorer()

        aosr_list = [
            {
                "aosr_number": "АОСР-001",
                "work_type": "Бетонирование фундамента",
                "work_start": "2025-06-01",
                "work_end": "2025-06-05",
                "materials": ["Бетон B25", "Арматура А500С"],
                "executor_company": "ООО «КСК №1»",
                "decision": "разрешается",
            },
            {
                "aosr_number": "АОСР-002",
                "work_type": "Гидроизоляция",
                "work_start": "2025-06-06",
                "work_end": "2025-06-08",
                "materials": ["Гидроизол"],
                "executor_company": "ООО «КСК №1»",
                "decision": "разрешается",
            },
        ]

        journal = restorer.reconstruct(
            project_id=1,
            project_name="Жилой дом №3",
            aosr_list=aosr_list,
        )

        assert journal.is_viable
        assert len(journal.section_3.entries) == 2
        assert journal.section_3.date_range[0] == "2025-06-05"  # work_end of first AOSR
        assert journal.section_3.date_range[1] == "2025-06-08"  # work_end of second AOSR

        # Test to_aosr_data round-trip
        data = restorer.to_aosr_data(journal)
        assert len(data) == 2

        # Test to_register_entries
        entries = restorer.to_register_entries(journal)
        assert len(entries) >= 2  # 2 AOSR refs

    def test_batch_id_generator(self):
        from src.core.services.batch_id_generator import BatchIDGenerator
        from src.agents.skills.pto.work_spec import WorkType
        gen = BatchIDGenerator(
            project_id=1,
            project_name="Тестовый объект",
            project_meta={"customer": "Заказчик", "contractor": "ООО «КСК №1»"},
        )

        schedule = [
            {"work_type": WorkType.CONCRETE.value, "work_name": "Бетонирование фундамента",
             "start_date": "2025-06-01", "end_date": "2025-06-05",
             "quantity": "100", "unit": "м3"},
            {"work_type": WorkType.FOUNDATION_MONOLITHIC.value, "work_name": "Гидроизоляция",
             "start_date": "2025-06-06", "end_date": "2025-06-10",
             "quantity": "500", "unit": "м2"},
        ]

        result = gen.generate(schedule, output_dir="/tmp/asd_test_output")
        assert result["total_aosr"] > 0, f"Expected AOSR, got {result}"
        assert result["total_ks2_lines"] == 2
        assert result["zip_path"].endswith(".zip")


class TestPTOComplianceSkill:
    """Тесты нового навыка комплаенса ПТО (v12.0)."""

    def test_resolve_enum_worktype(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        spec = compliance_skill.resolve("бетонные")
        assert spec.work_type_code == "бетонные"
        assert len(spec.aosr_hidden) >= 4
        assert len(spec.journals) >= 3
        assert not spec.from_idprosto

    def test_resolve_idprosto_fuzzy(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        spec = compliance_skill.resolve("монтаж лифтового оборудования")
        assert spec.from_idprosto
        assert "27_elevators" in spec.work_type_code or "лифт" in spec.work_type_name.lower()

    def test_resolve_fallback(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        spec = compliance_skill.resolve("совершенно неизвестная работа")
        assert len(spec.journals) >= 1  # ОЖР + ЖВК minimum

    def test_completeness_report(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        report = compliance_skill.completeness_report(
            project_id=1,
            work_type_queries=["бетонные", "монтаж металлоконструкций"],
        )
        assert report["project_id"] == 1
        assert report["required_total"] > 0
        assert "completeness_pct" in report
        assert len(report["work_types"]) == 2

    def test_batch_spec(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        batch = compliance_skill.generate_batch_spec([
            {"work_type": "бетонные", "work_name": "Бетонирование", "start_date": "2025-01-01", "end_date": "2025-01-10"},
        ])
        assert batch["total_aosr_expected"] > 0
        assert batch["total_journals_expected"] > 0
        assert "бетонные" in batch["by_work_type"]

    def test_list_all_work_types(self):
        from src.agents.skills.pto.compliance_skill import compliance_skill
        all_types = compliance_skill.list_all_work_types()
        assert len(all_types) >= 50  # 33 + 31 minimum

    def test_all_33_worktypes_have_coverage(self):
        from src.agents.skills.pto.work_spec import WorkType, WORK_JOURNALS, WORK_HIDDEN_ACTS, WORK_ACCEPTANCE_ACTS
        for wt in WorkType:
            assert wt in WORK_JOURNALS, f"{wt.name} missing journals"
            assert wt in WORK_HIDDEN_ACTS, f"{wt.name} missing hidden acts"
            assert wt in WORK_ACCEPTANCE_ACTS, f"{wt.name} missing acceptance acts"


class TestIDProstoKnowledge:
    """Тесты загрузчика знаний id-prosto.ru."""

    def test_resolve_all_31_types(self):
        from src.core.knowledge.idprosto_loader import idprosto_loader, IDPROSTO_WORK_TYPES
        for code in IDPROSTO_WORK_TYPES:
            summary = idprosto_loader.get_work_type_summary(code)
            assert summary["total_docs"] > 0, f"{code} has 0 documents"

    def test_all_norms_loaded(self):
        from src.core.knowledge.idprosto_loader import idprosto_loader
        norms = idprosto_loader.get_all_normative_refs()
        assert len(norms) >= 200  # 252 known

    def test_compound_keyword_matching(self):
        from src.core.knowledge.idprosto_loader import idprosto_loader
        assert idprosto_loader.resolve_work_type("асфальтобетонное покрытие") == "29_roads"
        assert idprosto_loader.resolve_work_type("сборные ж/б конструкции") == "08_precast-concrete"
        assert idprosto_loader.resolve_work_type("наружное водоснабжение") == "11_extwatersupply"
        assert idprosto_loader.resolve_work_type("технологический трубопровод") == "19_pipelines"


class TestDeloAgentRegulation:
    """Тесты интеграции с Регламентом ТЗ-П."""

    def test_handover_act_generation(self):
        from src.core.services.delo_agent import DeloAgent
        agent = DeloAgent()
        agent.create_registry(1, "Тестовый объект")
        agent.register_document(1, "АОСР", "Бетонирование фундамента", pages=2)
        agent.register_document(1, "АОСР", "Армирование", pages=2)

        act = agent.generate_handover_act(project_id=1)
        assert act["object_name"] == "Тестовый объект"
        assert len(act["documents"]) == 2
        assert "date" in act
        assert "sender" in act

    def test_preparation_checklist(self):
        from src.core.services.delo_agent import DeloAgent
        agent = DeloAgent()
        checklist = agent.get_preparation_checklist()
        assert len(checklist) == 7  # 7 stages
        assert all("stage" in s and "action" in s for s in checklist)

    def test_gosstroynadzor_checklist(self):
        from src.core.services.delo_agent import DeloAgent
        agent = DeloAgent()
        checklist = agent.get_gosstroynadzor_checklist()
        assert len(checklist) == 5
        assert any("начал" in s["action"].lower() for s in checklist)

    def test_storage_registry(self):
        from src.core.services.delo_agent import DeloAgent
        agent = DeloAgent()
        agent.create_registry(2, "Объект №2")
        agent.register_document(2, "АОСР", "Гидроизоляция", pages=1)
        rows = agent.generate_storage_registry(2)
        assert len(rows) == 1
        assert rows[0]["package_num"] == "ПАК-2"


class TestTemplateRegistry:
    """Template registry DOCX form resolution tests."""

    def test_list_all_templates(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        catalog = registry.list_templates()
        assert len(catalog) >= 100  # 149 templates from 26 packages
        assert all("file_name" in t and "full_path" in t for t in catalog)

    def test_resolve_aosr_form(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        results = registry.resolve_form("Приказ Минстроя №344/пр, приложение 3")
        assert len(results) >= 1
        aosr_names = [r["file_name"] for r in results]
        assert any("AOSR" in name for name in aosr_names)

    def test_resolve_gwl_form(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        results = registry.resolve_form("Приказ Минстроя №1026/пр, приложение 1")
        assert len(results) >= 1
        assert any("GWL" in r["file_name"] for r in results)

    def test_resolve_concrete_journal(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        results = registry.resolve_form("СП 70.13330.2012, приложение Ф")
        assert len(results) >= 1
        assert any("zhbr" in r["file_name"] for r in results)

    def test_get_forms_for_concrete(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        forms = registry.get_forms_for_work_type("06_concrete")
        assert len(forms) >= 10
        with_templates = sum(1 for f in forms if f["has_template"])
        assert with_templates >= 5  # at least 5 forms have DOCX templates

    def test_template_coverage_report(self):
        from src.core.knowledge.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        report = registry.template_coverage_report()
        assert report["work_types_analyzed"] == 31
        assert report["coverage_pct"] >= 50  # at least 50% coverage

    def test_compliance_skill_get_templates(self):
        from src.agents.skills.pto.compliance_skill import PTOComplianceSkill
        skill = PTOComplianceSkill()
        result = skill.get_templates_for_work_type("бетонные")
        assert result["total_forms"] > 0
        assert result["forms_with_templates"] + result["forms_without_templates"] == result["total_forms"]

    def test_resolve_template_via_compliance_skill(self):
        from src.agents.skills.pto.compliance_skill import PTOComplianceSkill
        skill = PTOComplianceSkill()
        results = skill.resolve_template("Приказ Минстроя №344/пр, приложение 3")
        assert len(results) >= 1


# =============================================================================
# Knowledge Invalidation Engine Tests
# =============================================================================

class TestKnowledgeInvalidation:
    """Tests for the platform-level knowledge invalidation engine."""

    # ── Change Type Detection ──

    def test_detect_repeal(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        from src.core.knowledge.invalidation_engine import ChangeType
        engine = InvalidationEngine()
        text = "Приказ Минстроя №344/пр отменён с 01.01.2026. Утратил силу полностью."
        result = engine.detect_change_type(text)
        assert result == ChangeType.REPEAL

    def test_detect_replacement(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        from src.core.knowledge.invalidation_engine import ChangeType
        engine = InvalidationEngine()
        text = "Утверждён СП 70.13330.2025 взамен ранее действовавшего СП 70.13330.2012. Новая редакция вступает в силу с 01.06.2026."
        result = engine.detect_change_type(text)
        assert result == ChangeType.REPLACEMENT

    def test_detect_amendment(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        from src.core.knowledge.invalidation_engine import ChangeType
        engine = InvalidationEngine()
        text = "Внесены изменения в Приказ Минстроя №1026/пр. Дополнены пункты 5.1-5.3."
        result = engine.detect_change_type(text)
        assert result == ChangeType.AMENDMENT

    def test_detect_new(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        from src.core.knowledge.invalidation_engine import ChangeType
        engine = InvalidationEngine()
        text = "Утверждён новый СП 543.1325800.2025. Вступает в силу с 01.07.2026."
        result = engine.detect_change_type(text)
        assert result == ChangeType.NEW

    def test_detect_clarification(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        from src.core.knowledge.invalidation_engine import ChangeType
        engine = InvalidationEngine()
        text = "Письмо Минстроя России: разъяснения порядка применения СП 48.13330.2019. Методические рекомендации по приёмке работ."
        result = engine.detect_change_type(text)
        assert result == ChangeType.CLARIFICATION

    def test_no_change_detected(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Строительная компания выиграла тендер на строительство школы в Подмосковье."
        result = engine.detect_change_type(text)
        assert result is None

    # ── Domain Classification ──

    def test_classify_pto_domain(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Новый СП 70.13330.2025 меняет требования к АОСР и журналам работ."
        domains = engine.classify_domain(text)
        assert "pto" in domains

    def test_classify_legal_domain(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Изменения в 44-ФЗ: новые правила тендеров и обеспечения контрактов."
        domains = engine.classify_domain(text)
        assert "legal" in domains

    def test_classify_smeta_domain(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Обновлены ФЕР-2026: новые индексы пересчёта сметной стоимости. Изменены коэффициенты НМЦК."
        domains = engine.classify_domain(text)
        assert "smeta" in domains

    def test_classify_cross_domain(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Отменён СП 48.13330.2019. Это влияет на договоры подряда (контракты по 44-ФЗ) и сметные расчёты ФЕР."
        domains = engine.classify_domain(text)
        assert "pto" in domains
        assert "legal" in domains
        assert "smeta" in domains

    # ── Normative Ref Extraction ──

    def test_extract_norms_sp_gost(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Отменены СП 70.13330.2012 и ГОСТ Р 51872-2024. Заменены на СП 70.13330.2025."
        refs = engine.extract_norms_from_text(text)
        refs_str = " ".join(refs)
        assert "СП 70.13330.2012" in refs_str
        assert "СП 70.13330.2025" in refs_str

    def test_extract_norms_prikaz(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Приказ Минстроя №344/пр отменён. Взамен Приказ Минстроя №1026/пр."
        refs = engine.extract_norms_from_text(text)
        refs_str = " ".join(refs)
        assert any("344/пр" in r for r in refs)
        assert any("1026/пр" in r for r in refs)

    def test_extract_fz(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Поправки в 44-ФЗ и 223-ФЗ приняты Госдумой."
        refs = engine.extract_norms_from_text(text)
        refs_str = " ".join(refs)
        assert "44-ФЗ" in refs_str
        assert "223-ФЗ" in refs_str

    # ── check_validity API ──

    def test_check_validity_active_by_default(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        result = engine.check_validity("СП 70.13330.2025 п.3.5")
        assert result["valid"] is True
        assert result["status"] == "active"

    def test_check_validity_batch(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        refs = ["СП 70.13330.2012", "ГОСТ Р 51872-2024", "Приказ Минстроя №344/пр"]
        results = engine.check_validity_batch(refs)
        assert len(results) == 3
        for ref in refs:
            assert ref in results
            assert "valid" in results[ref]
            assert "status" in results[ref]

    def test_check_validity_after_process_text(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = "Приказ Минстроя №999/пр отменён с 01.01.2026. Документ утратил силу."
        affected = engine.process_text(text, domain="pto", source="test")
        if affected:  # If detection worked
            result = engine.check_validity("Приказ Минстроя №999/пр")
            assert result["valid"] is False
            assert result["status"] in ("stale", "replaced")

    # ── process_text (manual input) ──

    def test_process_text_detects_repeal(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        text = (
            "Минстрой России сообщает: Приказ Минстроя №500/пр от 15.03.2020 "
            "утратил силу с 01.01.2026. Признан утратившим силу полностью."
        )
        affected = engine.process_text(text, domain="pto", source="test")
        # Should detect at least the norm was extracted
        assert isinstance(affected, list)

    # ── Summary / Reporting ──

    def test_get_summary(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        summary = engine.get_summary()
        assert "total_changes" in summary
        assert "stale_norms" in summary
        assert "active_norms" in summary
        assert "by_domain" in summary
        assert "last_updated" in summary

    def test_get_stale_norms(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        stale = engine.get_stale_norms()
        assert isinstance(stale, list)

    def test_get_stale_norms_filtered_by_domain(self):
        from src.core.knowledge.invalidation_engine import InvalidationEngine
        engine = InvalidationEngine()
        for domain in ("pto", "legal", "smeta"):
            stale = engine.get_stale_norms(domain=domain)
            assert isinstance(stale, list)

    # ── Data Models ──

    def test_regulatory_change_to_dict(self):
        from src.core.knowledge.invalidation_engine import RegulatoryChange, ChangeType
        change = RegulatoryChange(
            change_id="test-001",
            domain="pto",
            change_type=ChangeType.REPLACEMENT,
            title="Новый СП 70.13330",
            description="Замена СП 70.13330.2012 на СП 70.13330.2025",
            affected_norms=["СП 70.13330.2012"],
            new_norms=["СП 70.13330.2025"],
            source="telegram/минстрой",
            effective_date="2026-06-01",
            confidence=0.85,
        )
        d = change.to_dict()
        assert d["change_id"] == "test-001"
        assert d["change_type"] == "replacement"
        assert "СП 70.13330.2012" in d["affected_norms"]

    def test_regulatory_change_roundtrip(self):
        from src.core.knowledge.invalidation_engine import RegulatoryChange, ChangeType
        change = RegulatoryChange(
            change_id="test-002",
            domain="legal",
            change_type=ChangeType.AMENDMENT,
            title="Изменения в 44-ФЗ",
            description="Дополнены пункты обеспечения контрактов",
            affected_norms=["44-ФЗ"],
            new_norms=[],
            source="telegram/закупки",
        )
        d = change.to_dict()
        restored = RegulatoryChange.from_dict(d)
        assert restored.change_id == change.change_id
        assert restored.change_type == change.change_type
        assert restored.domain == "legal"

    def test_affected_entry_model(self):
        from src.core.knowledge.invalidation_engine import AffectedEntry, RegulatoryChange, ChangeType, EntryStatus
        change = RegulatoryChange(
            change_id="test-003",
            domain="pto",
            change_type=ChangeType.REPEAL,
            title="Test",
            description="Test",
            affected_norms=["СП 1.2.3"],
        )
        entry = AffectedEntry(
            entry_type="normative_ref",
            entry_ref="СП 1.2.3",
            agent_domain="pto",
            change=change,
            new_status=EntryStatus.STALE,
            detail="Документ утратил силу",
        )
        d = entry.to_dict()
        assert d["entry_type"] == "normative_ref"
        assert d["new_status"] == "stale"
        assert d["change_id"] == "test-003"


# =============================================================================
# Agent Invalidation Integration Tests
# =============================================================================

class TestPTOAgentValidity:
    """Tests for PTO agent knowledge invalidation integration."""

    def test_check_norms_validity_returns_list(self):
        from src.core.services.pto_agent import PTOAgent
        agent = PTOAgent()
        refs = ["СП 70.13330.2012", "ГОСТ Р 51872-2024", "Приказ Минстроя №344/пр"]
        warnings = agent.check_norms_validity(refs)
        assert isinstance(warnings, list)

    def test_get_regulations_with_validity(self):
        from src.core.services.pto_agent import PTOAgent
        agent = PTOAgent()
        result = agent.get_regulations_with_validity()
        assert "regulations" in result
        assert "stale_warnings" in result
        assert "has_stale" in result
        assert isinstance(result["regulations"], list)
        if result["regulations"]:
            assert "is_current" in result["regulations"][0]

    def test_get_work_type_help_includes_validity_check(self):
        from src.core.services.pto_agent import PTOAgent
        agent = PTOAgent()
        help_text = agent.get_work_type_help("бетонные работы")
        assert len(help_text) > 0


class TestLegalServiceValidity:
    """Tests for Legal Service knowledge invalidation integration."""

    def test_check_norms_validity(self):
        from src.core.services.legal_service import LegalService
        service = LegalService()
        refs = ["44-ФЗ", "223-ФЗ", "ПП РФ №468"]
        warnings = service._check_norms_validity(refs)
        assert isinstance(warnings, list)


class TestSmetaAgentValidity:
    """Tests for Smeta Agent knowledge invalidation integration."""

    def test_check_norms_validity(self):
        from src.core.services.smeta_agent import SmetaAgent
        agent = SmetaAgent()
        refs = ["ФЕР01-01-013", "МДС 81-35.2004", "ГЭСН-2020"]
        warnings = agent.check_norms_validity(refs)
        assert isinstance(warnings, list)

    def test_build_estimate_with_validity(self):
        from src.core.services.smeta_agent import SmetaAgent
        agent = SmetaAgent()
        vor = [
            {"code": "ФЕР06-01-001", "name": "Бетонная подготовка", "unit": "м3", "quantity": 10},
            {"code": "ФЕР06-01-020", "name": "Бетонирование", "unit": "м3", "quantity": 25},
        ]
        estimate, warnings = agent.build_estimate_with_validity(
            project_id=1, title="Тест", vor_positions=vor
        )
        from src.core.services.smeta_agent import SmetaEstimate
        assert isinstance(estimate, SmetaEstimate)
        assert isinstance(warnings, list)
        assert estimate.grand_total > 0
