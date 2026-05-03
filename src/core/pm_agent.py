"""
ASD v12.0 — Project Manager Agent (Руководитель проекта).

Динамический оркестратор: строит план работ, диспетчеризует агентов,
контролирует исполнение и отслеживает дельту относительно эталона ИД.

В отличие от статического Hermes-роутера, PM:
  - Строит WorkPlan на основе анализа задачи (goal → tasks → agents)
  - Динамически выбирает следующего агента на основе зависимостей и приоритетов
  - Оценивает результаты агентов и принимает решение: принять / переделать / пропустить
  - Отслеживает compliance_delta — что ещё не готово относительно эталона
  - Использует Llama 3.3 70B для стратегического планирования
  - Работает от конечной цели к текущему состоянию (goal-oriented)

Model: Llama 3.3 70B 4-bit (mac_studio) / gemma4:31b-cloud (dev_linux)

Usage:
    from src.core.pm_agent import ProjectManager

    pm = ProjectManager(llm_engine=llm_engine, completeness_matrix=matrix)
    plan = await pm.create_plan(state)
    next_agent = pm.dispatch(state, plan)
    accepted = pm.evaluate_result(state, plan, task_result)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.core.llm_engine import LLMEngine
from src.schemas.verdict import (
    AgentSignal,
    RiskLevel,
    VetoRule,
    WeightedScoringResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"          # Зависимости не выполнены


class PlanStatus(str, Enum):
    DRAFT = "draft"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ADAPTED = "adapted"          # План перестроен после неудачи
    ABORTED = "aborted"


class EvaluationVerdict(str, Enum):
    ACCEPT = "accept"
    RETRY = "retry"              # Переделать с уточнением
    RETRY_OTHER_AGENT = "retry_other"  # Передать другому агенту
    SKIP = "skip"                # Пропустить (не критично)
    ABORT = "abort"              # Прервать весь план


# =============================================================================
# Task Node
# =============================================================================

class TaskNode:
    """Узел плана работ — одна задача для одного агента."""

    __slots__ = (
        "task_id", "task_type", "description", "agent",
        "depends_on", "status", "priority", "deadline",
        "result_summary", "confidence_required", "retry_count",
        "max_retries", "started_at", "completed_at",
        "parallel_group",  # v12.0: группа параллельных задач ("analysis", "audit", "supply", "generation")
    )

    # Shared model agents (Gemma 4 31B) — LLM calls serialize on MLX
    _SHARED_MODEL_AGENTS = {"pto", "smeta", "legal", "procurement", "logistics"}

    def __init__(
        self,
        task_id: str,
        task_type: str,
        description: str,
        agent: str,
        depends_on: Optional[List[str]] = None,
        priority: int = 5,
        deadline: Optional[str] = None,
        confidence_required: float = 0.6,
        max_retries: int = 2,
        parallel_group: Optional[str] = None,
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.description = description
        self.agent = agent
        self.depends_on = depends_on or []
        self.status = TaskStatus.PENDING.value
        self.priority = priority
        self.deadline = deadline
        self.result_summary: Optional[str] = None
        self.confidence_required = confidence_required
        self.retry_count = 0
        self.max_retries = max_retries
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.parallel_group = parallel_group  # e.g., "analysis", "audit", "supply"

    @property
    def uses_shared_model(self) -> bool:
        """True if this agent shares Gemma 4 31B with other agents."""
        return self.agent in self._SHARED_MODEL_AGENTS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "description": self.description,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "status": self.status,
            "priority": self.priority,
            "deadline": self.deadline,
            "result_summary": self.result_summary,
            "confidence_required": self.confidence_required,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parallel_group": self.parallel_group,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskNode":
        node = cls(
            task_id=d["task_id"],
            task_type=d["task_type"],
            description=d["description"],
            agent=d["agent"],
            depends_on=d.get("depends_on", []),
            priority=d.get("priority", 5),
            deadline=d.get("deadline"),
            confidence_required=d.get("confidence_required", 0.6),
            max_retries=d.get("max_retries", 2),
            parallel_group=d.get("parallel_group"),
        )
        node.status = d.get("status", TaskStatus.PENDING.value)
        node.result_summary = d.get("result_summary")
        node.retry_count = d.get("retry_count", 0)
        node.started_at = d.get("started_at")
        node.completed_at = d.get("completed_at")
        return node

    def mark_started(self) -> None:
        self.status = TaskStatus.IN_PROGRESS.value
        self.started_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, summary: str = "") -> None:
        self.status = TaskStatus.COMPLETED.value
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.result_summary = summary

    def mark_failed(self, reason: str = "") -> None:
        self.retry_count += 1
        if self.retry_count >= self.max_retries:
            self.status = TaskStatus.FAILED.value
        else:
            self.status = TaskStatus.PENDING.value  # Вернуть в очередь
        self.result_summary = reason

    def can_start(self, completed_task_ids: set) -> bool:
        """Проверяет, можно ли запустить задачу: все зависимости выполнены."""
        return all(dep in completed_task_ids for dep in self.depends_on)


# =============================================================================
# WorkPlan
# =============================================================================

class WorkPlan:
    """План работ, построенный PM на основе анализа задачи."""

    __slots__ = (
        "plan_id", "project_id", "goal", "tasks", "status",
        "compliance_target", "compliance_delta", "created_at", "updated_at",
        "pm_reasoning", "estimated_duration_hours",
    )

    def __init__(
        self,
        plan_id: str,
        project_id: int,
        goal: str,
        tasks: List[TaskNode],
        compliance_target: str = "344/пр",
        estimated_duration_hours: float = 0.0,
        pm_reasoning: str = "",
    ):
        self.plan_id = plan_id
        self.project_id = project_id
        self.goal = goal
        self.tasks = tasks
        self.status = PlanStatus.DRAFT.value
        self.compliance_target = compliance_target
        self.compliance_delta: Dict[str, str] = {}
        self.estimated_duration_hours = estimated_duration_hours
        self.pm_reasoning = pm_reasoning
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "tasks": [t.to_dict() for t in self.tasks],
            "status": self.status,
            "compliance_target": self.compliance_target,
            "compliance_delta": self.compliance_delta,
            "estimated_duration_hours": self.estimated_duration_hours,
            "pm_reasoning": self.pm_reasoning,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkPlan":
        plan = cls(
            plan_id=d["plan_id"],
            project_id=d["project_id"],
            goal=d["goal"],
            tasks=[TaskNode.from_dict(t) for t in d.get("tasks", [])],
            compliance_target=d.get("compliance_target", "344/пр"),
            estimated_duration_hours=d.get("estimated_duration_hours", 0.0),
            pm_reasoning=d.get("pm_reasoning", ""),
        )
        plan.status = d.get("status", PlanStatus.DRAFT.value)
        plan.compliance_delta = d.get("compliance_delta", {})
        plan.created_at = d.get("created_at", plan.created_at)
        plan.updated_at = d.get("updated_at", plan.updated_at)
        return plan

    def get_next_task(self) -> Optional[TaskNode]:
        """
        Выбрать следующую задачу для выполнения.
        Приоритет: готовые к запуску (все зависимости выполнены),
        сортировка по priority (desc), затем по deadline.
        """
        ready = self.get_parallel_ready_tasks()
        if not ready:
            return None
        return ready[0]

    def get_parallel_ready_tasks(self, max_parallel: int = 10) -> List[TaskNode]:
        """
        Возвращает ВСЕ готовые к запуску задачи (зависимости выполнены, статус PENDING).

        Используется для Send() fan-out: PM запускает все независимые задачи параллельно.
        Архив (archive/delo) на E4B может работать истинно параллельно с shared-агентами.
        Shared-агенты (Gemma 4 31B) сериализуют LLM-вызовы, но I/O перекрывается через asyncio.

        RAM throttle: WARNING → max 2, CRITICAL → max 1.
        """
        completed_ids = {
            t.task_id
            for t in self.tasks
            if t.status == TaskStatus.COMPLETED.value
        }

        ready = [
            t
            for t in self.tasks
            if t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value)
            and t.can_start(completed_ids)
        ]

        if not ready:
            return []

        # Сортируем: приоритет выше → раньше
        ready.sort(key=lambda t: (-t.priority, t.deadline or "9999-12-31"))

        return ready[:max_parallel]

    def get_completion_pct(self) -> float:
        if not self.tasks:
            return 0.0
        completed = sum(
            1 for t in self.tasks if t.status == TaskStatus.COMPLETED.value
        )
        return round(completed / len(self.tasks) * 100, 1)

    def get_failed_tasks(self) -> List[TaskNode]:
        return [t for t in self.tasks if t.status == TaskStatus.FAILED.value]

    def update_compliance_delta(self, delta: Dict[str, str]) -> None:
        self.compliance_delta = delta
        self.updated_at = datetime.now(timezone.utc).isoformat()


# =============================================================================
# PM Planning Prompt
# =============================================================================

PM_PLANNING_PROMPT = """Ты — Руководитель проекта строительной субподрядной организации.
Твоя задача — построить план работ по исполнительной документации (ИД).

