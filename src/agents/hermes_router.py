"""
ASD v12.0 — Hermes Hybrid Decision Router.

Гибридная модель принятия решений Hermes:
  Этап 1: Весовой скоринг (быстрый, детерминистичный)
  Этап 2: LLM-рассуждение (только для серой зоны 0.3-0.7)
  Этап 3: Veto-правила (hard constraints, override)

Веса агентов по умолчанию:
  Юрист      0.35  — правовые ловушки — главный риск субподрядчика
  Сметчик    0.25  — рентабельность — критерий выживания
  ПТО        0.20  — объёмы работ — основа калькуляции
  Закупщик   0.12  — рыночная информация
  Логист     0.08  — поставки

Usage:
    from src.agents.hermes_router import HermesRouter

    router = HermesRouter(llm_engine=llm_engine)
    report = await router.decide(state)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.state import AgentState, HermesDecision, HermesVerdict
from src.core.llm_engine import LLMEngine
from src.schemas.verdict import (
    AgentSignal,
    DecisionMethod,
    RiskLevel,
    TenderVerdict,
    VetoRule,
    VerdictReport,
    VerdictReportBuilder,
    WeightedScoringResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Default Agent Weights
# =============================================================================

DEFAULT_AGENT_WEIGHTS: Dict[str, float] = {
    "legal": 0.35,
    "smeta": 0.25,
    "pto": 0.20,
    "procurement": 0.12,
    "logistics": 0.08,
}

# Пороги для зон решений
GO_THRESHOLD = 0.70
NO_GO_THRESHOLD = 0.30


# =============================================================================
# Veto Rules (Hard Constraints)
# =============================================================================

DEFAULT_VETO_RULES: List[VetoRule] = [
    VetoRule(
        rule_id="veto_dangerous_verdict",
        rule_name="Юридический вето",
        description="Вердикт Юриста DANGEROUS — подписание недопустимо",
        condition="legal_result.verdict == 'dangerous'",
        triggered=False,
        override_verdict=TenderVerdict.NO_GO,
    ),
    VetoRule(
        rule_id="veto_margin_below_10",
        rule_name="Маржа ниже минимума",
        description="Маржа ниже 10% — работа в убыток или на грани",
        condition="smeta_result.profit_margin_pct < 10",
        triggered=False,
        override_verdict=TenderVerdict.NO_GO,
    ),
    VetoRule(
        rule_id="veto_critical_traps_3plus",
        rule_name="3+ критических ловушки",
        description="3 и более критических юридических ловушки — слишком рискованно",
        condition="legal_result.critical_count >= 3",
        triggered=False,
        override_verdict=TenderVerdict.NO_GO,
    ),
    VetoRule(
        rule_id="veto_nmck_below_70pct",
        rule_name="НМЦК ниже 70% рынка",
        description="НМЦК ниже 70% рыночной стоимости — демпинг",
        condition="smeta_result.nmck_below_70pct == True",
        triggered=False,
        override_verdict=TenderVerdict.NO_GO,
    ),
]


# =============================================================================
# Signal Extractor — получение сигнала от агента
# =============================================================================

def extract_legal_signal(state: AgentState) -> AgentSignal:
    """Извлечь сигнал Юриста из состояния."""
    legal = state.get("legal_result")
    confidence = state.get("confidence_scores", {}).get("legal", 0.5)

    if not legal:
        return AgentSignal(
            agent_name="legal",
            signal=0.5,
            confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["legal"],
            reasoning="Юридический анализ не проводился",
        )

    # Маппинг вердикта Юриста → сигнал
    verdict_signal_map = {
        "approved": 0.95,
        "approved_with_comments": 0.65,
        "rejected": 0.15,
        "dangerous": 0.05,
    }
    verdict = legal.get("verdict", "approved_with_comments")
    base_signal = verdict_signal_map.get(verdict, 0.5)

    # Корректировка на количество находок
    critical = legal.get("critical_count", 0)
    high = legal.get("high_count", 0)
    penalty = critical * 0.15 + high * 0.05
    signal = max(0.0, min(1.0, base_signal - penalty))

    key_findings = legal.get("blc_matches", [])[:3]

    return AgentSignal(
        agent_name="legal",
        signal=round(signal, 3),
        confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["legal"],
        reasoning=f"Вердикт: {verdict}, критических: {critical}, высоких: {high}",
        key_findings=key_findings,
    )


def extract_smeta_signal(state: AgentState) -> AgentSignal:
    """Извлечь сигнал Сметчика из состояния."""
    smeta = state.get("smeta_result")
    confidence = state.get("confidence_scores", {}).get("smeta", 0.5)

    if not smeta:
        return AgentSignal(
            agent_name="smeta",
            signal=0.5,
            confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["smeta"],
            reasoning="Расчёт стоимости не проводился",
        )

    # Маппинг маржи → сигнал
    margin = smeta.get("profit_margin_pct", 0)
    if margin > 40:
        signal = 0.95
    elif margin > 25:
        signal = 0.80
    elif margin > 15:
        signal = 0.65
    elif margin > 10:
        signal = 0.40
    elif margin > 0:
        signal = 0.20
    else:
        signal = 0.05

    key_findings = [f"margin_{margin:.1f}_pct"]
    if smeta.get("low_margin_positions"):
        key_findings.append(f"low_margin_{len(smeta['low_margin_positions'])}_positions")

    return AgentSignal(
        agent_name="smeta",
        signal=round(signal, 3),
        confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["smeta"],
        reasoning=f"Маржа: {margin:.1f}%, ФЕР покрытие: {smeta.get('fer_coverage_pct', 0):.0f}%",
        key_findings=key_findings,
    )


def extract_pto_signal(state: AgentState) -> AgentSignal:
    """Извлечь сигнал ПТО из состояния."""
    vor = state.get("vor_result")
    confidence = state.get("confidence_scores", {}).get("pto", 0.5)

    if not vor:
        return AgentSignal(
            agent_name="pto",
            signal=0.5,
            confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["pto"],
            reasoning="Извлечение ВОР не проводилось",
        )

    # Сигнал на основе уверенности ПТО и полноты ВОР
    vor_confidence = vor.get("confidence_score", 0.5)
    unit_mismatches = len(vor.get("unit_mismatches", []))

    signal = vor_confidence
    if unit_mismatches > 0:
        signal -= unit_mismatches * 0.05

    signal = max(0.0, min(1.0, signal))

    key_findings = [f"vor_positions_{vor.get('total_positions', 0)}"]
    if unit_mismatches:
        key_findings.append(f"unit_mismatches_{unit_mismatches}")

    return AgentSignal(
        agent_name="pto",
        signal=round(signal, 3),
        confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["pto"],
        reasoning=f"ВОР: {vor.get('total_positions', 0)} позиций, уверенность: {vor_confidence:.0%}",
        key_findings=key_findings,
    )


def extract_procurement_signal(state: AgentState) -> AgentSignal:
    """Извлечь сигнал Закупщика из состояния."""
    proc = state.get("procurement_result")
    confidence = state.get("confidence_scores", {}).get("procurement", 0.5)

    if not proc:
        return AgentSignal(
            agent_name="procurement",
            signal=0.5,
            confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["procurement"],
            reasoning="Анализ тендера не проводился",
        )

    decision = proc.get("decision", "watch")
    nmck_vs = proc.get("nmck_vs_market", 0)

    decision_signal_map = {
        "bid": 0.75,
        "watch": 0.45,
        "skip": 0.20,
    }
    signal = decision_signal_map.get(decision, 0.5)

    # Корректировка: НМЦК ниже рынка — тревожно
    if nmck_vs < -20:
        signal -= 0.15
    elif nmck_vs < -10:
        signal -= 0.05

    signal = max(0.0, min(1.0, signal))

    return AgentSignal(
        agent_name="procurement",
        signal=round(signal, 3),
        confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["procurement"],
        reasoning=f"Решение: {decision}, НМЦК vs рынок: {nmck_vs:+.1f}%",
        key_findings=[f"competitors_{proc.get('competitor_count', 0)}"],
    )


def extract_logistics_signal(state: AgentState) -> AgentSignal:
    """Извлечь сигнал Логиста из состояния."""
    logistics = state.get("logistics_result")
    confidence = state.get("confidence_scores", {}).get("logistics", 0.5)

    if not logistics:
        return AgentSignal(
            agent_name="logistics",
            signal=0.5,
            confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["logistics"],
            reasoning="Анализ логистики не проводился",
        )

    vendors = logistics.get("vendors_found", 0)
    delivery = logistics.get("delivery_available", False)

    if vendors >= 3 and delivery:
        signal = 0.80
    elif vendors >= 1 and delivery:
        signal = 0.60
    elif vendors >= 1:
        signal = 0.40
    else:
        signal = 0.20

    return AgentSignal(
        agent_name="logistics",
        signal=round(signal, 3),
        confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["logistics"],
        reasoning=f"Поставщиков: {vendors}, доставка: {'да' if delivery else 'нет'}",
        key_findings=[f"vendors_{vendors}"],
    )


# =============================================================================
# Weighted Scoring Engine
# =============================================================================

def compute_weighted_score(signals: List[AgentSignal]) -> WeightedScoringResult:
    """
    Рассчитать взвешенный скоринг по сигналам агентов.

    Formula:
        Score = Σ (signal × weight × confidence) / Σ (weight × confidence)

    Returns WeightedScoringResult with zone classification.
    """
    numerator = 0.0
    denominator = 0.0
    contributions = {}

    for s in signals:
        effective_weight = s.weight * s.confidence
        contribution = s.signal * effective_weight
        numerator += contribution
        denominator += effective_weight
        contributions[s.agent_name] = round(contribution, 4)

    if denominator == 0:
        normalized_score = 0.5
    else:
        normalized_score = numerator / denominator

    raw_score = numerator  # Сумма взвешенных сигналов

    # Зона
    if normalized_score >= GO_THRESHOLD:
        zone = "go_zone"
    elif normalized_score <= NO_GO_THRESHOLD:
        zone = "no_go_zone"
    else:
        zone = "grey_zone"

    return WeightedScoringResult(
        raw_score=round(raw_score, 4),
        normalized_score=round(normalized_score, 4),
        agent_contributions=contributions,
        zone=zone,
        go_threshold=GO_THRESHOLD,
        no_go_threshold=NO_GO_THRESHOLD,
    )


# =============================================================================
# Veto Engine
# =============================================================================

def check_veto_rules(state: AgentState, rules: List[VetoRule]) -> tuple[Optional[str], List[VetoRule]]:
    """
    Проверить veto-правила.

    Returns:
        (triggered_rule_id, updated_rules) — ID сработавшего правила или None
    """
    legal = state.get("legal_result") or {}
    smeta = state.get("smeta_result") or {}

    updated_rules = []

    for rule in rules:
        triggered = False

        if rule.rule_id == "veto_dangerous_verdict":
            triggered = legal.get("verdict") == "dangerous"

        elif rule.rule_id == "veto_margin_below_10":
            triggered = smeta.get("profit_margin_pct", 100) < 10

        elif rule.rule_id == "veto_critical_traps_3plus":
            triggered = legal.get("critical_count", 0) >= 3

        elif rule.rule_id == "veto_nmck_below_70pct":
            triggered = smeta.get("nmck_below_70pct", False)

        updated_rule = rule.model_copy(update={"triggered": triggered})
        updated_rules.append(updated_rule)

        if triggered:
            logger.warning(f"VETO triggered: {rule.rule_id} — {rule.rule_name}")
            return rule.rule_id, updated_rules

    return None, updated_rules


# =============================================================================
# LLM Reasoning (Grey Zone)
# =============================================================================

LLM_REASONING_PROMPT = """Ты — опытный руководитель строительной компании. Принимаешь решение о подаче на тендер.

