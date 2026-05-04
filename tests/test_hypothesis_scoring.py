"""
ASD v12.0 — Hypothesis property-based tests for the scoring engine.

Tests the weighted scoring, signal extractors, and veto rules
with property-based testing to catch edge cases that example-based
tests miss.
"""
import pytest
from hypothesis import assume, given, settings, strategies as st
from src.core.pm_agent import (
    compute_weighted_score,
    check_veto_rules,
    extract_legal_signal,
    extract_smeta_signal,
    extract_pto_signal,
    extract_procurement_signal,
    extract_logistics_signal,
    DEFAULT_VETO_RULES,
    DEFAULT_AGENT_WEIGHTS,
    GO_THRESHOLD,
    NO_GO_THRESHOLD,
    AgentSignal,
)

# ── Strategies ─────────────────────────────────────────────────────────────

agent_signal_st = st.builds(
    AgentSignal,
    agent_name=st.sampled_from(["legal", "smeta", "pto", "procurement", "logistics"]),
    signal=st.floats(min_value=0.0, max_value=1.0),
    confidence=st.floats(min_value=0.0, max_value=1.0),
    weight=st.floats(min_value=0.0, max_value=1.0),
    reasoning=st.text(max_size=50),
    key_findings=st.lists(st.text(max_size=20), max_size=3),
)

valid_weight_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


# ── Weighted Scoring Properties ─────────────────────────────────────────────

class TestWeightedScoringProperties:
    """Property-based tests for compute_weighted_score."""

    @given(st.lists(agent_signal_st, min_size=1, max_size=10))
    def test_score_always_in_0_1_range(self, signals):
        """Normalized score must always be in [0, 1] for any valid signals."""
        result = compute_weighted_score(signals)
        assert 0.0 <= result.normalized_score <= 1.0
        assert 0.0 <= result.raw_score

    @given(st.lists(agent_signal_st, min_size=1, max_size=10))
    def test_zone_consistent_with_score(self, signals):
        """Zone must be consistent with threshold boundaries."""
        result = compute_weighted_score(signals)
        s = result.normalized_score
        if s >= GO_THRESHOLD:
            assert result.zone == "go_zone"
        elif s <= NO_GO_THRESHOLD:
            assert result.zone == "no_go_zone"
        else:
            assert result.zone == "grey_zone"

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_homogeneous_signals_equal_that_value(self, value):
        """If all agents report the same signal, the score equals that signal."""
        signals = [
            AgentSignal(
                agent_name=name, signal=value, confidence=0.5,
                weight=w, reasoning="",
            )
            for name, w in DEFAULT_AGENT_WEIGHTS.items()
        ]
        result = compute_weighted_score(signals)
        assert abs(result.normalized_score - value) < 1e-4

    @given(st.lists(agent_signal_st, min_size=1, max_size=5))
    def test_zero_confidence_is_ignored(self, signals):
        """Signals with zero confidence should not affect the result."""
        # Give all signals zero confidence — denominator collapses to 0
        zero_signals = [
            AgentSignal(
                agent_name=s.agent_name, signal=s.signal, confidence=0.0,
                weight=s.weight, reasoning=s.reasoning,
                key_findings=s.key_findings,
            )
            for s in signals
        ]
        result = compute_weighted_score(zero_signals)
        # Default fallback when denominator is 0
        assert result.normalized_score == 0.5

    @given(st.lists(agent_signal_st, min_size=2, max_size=5))
    def test_max_signal_dominates_with_weight(self, signals):
        """Signal=1.0 with confidence=1.0 dominates when others have zero confidence."""
        # Set first signal to strong GO, all others to zero confidence
        signals[0] = AgentSignal(
            agent_name=signals[0].agent_name,
            signal=1.0, confidence=1.0, weight=1.0,
            reasoning="",
        )
        for i in range(1, len(signals)):
            signals[i] = AgentSignal(
                agent_name=signals[i].agent_name,
                signal=0.0, confidence=0.0, weight=0.0,
                reasoning="",
            )
        result = compute_weighted_score(signals)
        assert result.normalized_score == 1.0

    @given(st.lists(agent_signal_st, min_size=2, max_size=5))
    def test_monotonic_increasing_signal(self, signals):
        """Increasing any agent's signal should never decrease the score."""
        assume(len(signals) > 0)
        result_before = compute_weighted_score(signals)
        # Increase the first agent's signal
        increased = list(signals)
        increased[0] = AgentSignal(
            agent_name=signals[0].agent_name,
            signal=min(1.0, signals[0].signal + 0.1),
            confidence=signals[0].confidence,
            weight=signals[0].weight,
            reasoning=signals[0].reasoning,
            key_findings=signals[0].key_findings,
        )
        result_after = compute_weighted_score(increased)
        assert result_after.normalized_score >= result_before.normalized_score - 1e-9

    @given(st.lists(agent_signal_st, min_size=1, max_size=5))
    def test_agent_contributions_present(self, signals):
        """Every agent must appear in contributions dict."""
        result = compute_weighted_score(signals)
        for s in signals:
            assert s.agent_name in result.agent_contributions