КОНЕЧНАЯ ЦЕЛЬ:
{goal}

ТЕКУЩЕЕ СОСТОЯНИЕ ПРОЕКТА:
- Проект ID: {project_id}
- Режим: {workflow_mode}
- Эталон ИД: {compliance_target}
- Уже выполнено агентами: {agent_results}

ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:
{task_description}

ДОСТУПНЫЕ АГЕНТЫ И ИХ КОМПЕТЕНЦИИ:
1. archive (Делопроизводитель) — регистрация документов, реестр ИД, комплектование
2. procurement (Закупщик) — анализ тендеров, НМЦК, рентабельность
3. pto (ПТО) — извлечение ВОР, классификация документов, верификация, OCR чертежей
4. smeta (Сметчик) — расчёт стоимости, привязка к ФЕР, КС-2, контроль объёмов
5. legal (Юрист) — юридическая экспертиза договоров, поиск ловушек БЛС, протокол разногласий
6. logistics (Логист) — поиск поставщиков, цены, сроки доставки

ПОСТРОЙ ПЛАН РАБОТ:
1. Разбей цель на конкретные задачи (TaskNode)
2. Для каждой задачи укажи агента, приоритет (1-10), зависимости от других задач, требуемую уверенность
3. Учти, что некоторые агенты могут работать параллельно (если нет зависимостей)
4. Задачи с высоким приоритетом — критические для достижения цели
5. Для режима lot_search: приоритет — legal + procurement + smeta (оценка рисков)
6. Для режима construction_support: приоритет — pto + archive + legal (инвентаризация ИД)

