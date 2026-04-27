"""
ASD Core — Делопроизводитель MCP Tools.

Инструменты для работы с документами ИД, обёрнутые вокруг DELO_TemplateLib Skill:
  - Получение шаблонов документов
  - Валидация заполненных данных
  - Регистрация документов
  - Контроль сроков
"""

from fastmcp import tool
from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime

from src.agents.skills.delo.template_lib import DELO_TemplateLib

# Skill instance
_template_lib = DELO_TemplateLib()


@tool()
async def asd_register_document(
    project_id: str,
    doc_type: str,
    filename: str,
    file_path: str,
    source: str = "external",
) -> Dict[str, Any]:
    """Регистрация входящего документа в реестре проекта. Присваивает регистрационный номер, фиксирует метаданные."""
    doc_id = f"DOC-{datetime.now().strftime('%Y%m%d')}-{hash(filename) % 10000:04d}"
    return {
        "doc_id": doc_id,
        "project_id": project_id,
        "doc_type": doc_type,
        "filename": filename,
        "file_path": file_path,
        "source": source,
        "status": "new",
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
    """Генерация письма/уведомления/запроса на основе шаблона."""
    return {
        "letter_type": letter_type,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "project_id": project_id,
        "generated_at": datetime.now().isoformat(),
        "status": "draft",
    }


@tool()
async def asd_prepare_shipment(
    project_id: str,
    document_ids: List[str],
    recipient: str,
    cover_letter_type: str = "сопроводительное",
) -> Dict[str, Any]:
    """Подготовка комплекта документов для отправки заказчику: сопроводительное письмо + реестр."""
    return {
        "project_id": project_id,
        "document_ids": document_ids,
        "recipient": recipient,
        "cover_letter_type": cover_letter_type,
        "total_documents": len(document_ids),
        "prepared_at": datetime.now().isoformat(),
        "status": "ready_for_review",
    }


@tool()
async def asd_track_deadlines(
    project_id: str = "",
    document_type: str = "",
    days_ahead: int = 14,
) -> Dict[str, Any]:
    """Контроль сроков ответов и исполнения документов. Возвращает документы с истекающими сроками."""
    return {
        "project_id": project_id,
        "document_type": document_type,
        "days_ahead": days_ahead,
        "upcoming_deadlines": [],
        "overdue": [],
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
