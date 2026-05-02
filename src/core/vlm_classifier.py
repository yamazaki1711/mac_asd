"""
ASD v12.0 — VLM Classifier.

Классифицирует сканированные PDF через VLM (Gemma 4 31B Cloud).
pdftoppm → base64 → Ollama /api/chat → структурированный результат.

Промпт отработан на ЛОС: извлекает тип, номер, дату, работы,
приложения (включая упомянутые сертификаты), статус подписей.

Usage:
    from src.core.vlm_classifier import vlm_classifier, VlmPageResult

    result = await vlm_classifier.classify_document(pdf_path)
    print(result.doc_type)           # "АОСР"
    print(result.embedded_refs)      # [{"type": "certificate", "id": "№21514"}]
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class VlmPageResult:
    """Результат анализа одной страницы через VLM."""
    page_num: int
    doc_type: str = ""              # "АОСР", "Сертификат", "КС-2", ...
    doc_number: str = ""            # номер документа
    doc_date: str = ""              # дата
    work_description: str = ""      # описание работ
    attachments: List[str] = field(default_factory=list)   # перечисленные приложения
    signatures_filled: bool = False  # заполнены ли подписи
    raw_response: str = ""           # сырой ответ VLM


@dataclass
class VlmDocResult:
    """Агрегированный результат анализа всего документа."""
    file_path: Path
    doc_type: str = ""              # основной тип (по первой странице)
    doc_number: str = ""
    doc_date: str = ""
    confidence: float = 0.85        # VLM confidence выше keyword
    pages_analyzed: int = 0
    page_results: List[VlmPageResult] = field(default_factory=list)
    embedded_refs: List[Dict[str, str]] = field(default_factory=list)
    # embedded_refs: [{"type": "certificate", "identifier": "№21514",
    #                  "date": "21.11.2022", "found_on_page": 2}]
    all_signatures_filled: bool = False
    errors: List[str] = field(default_factory=list)


# =============================================================================
# VLM Classifier
# =============================================================================

VLM_CLASSIFY_PROMPT = """Ты — инженер ПТО строительной компании. Проанализируй страницу документа.
Ответь СТРОГО в JSON-формате (без markdown, без комментариев):

{
  "doc_type": "тип документа (АОСР/Сертификат/Паспорт/КС-2/КС-3/КС-6а/Договор/Счёт/УПД/Протокол/Журнал/Исполнительная схема/Чертёж/Письмо/Неизвестно)",
  "doc_number": "номер документа (если виден, иначе пустая строка)",
  "doc_date": "дата в формате ДД.ММ.ГГГГ (если видна, иначе пустая строка)",
  "work_description": "какие строительные работы описаны (кратко, 1 предложение)",
  "attachments": ["перечень приложений, особенно ищи сертификаты, паспорта качества, исполнительные схемы"],
  "signatures_filled": true/false (заполнены ли подписи и штампы)
}

ВАЖНО при определении типа:
- ЖУРНАЛ — это таблица с МНОЖЕСТВОМ строк-записей, датами по дням, столбцами «дата/смена/описание/подпись». 
  Обычно альбомная ориентация, много мелкого текста в ячейках.
- ИСПОЛНИТЕЛЬНАЯ СХЕМА — это план/чертёж с осями здания, проектными и фактическими отметками, 
  привязками, допусками. Содержит штамп по ГОСТ 21.101.
- Если видишь таблицу с колонками дат и подписей на каждой строке — это Журнал, НЕ схема.

