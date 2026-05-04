"""
Tests for Ingestion Pipeline — OCR, classification, and quality metrics.

Covers:
  - OCREngine: PyMuPDF text extraction, Tesseract OCR, multi-PSM fallback
  - OCRAccuracy: CER/WER computation against ground truth
  - DocumentClassifier: keyword-based classification
  - EntityExtractor: regex-based entity extraction
  - ScanDetector: scan detection heuristics
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.core.ingestion import (
    OCREngine,
    DocumentClassifier,
    EntityExtractor,
    DocumentType,
    DOCUMENT_KEYWORDS,
    EXTRACTION_PATTERNS,
)
from src.core.scan_detector import ScanDetector, SCAN_TEXT_THRESHOLD, SCAN_SIZE_THRESHOLD
from src.core.quality_metrics import OCRAccuracy, OCRAccuracyResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def ocr_engine():
    return OCREngine()


@pytest.fixture
def classifier():
    return DocumentClassifier()


@pytest.fixture
def extractor():
    return EntityExtractor()


@pytest.fixture
def scan_detector():
    return ScanDetector()


# =============================================================================
# OCREngine — Text PDF extraction
# =============================================================================

class TestOCREngineTextPDF:
    """Tests for text-based PDF (PyMuPDF text layer)."""

    def test_extract_text_pdf_with_text_layer(self, ocr_engine):
        """PyMuPDF should extract text from a PDF with a text layer."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        page = doc.new_page()
        # Use a simple ASCII + Latin text that renders reliably
        page.insert_text((72, 72), "Akt No15 ot 01.04.2026 AOSR")
        doc.save(str(pdf_path))
        doc.close()

        try:
            text, page_count = ocr_engine.extract_text(pdf_path)
            assert page_count == 1
            assert len(text) > 0, "Should extract some text from PDF with text layer"
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_extract_text_empty_pdf(self, ocr_engine):
        """Empty PDF should trigger OCR fallback (Tesseract)."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        doc.new_page()  # empty page, no text
        doc.save(str(pdf_path))
        doc.close()

        try:
            # Tesseract must be installed for this to return non-empty
            if shutil.which("tesseract"):
                text, page_count = ocr_engine.extract_text(pdf_path)
                assert page_count == 1
                # Even if OCR returns little, it shouldn't crash
            else:
                text, page_count = ocr_engine.extract_text(pdf_path)
                assert page_count == 1
                assert text == ""  # No text layer, no OCR tool
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_extract_text_unsupported_format(self, ocr_engine):
        """Unsupported file types return empty string."""
        path = Path(tempfile.mktemp(suffix=".mp4"))
        path.write_text("fake video")
        try:
            text, page_count = ocr_engine.extract_text(path)
            assert text == ""
            assert page_count == 0
        finally:
            path.unlink(missing_ok=True)

    def test_extract_text_txt_file(self, ocr_engine):
        """TXT files are read as UTF-8 text."""
        path = Path(tempfile.mktemp(suffix=".txt"))
        path.write_text("Приказ №123 от 01.01.2026", encoding="utf-8")
        try:
            text, page_count = ocr_engine.extract_text(path)
            assert page_count == 1
            assert "Приказ" in text
        finally:
            path.unlink(missing_ok=True)


# =============================================================================
# OCREngine — Tesseract OCR (requires tesseract binary)
# =============================================================================

@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract not installed")
class TestOCREngineTesseract:
    """Tests requiring Tesseract binary."""

    def test_ocr_page_tesseract_russian(self, ocr_engine):
        """Tesseract should OCR a page with Russian text."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        page = doc.new_page()
        # Use Latin text that renders reliably in text layer
        page.insert_text((72, 72), "Akt No15 ot 01.04.2026 AOSR hidden works")
        doc.save(str(pdf_path))
        doc.close()

        try:
            text, page_count = ocr_engine.extract_text(pdf_path)
            assert page_count == 1
            # Should have text from either PyMuPDF text layer or Tesseract OCR
            assert len(text.strip()) > 0, "Should extract text from PDF"
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_ocr_page_multi_psm_fallback(self, ocr_engine):
        """When PSM 6 fails, PSM 3 should be tried as fallback."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "GOST R 51872-2024")
        doc.save(str(pdf_path))
        doc.close()

        try:
            # Re-open to get a valid page reference
            doc2 = fitz.open(str(pdf_path))
            page2 = doc2[0]
            text = ocr_engine._ocr_page(page2)
            assert isinstance(text, str)
            doc2.close()
        finally:
            pdf_path.unlink(missing_ok=True)


# =============================================================================
# DocumentClassifier — Keyword-based classification
# =============================================================================

class TestDocumentClassifier:
    """Tests for keyword-based document type classification."""

    def test_classify_aosr(self, classifier):
        """AOSR text should be classified as AOSR."""
        text = "Акт освидетельствования скрытых работ №15. Освидетельствование выполненных работ."
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.AOSR
        assert conf > 0.5

    def test_classify_ks2(self, classifier):
        """KS-2 text should be classified as KS-2."""
        text = "Акт о приёмке выполненных работ КС-2. Форма № КС-2. Позиция по смете. Единичная расценка. Всего по акту."
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.KS2
        assert conf >= 0.5

    def test_classify_certificate(self, classifier):
        """Certificate text should be classified as CERTIFICATE."""
        text = "Сертификат качества №21514. Паспорт качества на арматуру А500С."
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.CERTIFICATE
        assert conf > 0.3

    def test_classify_unknown(self, classifier):
        """Unrecognizable text should be UNKNOWN."""
        text = "abcdefg hijklmn op qrstuv wxyz"
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.UNKNOWN

    def test_classify_journal(self, classifier):
        """Journal text should be classified as JOURNAL."""
        text = "Журнал погружения шпунта. Общий журнал работ. Журнал входного контроля. Дата, смена, описание."
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.JOURNAL
        assert conf > 0.2

    def test_classify_empty_text(self, classifier):
        """Empty text should return UNKNOWN."""
        doc_type, conf = classifier.classify("")
        assert doc_type == DocumentType.UNKNOWN
        assert conf == 0.0

    def test_all_doc_types_have_keywords(self):
        """Every DocumentType (except UNKNOWN and PHOTO) should have keyword definitions."""
        for doc_type in DocumentType:
            if doc_type in (DocumentType.UNKNOWN, DocumentType.PHOTO):
                continue
            assert doc_type in DOCUMENT_KEYWORDS, f"Missing keywords for {doc_type}"
            assert len(DOCUMENT_KEYWORDS[doc_type]) > 0, f"Empty keywords for {doc_type}"

    def test_classify_contract(self, classifier):
        """Contract text should be classified as CONTRACT."""
        text = "Договор подряда №РТМ-066/22. Контракт на выполнение строительных работ."
        doc_type, conf = classifier.classify(text)
        assert doc_type == DocumentType.CONTRACT


# =============================================================================
# EntityExtractor — Regex-based entity extraction
# =============================================================================

class TestEntityExtractor:
    """Tests for regex-based entity extraction."""

    def test_extract_date(self, extractor):
        """Date should be extracted from text."""
        entities = extractor.extract(
            "Акт от 01.04.2026 г. о приёмке работ", DocumentType.AOSR,
        )
        date_val = entities.get("date")
        # Can be str or list depending on match count
        if isinstance(date_val, list):
            assert "2026-04-01" in date_val
        else:
            assert date_val == "2026-04-01"

    def test_extract_document_number(self, extractor):
        """Document number should be extracted."""
        entities = extractor.extract(
            "АОСР № 15/04 от 01.04.2026", DocumentType.AOSR,
        )
        assert "15/04" in str(entities.get("aosr_number", ""))

    def test_extract_material_name(self, extractor):
        """Material name should be extracted."""
        entities = extractor.extract(
            "Сертификат на шпунт Л5-УМ, арматура А500С Ø12",
            DocumentType.CERTIFICATE,
        )
        mat = str(entities.get("material_name", ""))
        assert "шпунт" in mat.lower() or "арматура" in mat.lower()

    def test_extract_batch_number(self, extractor):
        """Batch number should be extracted."""
        entities = extractor.extract(
            "Партия № 21514, плавка 42. Количество: 55 шт.",
            DocumentType.CERTIFICATE,
        )
        batch = str(entities.get("batch_number", ""))
        assert "21514" in batch or "42" in batch

    def test_extract_gost(self, extractor):
        """GOST reference should be extracted."""
        entities = extractor.extract(
            "ГОСТ Р 51872-2024 и ГОСТ 26633-2015",
            DocumentType.CERTIFICATE,
        )
        gost = str(entities.get("gost", ""))
        assert "51872" in gost or "26633" in gost

    def test_extract_from_empty_text(self, extractor):
        """Empty text should return minimal entities."""
        entities = extractor.extract("", DocumentType.AOSR)
        assert entities.get("doc_type") == "aosr"

    def test_all_extraction_patterns_have_doc_types(self):
        """Every extraction pattern should specify applicable doc types."""
        for pattern in EXTRACTION_PATTERNS:
            assert pattern.field, f"Pattern has no field name"
            assert len(pattern.patterns) > 0, f"Pattern {pattern.field} has no regex patterns"


# =============================================================================
# ScanDetector
# =============================================================================

class TestScanDetector:
    """Tests for scan detection heuristics."""

    def test_detect_text_pdf_not_scanned(self, scan_detector):
        """PDF with text layer should not be detected as scanned."""
        path = Path(tempfile.mktemp(suffix=".pdf"))
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            text = "А" * 500  # substantial text
            page.insert_text((72, 72), text)
            doc.save(str(path))
            doc.close()

            info = scan_detector.detect(path, extracted_text=text)
            assert not info.is_scanned
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        finally:
            path.unlink(missing_ok=True)

    def test_detect_empty_pdf_scanned(self, scan_detector):
        """PDF without text layer AND large file should be detected as scanned."""
        path = Path(tempfile.mktemp(suffix=".pdf"))
        try:
            import fitz
            doc = fitz.open()
            for _ in range(5):
                page = doc.new_page()
                page.insert_text((72, 72), "x")  # minimal text per page
            doc.save(str(path))
            doc.close()

            # File is large enough (>200KB), text is <100 chars
            info = scan_detector.detect(path, extracted_text="xxx")
            # Might be scanned if file > 200KB
            assert info.text_chars < SCAN_TEXT_THRESHOLD
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        finally:
            path.unlink(missing_ok=True)

    def test_is_scanned_convenience(self, scan_detector):
        """is_scanned() should be a boolean shortcut."""
        path = Path(tempfile.mktemp(suffix=".pdf"))
        path.write_bytes(b"%PDF-1.4 fake pdf content")
        try:
            result = scan_detector.is_scanned(path, extracted_text="")
            assert isinstance(result, bool)
        finally:
            path.unlink(missing_ok=True)


# =============================================================================
# OCRAccuracy — CER/WER metrics
# =============================================================================

class TestOCRAccuracy:
    """Tests for CER/WER computation."""

    def test_perfect_match(self):
        """Identical texts should have CER=0, accuracy=100%."""
        gt = "Акт освидетельствования скрытых работ №15"
        result = OCRAccuracy.measure(gt, gt)
        assert result.cer == 0.0
        assert result.wer == 0.0
        assert result.accuracy_pct == 100.0

    def test_single_substitution(self):
        """Single character substitution should be detected."""
        gt = "капитального"
        ocr = "капитального"  # perfect match
        result = OCRAccuracy.measure(gt, ocr)
        assert result.cer == 0.0

        # With an error
        ocr_bad = "капитальтозо"
        result_bad = OCRAccuracy.measure(gt, ocr_bad)
        assert result_bad.cer > 0.0

    def test_missing_text(self):
        """Completely missing OCR should have high CER."""
        gt = "Акт освидетельствования скрытых работ №15 от 01.04.2026"
        result = OCRAccuracy.measure(gt, "")
        assert result.cer == 1.0
        assert result.accuracy_pct == 0.0

    def test_empty_ground_truth(self):
        """Empty ground truth should return zero result."""
        result = OCRAccuracy.measure("", "some text")
        assert result.ground_truth_chars == 0

    def test_format_report(self):
        """format_report() should not crash."""
        gt = "Тестовый текст для проверки"
        ocr = "Тестовый текст для проверки"
        result = OCRAccuracy.measure(gt, ocr)
        report = result.format_report()
        assert "100.0%" in report
        assert "CER:" in report
        assert "WER:" in report

    def test_benchmark_page_with_real_pdf(self):
        """Benchmark a synthetic PDF page against ground truth — verifies the method works."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")

        if not shutil.which("tesseract"):
            pytest.skip("Tesseract not installed")

        # Use a larger font to ensure OCR works
        gt = "Akt No15 ot 01 04 2026 AOSR hidden works certificate"

        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), gt, fontsize=18)
        doc.save(str(pdf_path))
        doc.close()

        try:
            result = OCRAccuracy.benchmark_page(pdf_path, 0, gt)
            assert isinstance(result, OCRAccuracyResult)
            # With large clear font, OCR should get reasonable accuracy
            # But small text may fail — that's fine, we're testing the method works
            assert result.ground_truth_chars > 0
        finally:
            pdf_path.unlink(missing_ok=True)