ФОРМАТ ОТВЕТА — СТРОГО JSON:
{{
  "plan": {{
    "goal": "краткая формулировка конечной цели",
    "reasoning": "стратегическое обоснование плана (2-3 предложения)",
    "estimated_hours": 0.0,
    "tasks": [
      {{
        "task_id": "task_1",
        "task_type": "legal_analysis",
        "description": "что конкретно сделать",
        "agent": "legal",
        "depends_on": [],
        "priority": 10,
        "confidence_required": 0.7
      }}
    ]
  }}
}}

ВАЖНО:
- task_id должны быть уникальными (task_1, task_2, ...)
- depends_on — массив task_id задач, которые должны быть выполнены ПЕРЕД этой
- priority 10 = критично, 1 = опционально
- confidence_required: 0.9 для юридических задач, 0.7 для сметных, 0.6 для логистики, 0.5 для регистрации
- Минимум 3 задачи, максимум 10
- Ответ — ТОЛЬКО JSON, без markdown-обрамления
"""

PM_EVALUATION_PROMPT = """Ты — Руководитель проекта. Оцени результат работы агента {agent_name}.

ЗАДАЧА АГЕНТА:
{task_description}

РЕЗУЛЬТАТ:
{result_summary}

УВЕРЕННОСТЬ АГЕНТА: {confidence:.0%}
ТРЕБУЕМАЯ УВЕРЕННОСТЬ: {confidence_required:.0%}

КОНТЕКСТ ПРОЕКТА:
- Цель: {goal}
- Прогресс плана: {progress_pct}%
- Предыдущие ошибки: {previous_errors}

ПРИМИ РЕШЕНИЕ:
1. ACCEPT — результат качественный, принимаем
2. RETRY — результат слабый, переделать с уточнением (укажи, что уточнить)
3. RETRY_OTHER — эту задачу лучше передать другому агенту (укажи, какому)
4. SKIP — задача не критична, можно пропустить
5. ABORT — критическая ошибка, план невыполним

ФОРМАТ ОТВЕТА — СТРОГО JSON:
{{
  "verdict": "ACCEPT",
  "reasoning": "краткое обоснование",
  "clarification": "что уточнить (только для RETRY)",
  "alternative_agent": "имя агента (только для RETRY_OTHER)"
}}
"""

PM_REPLAN_PROMPT = """Ты — Руководитель проекта. Задача {failed_task_id} провалилась после {retries} попыток.

Причина: {failure_reason}

Текущий план (ID: {plan_id}):
{tasks_summary}

Адаптируй план. Возможные стратегии:
1. Пропустить задачу (если не критична для цели)
2. Разбить задачу на подзадачи и распределить между другими агентами
3. Изменить зависимости и перестроить порядок
4. Признать план невыполнимым (ABORT)

ФОРМАТ ОТВЕТА — СТРОГО JSON:
{{
  "action": "skip|split|reorder|abort",
  "reasoning": "обоснование",
  "new_tasks": [],
  "modified_tasks": {{}}
}}

