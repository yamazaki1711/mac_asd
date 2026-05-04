"""
ASD v12.0 — Rule-Based Fallback Router.

Работает когда PM-модель (Llama 70B) недоступна.
Принимает решения на основе правил (weighted scoring + veto), без LLM.

Использует те же веса агентов и veto-правила что и PM Agent,
но пропускает этап LLM-рассуждения (grey zone → NO_GO по умолчанию).

Usage:
    from src.core.fallback_router import fallback_decide

    # Когда Llama 70B упала:
    report = fallback_decide(state)

    # Или интегрировать в PM.evaluate_result():
    if not self._llm:
        return fallback_decide(state)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.schemas.verdict import (
        AgentSignal,
        DecisionMethod,
        RiskLevel,
        TenderVerdict,
        VerdictReport,
        VerdictReportBuilder,
    )


# =============================================================================
# Fallback Decision
# =============================================================================

def fallback_decide(state: Dict[str, Any]) -> "VerdictReport":
    """
    Принять решение по тендеру без LLM.

    Логика:
    1. Весовой скоринг → GO если >= 0.70, NO_GO если <= 0.30
    2. Для серой зоны (0.30-0.70): NO_GO по умолчанию
       (принцип предосторожности — без LLM не рискуем)
    3. Veto-правила применяются всегда

    Args:
        state: Состояние конвейера с результатами агентов

    Returns:
        VerdictReport с решением

    Raises:
        ValueError: если state не содержит minimal required данных
    """
    from src.core.pm_agent import (
        DEFAULT_AGENT_WEIGHTS,
        DEFAULT_VETO_RULES,
        compute_weighted_score,
        check_veto_rules,
        extract_legal_signal,
        extract_smeta_signal,
        extract_pto_signal,
        extract_procurement_signal,
        extract_logistics_signal,
        calculate_risk_level,
    )
    from src.schemas.verdict import (
        DecisionMethod,
        RiskLevel,
        TenderVerdict,
        VerdictReportBuilder,
    )

    lot_id = state.get("current_lot_id", "UNKNOWN")
    builder = VerdictReportBuilder(lot_id=lot_id, project_id=state.get("project_id"))

    # ── Добавить предупреждение о fallback ──
    builder.add_warning(
        "FALLBACK ROUTER ACTIVE: PM model (Llama 70B) is unavailable. "
        "Decision made by rule-based engine without LLM reasoning. "
        "Grey-zone cases default to NO_GO for safety."
    )

    # ── Этап 1: Извлечь сигналы ──
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
    veto_id, veto_rules = check_veto_rules(state, DEFAULT_VETO_RULES)
    for rule in veto_rules:
        builder.add_veto_rule(rule)

    if veto_id:
        builder.set_veto_triggered(veto_id)
        builder.set_verdict(
            verdict=TenderVerdict.NO_GO,
            method=DecisionMethod.VETO_OVERRIDE,
            risk_level=RiskLevel.CRITICAL,
        )
        veto_rule = next(r for r in veto_rules if r.rule_id == veto_id)
        builder.set_summary(
            f"[FALLBACK] Veto-правило «{veto_rule.rule_name}» сработало. "
            f"Подача на тендер не рекомендуется. {veto_rule.description}"
        )
        builder.add_risk(veto_rule.description)

        _add_fallback_note(builder)
        return builder.build()

    # ── Этап 4: Определение зоны (без LLM) ──
    risk_level = calculate_risk_level(state, scoring)

    if scoring.zone == "go_zone":
        # Чистый GO — все агенты согласны, можно без LLM
        builder.set_verdict(
            verdict=TenderVerdict.GO,
            method=DecisionMethod.WEIGHT_SCORING,
            risk_level=risk_level,
        )
        builder.set_summary(
            f"[FALLBACK] Взвешенный скоринг: {scoring.normalized_score:.2f} (зона GO). "
            f"Все веса агентов указывают на успешный тендер. Рекомендуется подача."
        )

    elif scoring.zone == "no_go_zone":
        # Чистый NO_GO
        builder.set_verdict(
            verdict=TenderVerdict.NO_GO,
            method=DecisionMethod.WEIGHT_SCORING,
            risk_level=risk_level,
        )
        builder.set_summary(
            f"[FALLBACK] Взвешенный скоринг: {scoring.normalized_score:.2f} (зона NO GO). "
            f"Подача на тендер не рекомендуется."
        )

    else:
        # Серая зона → NO_GO по принципу предосторожности
        builder.set_verdict(
            verdict=TenderVerdict.NO_GO,
            method=DecisionMethod.WEIGHT_SCORING,
            risk_level=RiskLevel.HIGH if risk_level != RiskLevel.CRITICAL else risk_level,
        )
        builder.set_summary(
            f"[FALLBACK] Взвешенный скоринг: {scoring.normalized_score:.2f} (серая зона). "
            f"Без LLM-рассуждения решение НЕ может быть принято безопасно. "
            f"Рекомендация: NO_GO (принцип предосторожности). "
            f"Дождитесь восстановления PM-модели для повторного анализа."
        )
        builder.add_risk("Решение в серой зоне без LLM — требуется ручная проверка")
        builder.add_condition("Дождаться восстановления Llama 70B и перезапустить анализ")

    _add_fallback_note(builder)
    return builder.build()


def _add_fallback_note(builder: VerdictReportBuilder):
    """Добавить стандартные рекомендации для fallback-режима."""
    builder.add_recommended_action(
        "Проверить статус PM-модели (Llama 3.3 70B) — health check"
    )
    builder.add_recommended_action(
        "После восстановления модели перезапустить конвейер для полного анализа"
    )
    builder.add_recommended_action(
        "Решение принято в fallback-режиме — требуется ручная верификация"
    )


# =============================================================================
# Health-Aware Router
# =============================================================================

class HealthAwareRouter:
    """
    Роутер с проверкой здоровья PM-модели.

    Автоматически переключается на fallback_decide() если Llama 70B недоступна.
    """

    def __init__(self, llm_engine=None):
        self._llm = llm_engine
        self._pm_healthy = True
        self._consecutive_failures = 0
        self._max_failures_before_fallback = 2

    async def is_pm_healthy(self) -> bool:
        """Проверить доступность PM-модели."""
        if not self._llm:
            return False

        try:
            await self._llm.chat(
                "pm",
                [{"role": "user", "content": "ping"}],
                temperature=0.0,
                num_ctx=256,
                keep_alive="0m",
            )
            self._pm_healthy = True
            self._consecutive_failures = 0
            return True
        except (OSError, ValueError, RuntimeError) as e:
            self._consecutive_failures += 1
            logger.warning("PM health check failed (%d/%d): %s",
                          self._consecutive_failures, self._max_failures_before_fallback, e)
            if self._consecutive_failures >= self._max_failures_before_fallback:
                self._pm_healthy = False
            return False

    async def decide(self, state: Dict[str, Any]) -> VerdictReport:
        """
        Принять решение с автоматическим fallback.

        Если PM-модель доступна → rule-based fallback с сигналами + veto.
        Если нет → использует rule-based fallback.
        """
        if not await self.is_pm_healthy():
            return fallback_decide(state)

        # PM доступен — используем полный PM с weighted scoring
        from src.core.pm_agent import ProjectManager
        pm = ProjectManager(llm_engine=self._llm)
        # Fallback: используем rule-based decide через сигналы + veto
        return fallback_decide(state)


# =============================================================================
# Quick API
# =============================================================================

def quick_health_check(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Быстрая проверка: можно ли принять решение без LLM?

    Returns:
        {"can_decide": bool, "zone": str, "recommendation": str}
    """
    from src.core.pm_agent import (
        DEFAULT_AGENT_WEIGHTS,
        DEFAULT_VETO_RULES,
        compute_weighted_score,
        check_veto_rules,
        extract_legal_signal,
        extract_smeta_signal,
        extract_pto_signal,
        extract_procurement_signal,
        extract_logistics_signal,
    )

    signals = [
        extract_legal_signal(state),
        extract_smeta_signal(state),
        extract_pto_signal(state),
        extract_procurement_signal(state),
        extract_logistics_signal(state),
    ]

    scoring = compute_weighted_score(signals)
    veto_id, _ = check_veto_rules(state, DEFAULT_VETO_RULES)

    if veto_id:
        return {
            "can_decide": True,
            "zone": "veto",
            "score": scoring.normalized_score,
            "recommendation": "NO_GO (veto triggered)",
        }

    if scoring.zone == "go_zone":
        return {
            "can_decide": True,
            "zone": "go_zone",
            "score": scoring.normalized_score,
            "recommendation": "GO — можно принимать без LLM",
        }

    if scoring.zone == "no_go_zone":
        return {
            "can_decide": True,
            "zone": "no_go_zone",
            "score": scoring.normalized_score,
            "recommendation": "NO_GO — можно принимать без LLM",
        }

    return {
        "can_decide": False,
        "zone": "grey_zone",
        "score": scoring.normalized_score,
        "recommendation": "Серая зона — требуется LLM или ручное решение",
    }
