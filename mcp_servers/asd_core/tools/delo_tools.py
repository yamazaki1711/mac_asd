"""
ASD v13.0 — Делопроизводитель MCP Tools.

Инструменты для работы с документами ИД, обёрнутые вокруг DeloAgent:
  - Регистрация документов в реестре
  - Генерация писем
  - Подготовка отправки (batching)
  - Контроль сроков
  - Шаблоны документов
  - Валидация
"""

from fastmcp import tool
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.agents.skills.delo.template_lib import DELO_TemplateLib
from src.core.services.delo_agent import (
    delo_agent,
    DocRegistryEntry,
    DeliveryMethod,
)

_template_lib = DELO_TemplateLib()

# Project name → ID mapping for string-based MCP tool args
_project_name_to_id: Dict[str, int] = {}


def _ensure_project(project_id: str, project_name: str = "") -> int:
    """Ensure a project registry exists for the given project_id (string or int)."""
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        pid = _project_name_to_id.get(project_id, hash(project_id) % 100000)

    if pid not in delo_agent._registries:
        delo_agent.create_registry(
            project_id=pid,
            project_name=project_name or f"Проект {project_id}",
        )
    if project_id not in _project_name_to_id and not project_id.isdigit():
        _project_name_to_id[project_id] = pid

    return pid


@tool()
async def asd_register_document(
    project_id: str,
    doc_type: str,
    filename: str,
    file_path: str,
    source: str = "external",
    project_name: str = "",
) -> Dict[str, Any]:
    """Регистрация входящего документа в реестре проекта. Присваивает регистрационный номер, фиксирует метаданные."""
    pid = _ensure_project(project_id, project_name)
    entry = delo_agent.register_document(
        project_id=pid,
        doc_type=doc_type,
        doc_name=filename,
        category_344=_map_doc_type_to_344(doc_type),
        file_path=file_path,
    )
    if entry is None:
        return {"status": "error", "message": f"Не удалось зарегистрировать документ в проекте {project_id}"}

    return {
        "status": "registered",
        "reg_id": entry.reg_id,
        "project_id": str(pid),
        "doc_type": doc_type,
        "filename": filename,
        "file_path": file_path,
        "source": source,
        "registered_at": datetime.now().isoformat(),
        "version": 1,
    }


@tool()
async def asd_generate_letter(
    letter_type: str,
    recipient: str,
    subject: str,
    body: str,
    project_id: str = "",
) -> Dict[str, Any]:
    """Генерация письма/уведомления/запроса на основе контекста проекта."""
    result = {
        "letter_type": letter_type,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "project_id": project_id,
        "generated_at": datetime.now().isoformat(),
        "status": "draft",
    }

    # Если указан project_id, добавляем реквизиты из реестра проекта
    if project_id:
        pid = _ensure_project(project_id)
        registry = delo_agent.get_registry(pid)
        if registry:
            result["customer"] = registry.customer
            result["contractor"] = registry.contractor
            result["contract_number"] = registry.contract_number
            result["object_address"] = registry.object_address

    return result


@tool()
async def asd_prepare_shipment(
    project_id: str,
    document_ids: List[str],
    recipient: str,
    cover_letter_type: str = "сопроводительное",
    project_name: str = "",
) -> Dict[str, Any]:
    """Подготовка комплекта документов для отправки заказчику: сопроводительное письмо + реестр."""
    pid = _ensure_project(project_id, project_name)

    # Создать submission batch через DeloAgent
    batch = delo_agent.create_submission_batch(pid)
    if not batch.batch_id:
        # Нет готовых документов — создаём batch вручную из переданных document_ids
        registry = delo_agent.get_registry(pid)
        ready = [e for e in (registry.entries if registry else []) if e.reg_id in document_ids] if registry else []
        batch_id = f"BATCH-{pid}-{len(registry.entries) if registry else 0:04d}"

        return {
            "project_id": project_id,
            "batch_id": batch_id,
            "document_ids": document_ids,
            "recipient": recipient,
            "cover_letter_type": cover_letter_type,
            "total_documents": len(ready) or len(document_ids),
            "prepared_at": datetime.now().isoformat(),
            "status": "ready_for_review",
            "note": "Документы ещё не зарегистрированы в реестре — зарегистрируйте их через asd_register_document",
        }

    return {
        "project_id": project_id,
        "batch_id": batch.batch_id,
        "document_ids": [e.reg_id for e in batch.entries],
        "recipient": recipient,
        "cover_letter_type": cover_letter_type,
        "total_documents": len(batch.entries),
        "total_pages": batch.total_pages,
        "delivery_method": batch.delivery_method.value,
        "response_deadline": batch.response_deadline,
        "prepared_at": batch.submitted_at or datetime.now().isoformat(),
        "status": "ready_for_review",
    }


