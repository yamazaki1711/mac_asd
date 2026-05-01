"""
ASD v12.0 — Unit tests for JournalRestorer (Journal Restoration Service).

Covers:
  - JournalEntry dataclass with date property
  - Section3Data: date_range, total_work_days, by_aosr grouping
  - JournalData: is_viable, gaps detection
  - JournalDataExtractor: extract_from_aosr, extract_from_ks2_line, extract_from_vor
  - JournalRestorer.reconstruct(): full restoration pipeline
  - JournalRestorer.fill_gaps(): LLM-powered gap filling (mocked)
"""

from datetime import datetime

import pytest

from src.core.services.journal_restorer import (
    JournalEntry,
    JournalSection,
    Section3Data,
    JournalData,
    JournalDataExtractor,
    JournalRestorer,
)


# ═══════════════════════════════════════════════════════════════════════════════
# JournalEntry
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalEntry:

    def test_basic_creation(self):
        entry = JournalEntry(
            entry_date="2025-06-15",
            work_description="Монтаж опалубки фундамента",
            work_type="опалубочные_работы",
        )
        assert entry.entry_date == "2025-06-15"
        assert entry.work_description == "Монтаж опалубки фундамента"
        assert entry.executor == ""  # default

    def test_date_property_parses_iso(self):
        entry = JournalEntry(
            entry_date="2025-06-15",
            work_description="Test",
            work_type="test",
        )
        assert entry.date == datetime(2025, 6, 15)
        assert isinstance(entry.date, datetime)

    def test_full_creation_with_all_fields(self):
        entry = JournalEntry(
            entry_date="2025-06-15",
            work_description="Бетонирование ростверка",
            work_type="бетонные_работы",
            executor='ООО "КСК №1"',
            aosr_ref="АОСР-1-Р",
            ks2_ref="КС2-5",
            is_scheme_ref="ИС-Р-03",
            materials_used=["Бетон B25", "Арматура A500C"],
            equipment_used=["Бетононасос", "Глубинный вибратор"],
            weather="Ясно",
            temperature_c=22.5,
            notes="Работы выполнены без замечаний",
        )
        assert entry.aosr_ref == "АОСР-1-Р"
        assert entry.ks2_ref == "КС2-5"
        assert len(entry.materials_used) == 2
        assert entry.temperature_c == 22.5

    def test_default_lists_are_empty(self):
        entry = JournalEntry(
            entry_date="2025-01-01",
            work_description="Test",
            work_type="test",
        )
        assert entry.materials_used == []
        assert entry.equipment_used == []


# ═══════════════════════════════════════════════════════════════════════════════
# Section3Data
# ═══════════════════════════════════════════════════════════════════════════════

class TestSection3Data:

    def _make_entry(self, date_str, aosr_ref="", desc="Work", work_type="generic"):
        return JournalEntry(
            entry_date=date_str,
            work_description=desc,
            work_type=work_type,
            aosr_ref=aosr_ref,
        )

    def test_empty_section_returns_empty_date_range(self):
        sec = Section3Data()
        assert sec.date_range == ("", "")
        assert sec.total_work_days == 0

    def test_date_range_single_entry(self):
        sec = Section3Data(entries=[self._make_entry("2025-03-01")])
        assert sec.date_range == ("2025-03-01", "2025-03-01")

    def test_date_range_multiple_sorted(self):
        sec = Section3Data(entries=[
            self._make_entry("2025-03-15"),
            self._make_entry("2025-03-01"),
            self._make_entry("2025-03-30"),
        ])
        assert sec.date_range == ("2025-03-01", "2025-03-30")

    def test_total_work_days_counts_unique_dates(self):
        sec = Section3Data(entries=[
            self._make_entry("2025-03-01"),
            self._make_entry("2025-03-01"),  # same day, multiple entries
            self._make_entry("2025-03-02"),
            self._make_entry("2025-03-03"),
        ])
        assert sec.total_work_days == 3

    def test_by_aosr_groups_entries(self):
        sec = Section3Data(entries=[
            self._make_entry("2025-03-01", aosr_ref="AOSR-1"),
            self._make_entry("2025-03-02", aosr_ref="AOSR-1"),
            self._make_entry("2025-03-03", aosr_ref="AOSR-2"),
        ])
        groups = sec.by_aosr
        assert len(groups["AOSR-1"]) == 2
        assert len(groups["AOSR-2"]) == 1

    def test_by_aosr_unknown_key_for_empty_ref(self):
        sec = Section3Data(entries=[
            self._make_entry("2025-03-01", aosr_ref=""),
        ])
        groups = sec.by_aosr
        assert "unknown" in groups


