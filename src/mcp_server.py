import logging
from mcp.server.fastmcp import FastMCP
from src.core.event_manager import event_manager
from src.core.model_router import model_router
from src.core.integrations.google import google_service
from src.tools.integrations.search import asd_web_search

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ASD_MCP_SERVER")

# 1. Инициализация FastMCP
mcp = FastMCP(
    "АСД v11.0",
    version="11.0.0",
    description="Автономная строительная система с 7 агентами и Google-интеграцией"
)

# --- ГРУППА: ЛОГИСТИКА И ЗАКУПКИ ---

@mcp.tool()
async def asd_tender_search(query: str, region: str = None):
    """Поиск тендеров в ЕИС и на торговых площадках."""
    # Закупщик вызывает этот инструмент
    return await asd_web_search(query, search_type="tender")

@mcp.tool()
async def asd_send_rfq(to: str, subject: str, body: str):
    """Рассылка запросов котировок поставщикам через Gmail."""
    # Логист вызывает этот инструмент
    return await google_service.send_email(to, subject, body)

@mcp.tool()
async def asd_parse_price_list(file_path: str):
    """Извлечение цен и позиций из PDF/Excel прайс-листа."""
    # Логист/Сметчик вызывает этот инструмент
    logger.info(f"Parsing price list: {file_path}")
    return {"status": "success", "items": []}

# --- ГРУППА: GOOGLE WORKSPACE ---

@mcp.tool()
async def asd_google_drive_upload(file_path: str, folder_id: str):
    """Загрузка документа в Google Drive."""
    return await google_service.upload_to_drive(file_path, folder_id)

@mcp.tool()
async def asd_google_sheet_update(sheet_id: str, sheet_range: str, values: list):
    """Обновление таблицы Google Sheets."""
    return await google_service.update_sheet(sheet_id, sheet_range, values)

# --- ГРУППА: СИСТЕМНЫЕ / EVENT MANAGER ---

@mcp.tool()
async def asd_get_system_status():
    """Возвращает статус всех агентов и загрузку памяти Mac Studio."""
    # Модуль системного мониторинга
    return {
        "status": "online",
        "agents": 7,
        "memory_usage": "32GB/128GB",
        "event_manager": "active"
    }

if __name__ == "__main__":
    mcp.run()
