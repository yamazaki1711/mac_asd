"""
MAC_ASD v11.3 — Skills Package 2 Test Script.

Тестирование PTO_WorkSpec и DELO_TemplateLib без LLM.
"""

import asyncio
import json
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.agents.skills.registry_setup import create_skill_registry
from src.agents.skills.common.base import SkillStatus


async def test_pto_work_spec():
    """Тест навыка PTO_WorkSpec."""
    print("=" * 60)
    print("TEST: PTO_WorkSpec")
    print("=" * 60)

    registry = create_skill_registry()
    skill = registry.get("PTO_WorkSpec")
    assert skill is not None, "PTO_WorkSpec not registered"

    # Тест 1: Бетонные работы
    print("\n1. Бетонные работы:")
    result = await skill.execute({"work_type": "бетонные"})
    print(f"   Status: {result.status.value}")
    print(f"   Журналов: {result.data['summary']['total_journals']}")
    print(f"   АОСР: {result.data['summary']['total_hidden_acts']} (критических: {result.data['summary']['critical_hidden_acts']})")
    print(f"   Сертификатов: {result.data['summary']['total_certificates']} (обязательных: {result.data['summary']['mandatory_certificates']})")
    assert result.is_success
    assert result.data["summary"]["total_hidden_acts"] == 11

    # Тест 2: Шпунтовые работы
    print("\n2. Шпунтовые работы:")
    result = await skill.execute({"work_type": "шпунтовые"})
    print(f"   Status: {result.status.value}")
    print(f"   АОСР: {result.data['summary']['total_hidden_acts']}")
    print(f"   Исполнительных схем: {result.data['summary']['total_executive_schemes']}")
    assert result.is_success

    # Тест 3: Исключённый вид работ
    print("\n3. Кабельные работы (исключённые):")
    result = await skill.execute({"work_type": "кабельные"})
    print(f"   Status: {result.status.value}")
    print(f"   Reason: {result.data.get('reason', '')}")
    assert result.status == SkillStatus.REJECTED

    # Тест 4: Сварочные работы
    print("\n4. Сварочные работы:")
    result = await skill.execute({"work_type": "сварочные"})
    print(f"   Status: {result.status.value}")
    print(f"   Журналов: {result.data['summary']['total_journals']}")
    assert result.is_success

    # Тест 5: Проверка совместимости
    print("\n5. Проверка совместимости:")
    result = await skill.check_compatibility(["бетонные", "кабельные", "неизвестный_вид"])
    print(f"   Supported: {result.data['supported']}")
    print(f"   Excluded: {result.data['excluded']}")
    print(f"   Unknown: {result.data['unknown']}")
    print(f"   All compatible: {result.data['all_compatible']}")

    # Тест 6: Список видов работ
    print("\n6. Список видов работ:")
    result = await skill.list_work_types()
    print(f"   Supported: {result.data['supported']}")
    print(f"   Excluded: {result.data['excluded']}")

    print("\n✅ PTO_WorkSpec: все тесты пройдены")


