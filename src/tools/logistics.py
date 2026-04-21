import logging
from typing import Dict, Any, List
from src.core.integrations.google import google_service
from src.tools.integrations.search import asd_web_search

logger = logging.getLogger("TOOLS_LOGISTICS")

async def asd_tender_search_tool(query: str, region: str = None) -> List[Dict[str, Any]]:
    """Поиск тендеров в ЕИС."""
    logger.info(f"Tool asd_tender_search called: {query}")
    # Вызов основного поискового движка
    return await asd_web_search(query, search_type="tender")

async def asd_send_rfq_tool(to_batch: List[str], subject: str, message_template: str, material_list: List[str]) -> Dict[str, Any]:
    """Массовая рассылка запросов котировок."""
    logger.info(f"Tool asd_send_rfq called for {len(to_batch)} vendors.")
    
    results = []
    for email in to_batch:
        body = f"{message_template}\n\nСписок материалов:\n" + "\n".join(f"- {m}" for m in material_list)
        success = await google_service.send_email(email, subject, body)
        results.append({"email": email, "status": "sent" if success else "failed"})
    
    return {"summary": "Batch processing complete", "details": results}

async def asd_parse_price_list_tool(file_path: str) -> Dict[str, Any]:
    """Парсинг прайс-листа (КП)."""
    logger.info(f"Tool asd_parse_price_list called: {file_path}")
    # Здесь будет интеграция с ParserEngine в будущем
    return {
        "status": "extracted",
        "vendor_info": {"name": "Detected Vendor"},
        "items": [
            {"name": "Material X", "price": 100, "unit": "т"}
        ]
    }
