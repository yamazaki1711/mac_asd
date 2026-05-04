"""
ASD v12.0 — Hybrid Document Classifier + Guidance System.

HybridClassifier: keyword-based (fast) + LLM fallback (accurate for edge cases)
GuidanceSystem (Штурман): даёт задания людям-операторам через Telegram
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Hybrid Classifier — keyword + LLM fallback
# =============================================================================

@dataclass
class ClassificationResult:
    """Результат классификации с объяснением."""
    doc_type: str
    confidence: float
    method: str  # "keyword", "llm", "hybrid"
    reasoning: str = ""
    alternatives: List[Tuple[str, float]] = field(default_factory=list)


class HybridClassifier:
    """
    Гибридный классификатор: keyword-based (быстро) + LLM fallback (точно).

    Стратегия:
      1. Сначала keyword-based классификация (мгновенно)
      2. Если confidence < 0.5 — пробуем LLM fallback
      3. LLM видит текст документа и список возможных типов
      4. Результат LLM сравнивается с keyword — если расходятся, приоритет LLM
    """

    def __init__(self, llm_engine=None):
        self._llm = llm_engine

    async def classify(self, text: str, enable_llm: bool = True) -> ClassificationResult:
        """
        Классифицировать документ гибридным методом.

        Args:
            text: извлечённый текст документа
            enable_llm: использовать LLM fallback при низкой уверенности

        Returns:
            ClassificationResult
        """
        # Шаг 1: keyword-based (быстро)
        from src.core.ingestion import DocumentClassifier, DocumentType
        kw_classifier = DocumentClassifier()
        kw_type, kw_conf = kw_classifier.classify(text)

        if kw_conf >= 0.7 or not enable_llm:
            return ClassificationResult(
                doc_type=kw_type.value,
                confidence=kw_conf,
                method="keyword",
                reasoning=f"Keyword match: {kw_type.value}",
            )

        # Шаг 2: LLM fallback для низкой уверенности
        if self._llm:
            try:
                llm_type, llm_conf, reasoning = await self._llm_classify(text)
                # Гибридное решение
                if llm_conf > kw_conf:
                    return ClassificationResult(
                        doc_type=llm_type,
                        confidence=llm_conf,
                        method="hybrid",
                        reasoning=reasoning,
                        alternatives=[(kw_type.value, kw_conf)],
                    )
            except Exception as e:
                logger.warning("LLM classification failed: %s", e)

        # Fallback: возвращаем keyword-результат как есть
        return ClassificationResult(
            doc_type=kw_type.value,
            confidence=kw_conf,
            method="keyword",
            reasoning="LLM unavailable, keyword only",
        )

    async def _llm_classify(self, text: str) -> Tuple[str, float, str]:
        """
        Классифицировать документ с помощью LLM.

        Отправляет LLM первые 3000 символов текста и список типов документов.
        """
        prompt = f"""Ты — эксперт по классификации строительных документов.
Определи тип документа по его содержимому.

Типы документов:
- aosr — Акт освидетельствования скрытых работ
- aook — Акт освидетельствования ответственных конструкций
- certificate — Сертификат/паспорт качества
- ttn — Товарно-транспортная накладная
- ks2 — Акт о приёмке выполненных работ (КС-2)
- ks3 — Справка о стоимости (КС-3)
- contract — Договор (подряда, поставки)
- claim — Претензия / иск
- vor — Ведомость объёмов работ
- journal — Журнал работ (ОЖР, ЖВК, ЖБР)
- executive_scheme — Исполнительная схема
- letter — Деловое письмо
- email — Email-переписка
- unknown — Не удалось определить

Текст документа:
{text[:3000]}