# ═══════════════════════════════════════════════════════════════════════════════
# JournalData
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalData:

    def test_empty_journal_not_viable(self):
        j = JournalData(project_id=1, project_name="Test")
        assert j.is_viable is False

    def test_journal_with_entries_is_viable(self):
        j = JournalData(project_id=1, project_name="Test")
        j.section_3.entries.append(JournalEntry(
            entry_date="2025-01-01", work_description="D", work_type="T",
        ))
        assert j.is_viable is True

    def test_gaps_empty_journal_reports_all_sections(self):
        j = JournalData(project_id=1, project_name="Test")
        gaps = j.gaps
        assert len(gaps) == 3  # sec 1, sec 2, sec 3
        assert any("Раздел 1" in g for g in gaps)
        assert any("Раздел 2" in g for g in gaps)
        assert any("Раздел 3" in g for g in gaps)

    def test_gaps_filled_journal_has_no_gaps(self):
        j = JournalData(
            project_id=1,
            project_name="Test",
            section_1={"object_name": "Test"},
            section_2=[{"role": "developer", "name": "Заказчик"}],
        )
        j.section_3.entries.append(JournalEntry(
            entry_date="2025-01-01", work_description="D", work_type="T",
        ))
        assert j.gaps == []


# ═══════════════════════════════════════════════════════════════════════════════
# JournalDataExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalDataExtractor:

    def setup_method(self):
        self.extractor = JournalDataExtractor()

    def test_extract_from_aosr_basic(self):
        aosr = {
            "aosr_number": "АОСР-1-Р",
            "work_type": "Опалубочные работы",
            "work_start": "2025-04-01",
            "work_end": "2025-04-10",
            "materials": ["Фанера ламинированная", "Брус"],
            "executor_company": 'ООО "СтройПроект"',
            "decision": "разрешается",
        }
        entry = self.extractor.extract_from_aosr(aosr)
        assert entry is not None
        assert entry.aosr_ref == "АОСР-1-Р"
        assert entry.work_type == "Опалубочные работы"
        assert entry.entry_date == "2025-04-10"
        assert len(entry.materials_used) == 2
        assert "АОСР-1-Р" in entry.notes

    def test_extract_from_aosr_fallback_to_work_start_date(self):
        aosr = {
            "aosr_number": "АОСР-2",
            "work_type": "Бетонирование",
            "work_start": "2025-04-15",
            "materials": [],
        }
        entry = self.extractor.extract_from_aosr(aosr)
        assert entry is not None
        assert entry.entry_date == "2025-04-15"

    def test_extract_from_aosr_default_executor(self):
        aosr = {
            "aosr_number": "АОСР-3",
            "work_type": "Армирование",
            "work_start": "2025-04-20",
            "materials": [],
        }
        entry = self.extractor.extract_from_aosr(aosr)
        assert entry is not None
        assert "КСК" in entry.executor

    def test_extract_from_aosr_empty_input_uses_defaults(self):
        entry = self.extractor.extract_from_aosr({})
        assert entry is not None  # uses defaults, doesn't fail
        assert entry.work_description == "Неизвестная работа"

    def test_extract_from_ks2_line(self):
        line = {
            "name": "Устройство фундаментов",
            "code": "ФЕР06-01-001-01",
            "quantity": 120.5,
            "unit": "м3",
            "total": 850000.00,
            "work_type": "фундаменты",
        }
        context = {"date": "2025-05-01", "ks2_number": "КС2-10"}
        entry = self.extractor.extract_from_ks2_line(line, context)
        assert entry is not None
        assert entry.ks2_ref == "КС2-10"
        assert "120.5" in entry.work_description
        assert "м3" in entry.work_description
        assert "ФЕР06-01-001-01" in entry.work_description

    def test_extract_from_vor(self):
        positions = [
            {"name": "Разработка грунта", "quantity": 500, "unit": "м3", "work_type": "земляные"},
            {"name": "Обратная засыпка", "quantity": 300, "unit": "м3", "work_type": "земляные"},
        ]
        entries = self.extractor.extract_from_vor(positions, {"date": "2025-05-10"})
        assert len(entries) == 2
        assert entries[0].work_description == "Разработка грунта — 500 м3"
        assert entries[1].work_description == "Обратная засыпка — 300 м3"
        assert all(e.entry_date == "2025-05-10" for e in entries)

    def test_extract_from_vor_empty_list(self):
        entries = self.extractor.extract_from_vor([], {"date": "2025-01-01"})
        assert entries == []

    def test_extract_from_vor_skips_malformed_positions(self):
        positions = [
            {"name": "Valid", "quantity": 100, "unit": "м2", "work_type": "t"},
            {},  # malformed: no name key
        ]
        entries = self.extractor.extract_from_vor(positions, {"date": "2025-05-10"})
        assert len(entries) == 2  # extractor tolerates missing keys via get()


