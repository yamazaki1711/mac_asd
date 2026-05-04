"""
ASD v13.0 — Tests for DeloAgent (Делопроизводитель).

Comprehensive coverage:
  - DocRegistryEntry lifecycle
  - DocRegistry batch operations
  - DeloAgent CRUD
  - Status transitions
  - Overdue tracking
  - Submission batching
  - Export pipelines
  - Persistence (save/load)
  - Regulation checklists
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, timedelta

from src.core.services.delo_agent import (
    DeloAgent,
    delo_agent,
    DocRegistryEntry,
    DocRegistry,
    DeloDocStatus,
    DocStatus,
    DeliveryMethod,
    SubmissionBatch,
)


# =============================================================================
# DocRegistryEntry Tests
# =============================================================================

class TestDocRegistryEntry:
    """DocRegistryEntry: lifecycle, overdue tracking, serialization."""

    def test_create_defaults(self):
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="АОСР №1 Бетонирование ростверка",
            category_344="act_aosr",
        )
        assert e.reg_id == "ASD-1-0001"
        assert e.status == DeloDocStatus.DRAFT
        assert e.pages == 0
        assert e.is_overdue is False
        assert e.days_since_submission is None

    def test_is_overdue(self):
        past_date = (datetime.now() - timedelta(days=5)).isoformat()
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test",
            category_344="act_aosr",
            deadline=past_date,
        )
        assert e.is_overdue is True

    def test_not_overdue_future(self):
        future_date = (datetime.now() + timedelta(days=10)).isoformat()
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test",
            category_344="act_aosr",
            deadline=future_date,
        )
        assert e.is_overdue is False

    def test_not_overdue_no_deadline(self):
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test",
            category_344="act_aosr",
        )
        assert e.is_overdue is False

    def test_days_since_submission(self):
        past_submission = (datetime.now() - timedelta(days=3)).isoformat()
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test",
            category_344="act_aosr",
            submitted_date=past_submission,
        )
        assert e.days_since_submission == 3

    def test_days_since_submission_none(self):
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test",
            category_344="act_aosr",
        )
        assert e.days_since_submission is None

    def test_to_dict(self):
        e = DocRegistryEntry(
            reg_id="ASD-1-0001",
            doc_type="АОСР",
            doc_name="Test doc",
            category_344="act_aosr",
            pages=3,
        )
        d = e.to_dict()
        assert d["reg_id"] == "ASD-1-0001"
        assert d["doc_type"] == "АОСР"
        assert d["status"] == "draft"
        assert d["pages"] == 3
        assert "is_overdue" in d
        assert "days_since_submission" in d


# =============================================================================
# DocRegistry Tests
# =============================================================================

class TestDocRegistry:
    """DocRegistry: aggregation, filtering, stats."""

    def _make_registry(self) -> DocRegistry:
        r = DocRegistry(
            project_id=1,
            project_name="Причалы №9-10",
            customer="ФКУ «Ространсмодернизация»",
            contractor="ООО «КСК №1»",
            object_address="г. Корсаков, ул. Портовая, 1",
        )
        return r

    def _add_entries(self, r: DocRegistry, count: int = 3):
        for i in range(count):
            e = DocRegistryEntry(
                reg_id=f"ASD-1-{i+1:04d}",
                doc_type="АОСР",
                doc_name=f"АОСР №{i+1}",
                category_344="act_aosr",
            )
            r.entries.append(e)
        return r.entries

    def test_create_defaults(self):
        r = self._make_registry()
        assert r.project_id == 1
        assert r.total_docs == 0
        assert r.accepted_count == 0
        assert r.rejected_count == 0
        assert r.overdue_count == 0
        assert r.completion_pct == 0.0

    def test_count_by_status(self):
        r = self._make_registry()
        entries = self._add_entries(r, 5)
        entries[0].status = DeloDocStatus.ACCEPTED
        entries[1].status = DeloDocStatus.ACCEPTED
        entries[2].status = DeloDocStatus.REJECTED
        entries[3].status = DeloDocStatus.SUBMITTED
        entries[4].status = DeloDocStatus.DRAFT

        assert r.accepted_count == 2
        assert r.rejected_count == 1
        assert r.total_docs == 5

    def test_completion_pct(self):
        r = self._make_registry()
        entries = self._add_entries(r, 4)
        entries[0].status = DeloDocStatus.ACCEPTED
        entries[1].status = DeloDocStatus.ACCEPTED
        assert r.completion_pct == 50.0

    def test_completion_pct_empty(self):
        r = self._make_registry()
        assert r.completion_pct == 0.0

    def test_overdue_count(self):
        r = self._make_registry()
        entries = self._add_entries(r, 3)
        past = (datetime.now() - timedelta(days=1)).isoformat()
        entries[0].deadline = past
        entries[1].deadline = (datetime.now() + timedelta(days=5)).isoformat()
        assert r.overdue_count == 1

    def test_by_status(self):
        r = self._make_registry()
        entries = self._add_entries(r, 3)
        entries[0].status = DeloDocStatus.ACCEPTED
        entries[1].status = DeloDocStatus.ACCEPTED
        entries[2].status = DeloDocStatus.REJECTED

        accepted = r.by_status(DeloDocStatus.ACCEPTED)
        assert len(accepted) == 2
        rejected = r.by_status(DeloDocStatus.REJECTED)
        assert len(rejected) == 1
        submitted = r.by_status(DeloDocStatus.SUBMITTED)
        assert len(submitted) == 0

    def test_by_category(self):
        r = self._make_registry()
        e1 = DocRegistryEntry("A1", "АОСР", "Doc 1", "act_aosr")
        e2 = DocRegistryEntry("A2", "ИГС", "Doc 2", "igs")
        e3 = DocRegistryEntry("A3", "Сертификат", "Doc 3", "certificate")
        r.entries.extend([e1, e2, e3])

        assert len(r.by_category("act_aosr")) == 1
        assert len(r.by_category("igs")) == 1
        assert len(r.by_category("nonexistent")) == 0

    def test_to_dict_includes_project_attrs(self):
        r = self._make_registry()
        d = r.to_dict()
        assert d["customer"] == "ФКУ «Ространсмодернизация»"
        assert d["contractor"] == "ООО «КСК №1»"
        assert d["object_address"] == "г. Корсаков, ул. Портовая, 1"
        assert d["total_docs"] == 0


# =============================================================================
# DeloAgent Tests
# =============================================================================

class TestDeloAgent:
    """DeloAgent: registry CRUD, status transitions, batching."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DeloAgent()
        self.agent._registries.clear()
        yield
        self.agent._registries.clear()

    def test_create_registry(self):
        r = self.agent.create_registry(1, "Тестовый проект")
        assert r.project_id == 1
        assert r.project_name == "Тестовый проект"
        assert r.contractor == "ООО «КСК №1»"

    def test_create_registry_with_full_attrs(self):
        r = self.agent.create_registry(
            2, "Объект А",
            customer="Заказчик ООО",
            contractor="Подрядчик ООО",
            developer="Девелопер ООО",
            object_address="г. Москва, ул. Тестовая, 1",
            contract_number="Д-001/26",
        )
        assert r.customer == "Заказчик ООО"
        assert r.contractor == "Подрядчик ООО"
        assert r.developer == "Девелопер ООО"
        assert r.object_address == "г. Москва, ул. Тестовая, 1"
        assert r.contract_number == "Д-001/26"

    def test_register_document(self):
        self.agent.create_registry(1, "Test")
        entry = self.agent.register_document(
            1, "АОСР", "АОСР №1 Бетонирование",
            category_344="act_aosr", pages=3, counterparty="Заказчик",
        )
        assert entry is not None
        assert entry.reg_id.startswith("ASD-1-")
        assert entry.doc_type == "АОСР"
        assert entry.pages == 3

    def test_register_document_no_registry(self):
        entry = self.agent.register_document(999, "АОСР", "Test")
        assert entry is None

    def test_register_document_sequential_ids(self):
        self.agent.create_registry(1, "Test")
        e1 = self.agent.register_document(1, "АОСР", "Doc1")
        e2 = self.agent.register_document(1, "АОСР", "Doc2")
        e3 = self.agent.register_document(1, "АОСР", "Doc3")
        assert e1.reg_id == "ASD-1-0001"
        assert e2.reg_id == "ASD-1-0002"
        assert e3.reg_id == "ASD-1-0003"

    def test_update_status(self):
        self.agent.create_registry(1, "Test")
        entry = self.agent.register_document(1, "АОСР", "Test doc")

        assert self.agent.update_status(1, entry.reg_id, DeloDocStatus.PREPARED)
        assert entry.status == DeloDocStatus.PREPARED

    def test_update_status_sets_submitted_date(self):
        self.agent.create_registry(1, "Test")
        entry = self.agent.register_document(1, "АОСР", "Test doc")

        self.agent.update_status(1, entry.reg_id, DeloDocStatus.SUBMITTED)
        assert entry.status == DeloDocStatus.SUBMITTED
        assert entry.submitted_date is not None
        assert entry.deadline is not None  # Deadline auto-set on submission

    def test_update_status_sets_accepted_date(self):
        self.agent.create_registry(1, "Test")
        entry = self.agent.register_document(1, "АОСР", "Test doc")

        self.agent.update_status(1, entry.reg_id, DeloDocStatus.ACCEPTED)
        assert entry.status == DeloDocStatus.ACCEPTED
        assert entry.accepted_date is not None

    def test_update_status_nonexistent_project(self):
        result = self.agent.update_status(999, "ASD-999-0001", DeloDocStatus.PREPARED)
        assert result is False

    def test_update_status_nonexistent_reg_id(self):
        self.agent.create_registry(1, "Test")
        result = self.agent.update_status(1, "NONEXISTENT", DeloDocStatus.PREPARED)
        assert result is False

    def test_full_lifecycle(self):
        """Полный жизненный цикл документа: регистрация → подготовка → отправка → приёмка."""
        self.agent.create_registry(1, "Project X")
        entry = self.agent.register_document(1, "АОСР", "АОСР №1")

        assert entry.status == DeloDocStatus.DRAFT
        self.agent.update_status(1, entry.reg_id, DeloDocStatus.PREPARED)
        assert entry.status == DeloDocStatus.PREPARED

        self.agent.update_status(1, entry.reg_id, DeloDocStatus.SIGNED_INTERNAL)
        assert entry.status == DeloDocStatus.SIGNED_INTERNAL

        self.agent.update_status(1, entry.reg_id, DeloDocStatus.SUBMITTED)
        assert entry.status == DeloDocStatus.SUBMITTED
        assert entry.deadline is not None

        self.agent.update_status(1, entry.reg_id, DeloDocStatus.ACCEPTED)
        assert entry.status == DeloDocStatus.ACCEPTED

    def test_get_registry(self):
        self.agent.create_registry(1, "Test")
        r = self.agent.get_registry(1)
        assert r is not None
        assert r.project_name == "Test"

    def test_get_registry_nonexistent(self):
        r = self.agent.get_registry(999)
        assert r is None

    def test_get_completion_stats(self):
        self.agent.create_registry(1, "Test")
        self.agent.register_document(1, "АОСР", "D1", category_344="act_aosr")
        self.agent.register_document(1, "ИГС", "D2", category_344="igs")

        stats = self.agent.get_completion_stats(1)
        assert stats["total"] == 2
        assert stats["accepted"] == 0
        assert stats["completion_pct"] == 0.0
        assert "act_aosr" in stats["by_category"]
        assert "igs" in stats["by_category"]

    def test_get_completion_stats_no_registry(self):
        stats = self.agent.get_completion_stats(999)
        assert stats == {}