@tool()
async def asd_track_deadlines(
    project_id: str = "",
    document_type: str = "",
    days_ahead: int = 14,
) -> Dict[str, Any]:
    """Контроль сроков ответов и исполнения документов. Возвращает документы с истекающими сроками."""
    upcoming = []
    overdue = []

    if project_id:
        pid = _ensure_project(project_id)
        registry = delo_agent.get_registry(pid)
        if registry:
            now = datetime.now()
            for e in registry.entries:
                if e.is_overdue:
                    overdue.append({
                        "reg_id": e.reg_id,
                        "doc_type": e.doc_type,
                        "doc_name": e.doc_name,
                        "status": e.status.value,
                        "deadline": e.deadline,
                        "days_overdue": e.days_since_submission,
                    })
                elif e.deadline:
                    dt = datetime.fromisoformat(e.deadline)
                    days_left = (dt - now).days
                    if 0 <= days_left <= days_ahead:
                        upcoming.append({
                            "reg_id": e.reg_id,
                            "doc_type": e.doc_type,
                            "doc_name": e.doc_name,
                            "status": e.status.value,
                            "deadline": e.deadline,
                            "days_left": days_left,
                        })

            if document_type:
                upcoming = [d for d in upcoming if d["doc_type"] == document_type]
                overdue = [d for d in overdue if d["doc_type"] == document_type]
    else:
        # Все проекты
        for pid, registry in delo_agent._registries.items():
            now = datetime.now()
            for e in registry.entries:
                if e.is_overdue:
                    overdue.append({
                        "project_id": str(pid),
                        "reg_id": e.reg_id,
                        "doc_type": e.doc_type,
                        "doc_name": e.doc_name,
                        "status": e.status.value,
                        "deadline": e.deadline,
                        "days_overdue": e.days_since_submission,
                    })
                elif e.deadline:
                    dt = datetime.fromisoformat(e.deadline)
                    days_left = (dt - now).days
                    if 0 <= days_left <= days_ahead:
                        upcoming.append({
                            "project_id": str(pid),
                            "reg_id": e.reg_id,
                            "doc_type": e.doc_type,
                            "doc_name": e.doc_name,
                            "status": e.status.value,
                            "deadline": e.deadline,
                            "days_left": days_left,
                        })

    return {
        "project_id": project_id or "all",
        "document_type": document_type or "all",
        "days_ahead": days_ahead,
        "upcoming_deadlines": upcoming,
        "overdue": overdue,
        "total_upcoming": len(upcoming),
        "total_overdue": len(overdue),
        "checked_at": datetime.now().isoformat(),
    }


@tool()
async def asd_get_template(template_type: str) -> Dict[str, Any]:
    """Получить шаблон документа ИД (АОСР, АООК, журналы и т.д.)."""
    result = await _template_lib.execute({
        "action": "get_template",
        "template_type": template_type,
    })
    return result.to_dict()


@tool()
async def asd_validate_template(
    template_type: str,
    filled_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Валидация заполненных данных шаблона документа ИД. Проверяет обязательные поля."""
    result = await _template_lib.execute({
        "action": "validate",
        "template_type": template_type,
        "filled_data": filled_data,
    })
    return result.to_dict()


@tool()
async def asd_list_templates(category: str = "all") -> Dict[str, Any]:
    """Перечислить все доступные шаблоны документов ИД (акты, журналы, отменённые формы)."""
    result = await _template_lib.execute({
        "action": "list",
        "category": category,
    })
    return result.to_dict()


# =============================================================================
# Helpers
# =============================================================================

def _map_doc_type_to_344(doc_type: str) -> str:
    """Map general doc_type to 344/пр category."""
    mapping = {
        "aosr": "act_aosr",
        "aook": "act_aook",
        "igs": "igs",
        "executive_scheme": "igs",
        "certificate": "certificate",
        "passport": "certificate",
        "ttn": "ttn",
        "ks2": "act_ks2",
        "ks3": "spravka_ks3",
        "journal": "journal",
        "contract": "contract",
        "letter": "letter",
        "claim": "claim",
        "protocol": "protocol",
    }
    return mapping.get(doc_type.lower(), "act_aosr")