# ── Signal Extractor Properties ─────────────────────────────────────────────

def _make_state(legal_result=None, smeta_result=None, pto_result=None,
                proc_result=None, log_result=None, confidences=None):
    state = {"confidence_scores": confidences or {}}
    if legal_result is not None:
        state["legal_result"] = legal_result
    if smeta_result is not None:
        state["smeta_result"] = smeta_result
    if pto_result is not None:
        state["vor_result"] = pto_result
    if proc_result is not None:
        state["procurement_result"] = proc_result
    if log_result is not None:
        state["logistics_result"] = log_result
    return state


class TestLegalSignalProperties:
    """Property-based tests for extract_legal_signal."""

    @given(
        verdict=st.sampled_from(["approved", "approved_with_comments", "rejected", "dangerous"]),
        critical_count=st.integers(min_value=0, max_value=20),
        high_count=st.integers(min_value=0, max_value=50),
    )
    def test_signal_always_in_0_1(self, verdict, critical_count, high_count):
        """Legal signal must always be in [0, 1]."""
        state = _make_state(
            legal_result={"verdict": verdict, "critical_count": critical_count,
                          "high_count": high_count},
            confidences={"legal": 0.8},
        )
        result = extract_legal_signal(state)
        assert 0.0 <= result.signal <= 1.0
        assert result.agent_name == "legal"

    def test_missing_legal_result_returns_neutral(self):
        """No legal analysis → neutral signal with zero confidence."""
        result = extract_legal_signal({})
        assert result.signal == 0.5
        assert result.confidence == 0.0

    def test_approved_without_issues_above_0_9(self):
        """Approved verdict with no critical/high findings → signal >= 0.9."""
        result = extract_legal_signal(_make_state(
            legal_result={"verdict": "approved", "critical_count": 0,
                          "high_count": 0},
            confidences={"legal": 0.8},
        ))
        assert result.signal >= 0.9

    @given(
        critical_count=st.integers(min_value=0, max_value=20),
        high_count=st.integers(min_value=0, max_value=50),
    )
    def test_dangerous_always_below_0_3(self, critical_count, high_count):
        """Dangerous verdict should stay very low regardless of other values."""
        result = extract_legal_signal(_make_state(
            legal_result={"verdict": "dangerous", "critical_count": critical_count,
                          "high_count": high_count},
            confidences={"legal": 0.8},
        ))
        assert result.signal <= 0.2


class TestSmetaSignalProperties:
    """Property-based tests for extract_smeta_signal."""

    @given(margin_pct=st.floats(min_value=-100.0, max_value=200.0))
    def test_signal_always_in_0_1(self, margin_pct):
        """Smeta signal must always be in [0, 1]."""
        state = _make_state(
            smeta_result={"profit_margin_pct": margin_pct, "fer_coverage_pct": 80},
            confidences={"smeta": 0.8},
        )
        result = extract_smeta_signal(state)
        assert 0.0 <= result.signal <= 1.0
        assert result.agent_name == "smeta"

    def test_missing_smeta_result_returns_neutral(self):
        """No smeta result → neutral with zero confidence."""
        result = extract_smeta_signal({})
        assert result.signal == 0.5
        assert result.confidence == 0.0

    @given(margin_pct=st.floats(min_value=-100.0, max_value=0.0))
    def test_negative_margin_gives_lowest_signal(self, margin_pct):
        """Any negative margin gives signal=0.05."""
        result = extract_smeta_signal(_make_state(
            smeta_result={"profit_margin_pct": margin_pct},
            confidences={"smeta": 0.8},
        ))
        assert result.signal == 0.05

    @given(margin_pct=st.floats(min_value=40.1, max_value=200.0))
    def test_high_margin_gives_high_signal(self, margin_pct):
        """Margin > 40% gives signal=0.95."""
        result = extract_smeta_signal(_make_state(
            smeta_result={"profit_margin_pct": margin_pct, "fer_coverage_pct": 80},
            confidences={"smeta": 0.8},
        ))
        assert result.signal == 0.95


class TestPTOProcurementLogisticsProperties:
    """Property tests for PTO, Procurement, and Logistics signal extractors."""

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_pto_signal_in_0_1(self, confidence):
        state = _make_state(
            pto_result={"vor_complete": True, "work_types": 5},
            confidences={"pto": confidence},
        )
        result = extract_pto_signal(state)
        assert 0.0 <= result.signal <= 1.0
        assert result.agent_name == "pto"

    def test_pto_missing_result_neutral(self):
        result = extract_pto_signal({})
        assert result.signal == 0.5
        assert result.confidence == 0.0

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_procurement_signal_in_0_1(self, confidence):
        state = _make_state(
            proc_result={"suppliers_found": 3, "avg_price_vs_market_pct": 95},
            confidences={"procurement": confidence},
        )
        result = extract_procurement_signal(state)
        assert 0.0 <= result.signal <= 1.0
        assert result.agent_name == "procurement"

    def test_procurement_missing_result_neutral(self):
        result = extract_procurement_signal({})
        assert result.signal == 0.5
        assert result.confidence == 0.0

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_logistics_signal_in_0_1(self, confidence):
        state = _make_state(
            log_result={"delivery_days": 14, "distance_km": 200},
            confidences={"logistics": confidence},
        )
        result = extract_logistics_signal(state)
        assert 0.0 <= result.signal <= 1.0
        assert result.agent_name == "logistics"

    def test_logistics_missing_result_neutral(self):
        result = extract_logistics_signal({})
        assert result.signal == 0.5
        assert result.confidence == 0.0


