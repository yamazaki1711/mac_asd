"""
ASD v12.0 — Verdict Report Schema.

Итоговый отчёт о решении по тендеру.
Генерируется Hermes после сбора сигналов от всех агентов.

Содержит:
- Взвешенный скоринг агентов
- Veto-правила (hard constraints)
- LLM-рассуждение (для grey zone)
- Финальный вердикт с обоснованием
"""

from datetime import datetime, timezone, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums
# =============================================================================

class TenderVerdict(str, Enum):
    """Итоговое решение по тендеру."""
    GO = "go"                                    # Подавать без оговорок
    CONDITIONAL_GO = "conditional_go"            # Подавать с протоколом разногласий
    NO_GO = "no_go"                              # Не подавать
    DEFERRED = "deferred"                        # Отложить решение (нужна доп. информация)


class DecisionMethod(str, Enum):
    """Метод принятия решения."""
    WEIGHT_SCORING = "weight_scoring"            # Весовой скоринг (detached, fast)
    LLM_REASONING = "llm_reasoning"              # LLM-рассуждение (grey zone)
    VETO_OVERRIDE = "veto_override"              # Veto-правило (hard constraint)
    MANUAL_OVERRIDE = "manual_override"          # Ручное переопределение пользователем


class RiskLevel(str, Enum):
    """Общий уровень риска тендера."""
    LOW = "low"                                  # Минимальные риски
    MEDIUM = "medium"                            # Умеренные риски
    HIGH = "high"                                # Существенные риски
    CRITICAL = "critical"                        # Критические риски


# =============================================================================
# Agent Signal
# =============================================================================

class AgentSignal(BaseModel):
    """Сигнал от одного агента для принятия решения."""
    agent_name: str = Field(
        description="Имя агента (legal, smeta, pto, procurement, logistics)"
    )
    signal: float = Field(
        ge=0.0, le=1.0,
        description="Сигнал агента: 1.0 = сильный GO, 0.0 = сильный NO GO"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Уверенность агента в своём сигнале"
    )
    weight: float = Field(
        ge=0.0, le=1.0,
        description="Вес агента в скоринге (сумма всех весов = 1.0)"
    )
    reasoning: str = Field(
        default="",
        description="Краткое обоснование сигнала от агента"
    )
    key_findings: List[str] = Field(
        default_factory=list,
        description="Ключевые находки агента (top 3)"
    )


# =============================================================================
# Veto Rule
# =============================================================================

class VetoRule(BaseModel):
    """Veto-правило — hard constraint, отменяющее решение."""
    rule_id: str = Field(
        description="ID правила (например, 'veto_dangerous_verdict')"
    )
    rule_name: str = Field(
        description="Человекочитаемое название"
    )
    description: str = Field(
        description="Описание правила"
    )
    condition: str = Field(
        description="Условие срабатывания (формальное)"
    )
    triggered: bool = Field(
        default=False,
        description="Сработало ли правило"
    )
    override_verdict: TenderVerdict = Field(
        default=TenderVerdict.NO_GO,
        description="Вердикт при срабатывании правила"
    )


# =============================================================================
# Weighted Scoring Result
# =============================================================================

class WeightedScoringResult(BaseModel):
    """Результат весового скоринга."""
    raw_score: float = Field(
        description="Сырой взвешенный скоринг (0.0 - 1.0)"
    )
    normalized_score: float = Field(
        description="Нормализованный скоринг с учётом confidence"
    )
    agent_contributions: Dict[str, float] = Field(
        default_factory=dict,
        description="Вклад каждого агента в итоговый скоринг"
    )
    zone: str = Field(
        description="Зона решения: 'go_zone' | 'grey_zone' | 'no_go_zone'"
    )
    go_threshold: float = Field(
        default=0.7,
        description="Порог для GO"
    )
    no_go_threshold: float = Field(
        default=0.3,
        description="Порог для NO GO"
    )


# =============================================================================
# Verdict Report (Main)
# =============================================================================