async def test_delo_template_lib():
    """Тест навыка DELO_TemplateLib."""
    print("\n" + "=" * 60)
    print("TEST: DELO_TemplateLib")
    print("=" * 60)

    registry = create_skill_registry()
    skill = registry.get("DELO_TemplateLib")
    assert skill is not None, "DELO_TemplateLib not registered"

    # Тест 1: Получить шаблон АОСР
    print("\n1. Шаблон АОСР:")
    result = await skill.execute({"action": "get_template", "template_type": "aosr"})
    print(f"   Status: {result.status.value}")
    print(f"   Name: {result.data['name']}")
    print(f"   Form: {result.data['form']}")
    print(f"   Fields: {len(result.data['fields'])}")
    assert result.is_success

    # Тест 2: Получить шаблон АОУС (неприменимый)
    print("\n2. Шаблон АОУС (неприменимый):")
    result = await skill.execute({"action": "get_template", "template_type": "aous"})
    print(f"   Status: {result.status.value}")
    print(f"   Warnings: {result.warnings}")
    assert result.status == SkillStatus.REJECTED

    # Тест 3: Список всех шаблонов
    print("\n3. Список шаблонов:")
    result = await skill.execute({"action": "list"})
    print(f"   Acts: {list(result.data.get('acts', {}).keys())}")
    print(f"   Journals: {list(result.data.get('journals', {}).keys())}")
    print(f"   Cancelled: {list(result.data.get('cancelled', {}).keys())}")
    assert result.is_success

    # Тест 4: Валидация заполненного АОСР
    print("\n4. Валидация АОСР (неполный):")
    result = await skill.execute({
        "action": "validate",
        "template_type": "aosr",
        "filled_data": {
            "location": "г. Москва",
            "date": "2026-04-18",
            # Отсутствуют обязательные поля
        }
    })
    print(f"   Status: {result.status.value}")
    print(f"   Valid: {result.data['is_valid']}")
    print(f"   Missing: {result.data['missing_required_fields']}")
    assert result.status == SkillStatus.PARTIAL

    # Тест 5: Валидация полного АОСР
    print("\n5. Валидация АОСР (полный):")
    result = await skill.execute({
        "action": "validate",
        "template_type": "aosr",
        "filled_data": {
            "location": "г. Москва",
            "date": "2026-04-18",
            "object_name": "Жилой дом №5",
            "contractor_name": "ООО СтройМонтаж",
            "work_description": "Установка арматуры фундаментной плиты",
            "project_docs": "КЖ-01, л.3",
            "materials": [{"name": "Арматура А500С d16", "doc": "Паспорт №123", "date": "2026-04-10", "number": "123"}],
            "work_start_date": "2026-04-15",
            "work_end_date": "2026-04-17",
            "signatures": ["Иванов И.И.", "Петров П.П.", "Сидоров С.С.", "Козлов К.К."],
        }
    })
    print(f"   Status: {result.status.value}")
    print(f"   Valid: {result.data['is_valid']}")
    assert result.is_success

    # Тест 6: Проверка отменённых форм
    print("\n6. Проверка отменённых форм:")
    result = await skill.execute({"action": "check_cancelled", "template_name": "РД-11-02-2006"})
    print(f"   Is cancelled: {result.data['is_cancelled']}")
    print(f"   Replaced by: {result.data.get('replaced_by', 'N/A')}")
    assert result.data["is_cancelled"] is True

    # Тест 7: Журнал бетонных работ
    print("\n7. Шаблон журнала бетонных работ:")
    result = await skill.execute({"action": "get_template", "template_type": "concrete_journal"})
    print(f"   Name: {result.data['name']}")
    print(f"   Form: {result.data['form']}")
    assert result.is_success

    print("\n✅ DELO_TemplateLib: все тесты пройдены")


async def test_integration():
    """Интеграционный тест: ПТО определяет, Делопроизводитель подбирает шаблон."""
    print("\n" + "=" * 60)
    print("TEST: Integration PTO_WorkSpec → DELO_TemplateLib")
    print("=" * 60)

    registry = create_skill_registry()
    pto = registry.get("PTO_WorkSpec")
    delo = registry.get("DELO_TemplateLib")

    # Сценарий: ПТО определяет документы для земляных работ
    print("\n1. ПТО: определяем состав ИД для земляных работ")
    spec = await pto.execute({"work_type": "земляные"})
    print(f"   Журналов: {spec.data['summary']['total_journals']}")
    print(f"   АОСР: {spec.data['summary']['total_hidden_acts']}")

    # Делопроизводитель получает шаблон для каждого журнала
    print("\n2. Делопроизводитель: получаем шаблоны журналов")
    for journal in spec.data["journals"]:
        print(f"   - {journal['name']} ({journal['form']})")

    # Делопроизводитель получает шаблон АОСР
    print("\n3. Делопроизводитель: шаблон АОСР")
    template = await delo.execute({"action": "get_template", "template_type": "aosr"})
    print(f"   Шаблон: {template.data['name']}")
    print(f"   Форма: {template.data['form']}")
    print(f"   Полей: {len(template.data['fields'])}")

    print("\n✅ Integration: тест пройден")


async def main():
    """Запуск всех тестов."""
    print("\n🧪 MAC_ASD v11.3 — Package 2 Skills Test Suite\n")

    try:
        await test_pto_work_spec()
        await test_delo_template_lib()
        await test_integration()

        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