ВАЖНО: в поле attachments обязательно перечисли ВСЕ упомянутые сертификаты, паспорта, 
исполнительные схемы, акты — даже если они просто упомянуты в тексте."""


class VLMClassifier:
    """
    Классификатор сканированных документов через VLM.

    Конвертирует PDF-страницы в JPEG, отправляет в Ollama VLM,
    агрегирует результаты по страницам.
    """

    def __init__(
        self,
        model: str = "gemma4:31b-cloud",
        base_url: str = "http://127.0.0.1:11434",
        dpi: int = 150,
    ):
        self.model = model
        self.base_url = base_url
        self.dpi = dpi
        self._chat_url = f"{base_url}/api/chat"
        self._checked_pdftoppm = False

    def _check_pdftoppm(self) -> bool:
        """Проверить наличие pdftoppm."""
        if self._checked_pdftoppm:
            return True
        try:
            subprocess.run(['pdftoppm', '-v'], capture_output=True, timeout=5)
            self._checked_pdftoppm = True
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.error("pdftoppm not found — VLM classification disabled")
            return False

    async def classify_document(self, pdf_path: Path) -> VlmDocResult:
        """
        Классифицировать весь PDF-документ через VLM.

        Args:
            pdf_path: путь к PDF

        Returns:
            VlmDocResult с типом и встроенными ссылками
        """
        result = VlmDocResult(file_path=pdf_path)

        if not self._check_pdftoppm():
            result.errors.append("pdftoppm not available")
            return result

        if not pdf_path.exists():
            result.errors.append(f"File not found: {pdf_path}")
            return result

        # Конвертируем все страницы в JPEG
        page_images = self._pdf_to_images(pdf_path)
        if not page_images:
            result.errors.append("No pages extracted")
            return result

        # Анализируем каждую страницу
        for page_num, img_path in enumerate(page_images, 1):
            try:
                page_result = await self._classify_page(img_path, page_num)
                result.page_results.append(page_result)

                # Первая страница задаёт основной тип
                if page_num == 1:
                    result.doc_type = page_result.doc_type
                    result.doc_number = page_result.doc_number
                    result.doc_date = page_result.doc_date

                # Собираем встроенные ссылки
                for att in page_result.attachments:
                    ref = self._parse_embedded_ref(att, page_num)
                    if ref:
                        result.embedded_refs.append(ref)

            except Exception as e:
                logger.warning("VLM failed for %s page %d: %s", pdf_path.name, page_num, e)
                result.errors.append(f"Page {page_num}: {e}")
            finally:
                # Чистим временный JPEG
                try:
                    os.unlink(img_path)
                except OSError:
                    pass

        result.pages_analyzed = len(result.page_results)
        result.all_signatures_filled = all(
            p.signatures_filled for p in result.page_results
        )
        return result

    def _pdf_to_images(self, pdf_path: Path) -> List[str]:
        """Конвертировать PDF в JPEG-изображения через pdftoppm."""
        tmpdir = tempfile.mkdtemp(prefix="asd_vlm_")
        prefix = os.path.join(tmpdir, "page")

        try:
            subprocess.run(
                ['pdftoppm', '-jpeg', '-r', str(self.dpi),
                 str(pdf_path), prefix],
                capture_output=True, timeout=60, check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error("pdftoppm failed: %s", e.stderr.decode()[:200])
            return []

        # Собираем пути (pdftoppm создаёт page-1.jpg, page-2.jpg, ...)
        images = []
        import glob as _glob
        for img in sorted(_glob.glob(os.path.join(tmpdir, "page-*.jpg"))):
            images.append(img)
        return images

    async def _classify_page(self, img_path: str, page_num: int) -> VlmPageResult:
        """Отправить страницу в VLM и распарсить ответ."""
        with open(img_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')

        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": VLM_CLASSIFY_PROMPT,
                "images": [img_b64],
            }],
            "format": "json",
            "stream": False,
        }

        # Используем синхронный requests (обёрнуто в async через to_thread в вызове)
        resp = requests.post(
            self._chat_url,
            json=payload,
            timeout=300,  # 5 минут на страницу
        )

        if resp.status_code != 200:
            raise RuntimeError(f"VLM API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        content = data.get("message", {}).get("content", "")

        # Парсим JSON из ответа
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Пробуем извлечь JSON из текста
            import re as _re
            match = _re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = {}

        return VlmPageResult(
            page_num=page_num,
            doc_type=parsed.get("doc_type", "Неизвестно"),
            doc_number=parsed.get("doc_number", ""),
            doc_date=parsed.get("doc_date", ""),
            work_description=parsed.get("work_description", ""),
            attachments=parsed.get("attachments", []),
            signatures_filled=parsed.get("signatures_filled", False),
            raw_response=content[:1000],
        )

    def _parse_embedded_ref(
        self, attachment_text: str, page_num: int
    ) -> Optional[Dict[str, str]]:
        """
        Распарсить строку приложения во встроенную ссылку.

        Примеры:
          "Сертификат качества №21514 от 21.11.2022"
          "Исполнительная схема №6 от 07.08.2025"
          "сертификат качества №21514 от 21.11.2022"
        """
        text = attachment_text.strip()
        if not text:
            return None

        # Определяем тип
        ref_type = "unknown"
        text_lower = text.lower()

        if any(kw in text_lower for kw in ['сертификат', 'паспорт качества', 'декларация']):
            ref_type = "certificate"
        elif any(kw in text_lower for kw in ['исполнительная схема', 'ис №', 'схема']):
            ref_type = "executive_scheme"
        elif any(kw in text_lower for kw in ['акт', 'аоср', 'аоок']):
            ref_type = "act"
        elif any(kw in text_lower for kw in ['протокол испытаний', 'лаборатор']):
            ref_type = "test_protocol"

        # Извлекаем дату
        import re as _re
        date_match = _re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
        date_str = date_match.group(1) if date_match else ""

        return {
            "type": ref_type,
            "identifier": text[:120],
            "date": date_str,
            "found_on_page": str(page_num),
        }


# Модульный синглтон
vlm_classifier = VLMClassifier(
    model=settings.MODEL_VISION or "gemma4:31b-cloud",
    base_url=settings.OLLAMA_BASE_URL,
)
