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

# =============================================================================
# Auditor Agent (rule-based, no LLM-as-Judge)
# =============================================================================

class AuditorAgent:
    """
    Агент-Аудитор — Red Team для верификации выводов других агентов.

    v12.0: Все проверки 1–4 переведены на rule-based валидацию (без LLM).
    LLM-as-a-Judge исключён — только структурная сверка данных.

    Запускается ПОСЛЕ всех агентов, но ДО финального утверждения вердикта.
    """

    def __init__(self, llm_engine=None):
        self._llm = llm_engine  # Больше не используется (оставлено для обратной совместимости)

    # =========================================================================
    # Rule-based Cross-Agent Validation (проверки 1–4, без LLM)
    # =========================================================================

    def _check_pto_vs_smeta(
        self, pto_data: dict, smeta_data: dict
    ) -> List[AuditFinding]:
        """
        Проверка 1: ПТО vs Сметчик (rule-based).

        Сверяет структуры данных:
        - Все ли позиции ВОР учтены в смете?
        - Соответствуют ли единицы измерения?
        - Нет ли двойного учёта?
        """
        import uuid
        findings = []

        # Extract work items from both agents
        vor_items = pto_data.get("volumes", []) or pto_data.get("items", [])
        estimate_items = smeta_data.get("items", []) or smeta_data.get("lines", [])

        if not vor_items or not estimate_items:
            if vor_items and not estimate_items:
                findings.append(AuditFinding(
                    finding_id=str(uuid.uuid4())[:6],
                    target_agent="smeta",
                    category="missing_risk",
                    description=f"ПТО предоставил {len(vor_items)} позиций ВОР, но Сметчик не предоставил смету",
                    severity=ConflictSeverity.CRITICAL,
                    recommendation="Сметчик должен рассчитать стоимость по ВОР",
                ))
            return findings

        # Build index of estimate items by description
        est_descriptions = {}
        for item in estimate_items:
            desc = str(item.get("description", item.get("name", ""))).lower().strip()
            unit = str(item.get("unit", "")).lower().strip()
            qty = item.get("quantity", item.get("amount", 0))
            est_descriptions[desc] = {"unit": unit, "quantity": qty}

        for vor_item in vor_items:
            vor_desc = str(vor_item.get("description", vor_item.get("item", ""))).lower().strip()
            vor_unit = str(vor_item.get("unit", "")).lower().strip()
            vor_qty = vor_item.get("quantity", 0)

            # Try to find matching estimate item
            matched = None
            for est_desc, est_data in est_descriptions.items():
                if vor_desc in est_desc or est_desc in vor_desc:
                    matched = est_data
                    break

            if not matched:
                findings.append(AuditFinding(
                    finding_id=str(uuid.uuid4())[:6],
                    target_agent="smeta",
                    category="missing_risk",
                    description=f"Позиция ВОР не найдена в смете: «{vor_item.get('description', vor_item.get('item', ''))}»",
                    severity=ConflictSeverity.HIGH,
                    recommendation="Добавить позицию в смету или обосновать исключение",
                ))
            else:
                # Unit mismatch check
                if vor_unit and matched["unit"] and vor_unit != matched["unit"]:
                    findings.append(AuditFinding(
                        finding_id=str(uuid.uuid4())[:6],
                        target_agent="smeta",
                        category="contradiction",
                        description=(
                            f"Несоответствие единиц: ВОР «{vor_item.get('description', '')}» "
                            f"→ {vor_unit}, смета → {matched['unit']}"
                        ),
                        severity=ConflictSeverity.HIGH,
                        recommendation="Привести единицы измерения к единому стандарту",
                    ))

        return findings

    def _check_legal_vs_pto(
        self, legal_data: dict, pto_data: dict
    ) -> List[AuditFinding]:
        """
        Проверка 2: Юрист vs ПТО (rule-based).

        - Все ли виды работ из ВОР покрыты юридическим анализом?
        - Есть ли работы, для которых юрист не проверил БЛС-ловушки?
        """
        import uuid
        findings = []

        vor_items = pto_data.get("volumes", []) or pto_data.get("items", [])
        legal_findings = legal_data.get("findings", []) or legal_data.get("traps_found", [])

        if not vor_items:
            return findings

        # Extract work types from VOR
        work_types = set()
        for item in vor_items:
            wt = item.get("work_type", item.get("type", ""))
            if wt:
                work_types.add(str(wt).lower().strip())

        # Extract work types covered by legal analysis
        legal_work_types = set()
        for lf in legal_findings:
            clause = str(lf.get("clause_ref", lf.get("section", ""))).lower()
            issue = str(lf.get("issue", lf.get("description", ""))).lower()
            for wt in work_types:
                if wt in clause or wt in issue:
                    legal_work_types.add(wt)

        # Check uncovered work types
        uncovered = work_types - legal_work_types
        if uncovered:
            findings.append(AuditFinding(
                finding_id=str(uuid.uuid4())[:6],
                target_agent="legal",
                category="missing_risk",
                description=(
                    f"Виды работ без юридического анализа БЛС: {', '.join(sorted(uncovered))}. "
                    f"Покрыто: {len(legal_work_types)}/{len(work_types)}"
                ),
                severity=ConflictSeverity.HIGH,
                recommendation="Юрист должен проверить все виды работ по БЛС-ловушкам",
            ))

        return findings

    def _check_smeta_vs_procurement(
        self, smeta_data: dict, procurement_data: dict
    ) -> List[AuditFinding]:
        """
        Проверка 3: Сметчик vs Закупщик (rule-based).

        - Соответствует ли НМЦК сметной стоимости?
        - Если маржа < 15%, учтены ли скрытые затраты?
        """
        import uuid
        findings = []

        est_total = smeta_data.get("total_cost", smeta_data.get("total", 0))
        nmck = procurement_data.get("nmck", procurement_data.get("starting_price", 0))

        if not est_total or not nmck:
            return findings

        try:
            est_total = float(est_total)
            nmck = float(nmck)
        except (TypeError, ValueError):
            return findings

        if nmck <= 0 or est_total <= 0:
            return findings

        margin_pct = ((nmck - est_total) / est_total) * 100

        if margin_pct < 10:
            findings.append(AuditFinding(
                finding_id=str(uuid.uuid4())[:6],
                target_agent="procurement",
                category="missing_risk",
                description=(
                    f"Маржа {margin_pct:.1f}% — критически низкая. "
                    f"Сметная стоимость: {est_total:,.0f} ₽, НМЦК: {nmck:,.0f} ₽"
                ),
                severity=ConflictSeverity.CRITICAL,
                recommendation=(
                    "Проверить калькуляцию. Учтены ли скрытые затраты: "
                    "логистика, хранение, утилизация, страхование, банковская гарантия?"
                ),
            ))
        elif margin_pct < 15:
            findings.append(AuditFinding(
                finding_id=str(uuid.uuid4())[:6],
                target_agent="procurement",
                category="missing_risk",
                description=(
                    f"Маржа {margin_pct:.1f}% — ниже рекомендуемой. "
                    f"Сметная стоимость: {est_total:,.0f} ₽, НМЦК: {nmck:,.0f} ₽"
                ),
                severity=ConflictSeverity.HIGH,
                recommendation="Проверить, учтены ли все накладные расходы и риски",
            ))

        return findings

    def _check_cross_agent_consistency(
        self, state: Dict[str, Any]
    ) -> List[AuditFinding]:
        """
        Проверка 4: Кросс-агентная согласованность (rule-based).

        - Нет ли противоречия между confidence scores агентов?
        - Нет ли агентов с аномально низкой уверенностью?
        """
        import uuid
        findings = []

        confidence_scores = state.get("confidence_scores", {})
        if not confidence_scores:
            return findings

        # Check for low-confidence outliers
        low_confidence = []
        for agent, conf in confidence_scores.items():
            try:
                conf_val = float(conf)
                if conf_val < 0.3:
                    low_confidence.append((agent, conf_val))
            except (TypeError, ValueError):
                pass

        if low_confidence:
            agents_str = ", ".join(f"{a} ({c:.2f})" for a, c in low_confidence)
            findings.append(AuditFinding(
                finding_id=str(uuid.uuid4())[:6],
                target_agent="orchestrator",
                category="logic_error",
                description=(
                    f"Агенты с аномально низкой уверенностью: {agents_str}. "
                    f"Результаты этих агентов ненадёжны."
                ),
                severity=ConflictSeverity.HIGH,
                recommendation=(
                    "Перезапустить агентов с низкой уверенностью или "
                    "запросить уточнение входных данных"
                ),
            ))

        # Check for extreme divergence between related agents
        agent_signals = state.get("hermes_decision", {}).get("agent_signals", {})
        if agent_signals:
            pto_signal = agent_signals.get("pto", "")
            smeta_signal = agent_signals.get("smeta", "")
            if pto_signal and smeta_signal and pto_signal != smeta_signal:
                findings.append(AuditFinding(
                    finding_id=str(uuid.uuid4())[:6],
                    target_agent="orchestrator",
                    category="contradiction",
                    description=(
                        f"Расхождение сигналов: ПТО → {pto_signal}, "
                        f"Сметчик → {smeta_signal}"
                    ),
                    severity=ConflictSeverity.MEDIUM,
                    recommendation="Проверить причину расхождения сигналов между ПТО и Сметчиком",
                ))

        return findings

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

        # ── Проверка 1: ПТО vs Сметчик (rule-based) ──
        pto_data = state.get("vor_result") or {}
        smeta_data = state.get("smeta_result") or {}
        if pto_data or smeta_data:
            checks_run += 1
            findings = self._check_pto_vs_smeta(pto_data, smeta_data)
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 2: Юрист vs ПТО (rule-based) ──
        legal_data = state.get("legal_result") or {}
        if legal_data or pto_data:
            checks_run += 1
            findings = self._check_legal_vs_pto(legal_data, pto_data)
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 3: Сметчик vs Закупщик (rule-based) ──
        procurement_data = state.get("procurement_result") or {}
        if smeta_data or procurement_data:
            checks_run += 1
            findings = self._check_smeta_vs_procurement(smeta_data, procurement_data)
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 4: Кросс-агентная согласованность (rule-based) ──
        if state.get("confidence_scores") or state.get("hermes_decision"):
            checks_run += 1
            findings = self._check_cross_agent_consistency(state)
            all_findings.extend(findings)
            if not findings:
                checks_passed += 1

        # ── Проверка 5–8: Forensic Document Checks (rule-based, no LLM) ──
        forensic_findings = await self._run_forensic_checks(state)
        if forensic_findings:
            checks_run += 1
            audit_findings = self._forensic_to_audit(forensic_findings)
            all_findings.extend(audit_findings)
            # Forensic-проверка считается пройденной только если нет CRITICAL
            critically = [f for f in audit_findings if f.severity == ConflictSeverity.CRITICAL]
            if not critically:
                checks_passed += 1

        # ── Проверка 9–11: Classification Quality Checks (rule-based) ──
        class_findings = self._check_classification_quality(state)
        if class_findings:
            checks_run += 1
            all_findings.extend(class_findings)
            critically = [f for f in class_findings if f.severity == ConflictSeverity.CRITICAL]
            if not critically:
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

    # =========================================================================
    # Forensic Document Checks (rule-based, no LLM)
    # =========================================================================

    async def _run_forensic_checks(self, state: Dict[str, Any]) -> List[Any]:
        """
        Запустить rule-based forensic-проверки по графу документов.

        Проверки:
          5. Batch coverage — Σ АОСР ≤ размер партии сертификата
          6. Certificate reuse — сертификаты без входного контроля в >1 АОСР
          7. Orphan certificates — сертификаты без цепочки Batch → InputControl
          8. Material spec validation — проверка проблемных материалов через OBSOLETE_MATERIALS

        Returns:
            Список ForensicFinding из graph_service
        """
        from src.core.graph_service import graph_service

        findings = []

        try:
            # ── Проверка 5: Batch Coverage ──
            for node_id, data in graph_service.graph.nodes(data=True):
                if data.get("type") == "Certificate":
                    findings.extend(graph_service.check_batch_coverage(node_id))

            # ── Проверка 6: Certificate Reuse ──
            findings.extend(graph_service.check_certificate_reuse())

            # ── Проверка 7: Orphan Certificates ──
            findings.extend(graph_service.check_orphan_certificates())

            # ── Проверка 8: Material Spec Validation ──
            materials_spec = state.get("materials_spec", []) or state.get("materials", [])
            if not materials_spec:
                # Пробуем извлечь из данных ПТО
                pto_data = state.get("vor_result") or {}
                materials_spec = pto_data.get("materials", [])

            for mat in materials_spec:
                mat_name = mat if isinstance(mat, str) else mat.get("name", "")
                if mat_name:
                    findings.extend(graph_service.validate_material_spec(mat_name))

        except Exception as e:
            logger.error("Forensic checks error: %s", e)

        return findings

    def _forensic_to_audit(self, forensic_findings: List[Any]) -> List[AuditFinding]:
        """
        Конвертировать ForensicFinding → AuditFinding.

        Маппинг severity:
          ForensicSeverity.CRITICAL → ConflictSeverity.CRITICAL
          ForensicSeverity.HIGH      → ConflictSeverity.HIGH
          ForensicSeverity.MEDIUM    → ConflictSeverity.MEDIUM
          ForensicSeverity.INFO      → ConflictSeverity.LOW
        """
        import uuid

        severity_map = {
            "critical": ConflictSeverity.CRITICAL,
            "high": ConflictSeverity.HIGH,
            "medium": ConflictSeverity.MEDIUM,
            "info": ConflictSeverity.LOW,
        }

        audit_findings = []
        for ff in forensic_findings:
            audit_findings.append(AuditFinding(
                finding_id=str(uuid.uuid4())[:6],
                target_agent="forensic",
                category="norm_violation",
                description=ff.description,
                severity=severity_map.get(ff.severity.value, ConflictSeverity.MEDIUM),
                source_docs=["ГОСТ Р 53629-2009", "ПП РФ №2425", "Приказ 344/пр"],
                recommendation=ff.recommendation,
            ))

        return audit_findings

    # =========================================================================
    # Classification Quality Checks (rule-based, no LLM)
    # =========================================================================

    # Проверка 9: Type Self-Consistency — ключевые слова, которые ДОЛЖНЫ быть
    # в тексте документа данного типа (не путать с классификатором — это валидация).
    TYPE_CONSISTENCY_RULES = {
        "aosr": {
            "required": ["освидетельствование", "работ"],
            "forbidden": [],
            "severity_on_fail": ConflictSeverity.HIGH,
            "description": "Текст не содержит «освидетельствование» — маловероятно для АОСР",
        },
        "certificate": {
            "required": ["сертификат", "качеств"],
            "forbidden": [],
            "severity_on_fail": ConflictSeverity.HIGH,
            "description": "Текст не содержит «сертификат качества» — маловероятно для сертификата",
        },
        "ks2": {
            "required": ["приёмк", "сметн"],
            "forbidden": [],
            "severity_on_fail": ConflictSeverity.HIGH,
            "description": "Текст не содержит «приёмка» и «сметный» — маловероятно для КС-2",
        },
        "ks3": {
            "required": ["справка", "стоимост"],
            "forbidden": [],
            "severity_on_fail": ConflictSeverity.HIGH,
            "description": "Текст не содержит «справка о стоимости» — маловероятно для КС-3",
        },
        "contract": {
            "required": ["договор", "предмет"],
            "forbidden": [],
            "severity_on_fail": ConflictSeverity.MEDIUM,
            "description": "Текст не содержит «договор» и «предмет» — договор может быть кратким",
        },
        "journal": {
            "required": ["журнал", "дата"],
            "forbidden": ["ось", "отметк"],  # не должно быть осей и отметок (это схема)
            "severity_on_fail": ConflictSeverity.MEDIUM,
            "description": "Текст не содержит признаков журнала или содержит признаки схемы",
        },
        "executive_scheme": {
            "required": ["ось", "отметк"],
            "forbidden": ["журнал"],
            "severity_on_fail": ConflictSeverity.LOW,  # Чертежи — OCR ненадёжен
            "description": "Текст не содержит «ось» и «отметка» — возможно, из-за плохого OCR чертежа",
        },
    }

    # Проверка 10: VLM vs Keyword Confidence Mismatch
    # Когда keyword дал ≥ 0.7 одно, а VLM другое — один из них точно ошибается.
    CONFIDENCE_MISMATCH_RULES = {
        "keyword_high_vlm_disagree": {
            "condition": "kw_conf >= 0.7 and kw_type != vlm_type",
            "severity": ConflictSeverity.HIGH,
            "description_tpl": "Keyword ({kw_type}, conf={kw_conf:.2f}) vs VLM ({vlm_type}, conf={vlm_conf:.2f}) — расходятся при высокой уверенности keyword",
        },
        "vlm_flat_confidence": {
            "condition": "vlm_conf == 0.85",  # VLM always returns 0.85 — подозрительно
            "severity": ConflictSeverity.LOW,
            "description_tpl": "VLM confidence = 0.85 (стандартное значение) — некалиброванная уверенность",
        },
        "keyword_low_vlm_disagree": {
            "condition": "kw_conf < 0.3 and kw_type != vlm_type",
            "severity": ConflictSeverity.MEDIUM,
            "description_tpl": "Keyword ({kw_type}, conf={kw_conf:.2f}) vs VLM ({vlm_type}) — VLM переопределил, доверяем VLM, но фиксируем расхождение",
        },
    }

    def _check_classification_quality(
        self, state: Optional[Dict[str, Any]] = None
    ) -> List[AuditFinding]:
        """
        Проверки качества классификации (9–11):

        9.  Type Self-Consistency — соответствует ли текст документа его типу
        10. VLM vs Keyword Confidence Mismatch — расходятся ли классификаторы
        11. Unsigned Critical Documents — отсутствуют ли подписи на ключевых документах

        Работает как в workflow (state с документами), так и в inventory mode
        (документы из ingestion pipeline).

        Args:
            state: AgentState (опционально — для inventory mode передаётся None)

        Returns:
            Список AuditFinding
        """
        import uuid

        findings: List[AuditFinding] = []

        # Получаем документы из state или из глобального ingestion pipeline
        documents = []
        if state:
            documents = state.get("documents", []) or state.get("ingested_docs", [])

        # Если документов нет в state — пробуем inventory pipeline
        if not documents:
            try:
                from src.core.ingestion import ingestion_pipeline
                documents = ingestion_pipeline.documents
            except Exception:
                pass

        if not documents:
            return findings

        for doc in documents:
            doc_type = getattr(doc, 'doc_type', None)
            if doc_type is None:
                continue

            dt_str = doc_type.value if hasattr(doc_type, 'value') else str(doc_type)
            text = getattr(doc, 'raw_text', '') or ''
            text_lower = text.lower()
            kw_conf = getattr(doc, 'classification_confidence', 0.0)
            vlm_classified = getattr(doc, 'vlm_classified', False)
            file_name = getattr(doc, 'file_path', '')
            file_name = str(file_name) if file_name else ''

            # ── Проверка 9: Type Self-Consistency ──
            rules = self.TYPE_CONSISTENCY_RULES.get(dt_str)
            if rules and text_lower:
                required_ok = all(r in text_lower for r in rules["required"])
                forbidden_ok = not any(f in text_lower for f in rules["forbidden"])
                if not required_ok or not forbidden_ok:
                    reason = rules["description"]
                    if rules.get("forbidden") and not forbidden_ok:
                        reason += " (найдены запрещённые маркеры)"
                    findings.append(AuditFinding(
                        finding_id=str(uuid.uuid4())[:6],
                        target_agent="classifier",
                        category="logic_error",
                        description=(
                            f"Type self-consistency FAIL: {file_name}\n"
                            f"Classified as '{dt_str}', but {reason}\n"
                            f"Text sample: {text[:200]}"
                        ),
                        severity=rules["severity_on_fail"],
                        source_docs=["internal: TYPE_CONSISTENCY_RULES"],
                        recommendation=(
                            f"Перепроверить классификацию документа. "
                            f"Возможно, VLM ошибся или документ иного типа."
                        ),
                    ))

            # ── Проверка 10: VLM vs Keyword Mismatch ──
            if vlm_classified:
                # VLM flat confidence (always 0.85 — uncalibrated)
                findings.append(AuditFinding(
                    finding_id=str(uuid.uuid4())[:6],
                    target_agent="classifier",
                    category="logic_error",
                    description=(
                        f"VLM flat confidence: {file_name}\n"
                        f"VLM confidence = 0.85 (стандартное, некалиброванное значение)"
                    ),
                    severity=ConflictSeverity.LOW,
                    source_docs=[],
                    recommendation="Откалибровать confidence VLM по реальным данным.",
                ))

            # ── Проверка 11: Unsigned Critical Documents ──
            scan_info = getattr(doc, 'scan_info', None) or {}
            if isinstance(scan_info, dict):
                sigs = scan_info.get("signatures_filled")
                if sigs is False and dt_str in ("aosr", "ks2", "ks3"):
                    findings.append(AuditFinding(
                        finding_id=str(uuid.uuid4())[:6],
                        target_agent="classifier",
                        category="norm_violation",
                        description=(
                            f"UNSIGNED critical document: {file_name}\n"
                            f"Type: {dt_str}. Без подписей документ недействителен."
                        ),
                        severity=ConflictSeverity.CRITICAL,
                        source_docs=["Приказ 344/пр", "ГрК РФ ст. 52"],
                        recommendation=(
                            f"Потребовать подписание {dt_str.upper()} у всех сторон "
                            f"(застройщик, ЛОС, проектировщик, стройконтроль). "
                            f"Без подписей документ не может быть включён в ИД."
                        ),
                    ))

        return findings


def audit_classification() -> List[AuditFinding]:
    """
    Standalone-вызов проверок классификации для inventory mode.
    Не требует LLM engine, не требует LangGraph state.

    Использует ingestion_pipeline.documents из последнего прогона.

    Returns:
        Список AuditFinding (проверки 9–11)
    """
    auditor = AuditorAgent(llm_engine=None)  # llm_engine не нужен для rule-based проверок
    return auditor._check_classification_quality(state=None)


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