# ── Veto Rules Properties ───────────────────────────────────────────────────

class TestVetoRulesProperties:
    """Property-based tests for check_veto_rules."""

    def test_no_veto_with_empty_state(self):
        """Empty state triggers no veto rules."""
        triggered, rules = check_veto_rules({}, DEFAULT_VETO_RULES)
        assert triggered is None
        assert all(not r.triggered for r in rules)

    def test_veto_idempotent(self):
        """Checking veto rules twice gives the same result."""
        state = {
            "legal_result": {"verdict": "dangerous", "critical_count": 5},
        }
        t1, _ = check_veto_rules(state, DEFAULT_VETO_RULES)
        t2, _ = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert t1 == t2

    def test_veto_dangerous_verdict_triggers(self):
        state = {"legal_result": {"verdict": "dangerous"}}
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_dangerous_verdict"

    def test_veto_margin_below_10_triggers(self):
        state = {"smeta_result": {"profit_margin_pct": 5.0}}
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_margin_below_10"

    def test_veto_critical_traps_3_triggers(self):
        state = {"legal_result": {"critical_count": 3, "verdict": "approved_with_comments"}}
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_critical_traps_3plus"

    def test_veto_nmck_below_70_triggers(self):
        state = {"smeta_result": {"profit_margin_pct": 15, "nmck_below_70pct": True}}
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_nmck_below_70pct"

    def test_first_veto_wins(self):
        """When multiple vetoes trigger, only the first one is returned."""
        state = {
            "legal_result": {"verdict": "dangerous", "critical_count": 5},
            "smeta_result": {"profit_margin_pct": 5.0, "nmck_below_70pct": True},
        }
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        # veto_dangerous_verdict is first in the list
        assert triggered == "veto_dangerous_verdict"

    @given(
        margin=st.floats(min_value=10.0, max_value=200.0),
        critical_count=st.integers(min_value=0, max_value=2),
    )
    def test_no_veto_with_safe_state(self, margin, critical_count):
        """Safe state (good margin, few criticals, no dangerous verdict) triggers no veto."""
        state = {
            "legal_result": {"verdict": "approved", "critical_count": critical_count},
            "smeta_result": {"profit_margin_pct": margin, "nmck_below_70pct": False},
        }
        triggered, rules = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered is None


# ── Agent Weights Properties ─────────────────────────────────────────────────

class TestAgentWeightsProperties:
    """Properties of the default agent weight configuration."""

    def test_weights_sum_to_one(self):
        """All agent weights must sum to 1.0 (within tolerance)."""
        total = sum(DEFAULT_AGENT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_all_agents_have_extractors(self):
        """Each agent with a weight must have a signal extractor."""
        extractors = {
            "legal": extract_legal_signal,
            "smeta": extract_smeta_signal,
            "pto": extract_pto_signal,
            "procurement": extract_procurement_signal,
            "logistics": extract_logistics_signal,
        }
        for agent in DEFAULT_AGENT_WEIGHTS:
            assert agent in extractors, f"No extractor for {agent}"

    @given(
        legal_w=st.floats(min_value=0.0, max_value=0.5),
        smeta_w=st.floats(min_value=0.0, max_value=0.5),
        pto_w=st.floats(min_value=0.0, max_value=0.5),
        proc_w=st.floats(min_value=0.0, max_value=0.5),
        log_w=st.floats(min_value=0.0, max_value=0.5),
    )
    def test_score_invariant_to_weight_scaling(self, legal_w, smeta_w, pto_w, proc_w, log_w):
        """Scaling all weights by same factor shouldn't change normalized score."""
        assume(legal_w + smeta_w + pto_w + proc_w + log_w > 1e-6)
        signals = [
            AgentSignal(agent_name="legal", signal=0.8, confidence=1.0,
                        weight=legal_w, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.6, confidence=1.0,
                        weight=smeta_w, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.7, confidence=1.0,
                        weight=pto_w, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.5, confidence=1.0,
                        weight=proc_w, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.9, confidence=1.0,
                        weight=log_w, reasoning=""),
        ]
        r1 = compute_weighted_score(signals)

        # Scale all weights by x2 (still within [0, 1] since inputs are ≤ 0.5)
        scaled = [
            AgentSignal(agent_name=s.agent_name, signal=s.signal,
                        confidence=s.confidence, weight=s.weight * 2,
                        reasoning=s.reasoning)
            for s in signals
        ]
        r2 = compute_weighted_score(scaled)
        assert abs(r1.normalized_score - r2.normalized_score) < 1e-9
