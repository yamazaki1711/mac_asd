"""
ASD v11.3 — Agent State Schema (Versioned).

Evolution from v11.3.0:
- Versioned schema with migration path
- Typed intermediate data (no more Dict[str, Any] bags)
- Confidence scores per agent output
- Revision history for rollback capability
- Audit trail with step-level logging
- Workflow mode discrimination (lot_search vs construction_support)
- Hermes decision model support (weight + LLM hybrid)

Migration: AgentStateV1 → AgentStateV2 via migrate_v1_to_v2()
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import add_messages


# =============================================================================
# Enums & Constants
# =============================================================================

class WorkflowMode(str, Enum):
    """Режим работы конвейера."""
    LOT_SEARCH = "lot_search"                    # Тендерный конвейер
    CONSTRUCTION_SUPPORT = "construction_support"  # Строительная поддержка (КС-2/3, ИД)


class StepStatus(str, Enum):
    """Статус выполнения шага агентом."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class HermesVerdict(str, Enum):
    """Итоговое решение Hermes о подаче/не подаче на тендер."""
    GO = "go"                                    # Подавать
    NO_GO = "no_go"                              # Не подавать
    CONDITIONAL_GO = "conditional_go"            # Подавать с условиями (протокол разногласий)
    GREY_ZONE = "grey_zone"                      # Требуется LLM-рассуждение


SCHEMA_VERSION = "2.0"


# =============================================================================
# Typed Sub-Structures for Intermediate Data
# =============================================================================

class VORResult(TypedDict, total=False):
    """Результат извлечения ВОР (ПТО)."""
    positions: List[Dict[str, Any]]              # [{code, name, unit, quantity, section}]
    total_positions: int
    confidence_score: float                      # 0.0 - 1.0, уверенность ПТО в извлечении
    raw_text_fallback: Optional[str]
    drawing_refs: List[str]                      # Ссылки на чертежи
    unit_mismatches: List[Dict[str, str]]        # [{position, expected_unit, found_unit}]


class LegalResult(TypedDict, total=False):
    """Результат юридического анализа."""
    verdict: str                                 # approved, approved_with_comments, rejected, dangerous
    findings_count: int
    critical_count: int
    high_count: int
    summary: str
    protocol_items_count: int
    confidence_score: float                      # 0.0 - 1.0, уверенность Юриста
    blc_matches: List[str]                       # IDs совпавших ловушек из БЛС


class SmetaResult(TypedDict, total=False):
    """Результат расчёта Сметчика."""
    total_cost: float                            # Себестоимость (руб.)
    nmck: float                                  # НМЦК (руб.)
    profit_margin_pct: float                     # Маржа (%)
    fer_positions_used: int                      # Кол-во позиций ФЕР
    region_coeff: float                          # Региональный коэффициент
    year_index: float                            # Индекс пересчёта
    confidence_score: float                      # 0.0 - 1.0
    low_margin_positions: List[str]              # Позиции с маржой < 10%


class ProcurementResult(TypedDict, total=False):
    """Результат анализа Закупщика."""
    lot_id: str
    nmck: float
    nmck_vs_market: float                        # Отклонение НМЦК от рынка (%)
    competitor_count: int                        # Кол-во конкурентов
    decision: str                                # bid, skip, watch
    confidence_score: float


class LogisticsResult(TypedDict, total=False):
    """Результат анализа Логиста."""
    vendors_found: int
    best_price: float
    delivery_available: bool
    lead_time_days: int
    confidence_score: float


class ArchiveResult(TypedDict, total=False):
    """Результат регистрации Делопроизводителем."""
    doc_id: str
    status: str
    pages_registered: int
    confidence_score: float


# =============================================================================
# Step Log (Audit Trail)
# =============================================================================