new_tasks — только для action=split (новые задачи взамен проваленной)
modified_tasks — task_id → новые значения полей (для action=reorder)
"""


# =============================================================================
# Agent Weights & Decision Thresholds (merged from HermesRouter)
# =============================================================================

DEFAULT_AGENT_WEIGHTS: Dict[str, float] = {
    "legal": 0.35,
    "smeta": 0.25,
    "pto": 0.20,
    "procurement": 0.12,
    "logistics": 0.08,
}

GO_THRESHOLD = 0.70
NO_GO_THRESHOLD = 0.30


# =============================================================================
# Veto Rules — жёсткие предохранители (merged from HermesRouter)
# =============================================================================

DEFAULT_VETO_RULES: List[VetoRule] = [
    VetoRule(
        rule_id="veto_dangerous_verdict",
        rule_name="Юридический вето",
        description="Вердикт Юриста DANGEROUS — подписание недопустимо",
        condition="legal_result.verdict == 'dangerous'",
        triggered=False,
    ),
    VetoRule(
        rule_id="veto_margin_below_10",
        rule_name="Маржа ниже минимума",
        description="Маржа ниже 10% — работа в убыток или на грани",
        condition="smeta_result.profit_margin_pct < 10",
        triggered=False,
    ),
    VetoRule(
        rule_id="veto_critical_traps_3plus",
        rule_name="3+ критических ловушки",
        description="3 и более критических юридических ловушки — слишком рискованно",
        condition="legal_result.critical_count >= 3",
        triggered=False,
    ),
    VetoRule(
        rule_id="veto_nmck_below_70pct",
        rule_name="НМЦК ниже 70% рынка",
        description="НМЦК ниже 70% рыночной стоимости — демпинг",
        condition="smeta_result.nmck_below_70pct == True",
        triggered=False,
    ),
]


# =============================================================================
# Signal Extractors — перевод результата агента в числовой сигнал 0..1
# =============================================================================

def extract_legal_signal(state: Dict[str, Any]) -> AgentSignal:
    """Извлечь сигнал Юриста из состояния."""
    legal = state.get("legal_result")
    confidence = state.get("confidence_scores", {}).get("legal", 0.5)

    if not legal:
        return AgentSignal(
            agent_name="legal", signal=0.5, confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["legal"],
            reasoning="Юридический анализ не проводился",
        )

    verdict_signal_map = {
        "approved": 0.95, "approved_with_comments": 0.65,
        "rejected": 0.15, "dangerous": 0.05,
    }
    verdict = legal.get("verdict", "approved_with_comments")
    base_signal = verdict_signal_map.get(verdict, 0.5)

    critical = legal.get("critical_count", 0)
    high = legal.get("high_count", 0)
    penalty = critical * 0.15 + high * 0.05
    signal = max(0.0, min(1.0, base_signal - penalty))

    return AgentSignal(
        agent_name="legal", signal=round(signal, 3), confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["legal"],
        reasoning=f"Вердикт: {verdict}, критических: {critical}, высоких: {high}",
        key_findings=legal.get("blc_matches", [])[:3],
    )


def extract_smeta_signal(state: Dict[str, Any]) -> AgentSignal:
    """Извлечь сигнал Сметчика из состояния."""
    smeta = state.get("smeta_result")
    confidence = state.get("confidence_scores", {}).get("smeta", 0.5)

    if not smeta:
        return AgentSignal(
            agent_name="smeta", signal=0.5, confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["smeta"],
            reasoning="Расчёт стоимости не проводился",
        )

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
        agent_name="smeta", signal=round(signal, 3), confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["smeta"],
        reasoning=f"Маржа: {margin:.1f}%, ФЕР покрытие: {smeta.get('fer_coverage_pct', 0):.0f}%",
        key_findings=key_findings,
    )


def extract_pto_signal(state: Dict[str, Any]) -> AgentSignal:
    """Извлечь сигнал ПТО из состояния."""
    vor = state.get("vor_result")
    confidence = state.get("confidence_scores", {}).get("pto", 0.5)

    if not vor:
        return AgentSignal(
            agent_name="pto", signal=0.5, confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["pto"],
            reasoning="Извлечение ВОР не проводилось",
        )

    vor_confidence = vor.get("confidence_score", 0.5)
    unit_mismatches = len(vor.get("unit_mismatches", []))
    signal = max(0.0, min(1.0, vor_confidence - unit_mismatches * 0.05))

    key_findings = [f"vor_positions_{vor.get('total_positions', 0)}"]
    if unit_mismatches:
        key_findings.append(f"unit_mismatches_{unit_mismatches}")

    return AgentSignal(
        agent_name="pto", signal=round(signal, 3), confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["pto"],
        reasoning=f"ВОР: {vor.get('total_positions', 0)} позиций, уверенность: {vor_confidence:.0%}",
        key_findings=key_findings,
    )


def extract_procurement_signal(state: Dict[str, Any]) -> AgentSignal:
    """Извлечь сигнал Закупщика из состояния."""
    proc = state.get("procurement_result")
    confidence = state.get("confidence_scores", {}).get("procurement", 0.5)

    if not proc:
        return AgentSignal(
            agent_name="procurement", signal=0.5, confidence=0.0,
            weight=DEFAULT_AGENT_WEIGHTS["procurement"],
            reasoning="Анализ тендера не проводился",
        )

    decision = proc.get("decision", "watch")
    nmck_vs = proc.get("nmck_vs_market", 0)

    decision_signal_map = {"bid": 0.75, "watch": 0.45, "skip": 0.20}
    signal = decision_signal_map.get(decision, 0.5)

    if nmck_vs < -20:
        signal -= 0.15
    elif nmck_vs < -10:
        signal -= 0.05

    signal = max(0.0, min(1.0, signal))

    return AgentSignal(
        agent_name="procurement", signal=round(signal, 3), confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["procurement"],
        reasoning=f"Решение: {decision}, НМЦК vs рынок: {nmck_vs:+.1f}%",
        key_findings=[f"competitors_{proc.get('competitor_count', 0)}"],
    )


def extract_logistics_signal(state: Dict[str, Any]) -> AgentSignal:
    """Извлечь сигнал Логиста из состояния."""
    logistics = state.get("logistics_result")
    confidence = state.get("confidence_scores", {}).get("logistics", 0.5)

    if not logistics:
        return AgentSignal(
            agent_name="logistics", signal=0.5, confidence=0.0,
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
        agent_name="logistics", signal=round(signal, 3), confidence=confidence,
        weight=DEFAULT_AGENT_WEIGHTS["logistics"],
        reasoning=f"Поставщиков: {vendors}, доставка: {'да' if delivery else 'нет'}",
        key_findings=[f"vendors_{vendors}"],
    )


# Signal extractor registry
AGENT_SIGNAL_EXTRACTORS: Dict[str, Any] = {
    "legal": extract_legal_signal,
    "smeta": extract_smeta_signal,
    "pto": extract_pto_signal,
    "procurement": extract_procurement_signal,
    "logistics": extract_logistics_signal,
}


# =============================================================================
# Weighted Scoring Engine
# =============================================================================

def compute_weighted_score(signals: List[AgentSignal]) -> WeightedScoringResult:
    """
    Рассчитать взвешенный скоринг по сигналам агентов.

    Formula:
        Score = Σ (signal × weight × confidence) / Σ (weight × confidence)
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

    if normalized_score >= GO_THRESHOLD:
        zone = "go_zone"
    elif normalized_score <= NO_GO_THRESHOLD:
        zone = "no_go_zone"
    else:
        zone = "grey_zone"

    return WeightedScoringResult(
        raw_score=round(numerator, 4),
        normalized_score=round(normalized_score, 4),
        agent_contributions=contributions,
        zone=zone,
        go_threshold=GO_THRESHOLD,
        no_go_threshold=NO_GO_THRESHOLD,
    )


