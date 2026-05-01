"""
ASD v12.0 — Unit tests for OutputPipeline (Document Generation System).

Covers:
  - DocumentNumber: formatting, suffix handling
  - NumberingService: sequential numbering, state management
  - A4Template: font/margin constants (smoke)
  - OutputPipeline: package bundling structure
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.core.output_pipeline import (
    DocumentNumber,
    NumberingService,
    A4Template,
    OutputPipeline,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DocumentNumber
# ═══════════════════════════════════════════════════════════════════════════════

class TestDocumentNumber:

    def test_basic_format_no_suffix(self):
        dn = DocumentNumber(prefix="AOSR", project_code="CK-2025", sequence=5)
        assert str(dn) == "AOSR-CK-2025-0005"

    def test_format_with_single_digit(self):
        dn = DocumentNumber(prefix="KC2", project_code="PRJ", sequence=1)
        assert str(dn) == "KC2-PRJ-0001"

    def test_format_with_large_sequence(self):
        dn = DocumentNumber(prefix="KC3", project_code="BUILD", sequence=9999)
        assert str(dn) == "KC3-BUILD-9999"

    def test_format_zero_pads_four_digits(self):
        dn = DocumentNumber(prefix="AOSR", project_code="X", sequence=42)
        result = str(dn)
        assert "0042" in result
        assert result.endswith("0042")

    def test_suffix_appended(self):
        dn = DocumentNumber(
            prefix="AOSR", project_code="SK-2025", sequence=3, suffix="/1"
        )
        assert str(dn) == "AOSR-SK-2025-0003/1"

    def test_sequence_does_not_truncate_above_9999(self):
        dn = DocumentNumber(prefix="T", project_code="P", sequence=12345)
        assert "12345" in str(dn)
        assert str(dn) == "T-P-12345"


# ═══════════════════════════════════════════════════════════════════════════════
# NumberingService
# ═══════════════════════════════════════════════════════════════════════════════

class TestNumberingService:

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp.close()
        self.svc = NumberingService(state_file=self.tmp.name)

    def teardown_method(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_first_number_starts_at_one(self):
        dn = self.svc.next_number("PRJ-001", "AOSR")
        assert dn.sequence == 1
        assert dn.prefix == "AOSR"
        assert str(dn) == "AOSR-PRJ-001-0001"

    def test_sequential_numbers_increment(self):
        for i in range(1, 6):
            dn = self.svc.next_number("PRJ-001", "AOSR")
            assert dn.sequence == i

    def test_different_prefixes_have_separate_counters(self):
        dn1 = self.svc.next_number("PRJ-001", "AOSR")
        dn2 = self.svc.next_number("PRJ-001", "KC2")
        assert dn1.sequence == 1
        assert dn2.sequence == 1  # separate counter

    def test_different_projects_have_separate_counters(self):
        dn1 = self.svc.next_number("PRJ-A", "AOSR")
        dn2 = self.svc.next_number("PRJ-B", "AOSR")
        assert dn1.sequence == 1
        assert dn2.sequence == 1

    def test_state_persisted_to_file(self):
        self.svc.next_number("PRJ-001", "AOSR")
        self.svc.next_number("PRJ-001", "AOSR")
        # Create new service from same file
        svc2 = NumberingService(state_file=self.tmp.name)
        dn = svc2.next_number("PRJ-001", "AOSR")
        assert dn.sequence == 3  # continues from persisted state

    def test_empty_state_file_does_not_crash(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.write(b"")  # empty file
        tmp.close()
        try:
            svc = NumberingService(state_file=tmp.name)
            dn = svc.next_number("P", "A")
            assert dn.sequence == 1
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def test_corrupted_state_file_defaults_to_empty(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w")
        tmp.write("this is not json {{{")
        tmp.close()
        try:
            svc = NumberingService(state_file=tmp.name)
            dn = svc.next_number("P", "A")
            assert dn.sequence == 1
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# A4Template (smoke)
# ═══════════════════════════════════════════════════════════════════════════════

class TestA4Template:
    """Verify A4Template constants and structure for DOCX generation."""

    def test_font_constants_are_set(self):
        tpl = A4Template()
        assert tpl.FONT_MAIN == "Times New Roman"
        assert tpl.FONT_SIZE_BODY is not None
        assert tpl.FONT_SIZE_TITLE is not None
        assert tpl.FONT_SIZE_SMALL is not None

    def test_margins_are_set(self):
        tpl = A4Template()
        assert tpl.MARGIN_TOP is not None
        assert tpl.MARGIN_BOTTOM is not None

    def test_save_requires_path(self):
        tpl = A4Template()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.docx"
            result = tpl.save(p)
            assert result == p
            assert p.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# OutputPipeline (smoke)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputPipelineSmoke:

    def test_pipeline_initializes(self):
        pipeline = OutputPipeline()
        assert pipeline is not None

    def test_generate_aosr_package_returns_path(self):
        pipeline = OutputPipeline()
        with tempfile.TemporaryDirectory() as tmp:
            data = {
                "aosr_number": "1-P",
                "work_type": "Земляные работы",
                "work_start": "01.06.2025",
                "work_end": "15.06.2025",
                "output_dir": tmp,
            }
            path = pipeline.generate_aosr_package("PRJ-001", data)
            assert path is not None
            assert path.exists()
            assert path.suffix == ".docx"

    def test_generate_ks_package_returns_tuple(self):
        pipeline = OutputPipeline()
        with tempfile.TemporaryDirectory() as tmp:
            data = {
                "contract_number": "СП-2025/01",
                "ks2_lines": [{"name": "Work", "code": "FER01", "quantity": 10,
                               "unit": "m3", "total": 50000}],
                "ks3_total": 50000,
                "output_dir": tmp,
            }
            ks2_path, ks3_path = pipeline.generate_ks_package("PRJ-001", data)
            assert ks2_path.exists()
            assert ks3_path.exists()
            assert ks2_path.suffix == ".docx"

    def test_generate_id_register_returns_path(self):
        pipeline = OutputPipeline()
        with tempfile.TemporaryDirectory() as tmp:
            proj = {
                "project_name": "Test Object",
                "project_code": "SP-001",
                "customer": "Customer LLC",
                "contract_number": "SP-001",
                "date": "01.06.2025",
                "output_dir": tmp,
                "documents": [
                    {"number": "1-R", "name": "AOSR Foundation", "pages": 3,
                     "date": "01.06.2025", "status": "approved", "note": ""},
                ],
            }
            path = pipeline.generate_id_register(proj)
            assert path is not None
            assert path.suffix == ".docx"
            assert path.exists()

    def test_bundle_package_creates_zip(self):
        pipeline = OutputPipeline()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            # Create dummy DOCX files
            (out / "AOSR_test.docx").write_text("dummy")
            (out / "KC2_test.docx").write_text("dummy")
            doc_paths = [out / "AOSR_test.docx", out / "KC2_test.docx"]
            zip_path = pipeline.bundle_package("TEST-001", doc_paths, output_dir=str(out))
            assert zip_path is not None
            assert zip_path.suffix == ".zip"
            assert zip_path.exists()
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                assert len(names) == 2