Агенты дали тебе следующие сигналы (0 = точно не подавать, 1 = точно подавать):

{agent_signals_text}

Контекст тендера:
- Лот: {lot_id}
- НМЦК: {nmck} руб.
- Маржа: {margin_pct}%
- Критические юридические ловушки: {critical_count}
- Высокие юридические ловушки: {high_count}
- Ключевые риски: {key_risks}
- Уверенность агентов: {confidence_text}

Взвешенный скоринг: {score:.2f} (серая зона между 0.30 и 0.70)

Прими решение: GO (подавать), CONDITIONAL_GO (подавать с условиями), или NO_GO (не подавать).

Объясни свою логику шаг за шагом:
1. Какой риск самый критический?
2. Можно ли его митигировать?
3. Перевешивает ли потенциальная прибыль риски?
4. Что бы сделал опытный руководитель на твоём месте?

Формат ответа:
DECISION: [GO|CONDITIONAL_GO|NO_GO]
REASONING: [твоё пошаговое рассуждение]
CONDITIONS: [если CONDITIONAL_GO — список условий через точку с запятой]
RISKS: [топ-3 риска через точку с запятой]
OPPORTUNITIES: [топ-3 возможности через точку с запятой]
"""


async def invoke_llm_reasoning(
    llm: LLMEngine,
    state: AgentState,
    signals: List[AgentSignal],
    scoring: WeightedScoringResult,
) -> Dict[str, Any]:
    """Вызвать LLM-рассуждение для grey zone."""
    agent_signals_text = "\n".join(
        f"- {s.agent_name}: сигнал={s.signal:.2f}, "
        f"уверенность={s.confidence:.2f}, "
        f"вес={s.weight:.2f}, "
        f"обоснование: {s.reasoning}"
        for s in signals
    )

    legal = state.get("legal_result") or {}
    smeta = state.get("smeta_result") or {}

    confidence_text = ", ".join(
        f"{s.agent_name}={s.confidence:.0%}" for s in signals
    )

    key_risks = []
    for s in signals:
        key_risks.extend(s.key_findings[:2])

    prompt = LLM_REASONING_PROMPT.format(
        agent_signals_text=agent_signals_text,
        lot_id=state.get("current_lot_id", "N/A"),
        nmck=f"{smeta.get('nmck', 0):,.0f}",
        margin_pct=f"{smeta.get('profit_margin_pct', 0):.1f}",
        critical_count=legal.get("critical_count", 0),
        high_count=legal.get("high_count", 0),
        key_risks="; ".join(key_risks) if key_risks else "нет",
        confidence_text=confidence_text,
        score=scoring.normalized_score,
    )

    messages = [
        {"role": "system", "content": "Ты опытный руководитель строительной субподрядной компании. Отвечаешь строго в заданном формате."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm.safe_chat(
            "pm",
            messages,
            fallback_response="DECISION: NO_GO\nREASONING: LLM unavailable, defaulting to safe decision\nCONDITIONS: \nRISKS: \nOPPORTUNITIES: ",
        )
        return _parse_llm_response(response)
    except Exception as e:
        logger.error(f"LLM reasoning failed: {e}")
        return {
            "decision": "NO_GO",
            "reasoning": f"LLM reasoning failed: {e}",
            "conditions": [],
            "risks": [],
            "opportunities": [],
        }


def _parse_llm_response(response: str) -> Dict[str, Any]:
    """Парсинг ответа LLM в структурированный формат."""
    result = {
        "decision": "NO_GO",
        "reasoning": "",
        "conditions": [],
        "risks": [],
        "opportunities": [],
    }

    lines = response.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.upper().startswith("DECISION:"):
            decision = line.split(":", 1)[1].strip().upper()
            if decision in ("GO", "CONDITIONAL_GO", "NO_GO"):
                result["decision"] = decision
        elif line.upper().startswith("REASONING:"):
            result["reasoning"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CONDITIONS:"):
            text = line.split(":", 1)[1].strip()
            result["conditions"] = [c.strip() for c in text.split(";") if c.strip()]
        elif line.upper().startswith("RISKS:"):
            text = line.split(":", 1)[1].strip()
            result["risks"] = [r.strip() for r in text.split(";") if r.strip()]
        elif line.upper().startswith("OPPORTUNITIES:"):
            text = line.split(":", 1)[1].strip()
            result["opportunities"] = [o.strip() for o in text.split(";") if o.strip()]

    return result


# =============================================================================
# Risk Level Calculator
# =============================================================================

def calculate_risk_level(state: AgentState, scoring: WeightedScoringResult) -> RiskLevel:
    """Рассчитать общий уровень риска тендера."""
    legal = state.get("legal_result") or {}
    smeta = state.get("smeta_result") or {}

    critical = legal.get("critical_count", 0)
    high = legal.get("high_count", 0)
    margin = smeta.get("profit_margin_pct", 100)

    if critical >= 3 or margin < 5 or scoring.normalized_score < 0.2:
        return RiskLevel.CRITICAL
    elif critical >= 1 or high >= 3 or margin < 15 or scoring.normalized_score < 0.4:
        return RiskLevel.HIGH
    elif high >= 1 or margin < 25 or scoring.normalized_score < 0.6:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


# =============================================================================
# Hermes Router (Main Class)
# =============================================================================

class HermesRouter:
    """
    Гибридный роутер принятия решений Hermes.

    3-этапная модель:
    1. Весовой скоринг → GO / GREY_ZONE / NO_GO
    2. LLM-рассуждение → только для grey zone
    3. Veto-правила → override любых решений
    """

    def __init__(
        self,
        llm_engine: Optional[LLMEngine] = None,
        agent_weights: Optional[Dict[str, float]] = None,
        veto_rules: Optional[List[VetoRule]] = None,
        go_threshold: float = GO_THRESHOLD,
        no_go_threshold: float = NO_GO_THRESHOLD,
    ):
        self._llm = llm_engine
        self._weights = agent_weights or DEFAULT_AGENT_WEIGHTS
        self._veto_rules = veto_rules or DEFAULT_VETO_RULES
        self._go_threshold = go_threshold
        self._no_go_threshold = no_go_threshold

    async def decide(self, state: AgentState) -> VerdictReport:
        """
        Принять решение по тендеру на основе состояния конвейера.

        Args:
            state: Текущее состояние конвейера (AgentState v2)

        Returns:
            VerdictReport — структурированный отчёт о решении
        """
        lot_id = state.get("current_lot_id", "UNKNOWN")
        builder = VerdictReportBuilder(lot_id=lot_id, project_id=state.get("project_id"))

        # ── LLM Fallback Warning ──
        if state.get("_llm_fallback_triggered"):
            fallback_agents = state.get("_llm_fallback_agents", [])
            builder.add_warning(
                f"LLM fallback triggered for agents: {', '.join(fallback_agents) or 'unknown'}. "
                f"Verdict is based on fallback responses and may be unreliable."
            )

        # ── Этап 1: Извлечь сигналы агентов ──
        signals = [
            extract_legal_signal(state),
            extract_smeta_signal(state),
            extract_pto_signal(state),
            extract_procurement_signal(state),
            extract_logistics_signal(state),
        ]
        for s in signals:
            builder.add_agent_signal(s)

        # ── Этап 2: Весовой скоринг ──
        scoring = compute_weighted_score(signals)
        builder.set_scoring(scoring)

        # ── Этап 3: Veto-правила ──
        veto_id, veto_rules = check_veto_rules(state, self._veto_rules)
        for rule in veto_rules:
            builder.add_veto_rule(rule)

        if veto_id:
            # Veto сработало → NO_GO, override
            builder.set_veto_triggered(veto_id)
            builder.set_verdict(
                verdict=TenderVerdict.NO_GO,
                method=DecisionMethod.VETO_OVERRIDE,
                risk_level=RiskLevel.CRITICAL,
            )
            veto_rule = next(r for r in veto_rules if r.rule_id == veto_id)
            builder.set_summary(
                f"Veto-правило «{veto_rule.rule_name}» сработало. "
                f"Подача на тендер не рекомендуется. {veto_rule.description}"
            )
            builder.add_risk(veto_rule.description)

            # Записать в состояние
            _update_state_decision(state, "no_go", scoring, signals, "veto_override", veto_id)
            return builder.build()

        # ── Этап 4: Определить зону решения ──
        risk_level = calculate_risk_level(state, scoring)

        if scoring.zone == "go_zone":
            # Чистый GO
            builder.set_verdict(
                verdict=TenderVerdict.GO,
                method=DecisionMethod.WEIGHT_SCORING,
                risk_level=risk_level,
            )
            builder.set_summary(
                f"Взвешенный скоринг: {scoring.normalized_score:.2f} (зона GO). "
                f"Рекомендуется подача на тендер."
            )
            _update_state_decision(state, "go", scoring, signals, "weight_scoring")

        elif scoring.zone == "no_go_zone":
            # Чистый NO_GO
            builder.set_verdict(
                verdict=TenderVerdict.NO_GO,
                method=DecisionMethod.WEIGHT_SCORING,
                risk_level=risk_level,
            )
            builder.set_summary(
                f"Взвешенный скоринг: {scoring.normalized_score:.2f} (зона NO GO). "
                f"Подача на тендер не рекомендуется."
            )
            _update_state_decision(state, "no_go", scoring, signals, "weight_scoring")

        else:
            # ── Серая зона: LLM-рассуждение ──
            if self._llm:
                llm_result = await invoke_llm_reasoning(self._llm, state, signals, scoring)
                decision_str = llm_result.get("decision", "NO_GO")
                verdict_map = {
                    "GO": TenderVerdict.GO,
                    "CONDITIONAL_GO": TenderVerdict.CONDITIONAL_GO,
                    "NO_GO": TenderVerdict.NO_GO,
                }
                verdict = verdict_map.get(decision_str, TenderVerdict.NO_GO)

                builder.set_verdict(
                    verdict=verdict,
                    method=DecisionMethod.LLM_REASONING,
                    risk_level=risk_level,
                )
                builder.set_llm_reasoning(llm_result.get("reasoning", ""))
                builder.set_summary(
                    f"Серая зона (скоринг: {scoring.normalized_score:.2f}). "
                    f"LLM-рассуждение: {llm_result.get('reasoning', 'N/A')[:200]}"
                )
                for cond in llm_result.get("conditions", []):
                    builder.add_condition(cond)
                for risk in llm_result.get("risks", []):
                    builder.add_risk(risk)
                for opp in llm_result.get("opportunities", []):
                    builder.add_opportunity(opp)

                _update_state_decision(
                    state,
                    verdict.value,
                    scoring,
                    signals,
                    "llm_reasoning",
                )
            else:
                # LLM недоступен — консервативный подход
                builder.set_verdict(
                    verdict=TenderVerdict.NO_GO,
                    method=DecisionMethod.WEIGHT_SCORING,
                    risk_level=risk_level,
                )
                builder.set_summary(
                    f"Серая зона (скоринг: {scoring.normalized_score:.2f}). "
                    f"LLM недоступен — консервативное решение: не подавать."
                )
                _update_state_decision(state, "no_go", scoring, signals, "weight_scoring")

        # ── Дополнительные данные ──
        legal = state.get("legal_result") or {}
        if legal.get("critical_count", 0) > 0 or legal.get("high_count", 0) > 0:
            builder.set_protocol(needed=True, items_count=legal.get("protocol_items_count", 0))
            builder.add_recommended_action("Подготовить протокол разногласий")

        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            builder.add_recommended_action("Провести дополнительную экспертизу договора")

        return builder.build()


# =============================================================================
# State Update Helper
# =============================================================================

def _update_state_decision(
    state: AgentState,
    verdict: str,
    scoring: WeightedScoringResult,
    signals: List[AgentSignal],
    decided_via: str,
    veto_id: Optional[str] = None,
) -> None:
    """Обновить AgentState с записью решения Hermes."""
    now = datetime.utcnow().isoformat()

    agent_signals = {s.agent_name: s.signal for s in signals}
    agent_weights = {s.agent_name: s.weight for s in signals}
    confidence_scores = {s.agent_name: s.confidence for s in signals}

    decision = HermesDecision(
        verdict=verdict,
        weighted_score=scoring.normalized_score,
        agent_signals=agent_signals,
        agent_weights=agent_weights,
        confidence_scores=confidence_scores,
        veto_triggered=veto_id,
        llm_reasoning=None,  # Заполняется отдельно если LLM
        decided_at=now,
        decided_via=decided_via,
    )

    state["hermes_decision"] = decision
    state["confidence_scores"] = {**state.get("confidence_scores", {}), **confidence_scores}
    state["updated_at"] = now