class StepLog(TypedDict, total=False):
    """Запись об одном шаге выполнения агентом."""
    step_id: str                                 # UUID
    agent: str                                   # Имя агента (hermes, pto, legal, ...)
    action: str                                  # Действие (extract_vor, analyze_contract, ...)
    status: str                                  # pending, running, completed, failed, skipped
    started_at: str                              # ISO 8601
    completed_at: Optional[str]                  # ISO 8601
    duration_ms: Optional[int]
    input_summary: Optional[str]                 # Краткое описание входа
    output_summary: Optional[str]                # Краткое описание выхода
    error_message: Optional[str]                 # Если failed
    rollback_point: Optional[str]                # ID шага для отката


# =============================================================================
# Hermes Decision Record
# =============================================================================

class HermesDecision(TypedDict, total=False):
    """Запись о решении Hermes (весовой скоринг + LLM)."""
    verdict: str                                 # go, no_go, conditional_go, grey_zone
    weighted_score: float                        # 0.0 - 1.0
    agent_signals: Dict[str, float]              # {agent_name: signal_value}
    agent_weights: Dict[str, float]              # {agent_name: weight}
    confidence_scores: Dict[str, float]          # {agent_name: confidence}
    veto_triggered: Optional[str]                # Какое veto-правило сработало
    llm_reasoning: Optional[str]                 # Chain-of-thought (только для grey_zone)
    decided_at: str                              # ISO 8601
    decided_via: str                             # "weight_scoring" | "llm_reasoning" | "veto_override"


# =============================================================================
# Revision History Entry
# =============================================================================

class RevisionEntry(TypedDict, total=False):
    """Запись в истории ревизий состояния."""
    revision_id: str
    timestamp: str                               # ISO 8601
    trigger: str                                 # "agent_step" | "rollback" | "correction" | "retry"
    agent: str
    step: str
    changes_summary: str                         # Что изменилось
    snapshot_key: Optional[str]                  # Ключ к полному снимку (если хранится)


# =============================================================================
# AgentState V2 (Main Schema)
# =============================================================================

class AgentState(TypedDict):
    """
    Состояние графа ASD v2.0.

    Передаётся между агентами через LangGraph StateGraph.
    Версионировано для совместимости и миграции.

    Ключевые отличия от v1:
    - schema_version: версионирование схемы
    - workflow_mode: разделение режимов работы
    - revision_history: история ревизий для rollback
    - audit_trail: пошаговый аудит выполнения
    - confidence_scores: уверенность агентов в своих результатах
    - hermes_decision: структурированное решение Hermes
    - rollback_point: точка отката при ошибке
    - Типизированные sub-структуры вместо Dict[str, Any]
    """
    # ── Версионирование ──
    schema_version: str                          # "2.0" — для миграций

    # ── Режим работы ──
    workflow_mode: str                           # "lot_search" | "construction_support"

    # ── Идентификация ──
    project_id: int                              # ID проекта в БД
    current_lot_id: Optional[str]                # ID тендерного лота
    task_description: str                        # Описание задачи

    # ── Сообщения (LangGraph) ──
    messages: Annotated[List[Any], add_messages]  # Накопление истории чата

    # ── Типизированные результаты агентов ──
    vor_result: Optional[VORResult]              # ПТО: извлечённая ВОР
    legal_result: Optional[LegalResult]          # Юрист: юридический анализ
    smeta_result: Optional[SmetaResult]          # Сметчик: расчёт стоимости
    procurement_result: Optional[ProcurementResult]  # Закупщик: анализ тендера
    logistics_result: Optional[LogisticsResult]  # Логист: поставки
    archive_result: Optional[ArchiveResult]      # Делопроизводитель: регистрация

    # ── Legacy intermediate_data (обратная совместимость) ──
    intermediate_data: Dict[str, Any]            # Для агентов без типизированных структур

    # ── Аналитика ──
    findings: List[Dict[str, Any]]               # Найденные риски/ловушки

    # ── Уверенность агентов ──
    confidence_scores: Dict[str, float]          # {agent_name: 0.0-1.0}

    # ── Решение Hermes ──
    hermes_decision: Optional[HermesDecision]    # Структурированное решение

    # ── Оркестрация ──
    current_step: str                            # Текущий шаг конвейера
    next_step: str                               # Следующий узел (routing)
    event_type: Optional[str]                    # Тип события для EventManager
    is_complete: bool                            # Флаг завершения

    # ── Аудит и откат ──
    audit_trail: List[StepLog]                   # Пошаговый лог выполнения
    revision_history: List[RevisionEntry]        # История ревизий
    rollback_point: Optional[str]                # ID шага для отката

    # ── Метаданные ──
    created_at: str                              # ISO 8601 — создание состояния
    updated_at: str                              # ISO 8601 — последнее обновление


