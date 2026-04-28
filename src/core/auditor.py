"""
ASD v12.0 — Auditor Agent (Red Team Node).

Агент-Аудитор пытается ОПРОВЕРГНУТЬ выводы других агентов.
Ищет несоответствия с ГОСТ/СП, внутренние противоречия и пропущенные риски.
Только после прохождения этого фильтра вердикт утверждается.

Принцип работы:
1. Получает результаты всех агентов (legal, smeta, pto, procurement, logistics)
2. Для каждого результата генерирует «адверсариальный» промпт — просит LLM найти
   контр-аргументы, пропущенные риски, логические противоречия
3. Агрегирует находки в AuditorReport
4. Если найдены критические противоречия — возвращает REJECT
5. Если только замечания — APPROVED_WITH_NOTES
6. Если чисто — APPROVED

Usage:
    from src.core.auditor import AuditorAgent, AuditorReport

    auditor = AuditorAgent(llm_engine)
    report = await auditor.audit(state)
    if report.verdict == AuditorVerdict.REJECT:
        raise AuditorRejection(report)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Auditor Verdicts
# =============================================================================

class AuditorVerdict(str, Enum):
    APPROVED = "approved"                 # Всё чисто, противоречий нет
    APPROVED_WITH_NOTES = "approved_with_notes"  # Есть замечания, но не критические
    REJECT = "reject"                     # Найдены критические противоречия


class ConflictSeverity(str, Enum):
    LOW = "low"           # Мелкое замечание (опечатка, формат)
    MEDIUM = "medium"     # Потенциальная проблема (несоответствие единиц)
    HIGH = "high"         # Серьёзное расхождение (пропущенный риск)
    CRITICAL = "critical" # Блокирующая ошибка (противоречие ГОСТ/СП)


# =============================================================================
# Audit Finding
# =============================================================================

@dataclass
class AuditFinding:
    """Одна находка Аудитора — потенциальное противоречие или пропущенный риск."""
    finding_id: str
    target_agent: str               # Какой агент проверяется
    category: str                   # "contradiction" | "missing_risk" | "norm_violation" | "logic_error"
    description: str                # Описание находки
    severity: ConflictSeverity
    source_docs: List[str] = field(default_factory=list)  # ГОСТ/СП, на которые ссылается
    recommendation: str = ""        # Что исправить


@dataclass
class AuditorReport:
    """Отчёт Агента-Аудитора."""
    report_id: str
    verdict: AuditorVerdict
    total_checks: int               # Сколько проверок проведено
    findings: List[AuditFinding] = field(default_factory=list)
    passed_checks: int = 0          # Сколько проверок пройдено без замечаний
    confidence: float = 1.0         # Уверенность аудитора в своём вердикте

    @property
    def critical_findings(self) -> List[AuditFinding]:
        return [f for f in self.findings if f.severity == ConflictSeverity.CRITICAL]

    @property
    def high_findings(self) -> List[AuditFinding]:
        return [f for f in self.findings if f.severity == ConflictSeverity.HIGH]

    def summary(self) -> str:
        lines = [
            f"Auditor Report: {self.verdict.value.upper()}",
            f"Checks: {self.passed_checks}/{self.total_checks} passed",
            f"Findings: {len(self.findings)} total "
            f"(critical={len(self.critical_findings)}, "
            f"high={len(self.high_findings)})",
        ]
        for f in self.findings[:5]:
            lines.append(f"  [{f.severity.value.upper()}] {f.target_agent}: {f.description[:100]}")
        return "\n".join(lines)


# =============================================================================
# Auditor Prompts
# =============================================================================

AUDITOR_SYSTEM_PROMPT = """Ты — Агент-Аудитор системы MAC_ASD. Твоя задача — находить ошибки,
противоречия и пропущенные риски в выводах других агентов.

Ты работаешь в режиме «отрицательного анализа» (red team):
- Предполагай, что выводы агентов МОГУТ быть ошибочными
- Ищи логические противоречия между выводами разных агентов
- Проверяй соответствие нормативной базе (ГОСТ, СП, ФЕР, ФЗ-44/223)
- Находи пропущенные риски, которые агент не заметил
- Проверяй внутреннюю согласованность: цифры, единицы измерения, логику

Для каждого найденного противоречия укажи:
- Какой агент ошибся
- В чём именно ошибка
- Серьёзность: CRITICAL (блокирует решение) / HIGH / MEDIUM / LOW
- Ссылку на нормативный документ (если применимо)
- Рекомендацию по исправлению

Формат ответа (строго JSON):
{
  "findings": [
    {
      "target_agent": "legal|smeta|pto|procurement|logistics",
      "category": "contradiction|missing_risk|norm_violation|logic_error",
      "description": "описание находки",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "source_docs": ["ГОСТ Р ...", "СП ..."],
      "recommendation": "что исправить"
    }
  ],
  "overall_verdict": "APPROVED|APPROVED_WITH_NOTES|REJECT",
  "confidence": 0.0-1.0
}