# =============================================================================
# Submission Batching Tests
# =============================================================================

class TestSubmissionBatching:
    """DeloAgent: create_submission_batch."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DeloAgent()
        self.agent._registries.clear()
        yield
        self.agent._registries.clear()

    def test_batch_picks_prepared_docs(self):
        self.agent.create_registry(1, "Test")
        e1 = self.agent.register_document(1, "АОСР", "Doc 1")
        e2 = self.agent.register_document(1, "АОСР", "Doc 2")
        e3 = self.agent.register_document(1, "АОСР", "Doc 3")

        # Mark first two as prepared
        self.agent.update_status(1, e1.reg_id, DeloDocStatus.PREPARED)
        self.agent.update_status(1, e2.reg_id, DeloDocStatus.SIGNED_INTERNAL)
        # e3 stays DRAFT

        batch = self.agent.create_submission_batch(1)
        assert len(batch.entries) == 2
        assert batch.total_pages == 0  # No pages set
        assert batch.delivery_method == DeliveryMethod.ELECTRONIC
        assert batch.submitted_at is not None
        assert batch.response_deadline != ""

        # Statuses should be updated to SUBMITTED
        assert e1.status == DeloDocStatus.SUBMITTED
        assert e2.status == DeloDocStatus.SUBMITTED
        assert e3.status == DeloDocStatus.DRAFT

    def test_batch_no_registry(self):
        batch = self.agent.create_submission_batch(999)
        assert batch.batch_id == ""

    def test_batch_empty(self):
        self.agent.create_registry(1, "Test")
        self.agent.register_document(1, "АОСР", "Doc 1")  # DRAFT
        batch = self.agent.create_submission_batch(1)
        assert len(batch.entries) == 0

    def test_batch_with_category_filter(self):
        self.agent.create_registry(1, "Test")
        e1 = self.agent.register_document(1, "АОСР", "Doc 1", category_344="act_aosr")
        e2 = self.agent.register_document(1, "ИГС", "Doc 2", category_344="igs")

        self.agent.update_status(1, e1.reg_id, DeloDocStatus.PREPARED)
        self.agent.update_status(1, e2.reg_id, DeloDocStatus.PREPARED)

        batch = self.agent.create_submission_batch(1, category_filter="act_aosr")
        assert len(batch.entries) == 1
        assert batch.entries[0].category_344 == "act_aosr"

    def test_batch_pages_sum(self):
        self.agent.create_registry(1, "Test")
        e1 = self.agent.register_document(1, "АОСР", "Doc 1", pages=3)
        e2 = self.agent.register_document(1, "АОСР", "Doc 2", pages=5)

        self.agent.update_status(1, e1.reg_id, DeloDocStatus.PREPARED)
        self.agent.update_status(1, e2.reg_id, DeloDocStatus.PREPARED)

        batch = self.agent.create_submission_batch(1)
        assert batch.total_pages == 8


# =============================================================================
# Export Pipeline Tests
# =============================================================================

class TestExports:
    """DeloAgent: export pipelines."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DeloAgent()
        self.agent._registries.clear()
        self.agent.create_registry(
            1, "Причалы №9-10",
            customer="ФКУ Ространсмодернизация",
            contractor="ООО «КСК №1»",
            object_address="г. Корсаков",
        )
        self.agent.register_document(1, "АОСР", "АОСР №1", category_344="act_aosr", work_type="Бетонирование", pages=2)
        self.agent.register_document(1, "ИГС", "Исполнительная схема", category_344="igs", pages=1)
        yield
        self.agent._registries.clear()

    def test_export_registry_for_output(self):
        data = self.agent.export_registry_for_output(1)
        assert data["project_name"] == "Причалы №9-10"
        assert data["customer"] == "ФКУ Ространсмодернизация"
        assert data["contractor"] == "ООО «КСК №1»"
        assert len(data["documents"]) == 2
        assert "stats" in data

    def test_export_registry_for_output_empty(self):
        data = self.agent.export_registry_for_output(999)
        assert data == {}

    def test_export_aosr_batch_for_output(self):
        items = self.agent.export_aosr_batch_for_output(1, category_filter="act_aosr")
        assert len(items) == 1
        assert items[0]["work_type"] == "Бетонирование"
        assert items[0]["customer_company"] == "ФКУ Ространсмодернизация"
        assert items[0]["executor_company"] == "ООО «КСК №1»"

    def test_export_aosr_batch_no_registry(self):
        items = self.agent.export_aosr_batch_for_output(999)
        assert items == []

    def test_generate_handover_act(self):
        data = self.agent.generate_handover_act(
            1,
            sender_org="ООО «КСК №1»",
            sender_rep="Иванов И.И.",
            receiver_org="ФКУ РМ",
            receiver_rep="Петров П.П.",
        )
        assert data["object_name"] == "Причалы №9-10"
        assert data["sender"]["org"] == "ООО «КСК №1»"
        assert data["receiver"]["org"] == "ФКУ РМ"
        assert len(data["documents"]) == 2
        assert data["electronic"]["disks"][0]["org"] == "ООО «КСК №1»"

    def test_generate_handover_act_no_registry(self):
        data = self.agent.generate_handover_act(999)
        assert data == {}

    def test_generate_storage_registry(self):
        rows = self.agent.generate_storage_registry(1)
        assert len(rows) == 2
        assert rows[0]["package_num"] == "ПАК-1"
        assert rows[0]["contractor"] == "ООО «КСК №1»"

    def test_generate_storage_registry_empty(self):
        rows = self.agent.generate_storage_registry(999)
        assert rows == []

    def test_generate_registry_report(self):
        report = self.agent.generate_registry_report(1)
        assert "Причалы №9-10" in report
        assert "Всего документов: 2" in report

    def test_generate_registry_report_no_registry(self):
        report = self.agent.generate_registry_report(999)
        assert "не найден" in report.lower()


