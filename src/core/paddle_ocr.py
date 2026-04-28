"""
ASD v12.0 — PaddleOCR Adapter.

Pluggable OCR engine that auto-detects PaddleOCR and uses it
when available, with graceful fallback to rapidocr + tesseract.

Upgrade path for Russian construction documents:
  rapidocr (current) → PaddleOCR PP-OCRv5 (when installed)
  PP-OCRv5: 109 languages, Cyrillic native, 13% accuracy boost over v4
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try PaddleOCR
PADDLEOCR_AVAILABLE = False
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR available ✓")
except ImportError:
    logger.info("PaddleOCR not installed — using rapidocr + tesseract fallback")

# Try rapidocr
RAPIDOCR_AVAILABLE = False
try:
    from rapidocr import RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    pass


class PaddleOCRAdapter:
    """
    Единый OCR-интерфейс с авто-выбором лучшего движка.

    Приоритет:
      1. PaddleOCR (PP-OCRv5) — 109 языков, SOTA для русского
      2. RapidOCR — быстрый, легковесный
      3. Tesseract — системный fallback
    """

    def __init__(self, lang: str = "rus"):
        self.lang = lang
        self._engine = None
        self._engine_name = "none"
        self._init_engine()

    def _init_engine(self):
        """Авто-выбор лучшего доступного OCR-движка."""
        if PADDLEOCR_AVAILABLE:
            try:
                self._engine = PaddleOCR(
                    lang=self.lang,
                    use_angle_cls=True,
                    use_gpu=False,
                    show_log=False,
                )
                self._engine_name = "paddleocr"
                logger.info("PaddleOCR engine initialized")
                return
            except Exception as e:
                logger.warning("PaddleOCR init failed: %s", e)

        if RAPIDOCR_AVAILABLE:
            try:
                self._engine = RapidOCR()
                self._engine_name = "rapidocr"
                logger.info("RapidOCR engine initialized")
                return
            except Exception as e:
                logger.warning("RapidOCR init failed: %s", e)

        self._engine_name = "tesseract"
        logger.info("Using tesseract CLI fallback")

    def ocr_image(self, image_path: str) -> str:
        """
        Распознать текст с изображения.

        Args:
            image_path: путь к PNG/JPG файлу

        Returns:
            Распознанный текст
        """
        if self._engine_name == "paddleocr":
            return self._ocr_paddle(image_path)
        elif self._engine_name == "rapidocr":
            return self._ocr_rapid(image_path)
        else:
            return self._ocr_tesseract(image_path)

    def ocr_bytes(self, image_bytes: bytes) -> str:
        """Распознать текст из байтов изображения."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(image_bytes)
            tmp_path = f.name
        try:
            return self.ocr_image(tmp_path)
        finally:
            os.unlink(tmp_path)

    def ocr_pdf_page(self, page_pixmap, dpi: int = 200) -> str:
        """
        Распознать страницу PDF (PyMuPDF page → pixmap).

        Args:
            page_pixmap: fitz.Pixmap
            dpi: разрешение

        Returns:
            Текст страницы
        """
        import tempfile
        pix = page_pixmap
        if dpi != 200:
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page_pixmap.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        return self.ocr_bytes(img_bytes)

    # ── Private OCR methods ──

    def _ocr_paddle(self, image_path: str) -> str:
        """OCR через PaddleOCR."""
        result = self._engine.ocr(image_path, cls=True)
        if not result or not result[0]:
            return ""
        return "\n".join(
            line[1][0] for line in result[0] if line and len(line) > 1
        )

    def _ocr_rapid(self, image_path: str) -> str:
        """OCR через RapidOCR."""
        result, _ = self._engine(image_path)
        if not result:
            return ""
        return "\n".join(item[1] for item in result if item[1])

    def _ocr_tesseract(self, image_path: str) -> str:
        """OCR через системный Tesseract CLI."""
        try:
            result = subprocess.run(
                ['tesseract', str(image_path), 'stdout',
                 '-l', f'{self.lang}+eng', '--psm', '6'],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error("Tesseract failed: %s", e)
            return ""

    @property
    def engine_info(self) -> dict:
        """Информация о текущем движке."""
        return {
            "engine": self._engine_name,
            "language": self.lang,
            "paddleocr_available": PADDLEOCR_AVAILABLE,
            "rapidocr_available": RAPIDOCR_AVAILABLE,
        }


# =============================================================================
# Integrate with existing OCREngine
# =============================================================================

def upgrade_ingestion_ocr():
    """
    Обновить OCREngine в ingestion.py для использования PaddleOCRAdapter.

    Патчит OCREngine._ocr_page для использования нового адаптера
    с авто-выбором лучшего OCR-движка.
    """
    try:
        from src.core.ingestion import OCREngine
        adapter = PaddleOCRAdapter(lang="rus")

        # Monkey-patch: заменить OCR страницы
        original_ocr_page = OCREngine._ocr_page

        def patched_ocr_page(self, page):
            """OCR страницы через PaddleOCRAdapter → tesseract fallback."""
            try:
                import fitz
                pix = page.get_pixmap(dpi=200)
                return adapter.ocr_bytes(pix.tobytes("png"))
            except Exception:
                # Fallback to original method
                return original_ocr_page(self, page)

        OCREngine._ocr_page = patched_ocr_page
        logger.info("OCREngine upgraded to use PaddleOCRAdapter (engine: %s)",
                     adapter.engine_info["engine"])
        return adapter
    except ImportError as e:
        logger.warning("Cannot upgrade OCREngine: %s", e)
        return None


# Singleton
paddle_adapter = PaddleOCRAdapter(lang="rus")