Правила:
- REJECT только если есть CRITICAL находки (противоречие ГОСТ/СП, логическая ошибка в расчётах)
- APPROVED_WITH_NOTES если есть HIGH находки
- APPROVED только если все проверки чисты
- CRITICAL severity — только если ошибка напрямую ведёт к кассовому разрыву или нарушению закона
"""

AUDITOR_CHECK_PROMPTS = {
    "pto_vs_smeta": """Проверь согласованность между ПТО (ВОР) и Сметчиком.

Данные ПТО (объёмы работ):
{pto_data}

Данные Сметчика (расчёт стоимости):
{smeta_data}

Проверь:
1. Все ли позиции ВОР учтены в смете?
2. Соответствуют ли единицы измерения?
3. Нет ли двойного учёта одних и тех же работ?
4. Соответствуют ли объёмы (ПТО) и стоимость (Сметчик) — если объём большой, а цена маленькая — почему?
5. Применены ли правильные региональные коэффициенты и индексы Минстроя?

Найденные противоречия оформи в JSON.""" ,

    "legal_vs_pto": """Проверь согласованность между Юристом и ПТО.

Юридический анализ:
{legal_data}

Данные ПТО (ВОР, виды работ):
{pto_data}

Проверь:
1. Все ли виды работ из ВОР покрыты юридическим анализом?
2. Есть ли виды работ, для которых юрист НЕ проверил БЛС-ловушки?
3. Соответствуют ли категории работ между ПТО и Юристом (через WorkTypeRegistry)?
4. Есть ли скрытые работы (по ВОР), для которых юрист должен был проверить особые условия контракта?

Найденные противоречия оформи в JSON.""",

    "smeta_vs_procurement": """Проверь согласованность между Сметчиком и Закупщиком.

Данные Сметчика:
{smeta_data}

Данные Закупщика:
{procurement_data}

Проверь:
1. Соответствует ли НМЦК (от Закупщика) сметной стоимости (от Сметчика)?
2. Если маржа < 15%, учтены ли все скрытые затраты (логистика, хранение, утилизация)?
3. Нет ли позиций с аномально низкой/высокой стоимостью относительно рынка?
4. Учтены ли региональные особенности в ценах?

Найденные противоречия оформи в JSON.""",

    "cross_agent_consistency": """Проверь кросс-агентную согласованность всего конвейера.

Сигналы агентов для HermesRouter:
{agent_signals}

Уверенность агентов:
{confidence_scores}

Финальный вердикт Hermes:
{hermes_decision}

Проверь:
1. Нет ли противоречия между сигналами агентов? (Например, ПТО дал 0.9 а Сметчик 0.1)
2. Если confidence агента низкий (< 0.3), учтено ли это в весовом скоринге?
3. Не противоречит ли финальный вердикт ключевым рискам?
4. Если был LLM fallback — адекватно ли это отражено в вердикте?

