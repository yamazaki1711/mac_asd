"""
MAC_ASD v12.0 — Smoke Tests for Full Pipeline.

Tests the full agent pipeline end-to-end with mock LLM responses.
Verifies: AgentState v2 structure, HermesRouter decision model,
confidence scoring, fallback detection, and error propagation.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


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
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
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

    async def test_hermes_node_routing_start_to_archive(self, base_state):
        """Verify Hermes routes start → archive."""
        from src.agents.nodes import hermes_node

        result = await hermes_node(base_state)
        assert result["next_step"] == "archive"

    async def test_hermes_node_full_routing_chain(self, base_state):
        """Verify Hermes routes full chain: archive → procurement → pto → smeta → legal → logistics → verdict."""
        from src.agents.nodes import hermes_node

        routing_chain = [
            ("start", "archive"),
            ("archive", "procurement"),
            ("procurement", "pto"),
            ("pto", "smeta"),
            ("smeta", "legal"),
            ("legal", "logistics"),
        ]

        for from_step, expected_next in routing_chain:
            state = {**base_state, "next_step": from_step}
            result = await hermes_node(state)
            assert result["next_step"] == expected_next, f"from {from_step} expected {expected_next}, got {result['next_step']}"

    async def test_hermes_node_verdict_fallback_detection(self, base_state):
        """Verify Hermes detects LLM fallback before computing verdict."""
        from src.agents.nodes import hermes_node
        import logging

        state = {
            **base_state,
            "next_step": "logistics",
            "_llm_fallback_triggered": True,
            "_llm_fallback_agents": ["pto", "smeta"],
            "legal_result": {"verdict": "approved", "critical_count": 0, "high_count": 0},
            "smeta_result": {"profit_margin_pct": 25},
            "vor_result": {"total_positions": 10, "unit_mismatches": [], "confidence_score": 0.0},
            "procurement_result": {"decision": "bid", "nmck_vs_market": 5, "competitor_count": 3},
            "logistics_result": {"vendors_found": 0, "delivery_available": True},
            "confidence_scores": {
                "legal": 0.8, "smeta": 0.0, "pto": 0.0, "procurement": 0.7, "logistics": 0.1,
            },
        }

        # Should not crash even with fallback flags set
        result = await hermes_node(state)
        assert "next_step" in result


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

        matrix = agent.build_completeness_matrix(["concrete"])
        assert matrix[ID344Category.ACT_AOSR] > 0, "Concrete work must require AOSR"
        assert matrix[ID344Category.JOURNALS] == 1
        assert matrix[ID344Category.ACT_GRO] == 1

    def test_pto_aosr_trail(self):
        from src.core.services.pto_agent import PTOAgent
        agent = PTOAgent()

        trail = agent.build_aosr_trail("Бетонирование фундамента", "concrete")
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
        assert journal.section_3.date_range[0] == "2025-06-01"
        assert journal.section_3.date_range[1] == "2025-06-08"

        # Test to_aosr_data round-trip
        data = restorer.to_aosr_data(journal)
        assert len(data) == 2

        # Test to_register_entries
        entries = restorer.to_register_entries(journal)
        assert len(entries) >= 2  # 2 AOSR refs

    def test_batch_id_generator(self):
        from src.core.services.batch_id_generator import BatchIDGenerator
        gen = BatchIDGenerator(
            project_id=1,
            project_name="Тестовый объект",
            project_meta={"customer": "Заказчик", "contractor": "ООО «КСК №1»"},
        )

        schedule = [
            {"work_type": "concrete", "work_name": "Бетонирование фундамента",
             "start_date": "2025-06-01", "end_date": "2025-06-05",
             "quantity": "100", "unit": "м3"},
            {"work_type": "waterproofing", "work_name": "Гидроизоляция",
             "start_date": "2025-06-06", "end_date": "2025-06-10",
             "quantity": "500", "unit": "м2"},
        ]

        result = gen.generate(schedule, output_dir="/tmp/asd_test_output")
        assert result["total_aosr"] > 0, f"Expected AOSR, got {result}"
        assert result["total_ks2_lines"] == 2
        assert result["zip_path"].endswith(".zip")
