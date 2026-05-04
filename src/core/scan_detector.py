"""
ASD v12.0 — Scan Detector.

Определяет, является ли PDF сканированным документом без текстового слоя.
Критерий: pdftotext вернул < 100 символов И файл > 200 KB.

Сканы офисных сканеров (hp officejet и др.) — 0.5-7 MB для 1-12 страниц,
не содержат текстового слоя. Keyword-классификатор на них бесполезен.

Usage:
    from src.core.scan_detector import scan_detector, ScanInfo

    info = scan_detector.detect(filepath, extracted_text)
    if info.is_scanned:
        # Нужен VLM-анализ
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Пороги детекции
SCAN_TEXT_THRESHOLD = 100       # символов: меньше → вероятный скан
SCAN_SIZE_THRESHOLD = 200 * 1024  # байт: 200 KB


@dataclass
class ScanInfo:
    """Информация о сканированном документе."""
    is_scanned: bool
    file_path: Path
    file_size_bytes: int
    text_chars: int           # сколько символов извлёк pdftotext
    page_count: int           # из pdfinfo
    scanner_model: Optional[str] = None   # из pdfinfo (Creator/Producer)
    text_pages: int = 0       # страниц с текстом
    scan_pages: int = 0       # страниц без текста (скан)


class ScanDetector:
    """
    Детектор сканированных PDF.

    Использует pdfinfo для метаданных и анализ текстового слоя
    для определения, является ли PDF сканом.
    """

    def detect(self, file_path: Path, extracted_text: str = "") -> ScanInfo:
        """
        Определить, является ли файл сканом.

        Args:
            file_path: путь к PDF
            extracted_text: текст, извлечённый через pdftotext/PyMuPDF

        Returns:
            ScanInfo с результатом детекции
        """
        file_size = file_path.stat().st_size if file_path.exists() else 0
        text_chars = len(extracted_text.strip()) if extracted_text else 0
        page_count = 1
        scanner_model = None

        # Получаем метаданные через pdfinfo
        if file_path.suffix.lower() == '.pdf':
            try:
                result = subprocess.run(
                    ['pdfinfo', str(file_path)],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('Pages:'):
                        try:
                            page_count = int(line.split(':')[1].strip())
                        except ValueError:
                            logger.debug("Failed to parse page count from pdfinfo line: %s", line.strip())
                    elif line.startswith('Creator:'):
                        scanner_model = line.split(':', 1)[1].strip()
                        if not scanner_model or scanner_model == '—':
                            scanner_model = None
                    elif line.startswith('Producer:') and not scanner_model:
                        scanner_model = line.split(':', 1)[1].strip()
                        if not scanner_model or scanner_model == '—':
                            scanner_model = None
            except Exception as e:
                logger.debug("pdfinfo failed for %s: %s", file_path.name, e)

        # Эвристика скана
        is_scanned = (
            text_chars < SCAN_TEXT_THRESHOLD
            and file_size > SCAN_SIZE_THRESHOLD
        )

        # Если текста достаточно — файл не скан (даже если большой)
        if text_chars >= SCAN_TEXT_THRESHOLD:
            is_scanned = False

        return ScanInfo(
            is_scanned=is_scanned,
            file_path=file_path,
            file_size_bytes=file_size,
            text_chars=text_chars,
            page_count=page_count,
            scanner_model=scanner_model,
            text_pages=1 if not is_scanned else 0,
            scan_pages=page_count if is_scanned else 0,
        )

    def is_scanned(self, file_path: Path, extracted_text: str = "") -> bool:
        """Быстрая проверка: является ли файл сканом."""
        return self.detect(file_path, extracted_text).is_scanned


# Модульный синглтон
scan_detector = ScanDetector()
