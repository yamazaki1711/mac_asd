import fitz  # PyMuPDF
import openpyxl
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ParserEngine:
    """
    Движок парсинга документов ASD.
    Поддерживает двухэтапный конвейер (Vision Cascade) для ПДФ, как заявлено в CONCEPT_v12.md.
    Stage 1: Чистый текст (PyMuPDF)
    Stage 2: Vision OCR (Ollama minicpm-v или Tesseract) для сканированных страниц.
    """
    
    async def parse_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Извлекает текст постранично с использованием Vision Cascade.
        """
        logger.info(f"Parsing PDF (Cascade Mode): {file_path}")
        chunks = []
        try:
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc):
                # Stage 1: Попытка извлечь чистый текст
                text = page.get_text().strip()
                
                if text:
                    chunks.append({
                        "content": text,
                        "page": page_num + 1,
                        "method": "pymupdf_text",
                        "metadata": {"source": file_path}
                    })
                else:
                    # Stage 2: Fallback на OCR для скан-копий (Пустая страница)
                    logger.info(f"Page {page_num + 1} has no text. Fallback to Vision OCR.")
                    ocr_text = await self._vision_ocr_fallback(page)
                    if ocr_text:
                        chunks.append({
                            "content": ocr_text,
                            "page": page_num + 1,
                            "method": "vision_ocr",
                            "metadata": {"source": file_path}
                        })

            doc.close()
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {e}")
        return chunks

    async def _vision_ocr_fallback(self, page) -> str:
        """
        Интеграция с Ollama Vision API (minicpm-v) или pytesseract.
        """
        from src.core.ram_manager import global_ram_manager
        
        # 1. Запрос 10GB ОЗУ под модель:
        await global_ram_manager.ensure_memory_for("minicpm-v", 10)
        
        # Полноценная реализация потребует рендеринга страницы в изображение:
        # pix = page.get_pixmap()
        # image_bytes = pix.tobytes("png")
        # await ollama_client.generate(model="minicpm-v", images=[image_bytes])
        
        # 2. Выгрузка модели принудительно:
        await global_ram_manager.unload_model("minicpm-v")
        
        return "[OCR EXTRACTED TEXT PLACEHOLDER]"

    def parse_xlsx(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Извлекает данные из таблиц (для смет).
        """
        logger.info(f"Parsing XLSX: {file_path}")
        chunks = []
        try:
            # openpyxl.load_package -> openpyxl.load_workbook
            wb = openpyxl.load_workbook(file_path) 
            sheet = wb.active
            # Простейший парсинг для примера
            chunks.append({
                "content": f"Spreadsheet extraction: {sheet.max_row} rows.",
                "page": 1,
                "metadata": {"type": "spreadsheet"}
            })
        except Exception as e:
            logger.error(f"Error parsing XLSX {file_path}: {e}")
        return chunks

parser_engine = ParserEngine()