# =============================================================================
# Regulation Checklists
# =============================================================================

class TestRegulationChecklists:
    """DeloAgent: regulation and GSN checklists."""

    def test_preparation_checklist(self):
        agent = DeloAgent()
        checklist = agent.get_preparation_checklist()
        assert len(checklist) == 7
        assert checklist[0]["stage"] == "1"
        assert "Уведомить заказчика" in checklist[0]["action"]
        assert "ПП РФ №468" in checklist[0]["ref"]

    def test_gosstroynadzor_checklist(self):
        agent = DeloAgent()
        checklist = agent.get_gosstroynadzor_checklist()
        assert len(checklist) == 5
        assert checklist[0]["stage"] == "1"
        assert "Извещение о начале строительства" in checklist[0]["action"]
        assert "ГрК РФ" in checklist[0]["ref"]

    def test_load_regulation_templates(self):
        agent = DeloAgent()
        # Should not crash even if file doesn't exist
        templates = agent.load_regulation_templates()
        assert isinstance(templates, dict)


# =============================================================================
# DocStatus Backward Compatibility
# =============================================================================

class TestDocStatusCompatibility:
    """Verify DocStatus alias works."""

    def test_alias_is_same_enum(self):
        assert DocStatus is DeloDocStatus
        assert DocStatus.DRAFT == DeloDocStatus.DRAFT
        assert DocStatus.ACCEPTED == DeloDocStatus.ACCEPTED