# =============================================================================
# Default State Factory
# =============================================================================

def create_initial_state(
    project_id: int,
    task_description: str,
    workflow_mode: str = "lot_search",
    lot_id: Optional[str] = None,
) -> AgentState:
    """
    Создаёт начальное состояние AgentState v2.0.

    Args:
        project_id: ID проекта в БД
        task_description: Описание задачи для конвейера
        workflow_mode: Режим работы (lot_search / construction_support)
        lot_id: ID тендерного лота (опционально)

    Returns:
        AgentState с дефолтными значениями
    """
    now = datetime.utcnow().isoformat()
    return AgentState(
        schema_version=SCHEMA_VERSION,
        workflow_mode=workflow_mode,
        project_id=project_id,
        current_lot_id=lot_id,
        task_description=task_description,
        messages=[],
        vor_result=None,
        legal_result=None,
        smeta_result=None,
        procurement_result=None,
        logistics_result=None,
        archive_result=None,
        intermediate_data={},
        findings=[],
        confidence_scores={},
        hermes_decision=None,
        current_step="start",
        next_step="archive",
        event_type=None,
        is_complete=False,
        audit_trail=[],
        revision_history=[],
        rollback_point=None,
        created_at=now,
        updated_at=now,
    )


# =============================================================================
# Migration V1 → V2
# =============================================================================

def migrate_v1_to_v2(v1_state: Dict[str, Any]) -> AgentState:
    """
    Миграция состояния из схемы v1 (AgentState без версионирования)
    в схему v2.0.

    V1 поля → V2 маппинг:
    - messages → messages (без изменений)
    - project_id → project_id
    - current_lot_id → current_lot_id
    - task_description → task_description
    - intermediate_data → intermediate_data + типизированные поля
    - findings → findings
    - next_step → next_step
    - event_type → event_type
    - is_complete → is_complete

    Новые поля V2 получают дефолтные значения.
    """
    now = datetime.utcnow().isoformat()

    # Попытка извлечь типизированные данные из intermediate_data
    intermediate = v1_state.get("intermediate_data", {})

    vor_result = None
    if "vor" in intermediate:
        vor_data = intermediate["vor"]
        vor_result = VORResult(
            positions=vor_data if isinstance(vor_data, list) else [],
            total_positions=len(vor_data) if isinstance(vor_data, list) else 0,
            confidence_score=0.5,  # V1 не сохранял confidence
            raw_text_fallback=vor_data.get("raw_text") if isinstance(vor_data, dict) else None,
            drawing_refs=[],
            unit_mismatches=[],
        )

    smeta_result = None
    if "costs" in intermediate:
        costs_data = intermediate["costs"]
        smeta_result = SmetaResult(
            total_cost=0.0,
            nmck=0.0,
            profit_margin_pct=0.0,
            fer_positions_used=0,
            region_coeff=1.0,
            year_index=1.0,
            confidence_score=0.5,
            low_margin_positions=[],
        )

    legal_result = None
    legal_verdict = intermediate.get("legal_verdict")
    if legal_verdict:
        legal_result = LegalResult(
            verdict=legal_verdict,
            findings_count=v1_state.get("findings", []).__len__(),
            critical_count=intermediate.get("legal_critical_count", 0),
            high_count=intermediate.get("legal_high_count", 0),
            summary=intermediate.get("legal_summary", ""),
            protocol_items_count=0,
            confidence_score=0.5,
            blc_matches=[],
        )

    return AgentState(
        schema_version=SCHEMA_VERSION,
        workflow_mode="lot_search",  # V1 не различал режимы
        project_id=v1_state.get("project_id", 0),
        current_lot_id=v1_state.get("current_lot_id"),
        task_description=v1_state.get("task_description", ""),
        messages=v1_state.get("messages", []),
        vor_result=vor_result,
        legal_result=legal_result,
        smeta_result=smeta_result,
        procurement_result=None,
        logistics_result=None,
        archive_result=None,
        intermediate_data=intermediate,
        findings=v1_state.get("findings", []),
        confidence_scores={},
        hermes_decision=None,
        current_step=v1_state.get("next_step", "start"),
        next_step=v1_state.get("next_step", "archive"),
        event_type=v1_state.get("event_type"),
        is_complete=v1_state.get("is_complete", False),
        audit_trail=[],
        revision_history=[],
        rollback_point=None,
        created_at=now,
        updated_at=now,
    )