class VerdictReport(BaseModel):
    """
    Итоговый отчёт о решении по тендеру.

    Генерируется Hermes как финальный артефакт конвейера.
    Содержит полную трассировку принятия решения.
    """
    # ── Идентификация ──
    report_id: str = Field(
        description="UUID отчёта"
    )
    lot_id: str = Field(
        description="ID тендерного лота"
    )
    project_id: Optional[int] = Field(
        default=None,
        description="ID проекта в БД"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Дата/время создания (ISO 8601)"
    )

    # ── Решение ──
    verdict: TenderVerdict = Field(
        description="Итоговый вердикт: go / conditional_go / no_go / deferred"
    )
    risk_level: RiskLevel = Field(
        description="Общий уровень риска"
    )
    decision_method: DecisionMethod = Field(
        description="Метод принятия решения"
    )

    # ── Весовой скоринг ──
    scoring: Optional[WeightedScoringResult] = Field(
        default=None,
        description="Результат весового скоринга"
    )

    # ── Сигналы агентов ──
    agent_signals: List[AgentSignal] = Field(
        default_factory=list,
        description="Сигналы от всех агентов"
    )

    # ── Veto-правила ──
    veto_rules: List[VetoRule] = Field(
        default_factory=list,
        description="Проверенные veto-правила"
    )
    veto_triggered: Optional[str] = Field(
        default=None,
        description="ID сработавшего veto-правила (если есть)"
    )

    # ── LLM рассуждение ──
    llm_reasoning: Optional[str] = Field(
        default=None,
        description="Chain-of-thought рассуждение Hermes (только для grey zone)"
    )

    # ── Обоснование ──
    summary: str = Field(
        description="Краткое человекочитаемое обоснование решения"
    )
    conditions: List[str] = Field(
        default_factory=list,
        description="Условия (для conditional_go) — что исправить в протоколе"
    )
    key_risks: List[str] = Field(
        default_factory=list,
        description="Топ-3 ключевых риска"
    )
    key_opportunities: List[str] = Field(
        default_factory=list,
        description="Топ-3 ключевых возможности/преимущества"
    )

    # ── Рекомендации ──
    recommended_actions: List[str] = Field(
        default_factory=list,
        description="Рекомендуемые действия"
    )
    protocol_needed: bool = Field(
        default=False,
        description="Необходим протокол разногласий"
    )
    protocol_items_count: int = Field(
        default=0,
        description="Количество пунктов для протокола"
    )

    # ── Метаданные ──
    pipeline_duration_ms: Optional[int] = Field(
        default=None,
        description="Общее время конвейера (мс)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Некритические предупреждения (LLM fallback, превышение лимитов и т.д.)"
    )
    schema_version: str = Field(
        default="1.0",
        description="Версия схемы отчёта"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_id": "a1b2c3d4",
                "lot_id": "T-2026-0451",
                "project_id": 42,
                "verdict": "conditional_go",
                "risk_level": "high",
                "decision_method": "weight_scoring",
                "scoring": {
                    "raw_score": 0.52,
                    "normalized_score": 0.48,
                    "zone": "grey_zone",
                    "go_threshold": 0.7,
                    "no_go_threshold": 0.3,
                },
                "agent_signals": [
                    {
                        "agent_name": "legal",
                        "signal": 0.3,
                        "confidence": 0.85,
                        "weight": 0.35,
                        "reasoning": "3 критических ловушки в оплате",
                        "key_findings": ["payment_01", "penalty_03", "scope_05"],
                    },
                    {
                        "agent_name": "smeta",
                        "signal": 0.8,
                        "confidence": 0.75,
                        "weight": 0.25,
                        "reasoning": "Маржа 32%, ФЕР позиции покрыты",
                        "key_findings": ["margin_32_pct", "fer_coverage_95_pct"],
                    },
                ],
                "veto_triggered": None,
                "summary": "Тендер рентабелен (маржа 32%), но содержит 3 критических юридических ловушки. Рекомендуется подача с протоколом разногласий.",
                "conditions": [
                    "Удалить пункт о удержании 10% без обоснования",
                    "Ограничить неустойку ставкой ЦБ РФ",
                    "Установить срок оплаты не более 30 дней",
                ],
                "protocol_needed": True,
                "protocol_items_count": 7,
            }
        }
    )


