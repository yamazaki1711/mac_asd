"""
ASD v12.0 — Delo Agent (Делопроизводитель).

Реестр исполнительной документации, комплектование, трекинг статуса,
контроль сроков ответа заказчика, отправка документации.

Нормативная база:
  - Приказ Минстроя №344/пр (состав и порядок ведения ИД)
  - ПП РФ №468 (правила приёмки скрытых работ)
  - ГОСТ Р 70108-2025 (электронная ИД)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class DeloDocStatus(str, Enum):
    DRAFT = "draft"                # Черновик — не оформлен
    PREPARED = "prepared"         # Подготовлен — ждёт подписания
    SIGNED_INTERNAL = "signed_internal"  # Подписан Подрядчиком
    SUBMITTED = "submitted"       # Передан Заказчику
    ACCEPTED = "accepted"         # Принят Заказчиком
    REJECTED = "rejected"         # Отклонён — требует доработки
    ARCHIVED = "archived"         # В архиве


class DeliveryMethod(str, Enum):
    PAPER = "paper"                # Бумажный носитель
    ELECTRONIC = "electronic"      # Электронно (ЭДО/XML)
    HYBRID = "hybrid"              # Смешанный


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DocRegistryEntry:
    """Одна запись в реестре ИД."""
    reg_id: str                    # Регистрационный номер
    doc_type: str                  # Тип: АОСР, АООК, ИГС, сертификат...
    doc_name: str                  # Наименование документа
    category_344: str              # Категория по 344/пр (act_aosr, igs, ...)
    work_type: str = ""            # Вид работ
    status: DeloDocStatus = DeloDocStatus.DRAFT
    pages: int = 0
    prepared_date: Optional[str] = None
    submitted_date: Optional[str] = None
    accepted_date: Optional[str] = None
    deadline: Optional[str] = None  # Крайний срок ответа Заказчика
    counterparty: str = ""         # Кто должен подписать (Заказчик, Автор, Стройконтроль...)
    file_path: Optional[str] = None
    notes: str = ""

    @property
    def is_overdue(self) -> bool:
        if not self.deadline:
            return False
        return datetime.now() > datetime.fromisoformat(self.deadline)

    @property
    def days_since_submission(self) -> Optional[int]:
        if not self.submitted_date:
            return None
        return (datetime.now() - datetime.fromisoformat(self.submitted_date)).days

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reg_id": self.reg_id,
            "doc_type": self.doc_type,
            "doc_name": self.doc_name,
            "category_344": self.category_344,
            "status": self.status.value,
            "pages": self.pages,
            "submitted_date": self.submitted_date,
            "deadline": self.deadline,
            "is_overdue": self.is_overdue,
            "days_since_submission": self.days_since_submission,
        }


@dataclass
class DocRegistry:
    """Полный реестр ИД по проекту."""
    project_id: int
    project_name: str
    entries: List[DocRegistryEntry] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total_docs(self) -> int:
        return len(self.entries)

    @property
    def accepted_count(self) -> int:
        return sum(1 for e in self.entries if e.status == DeloDocStatus.ACCEPTED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for e in self.entries if e.status == DeloDocStatus.REJECTED)

    @property
    def overdue_count(self) -> int:
        return sum(1 for e in self.entries if e.is_overdue)

    @property
    def completion_pct(self) -> float:
        if not self.entries:
            return 0.0
        return round(self.accepted_count / self.total_docs * 100, 1)

    def by_status(self, status: DeloDocStatus) -> List[DocRegistryEntry]:
        return [e for e in self.entries if e.status == status]

    def by_category(self, category: str) -> List[DocRegistryEntry]:
        return [e for e in self.entries if e.category_344 == category]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "total_docs": self.total_docs,
            "accepted": self.accepted_count,
            "rejected": self.rejected_count,
            "overdue": self.overdue_count,
            "completion_pct": self.completion_pct,
            "entries": [e.to_dict() for e in self.entries],
        }


@dataclass
class SubmissionBatch:
    """Пакет документов для отправки Заказчику."""
    batch_id: str
    project_id: int
    entries: List[DocRegistryEntry] = field(default_factory=list)
    delivery_method: DeliveryMethod = DeliveryMethod.ELECTRONIC
    cover_letter: str = ""
    submitted_at: Optional[str] = None
    expected_response_days: int = 10  # Стандартный срок ответа

    @property
    def total_pages(self) -> int:
        return sum(e.pages for e in self.entries)

    @property
    def response_deadline(self) -> str:
        if self.submitted_at:
            dt = datetime.fromisoformat(self.submitted_at) + timedelta(days=self.expected_response_days)
            return dt.isoformat()
        return ""


# =============================================================================
# Delo Agent
# =============================================================================

class DeloAgent:
    """Агент-Делопроизводитель ASD v12.0."""

    def __init__(self, llm_engine=None):
        from src.core.llm_engine import llm_engine as _llm
        self._llm = llm_engine or _llm
        self._registries: Dict[int, DocRegistry] = {}

    # -------------------------------------------------------------------------
    # Registry Operations
    # -------------------------------------------------------------------------

    def create_registry(self, project_id: int, project_name: str) -> DocRegistry:
        """Создать реестр ИД по проекту."""
        registry = DocRegistry(project_id=project_id, project_name=project_name)
        self._registries[project_id] = registry
        logger.info("Registry created: project %d — %s", project_id, project_name)
        return registry

    def register_document(
        self,
        project_id: int,
        doc_type: str,
        doc_name: str,
        category_344: str = "act_aosr",
        work_type: str = "",
        pages: int = 0,
        counterparty: str = "",
        file_path: str = "",
    ) -> Optional[DocRegistryEntry]:
        """Зарегистрировать документ в реестре."""
        registry = self._registries.get(project_id)
        if not registry:
            logger.warning("No registry for project %d", project_id)
            return None

        reg_id = f"ASD-{project_id}-{len(registry.entries) + 1:04d}"
        entry = DocRegistryEntry(
            reg_id=reg_id,
            doc_type=doc_type,
            doc_name=doc_name,
            category_344=category_344,
            work_type=work_type,
            pages=pages,
            counterparty=counterparty,
            file_path=file_path,
        )
        registry.entries.append(entry)
        logger.info("Registered: %s — %s [%s]", reg_id, doc_type, doc_name)
        return entry

    def update_status(
        self, project_id: int, reg_id: str, status: DeloDocStatus, notes: str = ""
    ) -> bool:
        """Обновить статус документа."""
        registry = self._registries.get(project_id)
        if not registry:
            return False
        for entry in registry.entries:
            if entry.reg_id == reg_id:
                entry.status = status
                now = datetime.now().isoformat()
                if status == DeloDocStatus.SUBMITTED:
                    entry.submitted_date = now
                    entry.deadline = (datetime.now() + timedelta(days=10)).isoformat()
                elif status == DeloDocStatus.ACCEPTED:
                    entry.accepted_date = now
                if notes:
                    entry.notes = notes
                return True
        return False

    def get_registry(self, project_id: int) -> Optional[DocRegistry]:
        return self._registries.get(project_id)

    # -------------------------------------------------------------------------
    # комплектование (Batching)
    # -------------------------------------------------------------------------

    def create_submission_batch(
        self,
        project_id: int,
        category_filter: Optional[str] = None,
        delivery_method: DeliveryMethod = DeliveryMethod.ELECTRONIC,
    ) -> SubmissionBatch:
        """Сформировать пакет документов для отправки Заказчику."""
        registry = self._registries.get(project_id)
        if not registry:
            return SubmissionBatch(batch_id="", project_id=project_id)

        # Отбираем подготовленные, но не отправленные документы
        ready = [
            e for e in registry.entries
            if e.status in (DeloDocStatus.PREPARED, DeloDocStatus.SIGNED_INTERNAL)
        ]

        if category_filter:
            ready = [e for e in ready if e.category_344 == category_filter]

        batch_id = f"BATCH-{project_id}-{len(registry.entries):04d}"
        batch = SubmissionBatch(
            batch_id=batch_id,
            project_id=project_id,
            entries=ready,
            delivery_method=delivery_method,
        )
        batch.submitted_at = datetime.now().isoformat()

        # Обновляем статусы
        for entry in ready:
            entry.status = DeloDocStatus.SUBMITTED
            entry.submitted_date = batch.submitted_at
            entry.deadline = batch.response_deadline

        logger.info(
            "Batch %s: %d docs, %d pages, method=%s",
            batch_id, len(ready), batch.total_pages, delivery_method.value,
        )
        return batch

    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------

    def generate_registry_report(self, project_id: int) -> str:
        """Сформировать отчёт по реестру ИД."""
        registry = self._registries.get(project_id)
        if not registry:
            return "Реестр не найден."

        lines = [
            f"═══════════════════════════════════════════",
            f"  РЕЕСТР ИД — {registry.project_name}",
            f"  Проект #{project_id}",
            f"═══════════════════════════════════════════",
            f"  Всего документов: {registry.total_docs}",
            f"  Принято: {registry.accepted_count}",
            f"  Отклонено: {registry.rejected_count}",
            f"  Просрочено ответов: {registry.overdue_count}",
            f"  Готовность: {registry.completion_pct}%",
            f"═══════════════════════════════════════════",
        ]

        # По статусам
        for status in DeloDocStatus:
            docs = registry.by_status(status)
            if docs:
                lines.append(f"\n  [{status.value}] — {len(docs)} док.:")
                for d in docs[:5]:
                    overdue = " ⚠ ПРОСРОЧЕН" if d.is_overdue else ""
                    lines.append(f"    {d.reg_id}: {d.doc_name[:60]}{overdue}")

        # Просроченные
        overdue_docs = [e for e in registry.entries if e.is_overdue]
        if overdue_docs:
            lines.append(f"\n  ⚠ ПРОСРОЧЕННЫЕ ДОКУМЕНТЫ ({len(overdue_docs)}):")
            for d in overdue_docs:
                days = d.days_since_submission or 0
                lines.append(f"    {d.reg_id}: {d.doc_name[:50]} — {days} дн.")

        return "\n".join(lines)

    def get_completion_stats(self, project_id: int) -> Dict[str, Any]:
        """Статистика комплектности."""
        registry = self._registries.get(project_id)
        if not registry:
            return {}

        by_cat = {}
        for entry in registry.entries:
            cat = entry.category_344
            if cat not in by_cat:
                by_cat[cat] = {"total": 0, "accepted": 0}
            by_cat[cat]["total"] += 1
            if entry.status == DeloDocStatus.ACCEPTED:
                by_cat[cat]["accepted"] += 1

        return {
            "total": registry.total_docs,
            "accepted": registry.accepted_count,
            "rejected": registry.rejected_count,
            "overdue": registry.overdue_count,
            "completion_pct": registry.completion_pct,
            "by_category": {
                cat: {
                    "total": s["total"],
                    "accepted": s["accepted"],
                    "pct": round(s["accepted"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
                }
                for cat, s in by_cat.items()
            },
        }

    # -------------------------------------------------------------------------
    # Export to OutputPipeline
    # -------------------------------------------------------------------------

    def export_registry_for_output(self, project_id: int) -> Dict[str, Any]:
        """
        Экспортирует реестр в формат, готовый для IDRegisterGenerator.

        Устраняет разрыв между DeloAgent (трекинг) и OutputPipeline (генерация DOCX).
        """
        registry = self._registries.get(project_id)
        if not registry:
            return {}

        return {
            "project_name": registry.project_name,
            "project_code": f"PRJ-{project_id}",
            "customer": getattr(registry, 'customer', 'Заказчик'),
            "contractor": getattr(registry, 'contractor', 'ООО «КСК №1»'),
            "date": datetime.now().strftime("%d.%m.%Y"),
            "documents": [
                {
                    "number": e.reg_id,
                    "name": e.doc_name,
                    "pages": e.pages,
                    "date": e.prepared_date or e.submitted_date or "",
                    "status": e.status.value,
                    "note": e.notes,
                }
                for e in registry.entries
            ],
            "stats": self.get_completion_stats(project_id),
        }

    def export_aosr_batch_for_output(
        self, project_id: int, category_filter: str = "act_aosr"
    ) -> List[Dict[str, Any]]:
        """
        Экспортирует данные АОСР из реестра для пакетной генерации DOCX.

        Returns:
            Список dict, готовых для AOSRGenerator.generate().
        """
        registry = self._registries.get(project_id)
        if not registry:
            return []

        entries = registry.by_category(category_filter)
        return [
            {
                "aosr_number": e.reg_id,
                "project_name": registry.project_name,
                "work_type": e.work_type,
                "object_address": getattr(registry, 'object_address', ''),
                "executor_company": getattr(registry, 'contractor', 'ООО «КСК №1»'),
                "customer_company": getattr(registry, 'customer', 'Заказчик'),
                "developer_company": getattr(registry, 'developer', ''),
                "decision": "разрешается",
                "date": e.prepared_date or datetime.now().strftime("%d.%m.%Y"),
                "materials": [],
                "certificates": [],
                "design_docs": [],
                "commission_members": [
                    {"name": "", "role": "Представитель заказчика", "company": getattr(registry, 'customer', '')},
                    {"name": "", "role": "Представитель подрядчика", "company": getattr(registry, 'contractor', '')},
                    {"name": "", "role": "Представитель стройконтроля", "company": ""},
                ],
            }
            for e in entries
        ]

    # -------------------------------------------------------------------------
    # Handover Act & Regulation Workflows (from Регламент взаимодействия ТЗ с П)
    # -------------------------------------------------------------------------

    def generate_handover_act(
        self,
        project_id: int,
        sender_org: str = "",
        sender_rep: str = "",
        receiver_org: str = "",
        receiver_rep: str = "",
    ) -> Dict[str, Any]:
        """
        Генерирует данные для Акта приёма-передачи ИД (Приложение 3 Регламента).

        Включает бумажный реестр и информацию об электронной версии.
        """
        registry = self._registries.get(project_id)
        if not registry:
            return {}

        documents = []
        for i, e in enumerate(registry.entries, 1):
            documents.append({
                "num": i,
                "rd_type": "ИД",
                "queue": "1",
                "contractor": getattr(registry, 'contractor', ''),
                "aosr_first": e.reg_id,
                "aosr_last": "",
                "month_object": "",
            })

        return {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "place": getattr(registry, 'object_address', 'г. Москва'),
            "object_name": registry.project_name,
            "object_address": getattr(registry, 'object_address', ''),
            "sender": {"org": sender_org or getattr(registry, 'contractor', 'ООО «КСК №1»'), "rep": sender_rep},
            "receiver": {"org": receiver_org or getattr(registry, 'customer', 'Заказчик'), "rep": receiver_rep},
            "documents": documents,
            "electronic": {
                "disks": [{"num": 1, "org": sender_org, "folder": f"{registry.project_name}", "count": 1}],
            },
            "appendix": "Реестр исполнительной документации",
            "stats": self.get_completion_stats(project_id),
        }

    def generate_storage_registry(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Генерирует реестр хранения ИД (Приложение 5 Регламента).

        Используется для учёта мест хранения документов в архиве.
        """
        registry = self._registries.get(project_id)
        if not registry:
            return []

        rows = []
        for i, e in enumerate(registry.entries, 1):
            rows.append({
                "num": i,
                "package_num": f"ПАК-{project_id}",
                "rd_num": e.reg_id,
                "doc_name": e.doc_name,
                "doc_number": e.reg_id,
                "date": e.prepared_date or e.submitted_date or "",
                "work_type": e.work_type,
                "received_date": e.accepted_date or "",
                "status": e.status.value,
                "contractor": getattr(registry, 'contractor', ''),
                "note": e.notes,
            })
        return rows

    def get_preparation_checklist(self) -> List[Dict[str, str]]:
        """Возвращает чек-лист этапов подготовки ИД (из Регламента)."""
        return [
            {"stage": "1", "action": "Уведомить заказчика о готовности скрытых работ к освидетельствованию", "deadline": "Не позднее чем за 3 рабочих дня", "ref": "ПП РФ №468 п. 11"},
            {"stage": "2", "action": "Проверить НТД: соответствие проекту, наличие сертификатов, паспортов на материалы", "deadline": "До начала освидетельствования", "ref": "СП 543.1325800.2024"},
            {"stage": "3", "action": "Провести освидетельствование комиссией (заказчик, подрядчик, стройконтроль)", "deadline": "В назначенную дату", "ref": "Приказ 344/пр"},
            {"stage": "4", "action": "Оформить АОСР с подписями всех членов комиссии", "deadline": "В день освидетельствования", "ref": "Приказ 344/пр, Приложение 3"},
            {"stage": "5", "action": "Приложить к АОСР: исполнительные схемы, протоколы испытаний, паспорта качества", "deadline": "Вместе с АОСР", "ref": "ГОСТ Р 51872-2024"},
            {"stage": "6", "action": "Зарегистрировать АОСР в реестре ИД (сквозная нумерация)", "deadline": "В день оформления", "ref": "Приказ 344/пр"},
            {"stage": "7", "action": "Передать комплект ИД заказчику по реестру приёма-передачи", "deadline": "По графику передачи", "ref": "Приложение 3 Регламента"},
        ]

    def get_gosstroynadzor_checklist(self) -> List[Dict[str, str]]:
        """Возвращает чек-лист взаимодействия с Госстройнадзором."""
        return [
            {"stage": "1", "action": "Извещение о начале строительства", "deadline": "Не позднее чем за 7 рабочих дней до начала", "ref": "Ст. 52 ГрК РФ ч. 5"},
            {"stage": "2", "action": "Извещение о сроках завершения работ, подлежащих проверке", "deadline": "После получения извещения ГСН", "ref": "РД-11-04-2006 п. 9"},
            {"stage": "3", "action": "Предоставление ИД для проверки по запросу ГСН", "deadline": "В течение 3 рабочих дней", "ref": "РД-11-04-2006 п. 12"},
            {"stage": "4", "action": "Акт проверки ГСН — оформление в 2 экземплярах", "deadline": "По результатам проверки", "ref": "РД-11-04-2006 п. 14"},
            {"stage": "5", "action": "Извещение об окончании строительства", "deadline": "После завершения всех работ", "ref": "Ст. 55 ГрК РФ ч. 1 п. 3"},
        ]

    def load_regulation_templates(self) -> Dict[str, Any]:
        """Загружает шаблоны из Регламента взаимодействия ТЗ с П."""
        import json as _json
        from pathlib import Path as _Path
        tmpl_path = _Path(__file__).parent.parent.parent.parent / "data" / "knowledge" / "templates" / "regulation_templates.json"
        try:
            with open(tmpl_path, "r", encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            return {}


delo_agent = DeloAgent()