# =============================================================================
# Persistence Tests
# =============================================================================

class TestPersistence:
    """DeloAgent: save/load registries."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DeloAgent()
        self.agent._registries.clear()
        self.tmpdir = tempfile.mkdtemp()
        self.agent.set_persistence_dir(self.tmpdir)
        yield
        self.agent._registries.clear()
        # Cleanup
        for f in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_save_and_load(self):
        self.agent.create_registry(
            1, "Проект А",
            customer="Заказчик А",
            contractor="Подрядчик А",
            object_address="Адрес А",
            contract_number="Д-001",
        )
        self.agent.register_document(1, "АОСР", "АОСР №1", pages=3)
        self.agent.register_document(1, "ИГС", "Исп. схема", pages=1)

        # Mark one as accepted
        registry = self.agent.get_registry(1)
        registry.entries[0].status = DeloDocStatus.ACCEPTED

        assert self.agent.save_registry(1) is True

        # Clear and reload
        self.agent._registries.clear()
        loaded = self.agent.load_registry(1)

        assert loaded is not None
        assert loaded.project_name == "Проект А"
        assert loaded.customer == "Заказчик А"
        assert loaded.object_address == "Адрес А"
        assert loaded.contract_number == "Д-001"
        assert len(loaded.entries) == 2
        assert loaded.entries[0].status == DeloDocStatus.ACCEPTED
        assert loaded.entries[0].pages == 3

    def test_save_no_registry(self):
        assert self.agent.save_registry(999) is False

    def test_save_no_persistence_dir(self):
        agent = DeloAgent()
        agent.create_registry(1, "Test")
        assert agent.save_registry(1) is False

    def test_load_nonexistent(self):
        result = self.agent.load_registry(999)
        assert result is None

    def test_save_all(self):
        self.agent.create_registry(1, "Проект 1")
        self.agent.create_registry(2, "Проект 2")
        self.agent.register_document(1, "АОСР", "Doc1")
        self.agent.register_document(2, "АОСР", "Doc2")

        results = self.agent.save_all()
        assert results[1] is True
        assert results[2] is True

        # Verify files exist
        assert os.path.exists(f"{self.tmpdir}/registry_1.json")
        assert os.path.exists(f"{self.tmpdir}/registry_2.json")

    def test_load_all(self):
        # Save two registries
        self.agent.create_registry(1, "Проект 1")
        self.agent.create_registry(2, "Проект 2")
        self.agent.save_all()

        # Clear and reload
        self.agent._registries.clear()
        results = self.agent.load_all()
        assert 1 in results
        assert 2 in results
        assert results[1].project_name == "Проект 1"
        assert results[2].project_name == "Проект 2"


# =============================================================================
# Singleton
# =============================================================================

class TestSingleton:
    """Verify singleo delo_agent is a DeloAgent instance."""

    def test_singleton_is_delo_agent(self):
        assert isinstance(delo_agent, DeloAgent)

    def test_singleton_has_methods(self):
        assert hasattr(delo_agent, 'register_document')
        assert hasattr(delo_agent, 'create_registry')
        assert hasattr(delo_agent, 'get_registry')


# =============================================================================
# DeliveryMethod Enum
# =============================================================================

class TestDeliveryMethod:
    def test_values(self):
        assert DeliveryMethod.PAPER.value == "paper"
        assert DeliveryMethod.ELECTRONIC.value == "electronic"
        assert DeliveryMethod.HYBRID.value == "hybrid"