# =============================================================================
# Verdict Report Builder
# =============================================================================

class VerdictReportBuilder:
    """Строитель VerdictReport — пошаговое формирование отчёта."""

    def __init__(self, lot_id: str, project_id: Optional[int] = None):
        self._lot_id = lot_id
        self._project_id = project_id
        self._agent_signals: List[AgentSignal] = []
        self._veto_rules: List[VetoRule] = []
        self._scoring: Optional[WeightedScoringResult] = None
        self._verdict: Optional[TenderVerdict] = None
        self._risk_level: Optional[RiskLevel] = None
        self._decision_method: Optional[DecisionMethod] = None
        self._llm_reasoning: Optional[str] = None
        self._summary: str = ""
        self._conditions: List[str] = []
        self._key_risks: List[str] = []
        self._key_opportunities: List[str] = []
        self._recommended_actions: List[str] = []
        self._protocol_needed: bool = False
        self._protocol_items_count: int = 0
        self._veto_triggered: Optional[str] = None
        self._warnings: List[str] = []

    def add_agent_signal(self, signal: AgentSignal) -> "VerdictReportBuilder":
        self._agent_signals.append(signal)
        return self

    def add_veto_rule(self, rule: VetoRule) -> "VerdictReportBuilder":
        self._veto_rules.append(rule)
        return self

    def set_scoring(self, scoring: WeightedScoringResult) -> "VerdictReportBuilder":
        self._scoring = scoring
        return self

    def set_verdict(
        self,
        verdict: TenderVerdict,
        method: DecisionMethod,
        risk_level: RiskLevel,
    ) -> "VerdictReportBuilder":
        self._verdict = verdict
        self._decision_method = method
        self._risk_level = risk_level
        return self

    def set_llm_reasoning(self, reasoning: str) -> "VerdictReportBuilder":
        self._llm_reasoning = reasoning
        return self

    def set_summary(self, summary: str) -> "VerdictReportBuilder":
        self._summary = summary
        return self

    def add_condition(self, condition: str) -> "VerdictReportBuilder":
        self._conditions.append(condition)
        return self

    def add_risk(self, risk: str) -> "VerdictReportBuilder":
        self._key_risks.append(risk)
        return self

    def add_opportunity(self, opportunity: str) -> "VerdictReportBuilder":
        self._key_opportunities.append(opportunity)
        return self

    def add_recommended_action(self, action: str) -> "VerdictReportBuilder":
        self._recommended_actions.append(action)
        return self

    def set_protocol(self, needed: bool, items_count: int = 0) -> "VerdictReportBuilder":
        self._protocol_needed = needed
        self._protocol_items_count = items_count
        return self

    def set_veto_triggered(self, rule_id: str) -> "VerdictReportBuilder":
        self._veto_triggered = rule_id
        return self

    def add_warning(self, warning: str) -> "VerdictReportBuilder":
        """Добавить некритическое предупреждение (LLM fallback и т.д.)."""
        self._warnings.append(warning)
        return self

    def build(self) -> VerdictReport:
        """Собирает и валидирует VerdictReport."""
        import uuid

        if self._verdict is None:
            raise ValueError("Verdict must be set before building report")

        return VerdictReport(
            report_id=str(uuid.uuid4())[:8],
            lot_id=self._lot_id,
            project_id=self._project_id,
            verdict=self._verdict,
            risk_level=self._risk_level or RiskLevel.MEDIUM,
            decision_method=self._decision_method or DecisionMethod.WEIGHT_SCORING,
            scoring=self._scoring,
            agent_signals=self._agent_signals,
            veto_rules=self._veto_rules,
            veto_triggered=self._veto_triggered,
            llm_reasoning=self._llm_reasoning,
            summary=self._summary,
            conditions=self._conditions,
            key_risks=self._key_risks,
            key_opportunities=self._key_opportunities,
            recommended_actions=self._recommended_actions,
            protocol_needed=self._protocol_needed,
            protocol_items_count=self._protocol_items_count,
            warnings=self._warnings,
        )