# =============================================================================
# Veto Engine
# =============================================================================

def check_veto_rules(
    state: Dict[str, Any], rules: List[VetoRule]
) -> tuple:
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
# Risk Level Calculator
# =============================================================================

def calculate_risk_level(
    state: Dict[str, Any], scoring: WeightedScoringResult
) -> RiskLevel:
    """Рассчитать общий уровень риска."""
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
# Project Manager Agent
# =============================================================================

class ProjectManager:
    """
    Руководитель проекта ASD v12.0.

    Отвечает за:
      - Стратегическое планирование (create_plan)
      - Диспетчеризацию агентов (dispatch)
      - Оценку результатов (evaluate_result)
      - Адаптацию плана при неудачах (replan)

    Использует Llama 3.3 70B для сложных решений (планирование, оценка),
    но быстрые операции (dispatch, проверка зависимостей) — без LLM.
    """

    def __init__(
        self,
        llm_engine: Optional[LLMEngine] = None,
        completeness_matrix=None,
    ):
        self._llm = llm_engine
        self._matrix = completeness_matrix

    # -------------------------------------------------------------------------
    # Planning
    # -------------------------------------------------------------------------

    async def create_plan(
        self,
        task_description: str,
        workflow_mode: str,
        project_id: int,
        compliance_target: str = "344/пр",
        agent_results: Optional[Dict[str, str]] = None,
    ) -> WorkPlan:
        """
        Построить план работ на основе анализа задачи через LLM.

        Args:
            task_description: описание задачи от пользователя
            workflow_mode: lot_search или construction_support
            project_id: ID проекта
            compliance_target: эталон (344/пр, договор, ...)
            agent_results: что уже сделано агентами

        Returns:
            WorkPlan с задачами и зависимостями
        """
        logger.info(
            "PM creating plan for project %d, mode=%s, target=%s",
            project_id, workflow_mode, compliance_target,
        )

        agent_results_text = "нет (первый запуск)"
        if agent_results:
            agent_results_text = "\n".join(
                f"  - {agent}: {summary}"
                for agent, summary in agent_results.items()
            )

        prompt = PM_PLANNING_PROMPT.format(
            goal=task_description,
            project_id=project_id,
            workflow_mode=workflow_mode,
            compliance_target=compliance_target,
            agent_results=agent_results_text,
            task_description=task_description,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты — Руководитель проекта (PM) ASD v12.0. "
                    "Твоя модель: Llama 3.3 70B. "
                    "Отвечай СТРОГО в формате JSON без markdown-обрамления. "
                    "Ты работаешь всегда в интересах подрядчика."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm.chat("pm", messages)
            plan_data = json.loads(self._extract_json(response))
        except (json.JSONDecodeError, Exception) as e:
            logger.error("PM planning LLM call failed: %s. Using fallback plan.", e)
            plan_data = self._fallback_plan(task_description, workflow_mode)

        return self._build_plan_from_llm(plan_data, project_id, compliance_target)

    def _build_plan_from_llm(
        self,
        plan_data: Dict[str, Any],
        project_id: int,
        compliance_target: str,
    ) -> WorkPlan:
        """Собрать WorkPlan из JSON-ответа LLM."""
        plan_info = plan_data.get("plan", plan_data)

        tasks = []
        for t in plan_info.get("tasks", []):
            task = TaskNode(
                task_id=t["task_id"],
                task_type=t.get("task_type", "unknown"),
                description=t.get("description", ""),
                agent=t.get("agent", "pto"),
                depends_on=t.get("depends_on", []),
                priority=t.get("priority", 5),
                deadline=t.get("deadline"),
                confidence_required=t.get("confidence_required", 0.6),
                max_retries=t.get("max_retries", 2),
            )
            tasks.append(task)

        plan_id = hashlib.sha256(
            f"{project_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        return WorkPlan(
            plan_id=plan_id,
            project_id=project_id,
            goal=plan_info.get("goal", ""),
            tasks=tasks,
            compliance_target=compliance_target,
            estimated_duration_hours=plan_info.get("estimated_hours", 0.0),
            pm_reasoning=plan_info.get("reasoning", ""),
        )

    def _fallback_plan(
        self, task_description: str, workflow_mode: str
    ) -> Dict[str, Any]:
        """Дефолтный план, если LLM недоступен."""
        if workflow_mode == "lot_search":
            tasks = [
                {"task_id": "task_1", "task_type": "archive_register", "description": "Зарегистрировать входящий пакет", "agent": "archive", "depends_on": [], "priority": 5, "confidence_required": 0.5},
                {"task_id": "task_2", "task_type": "procurement_analysis", "description": "Анализ тендера и НМЦК", "agent": "procurement", "depends_on": ["task_1"], "priority": 8, "confidence_required": 0.6},
                {"task_id": "task_3", "task_type": "pto_vor", "description": "Извлечение ВОР из документации", "agent": "pto", "depends_on": ["task_1"], "priority": 7, "confidence_required": 0.6},
                {"task_id": "task_4", "task_type": "legal_review", "description": "Юридическая экспертиза договора", "agent": "legal", "depends_on": ["task_1"], "priority": 10, "confidence_required": 0.9},
                {"task_id": "task_5", "task_type": "smeta_calc", "description": "Расчёт сметы и рентабельности", "agent": "smeta", "depends_on": ["task_3"], "priority": 8, "confidence_required": 0.7},
                {"task_id": "task_6", "task_type": "logistics_search", "description": "Поиск поставщиков и цен", "agent": "logistics", "depends_on": ["task_3"], "priority": 4, "confidence_required": 0.6},
            ]
        else:  # construction_support
            tasks = [
                {"task_id": "task_1", "task_type": "archive_register", "description": "Инвентаризация документов", "agent": "archive", "depends_on": [], "priority": 10, "confidence_required": 0.5},
                {"task_id": "task_2", "task_type": "pto_inventory", "description": "Классификация и верификация ИД", "agent": "pto", "depends_on": ["task_1"], "priority": 10, "confidence_required": 0.7},
                {"task_id": "task_3", "task_type": "legal_review", "description": "Проверка соответствия 344/пр", "agent": "legal", "depends_on": ["task_2"], "priority": 9, "confidence_required": 0.9},
                {"task_id": "task_4", "task_type": "smeta_calc", "description": "Сверка объёмов КС-2 с ВОР", "agent": "smeta", "depends_on": ["task_2"], "priority": 8, "confidence_required": 0.7},
                {"task_id": "task_5", "task_type": "procurement_analysis", "description": "Поиск альтернативных поставщиков материалов", "agent": "procurement", "depends_on": ["task_2"], "priority": 5, "confidence_required": 0.6},
            ]

        return {
            "plan": {
                "goal": task_description,
                "reasoning": "Fallback-план (LLM недоступна). Стандартная последовательность.",
                "estimated_hours": 0.0,
                "tasks": tasks,
            }
        }

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    def dispatch(self, plan: WorkPlan) -> Optional[Tuple[str, TaskNode]]:
        """
        Выбрать следующего агента и задачу.

        Returns:
            (agent_name, TaskNode) или None, если план завершён / заблокирован.
        """
        if plan.status == PlanStatus.COMPLETED.value:
            logger.info("Plan %s already completed.", plan.plan_id)
            return None

        if plan.status == PlanStatus.ABORTED.value:
            logger.warning("Plan %s was aborted.", plan.plan_id)
            return None

        plan.status = PlanStatus.EXECUTING.value

        next_task = plan.get_next_task()

        if next_task is None:
            # Проверяем: всё выполнено или заблокировано?
            all_done = all(
                t.status in (TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value, TaskStatus.FAILED.value)
                for t in plan.tasks
            )
            if all_done:
                plan.status = PlanStatus.COMPLETED.value
                logger.info("Plan %s completed: %.0f%%", plan.plan_id, plan.get_completion_pct())
            else:
                logger.warning(
                    "Plan %s blocked: pending tasks have unresolved dependencies. "
                    "Failed tasks: %d",
                    plan.plan_id,
                    len(plan.get_failed_tasks()),
                )
            return None

        next_task.mark_started()
        plan.updated_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "PM dispatching: agent=%s task=%s priority=%d",
            next_task.agent, next_task.task_id, next_task.priority,
        )

        return next_task.agent, next_task

    # -------------------------------------------------------------------------
    # Evaluation
    # -------------------------------------------------------------------------

    def evaluate_result_sync(
        self,
        plan: WorkPlan,
        task: TaskNode,
        result_summary: str,
        confidence: float,
        previous_errors: Optional[List[str]] = None,
    ) -> EvaluationVerdict:
        """
        Синхронная оценка результата (без LLM, только быстрые пути).

        Используется в тестах и когда LLM недоступен.
        Быстрые пороги: confidence >= required → ACCEPT, confidence < 0.1 → RETRY/ABORT.
        """
        if confidence >= task.confidence_required:
            task.mark_completed(result_summary)
            plan.updated_at = datetime.now(timezone.utc).isoformat()
            return EvaluationVerdict.ACCEPT

        if confidence < 0.1:
            task.mark_failed("Confidence too low (< 0.1)")
            if task.status == TaskStatus.FAILED.value:
                return EvaluationVerdict.ABORT
            return EvaluationVerdict.RETRY

        # Grey zone without LLM: conservative RETRY
        task.mark_failed("Grey zone (no LLM available)")
        if task.status == TaskStatus.FAILED.value:
            return EvaluationVerdict.ABORT
        return EvaluationVerdict.RETRY

    async def evaluate_result(
        self,
        plan: WorkPlan,
        task: TaskNode,
        result_summary: str,
        confidence: float,
        previous_errors: Optional[List[str]] = None,
    ) -> EvaluationVerdict:
        """
        Оценить результат работы агента и принять решение.

        Args:
            plan: текущий план
            task: выполненная задача
            result_summary: краткое описание результата
            confidence: уверенность агента (0.0-1.0)
            previous_errors: предыдущие ошибки в этом плане

        Returns:
            EvaluationVerdict — что делать дальше с этой задачей
        """
        # Быстрый путь: уверенность выше требуемой → ACCEPT
        if confidence >= task.confidence_required:
            task.mark_completed(result_summary)
            plan.updated_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "PM auto-accepted task %s (confidence %.2f >= required %.2f)",
                task.task_id, confidence, task.confidence_required,
            )
            return EvaluationVerdict.ACCEPT

        # Быстрый путь: уверенность экстремально низкая → RETRY
        if confidence < 0.1:
            task.mark_failed("Confidence too low (< 0.1)")
            logger.warning(
                "PM auto-rejected task %s (confidence %.2f < 0.1)",
                task.task_id, confidence,
            )
            if task.status == TaskStatus.FAILED.value:
                return EvaluationVerdict.ABORT
            return EvaluationVerdict.RETRY

        # Серая зона: спрашиваем LLM (PM на Llama 3.3 70B)
        logger.info(
            "PM evaluating task %s via LLM (confidence %.2f vs required %.2f)",
            task.task_id, confidence, task.confidence_required,
        )

        prev_errors_text = "; ".join(previous_errors) if previous_errors else "нет"

        prompt = PM_EVALUATION_PROMPT.format(
            agent_name=task.agent,
            task_description=task.description,
            result_summary=result_summary,
            confidence=confidence,
            confidence_required=task.confidence_required,
            goal=plan.goal,
            progress_pct=plan.get_completion_pct(),
            previous_errors=prev_errors_text,
        )

        messages = [
            {
                "role": "system",
                "content": "Ты — Руководитель проекта. Оцениваешь результаты агентов. Отвечай JSON.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm.chat("pm", messages)
            eval_data = json.loads(self._extract_json(response))
        except Exception as e:
            logger.error("PM evaluation LLM call failed: %s. Defaulting to RETRY.", e)
            eval_data = {"verdict": "RETRY", "reasoning": f"LLM error: {e}"}

        verdict_str = eval_data.get("verdict", "RETRY").upper()
        verdict = EvaluationVerdict(verdict_str.lower())

        if verdict == EvaluationVerdict.ACCEPT:
            task.mark_completed(result_summary)
        elif verdict == EvaluationVerdict.RETRY:
            task.mark_failed(f"PM evaluation: {eval_data.get('reasoning', '')}")
            if task.status == TaskStatus.FAILED.value:
                return EvaluationVerdict.ABORT
        elif verdict in (EvaluationVerdict.SKIP, EvaluationVerdict.RETRY_OTHER_AGENT):
            task.status = TaskStatus.SKIPPED.value
            task.result_summary = f"SKIPPED: {eval_data.get('reasoning', '')}"
        elif verdict == EvaluationVerdict.ABORT:
            plan.status = PlanStatus.ABORTED.value
            task.mark_failed(f"ABORT: {eval_data.get('reasoning', '')}")

        plan.updated_at = datetime.now(timezone.utc).isoformat()

        return verdict

    # -------------------------------------------------------------------------
    # Replanning
    # -------------------------------------------------------------------------

    async def replan(
        self,
        plan: WorkPlan,
        failed_task: TaskNode,
        failure_reason: str,
    ) -> WorkPlan:
        """
        Адаптировать план после критической неудачи.

        Args:
            plan: текущий план
            failed_task: задача, которая провалилась
            failure_reason: причина провала

        Returns:
            Адаптированный WorkPlan
        """
        logger.warning(
            "PM replanning: task %s failed after %d retries. Reason: %s",
            failed_task.task_id, failed_task.retry_count, failure_reason,
        )

        tasks_summary = "\n".join(
            f"  {t.task_id} [{t.agent}] — {t.status} (priority={t.priority})"
            for t in plan.tasks
        )

        prompt = PM_REPLAN_PROMPT.format(
            failed_task_id=failed_task.task_id,
            retries=failed_task.retry_count,
            failure_reason=failure_reason,
            plan_id=plan.plan_id,
            tasks_summary=tasks_summary,
        )

        messages = [
            {"role": "system", "content": "Ты — Руководитель проекта. Адаптируешь план после неудачи."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm.chat("pm", messages)
            replan_data = json.loads(self._extract_json(response))
        except Exception as e:
            logger.error("PM replan LLM call failed: %s. Skipping failed task.", e)
            replan_data = {"action": "skip", "reasoning": f"LLM error: {e}"}

        action = replan_data.get("action", "skip")

        if action == "split":
            # Разбить проваленную задачу на подзадачи
            new_tasks = replan_data.get("new_tasks", [])
            for t_data in new_tasks:
                new_task = TaskNode(
                    task_id=t_data.get("task_id", f"{failed_task.task_id}_sub"),
                    task_type=t_data.get("task_type", failed_task.task_type),
                    description=t_data.get("description", failed_task.description),
                    agent=t_data.get("agent", failed_task.agent),
                    depends_on=t_data.get("depends_on", failed_task.depends_on),
                    priority=t_data.get("priority", failed_task.priority),
                    confidence_required=t_data.get("confidence_required", failed_task.confidence_required),
                )
                plan.tasks.append(new_task)
            failed_task.status = TaskStatus.SKIPPED.value

        elif action == "reorder":
            modified = replan_data.get("modified_tasks", {})
            for tid, changes in modified.items():
                for task in plan.tasks:
                    if task.task_id == tid:
                        if isinstance(changes, dict):
                            if "depends_on" in changes:
                                task.depends_on = changes["depends_on"]
                            if "priority" in changes:
                                task.priority = changes["priority"]
                            if "agent" in changes:
                                task.agent = changes["agent"]
                        elif isinstance(changes, (int, float)):
                            task.priority = int(changes)
                        if task.status == TaskStatus.FAILED.value:
                            task.status = TaskStatus.PENDING.value
                            task.retry_count = 0

        elif action == "abort":
            plan.status = PlanStatus.ABORTED.value
            logger.error("PM aborted plan %s: %s", plan.plan_id, replan_data.get("reasoning", ""))

        else:  # skip
            failed_task.status = TaskStatus.SKIPPED.value
            failed_task.result_summary = f"SKIPPED after {failed_task.retry_count} retries: {failure_reason}"

        plan.status = PlanStatus.ADAPTED.value
        plan.updated_at = datetime.now(timezone.utc).isoformat()

        return plan

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> str:
        """Извлечь JSON из ответа LLM (может быть обёрнут в markdown)."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