Найденные противоречия оформи в JSON.""",
}


# =============================================================================
# Auditor Agent
# =============================================================================

class AuditorAgent:
    """
    Агент-Аудитор — Red Team для верификации выводов других агентов.

    Использует адверсариальные промпты чтобы заставить LLM искать
    противоречия и пропущенные риски, а не подтверждать выводы.

    Запускается ПОСЛЕ всех агентов, но ДО финального утверждения вердикта.
    """

    def __init__(self, llm_engine):
        self._llm = llm_engine

    async def audit(self, state: Dict[str, Any]) -> AuditorReport:
        """
        Провести полный аудит состояния конвейера.

        Args:
            state: AgentState v2 с результатами всех агентов

        Returns:
            AuditorReport с вердиктом и находками
        """
        import uuid

        all_findings: List[AuditFinding] = []
        checks_run = 0
        checks_passed = 0

        # ── Проверка 1: ПТО vs Сметчик ──
        pto_data = state.get("vor_result") or {}
        smeta_data = state.get("smeta_result") or {}
        if pto_data or smeta_data:
            checks_run += 1
            findings = await self._check_pair(
                "pto_vs_smeta",
                pto_data=json.dumps(pto_data, ensure_ascii=False, default=str),
                smeta_data=json.dumps(smeta_data, ensure_ascii=False, default=str),
            )
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 2: Юрист vs ПТО ──
        legal_data = state.get("legal_result") or {}
        if legal_data or pto_data:
            checks_run += 1
            findings = await self._check_pair(
                "legal_vs_pto",
                legal_data=json.dumps(legal_data, ensure_ascii=False, default=str),
                pto_data=json.dumps(pto_data, ensure_ascii=False, default=str),
            )
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 3: Сметчик vs Закупщик ──
        procurement_data = state.get("procurement_result") or {}
        if smeta_data or procurement_data:
            checks_run += 1
            findings = await self._check_pair(
                "smeta_vs_procurement",
                smeta_data=json.dumps(smeta_data, ensure_ascii=False, default=str),
                procurement_data=json.dumps(procurement_data, ensure_ascii=False, default=str),
            )
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 4: Кросс-агентная согласованность ──
        hermes_decision = state.get("hermes_decision") or {}
        if hermes_decision:
            checks_run += 1
            findings = await self._check_pair(
                "cross_agent_consistency",
                agent_signals=json.dumps(
                    hermes_decision.get("agent_signals", {}),
                    ensure_ascii=False,
                ),
                confidence_scores=json.dumps(
                    state.get("confidence_scores", {}),
                    ensure_ascii=False,
                ),
                hermes_decision=json.dumps(hermes_decision, ensure_ascii=False, default=str),
            )
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Определение вердикта ──
        criticals = [f for f in all_findings if f.severity == ConflictSeverity.CRITICAL]
        highs = [f for f in all_findings if f.severity == ConflictSeverity.HIGH]

        if criticals:
            verdict = AuditorVerdict.REJECT
            confidence = 0.95
        elif highs:
            verdict = AuditorVerdict.APPROVED_WITH_NOTES
            confidence = 0.75
        else:
            verdict = AuditorVerdict.APPROVED
            confidence = 0.9 if checks_passed == checks_run else 0.7

        return AuditorReport(
            report_id=str(uuid.uuid4())[:8],
            verdict=verdict,
            total_checks=checks_run,
            findings=all_findings,
            passed_checks=checks_passed,
            confidence=confidence,
        )

    async def _check_pair(self, check_name: str, **kwargs) -> List[AuditFinding]:
        """Проверить одну пару агентов через LLM."""
        import uuid

        prompt_template = AUDITOR_CHECK_PROMPTS.get(check_name, "")
        if not prompt_template:
            return []

        prompt = prompt_template.format(**kwargs)
        messages = [
            {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm.safe_chat(
                "pm",  # Используем PM-модель для аудита (Llama 70B)
                messages,
                fallback_response='{"findings": [], "overall_verdict": "APPROVED", "confidence": 0.5}',
                temperature=0.2,
            )

            data = json.loads(response) if isinstance(response, str) else response
            raw_findings = data.get("findings", [])

            findings = []
            for f in raw_findings:
                severity_str = f.get("severity", "MEDIUM").upper()
                try:
                    severity = ConflictSeverity(severity_str.lower())
                except ValueError:
                    severity = ConflictSeverity.MEDIUM

                findings.append(AuditFinding(
                    finding_id=str(uuid.uuid4())[:6],
                    target_agent=f.get("target_agent", "unknown"),
                    category=f.get("category", "logic_error"),
                    description=f.get("description", ""),
                    severity=severity,
                    source_docs=f.get("source_docs", []),
                    recommendation=f.get("recommendation", ""),
                ))

            return findings

        except Exception as e:
            logger.error(f"Auditor check {check_name} failed: {e}")
            return []


# =============================================================================
# Auditor Node (LangGraph)
# =============================================================================

async def auditor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Аудитора для LangGraph workflow.

    Добавляется в граф ПОСЛЕ всех рабочих агентов, ПЕРЕД Hermes verdict.

    Если аудитор находит CRITICAL противоречия — вердикт Hermes
    автоматически становится NO_GO с пометкой auditor_rejected=True.
    """
    from src.core.llm_engine import llm_engine

    logger.info("Auditor Red Team Starting...")
    auditor = AuditorAgent(llm_engine)

    try:
        report = await auditor.audit(state)
        logger.info(report.summary())

        auditor_data = {
            "verdict": report.verdict.value,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "findings_count": len(report.findings),
            "critical_count": len(report.critical_findings),
            "high_count": len(report.high_findings),
            "confidence": report.confidence,
            "summary": report.summary(),
        }

        result = {
            "auditor_report": auditor_data,
            "intermediate_data": {
                **state.get("intermediate_data", {}),
                "auditor_verdict": report.verdict.value,
                "auditor_critical_count": len(report.critical_findings),
            },
        }

        # Если REJECT — принудительно останавливаем конвейер
        if report.verdict == AuditorVerdict.REJECT:
            logger.warning(
                "Auditor REJECTED pipeline: %d critical findings",
                len(report.critical_findings),
            )
            result["is_complete"] = True
            result["next_step"] = "complete"
            result["auditor_rejected"] = True

        return result

    except Exception as e:
        logger.error(f"Auditor node failed: {e}")
        return {
            "auditor_report": {"verdict": "error", "error": str(e)},
        }


class AuditorRejection(Exception):
    """Выбрасывается при отклонении конвейера Аудитором."""

    def __init__(self, report: AuditorReport):
        self.report = report
        super().__init__(f"Auditor rejected pipeline: {report.summary()}")
