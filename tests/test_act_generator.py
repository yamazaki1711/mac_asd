"""Tests for PTO_ActGenerator skill — act document generation."""

import os
import tempfile
import pytest

from src.agents.skills.pto.act_generator import PTO_ActGenerator


class TestPTOActGenerator:
    """Act document generation tests. NOTE: asserts must be inside the
    tempfile.TemporaryDirectory() context manager — the dir is deleted on exit."""

    @pytest.mark.asyncio
    async def test_generate_aosr_fallback(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "aosr",
                "context": {
                    "act_number": "1",
                    "project_name": "Тестовый проект",
                    "work_description": "Бетонирование фундамента",
                    "volume": 45.0,
                    "unit": "м3",
                },
                "output_dir": tmpdir,
            })

            assert result.is_success
            data = result.data
            assert data["act_type"] == "aosr"
            assert os.path.exists(data["file_path"])
            assert data["filename"].endswith(".docx")
            assert data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_generate_incoming_control(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "incoming_control",
                "context": {"work_description": "Входной контроль арматуры"},
                "output_dir": tmpdir,
            })

            assert result.is_success
            assert os.path.exists(result.data["file_path"])

    @pytest.mark.asyncio
    async def test_generate_hidden_works(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "hidden_works",
                "context": {"work_description": "Скрытые работы"},
                "output_dir": tmpdir,
            })

            assert result.is_success
            assert os.path.exists(result.data["file_path"])

    @pytest.mark.asyncio
    async def test_generate_inspection(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "inspection",
                "context": {"work_description": "Освидетельствование колонн"},
                "output_dir": tmpdir,
            })

            assert result.is_success
            assert os.path.exists(result.data["file_path"])

    @pytest.mark.asyncio
    async def test_unknown_act_type(self):
        skill = PTO_ActGenerator()
        result = await skill.execute({"act_type": "unknown_type"})

        assert not result.is_success
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_context_fields_in_document(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "aosr",
                "context": {
                    "act_number": "42",
                    "act_date": "01.05.2026",
                    "project_name": "Причалы порта Корсаков",
                    "work_description": "Погружение шпунта Л5-УМ",
                    "materials": [
                        {"name": "Шпунт Л5-УМ", "quantity": 120, "unit": "т"},
                    ],
                    "commission_members": [
                        {"role": "Заказчик", "name": "Иванов И.И."},
                    ],
                },
                "output_dir": tmpdir,
            })

            assert result.is_success
            file_path = result.data["file_path"]
            assert os.path.exists(file_path)
            assert result.data["size_bytes"] > 500

    @pytest.mark.asyncio
    async def test_output_dir_created(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as base_tmp:
            nested_dir = os.path.join(base_tmp, "nested", "acts")
            result = await skill.execute({
                "act_type": "aosr",
                "context": {"work_description": "Test"},
                "output_dir": nested_dir,
            })

            assert result.is_success
            assert os.path.exists(result.data["file_path"])
            assert os.path.isdir(nested_dir)

    @pytest.mark.asyncio
    async def test_validate_missing_act_type(self):
        skill = PTO_ActGenerator()
        result = await skill.execute({"context": {"work_description": "x"}})

        assert not result.is_success
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_default_values_filled(self):
        skill = PTO_ActGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await skill.execute({
                "act_type": "aosr",
                "context": {},
                "output_dir": tmpdir,
            })

            assert result.is_success
            assert os.path.exists(result.data["file_path"])
            assert result.data["size_bytes"] > 0