Ответь СТРОГО в формате JSON:
{{"type": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""

        try:
            response = await self._llm.safe_chat(
                "pm",
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                fallback_response='{"type": "unknown", "confidence": 0.3, "reasoning": "LLM error"}',
            )
            import json
            data = json.loads(response) if isinstance(response, str) else response
            return (data.get("type", "unknown"), data.get("confidence", 0.5), data.get("reasoning", ""))
        except (json.JSONDecodeError, ValueError, RuntimeError) as e:
            logger.warning("LLM classification parse failed: %s", e)
            return ("unknown", 0.0, "LLM parse error")


# =============================================================================
# Guidance System — Штурман
# =============================================================================

class TaskPriority(str, Enum):
    CRITICAL = "critical"  # Блокирует дальнейшую работу
    HIGH = "high"          # Срочно
    MEDIUM = "medium"      # В порядке очереди
    LOW = "low"            # Можно отложить


@dataclass
class OperatorTask:
    """Задание оператору (человеку в команде)."""
    task_id: str
    role: str                       # "operator", "pto_engineer", "lawyer", "estimator"
    title: str
    description: str
    priority: TaskPriority
    estimated_minutes: int
    depends_on: List[str] = field(default_factory=list)  # ID задач-зависимостей
    deliverables: List[str] = field(default_factory=list)  # Что должно быть на выходе
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


class GuidanceSystem:
    """
    Штурман — система постановки задач Оператору.

    На основе forensic-анализа (Auditor) и инвентаризации (Ingestion Pipeline)
    формирует задания для людей в команде:

    Роли:
      - operator:      Оператор АСД (сканирует, отправляет RFQ, получает КП)
      - pto_engineer:  Инженер ПТО (проверяет АОСР, верифицирует ИД)
      - lawyer:        Юрист (анализирует договоры, готовит претензии)
      - estimator:     Сметчик (проверяет сметы, считает рентабельность)

    Задания доставляются через Telegram бота @My_os_hermes_bot.
    """

    def __init__(self, project_code: str = ""):
        self.project_code = project_code
        self.tasks: List[OperatorTask] = []
        self.completed_tasks: List[OperatorTask] = []

    # =========================================================================
    # Task Generation
    # =========================================================================

    def generate_tasks_from_audit(
        self, forensic_findings: List[Any], project_code: str = ""
    ) -> List[OperatorTask]:
        """
        Сгенерировать задания на основе forensic-находок Auditor.

        Каждая CRITICAL/HIGH находка → задание Оператору.
        """
        tasks = []
        for i, finding in enumerate(forensic_findings):
            task = self._finding_to_task(finding, i, project_code)
            if task:
                tasks.append(task)
        self.tasks.extend(tasks)
        return tasks

    def generate_tasks_from_inventory(
        self, inventory_report: Dict[str, Any], project_code: str = ""
    ) -> List[OperatorTask]:
        """
        Сгенерировать задания на основе отчёта об инвентаризации.

        Чего не хватает → задание найти/отсканировать/запросить.
        """
        tasks = []
        doc_types_found = inventory_report.get("doc_types_found", {})
        unknown = inventory_report.get("unknown_docs", [])

        # Неизвестные документы → на ручную проверку
        for doc_path in unknown:
            tasks.append(OperatorTask(
                task_id=f"review_{len(tasks)}",
                role="operator",
                title=f"Идентифицировать документ: {doc_path}",
                description=(
                    f"Документ {doc_path} не удалось классифицировать автоматически. "
                    f"Откройте файл и определите тип вручную."
                ),
                priority=TaskPriority.MEDIUM,
                estimated_minutes=5,
                deliverables=["Тип документа"],
            ))

        # Каких типов документов не хватает
        required_types = ["aosr", "certificate", "ttn", "contract", "ks2", "ks3"]
        for dt in required_types:
            if dt not in doc_types_found:
                tasks.append(OperatorTask(
                    task_id=f"missing_{dt}_{len(tasks)}",
                    role="operator",
                    title=f"Найти документы типа '{dt}'",
                    description=(
                        f"В собранных материалах не найдено документов типа '{dt}'. "
                        f"Проверьте: папки на объекте, почту, флешки, переписку. "
                        f"Возможно, документы не отсканированы."
                    ),
                    priority=TaskPriority.HIGH,
                    estimated_minutes=30,
                ))

        self.tasks.extend(tasks)
        return tasks

    def generate_scanning_tasks(
        self, folders_to_scan: List[str], project_code: str = ""
    ) -> List[OperatorTask]:
        """
        Сгенерировать задачи на сканирование папок.

        Фаза «фидер» — первые дни на объекте.
        """
        tasks = []
        for folder in folders_to_scan:
            tasks.append(OperatorTask(
                task_id=f"scan_{len(tasks)}",
                role="operator",
                title=f"Отсканировать папку: {folder}",
                description=(
                    f"Все документы из папки «{folder}» должны быть отсканированы "
                    f"(А4/А3, 300 dpi, цветной режим для синих печатей). "
                    f"Сохранить в /scans/{folder}/"
                ),
                priority=TaskPriority.HIGH,
                estimated_minutes=45,
                deliverables=[f"PDF-файлы в /scans/{folder}/"],
            ))
        self.tasks.extend(tasks)
        return tasks

    # =========================================================================
    # Helpers
    # =========================================================================

    def _finding_to_task(self, finding: Any, idx: int, project_code: str) -> Optional[OperatorTask]:
        """Конвертировать ForensicFinding → OperatorTask."""
        severity = getattr(finding, 'severity', None)
        if not severity:
            return None

        sev_value = severity.value if hasattr(severity, 'value') else str(severity)

        priority_map = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "info": TaskPriority.LOW,
        }
        priority = priority_map.get(sev_value, TaskPriority.MEDIUM)

        # Определяем роль по типу проверки
        check_name = getattr(finding, 'check_name', '')
        role_map = {
            "batch_coverage": "operator",
            "certificate_reuse": "pto_engineer",
            "orphan_certificates": "operator",
            "material_spec_validation": "pto_engineer",
            "document_provenance": "operator",
        }
        role = role_map.get(check_name, "operator")

        description = getattr(finding, 'description', 'Без описания')
        recommendation = getattr(finding, 'recommendation', '')

        return OperatorTask(
            task_id=f"forensic_{check_name}_{idx}",
            role=role,
            title=f"[{check_name}] {description[:100]}",
            description=(
                f"{description}\n\n"
                f"Рекомендация: {recommendation}"
            ),
            priority=priority,
            estimated_minutes=30 if priority in (TaskPriority.CRITICAL, TaskPriority.HIGH) else 15,
            deliverables=["Устранённое замечание"],
        )

    # =========================================================================
    # Task Delivery — Telegram
    # =========================================================================

    def format_for_telegram(self, tasks: List[OperatorTask] = None) -> str:
        """
        Форматировать задания для отправки в Telegram.

        Returns:
            Markdown-текст для отправки через send_message.
        """
        todo = tasks or self.tasks
        if not todo:
            return "✅ Все задания выполнены. Новых задач нет."

        # Группировка по приоритету
        critical = [t for t in todo if t.priority == TaskPriority.CRITICAL]
        high = [t for t in todo if t.priority == TaskPriority.HIGH]
        medium = [t for t in todo if t.priority == TaskPriority.MEDIUM]

        lines = ["## 📋 Задания Оператору\n"]

        if critical:
            lines.append("### 🔴 КРИТИЧЕСКИЕ (блокируют работу)")
            for t in critical:
                lines.append(f"**{t.title}**")
                lines.append(f"  Роль: *{t.role}* | ⏱ ~{t.estimated_minutes} мин")
                lines.append(f"  {t.description[:200]}")
                if t.deliverables:
                    lines.append(f"  📦 Результат: {', '.join(t.deliverables)}")
                lines.append("")

        if high:
            lines.append("### 🟠 СРОЧНЫЕ")
            for t in high[:5]:
                lines.append(f"**{t.title}**")
                lines.append(f"  Роль: *{t.role}* | ⏱ ~{t.estimated_minutes} мин")
                lines.append("")

        if medium:
            lines.append("### 🟡 В ПОРЯДКЕ ОЧЕРЕДИ")
            for t in medium[:5]:
                lines.append(f"• {t.title} ({t.role})")
            if len(medium) > 5:
                lines.append(f"  ... и ещё {len(medium) - 5} задач")
            lines.append("")

        lines.append("---")
        lines.append(f"*Всего задач: {len(todo)} (🔴{len(critical)} 🟠{len(high)} 🟡{len(medium)})*")
        return "\n".join(lines)

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Статистика по задачам."""
        total = len(self.tasks)
        completed = len(self.completed_tasks)
        by_priority = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for t in self.tasks:
            by_priority[t.priority.value] = by_priority.get(t.priority.value, 0) + 1
        return {
            "total": total,
            "completed": completed,
            "pending": total - completed,
            "by_priority": by_priority,
        }


# =============================================================================
# Singletons
# =============================================================================

hybrid_classifier = HybridClassifier()
guidance_system = GuidanceSystem()