# =============================================================================
# Step Log Helpers
# =============================================================================

def start_step(state: AgentState, agent: str, action: str) -> str:
    """Создаёт запись о начале шага и возвращает step_id."""
    step_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    entry = StepLog(
        step_id=step_id,
        agent=agent,
        action=action,
        status=StepStatus.RUNNING.value,
        started_at=now,
        completed_at=None,
        duration_ms=None,
        input_summary=None,
        output_summary=None,
        error_message=None,
        rollback_point=None,
    )

    state["audit_trail"].append(entry)
    state["updated_at"] = now
    return step_id


def complete_step(
    state: AgentState,
    step_id: str,
    output_summary: Optional[str] = None,
) -> None:
    """Отмечает шаг как завершённый."""
    now = datetime.utcnow().isoformat()

    for entry in state["audit_trail"]:
        if entry.get("step_id") == step_id:
            entry["status"] = StepStatus.COMPLETED.value
            entry["completed_at"] = now
            if entry.get("started_at"):
                start = datetime.fromisoformat(entry["started_at"])
                end = datetime.fromisoformat(now)
                entry["duration_ms"] = int((end - start).total_seconds() * 1000)
            entry["output_summary"] = output_summary
            break

    state["updated_at"] = now


def fail_step(
    state: AgentState,
    step_id: str,
    error_message: str,
    set_rollback: bool = True,
) -> None:
    """Отмечает шаг как failed и устанавливает rollback_point."""
    now = datetime.utcnow().isoformat()

    for entry in state["audit_trail"]:
        if entry.get("step_id") == step_id:
            entry["status"] = StepStatus.FAILED.value
            entry["completed_at"] = now
            entry["error_message"] = error_message
            if entry.get("started_at"):
                start = datetime.fromisoformat(entry["started_at"])
                end = datetime.fromisoformat(now)
                entry["duration_ms"] = int((end - start).total_seconds() * 1000)
            if set_rollback:
                entry["rollback_point"] = step_id
            break

    if set_rollback:
        state["rollback_point"] = step_id

    state["updated_at"] = now


def add_revision(
    state: AgentState,
    trigger: str,
    agent: str,
    step: str,
    changes_summary: str,
) -> None:
    """Добавляет запись в историю ревизий."""
    now = datetime.utcnow().isoformat()
    revision_id = str(uuid.uuid4())[:8]

    entry = RevisionEntry(
        revision_id=revision_id,
        timestamp=now,
        trigger=trigger,
        agent=agent,
        step=step,
        changes_summary=changes_summary,
        snapshot_key=None,
    )

    state["revision_history"].append(entry)
    state["updated_at"] = now
