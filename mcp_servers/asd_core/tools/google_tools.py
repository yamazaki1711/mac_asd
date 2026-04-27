"""
ASD v12.0 — Google Workspace MCP Tools.

Инструменты для доступа агентов к Google Drive, Sheets, Docs, Gmail.
Каждый инструмент делегирует вызов GoogleWorkspaceService.

Используются агентами:
  - Hermes (PM):    drive_search, drive_list_folder, gmail_send
  - ПТО:            sheets_read, sheets_write, drive_search
  - Сметчик:        sheets_read, sheets_write, sheets_append
  - Юрист:          docs_from_template, drive_search, drive_export_pdf
  - Делопроизводитель: docs_from_template, sheets_append, drive_search, gmail_send
  - Закупщик:       sheets_read, drive_search
  - Логист:         sheets_read, sheets_append, drive_search
"""

import logging
from typing import Dict, Any, List, Optional

from src.core.integrations.google import google_service

logger = logging.getLogger(__name__)


# =============================================================================
# Google Drive Tools
# =============================================================================

async def asd_drive_search(
    query: str,
    file_types: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """
    Поиск файлов на Google Drive.

    Args:
        query: Поисковый запрос (имя файла)
        file_types: Фильтр по типам: "spreadsheet", "document", "pdf", "folder"
        folder_id: ID папки для ограничения поиска
        max_results: Максимум результатов (default 20)

    Returns:
        {"status": "success", "files": [...], "total": N}
    """
    try:
        files = await google_service.drive.search(
            query=query,
            file_types=file_types,
            folder_id=folder_id,
            max_results=max_results,
        )
        return {
            "status": "success",
            "files": files,
            "total": len(files),
        }
    except Exception as e:
        logger.error(f"asd_drive_search failed: {e}")
        return {"status": "error", "message": str(e), "files": []}


async def asd_drive_list_folder(
    folder_id: str,
    file_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Список файлов в папке Google Drive.

    Args:
        folder_id: ID папки Google Drive
        file_types: Фильтр по типам (optional)

    Returns:
        {"status": "success", "files": [...], "total": N}
    """
    try:
        files = await google_service.drive.list_folder(
            folder_id=folder_id,
            file_types=file_types,
        )
        return {
            "status": "success",
            "files": files,
            "total": len(files),
        }
    except Exception as e:
        logger.error(f"asd_drive_list_folder failed: {e}")
        return {"status": "error", "message": str(e), "files": []}


async def asd_drive_get_file(file_id: str) -> Dict[str, Any]:
    """
    Получить метаданные файла Google Drive.

    Args:
        file_id: ID файла

    Returns:
        Метаданные файла (name, mimeType, webViewLink, ...)
    """
    try:
        file_info = await google_service.drive.get_file(file_id)
        if file_info:
            return {"status": "success", "file": file_info}
        return {"status": "not_found", "file_id": file_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_drive_copy_file(
    source_id: str,
    new_name: str,
    parent_folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Копировать файл на Google Drive (для создания из шаблона).

    Args:
        source_id: ID исходного файла (шаблона)
        new_name: Имя копии
        parent_folder_id: ID папки назначения (optional)

    Returns:
        {"status": "success", "new_file_id": "..."}
    """
    try:
        new_id = await google_service.drive.copy_file(
            source_id=source_id,
            new_name=new_name,
            parent_folder_id=parent_folder_id,
        )
        if new_id:
            return {"status": "success", "new_file_id": new_id}
        return {"status": "error", "message": "Copy failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_drive_create_folder(
    name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создать папку на Google Drive.

    Args:
        name: Имя папки
        parent_id: ID родительской папки (optional)

    Returns:
        {"status": "success", "folder_id": "..."}
    """
    try:
        folder_id = await google_service.drive.create_folder(
            name=name, parent_id=parent_id,
        )
        if folder_id:
            return {"status": "success", "folder_id": folder_id}
        return {"status": "error", "message": "Folder creation failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_drive_export_pdf(
    file_id: str,
    output_path: str,
) -> Dict[str, Any]:
    """
    Экспорт Google Doc/Sheet как PDF.

    Args:
        file_id: ID файла
        output_path: Путь для сохранения PDF

    Returns:
        {"status": "success", "output_path": "..."}
    """
    try:
        success = await google_service.drive.export_pdf(file_id, output_path)
        if success:
            return {"status": "success", "output_path": output_path}
        return {"status": "error", "message": "Export failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Google Sheets Tools
# =============================================================================

async def asd_sheets_read(
    spreadsheet_id: str,
    range_name: str,
) -> Dict[str, Any]:
    """
    Чтение данных из Google Sheets.

    Args:
        spreadsheet_id: ID таблицы (из URL)
        range_name: Диапазон в формате A1 (например "Лист1!A1:Z100")

    Returns:
        {"status": "success", "values": [[...], [...]], "rows": N}
    """
    try:
        values = await google_service.sheets.read(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
        )
        return {
            "status": "success",
            "values": values,
            "rows": len(values),
        }
    except Exception as e:
        logger.error(f"asd_sheets_read failed: {e}")
        return {"status": "error", "message": str(e), "values": []}


async def asd_sheets_write(
    spreadsheet_id: str,
    range_name: str,
    values: List[List[Any]],
) -> Dict[str, Any]:
    """
    Запись данных в Google Sheets (перезапись диапазона).

    Args:
        spreadsheet_id: ID таблицы
        range_name: Целевой диапазон (например "Лист1!A1")
        values: Двумерный массив значений

    Returns:
        {"status": "success"}
    """
    try:
        success = await google_service.sheets.write(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            values=values,
        )
        return {"status": "success" if success else "error"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_sheets_append(
    spreadsheet_id: str,
    range_name: str,
    values: List[List[Any]],
) -> Dict[str, Any]:
    """
    Добавление строк в конец Google Sheets.

    Args:
        spreadsheet_id: ID таблицы
        range_name: Диапазон для определения таблицы (например "Лист1!A:Z")
        values: Массив строк для добавления

    Returns:
        {"status": "success"}
    """
    try:
        success = await google_service.sheets.append(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            values=values,
        )
        return {"status": "success" if success else "error"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_sheets_get_names(
    spreadsheet_id: str,
) -> Dict[str, Any]:
    """
    Получить список листов в Google Sheets.

    Args:
        spreadsheet_id: ID таблицы

    Returns:
        {"status": "success", "sheets": [{"title": "...", "sheet_id": N}]}
    """
    try:
        sheets = await google_service.sheets.get_sheet_names(spreadsheet_id)
        return {"status": "success", "sheets": sheets}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_sheets_create(
    title: str,
    sheet_names: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создать новую таблицу Google Sheets.

    Args:
        title: Название таблицы
        sheet_names: Имена листов (default: ["Лист1"])
        folder_id: ID папки на Drive

    Returns:
        {"status": "success", "spreadsheet_id": "...", "url": "..."}
    """
    try:
        result = await google_service.sheets.create_spreadsheet(
            title=title,
            sheet_names=sheet_names,
            folder_id=folder_id,
        )
        if result:
            return {"status": "success", **result}
        return {"status": "error", "message": "Spreadsheet creation failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Google Docs Tools
# =============================================================================

async def asd_docs_get_content(document_id: str) -> Dict[str, Any]:
    """
    Получить текстовое содержимое Google Doc.

    Args:
        document_id: ID документа

    Returns:
        {"status": "success", "title": "...", "text": "...", "tables": [...]}
    """
    try:
        content = await google_service.docs.get_content(document_id)
        return {"status": "success", **content}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_docs_replace_text(
    document_id: str,
    replacements: Dict[str, str],
) -> Dict[str, Any]:
    """
    Замена плейсхолдеров в Google Doc.

    Args:
        document_id: ID документа
        replacements: {"{{НАИМЕНОВАНИЕ}}": "ООО Стройка", ...}

    Returns:
        {"status": "success", "replacements_made": N}
    """
    try:
        count = await google_service.docs.replace_text(document_id, replacements)
        return {"status": "success", "replacements_made": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def asd_docs_from_template(
    template_id: str,
    new_name: str,
    replacements: Dict[str, str],
    folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создать документ из шаблона Google Doc с заменой плейсхолдеров.

    Пайплайн: copy template → replace placeholders → return new doc URL

    Args:
        template_id: ID шаблона
        new_name: Имя нового документа
        replacements: Словарь замен {"{{KEY}}": "value"}
        folder_id: ID папки для нового документа

    Returns:
        {"status": "success", "document_id": "...", "url": "...", "replacements_made": N}
    """
    try:
        result = await google_service.docs.create_from_template(
            template_id=template_id,
            new_name=new_name,
            replacements=replacements,
            folder_id=folder_id,
        )
        if result:
            return {"status": "success", **result}
        return {"status": "error", "message": "Template creation failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Gmail Tools
# =============================================================================

async def asd_gmail_send(
    to: str,
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Отправка письма через Gmail API.

    Args:
        to: Email получателя
        subject: Тема письма
        body: Текст письма
        cc: Копия (optional)
        attachments: Пути к вложениям (optional)

    Returns:
        {"status": "success"}
    """
    try:
        success = await google_service.gmail.send_email(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            attachments=attachments,
        )
        return {"status": "success" if success else "error"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Google Workspace Status
# =============================================================================

async def asd_google_status() -> Dict[str, Any]:
    """
    Проверить статус подключения Google Workspace API.

    Returns:
        {"configured": true/false, "services": {...}}
    """
    configured = google_service.is_configured()
    return {
        "status": "configured" if configured else "not_configured",
        "configured": configured,
        "services": {
            "drive": configured,
            "sheets": configured,
            "docs": configured,
            "gmail": configured,
        },
        "message": (
            "Google Workspace API ready"
            if configured
            else "Set GOOGLE_APPLICATION_CREDENTIALS env var or place service account key in credentials/"
        ),
    }