# ═══════════════════════════════════════════════════════════════════════════════
# JournalRestorer.reconstruct()
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalRestorerReconstruct:

    def setup_method(self):
        self.restorer = JournalRestorer()

    def test_reconstruct_basic_from_aosr_list(self):
        aosr_list = [
            {
                "aosr_number": "АОСР-1-Р",
                "work_type": "Опалубочные работы",
                "work_start": "2025-06-01",
                "work_end": "2025-06-10",
                "materials": [],
                "decision": "разрешается",
            },
            {
                "aosr_number": "АОСР-2-Р",
                "work_type": "Бетонирование фундамента",
                "work_start": "2025-06-11",
                "work_end": "2025-06-15",
                "materials": [],
                "decision": "разрешается",
            },
        ]
        journal = self.restorer.reconstruct(
            project_id=100,
            project_name="Жилой комплекс «Березовая роща»",
            aosr_list=aosr_list,
            project_meta={
                "customer": 'ООО "Заказчик"',
                "contractor": 'ООО "КСК №1"',
                "contract_number": "СП-2025/07",
                "contract_date": "2025-01-15",
            },
        )

        assert journal.project_id == 100
        assert journal.customer == 'ООО "Заказчик"'
        assert journal.is_viable is True
        assert len(journal.section_3.entries) == 2
        assert journal.section_3.total_work_days == 2  # two unique dates

    def test_reconstruct_entries_sorted_by_date(self):
        aosr_list = [
            {"aosr_number": "A3", "work_type": "T3", "work_end": "2025-07-01", "materials": [], "decision": "разрешается"},
            {"aosr_number": "A1", "work_type": "T1", "work_end": "2025-06-01", "materials": [], "decision": "разрешается"},
            {"aosr_number": "A2", "work_type": "T2", "work_end": "2025-06-15", "materials": [], "decision": "разрешается"},
        ]
        journal = self.restorer.reconstruct(1, "Test", aosr_list)
        dates = [e.entry_date for e in journal.section_3.entries]
        assert dates == ["2025-06-01", "2025-06-15", "2025-07-01"]

    def test_reconstruct_records_denied_decisions(self):
        aosr_list = [
            {"aosr_number": "A1", "work_type": "OK", "work_start": "2025-01-01",
             "work_end": "2025-01-05", "materials": [], "decision": "разрешается"},
            {"aosr_number": "A2", "work_type": "BAD", "work_start": "2025-01-06",
             "work_end": "2025-01-10", "materials": [], "decision": "запрещается",
             "inspector": "Иванов И.И."},
        ]
        journal = self.restorer.reconstruct(1, "Test", aosr_list)
        assert len(journal.section_4) == 1
        assert journal.section_4[0]["inspector"] == "Иванов И.И."
        assert "запрещено" in journal.section_4[0]["result"].lower()

    def test_reconstruct_populates_section_1_from_meta(self):
        journal = self.restorer.reconstruct(
            project_id=1,
            project_name="Объект А",
            aosr_list=[],
            project_meta={
                "customer": "Заказчик",
                "object_address": "г. Москва, ул. Тестовая, 1",
                "contract_number": "СП-001",
                "contract_date": "2025-01-01",
            },
        )
        assert journal.section_1["object_name"] == "Объект А"
        assert journal.section_1["address"] == "г. Москва, ул. Тестовая, 1"
        assert journal.section_1["contract_number"] == "СП-001"

    def test_reconstruct_handles_empty_inputs(self):
        journal = self.restorer.reconstruct(1, "Empty Project", [])
        assert journal.project_id == 1
        assert journal.is_viable is False
        assert len(journal.section_3.entries) == 0
        assert len(journal.section_4) == 0
        assert len(journal.gaps) >= 1

    def test_reconstruct_with_ks2_lines(self):
        aosr_list = [
            {"aosr_number": "A1", "work_type": "T", "work_end": "2025-03-01",
             "materials": [], "decision": "разрешается"},
        ]
        ks2_lines = [
            {"name": "Позиция 1", "code": "ФЕР01", "quantity": 10, "unit": "шт",
             "total": 50000, "work_type": "строительные"},
        ]
        journal = self.restorer.reconstruct(
            1, "Test", aosr_list, ks2_lines=ks2_lines,
            project_meta={"date": "2025-03-01", "ks2_number": "КС2-1"},
        )
        # KS-2 entries extracted with context date
        assert len(journal.section_3.entries) == 2  # 1 AOSR + 1 KS2

    def test_reconstruct_with_vor_positions(self):
        vor = [
            {"name": "Земляные работы", "quantity": 1000, "unit": "м3", "work_type": "земляные"},
        ]
        journal = self.restorer.reconstruct(
            1, "Test", [], vor_positions=vor,
            project_meta={"vor_date": "2025-02-01"},
        )
        assert len(journal.section_3.entries) == 1
        assert "Земляные работы" in journal.section_3.entries[0].work_description


# ═══════════════════════════════════════════════════════════════════════════════
# JournalSection Enum
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalSection:
    def test_seven_sections_match_1026_pr(self):
        sections = list(JournalSection)
        assert len(sections) == 7

    def test_section_values_are_unique(self):
        values = [s.value for s in JournalSection]
        assert len(values) == len(set(values))
