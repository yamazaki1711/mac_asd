"""
MAC_ASD v11.3 — DELO_TemplateLib Skill.

Библиотека шаблонов документов ИД. Хранит и управляет актуальными формами
всех документов по видам работ компании.

Ключевые принципы:
  - Только действующие формы (РД-11-02-2006 и РД 11-05-2007 ОТМЕНЕНЫ)
  - Версионирование шаблонов при изменении нормативной базы
  - Валидация заполняемых реквизитов
  - Специализация: только виды работ компании
"""

import logging
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Template Definitions (inline for Package 2; will migrate to YAML/JSON files)
# =============================================================================

TEMPLATE_VERSION = "2.0"
TEMPLATE_DATE = "2026-04-18"


class TemplateStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    CANCELLED = "cancelled"


# Шаблоны актов по Приказу № 344/пр
ACT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "aosr": {
        "name": "Акт освидетельствования скрытых работ",
        "form": "Приказ Минстроя № 344/пр, Приложение № 3",
        "status": TemplateStatus.ACTIVE,
        "replaces": "РД-11-02-2006 (ОТМЕНЁН с 09.10.2023)",
        "valid_until": "01.09.2029",
        "fields": [
            {"key": "location", "label": "Место составления акта", "type": "text", "required": True},
            {"key": "date", "label": "Дата составления", "type": "date", "required": True},
            {"key": "object_name", "label": "Наименование объекта капитального строительства", "type": "text", "required": True},
            {"key": "contractor_name", "label": "Наименование лица, выполняющего работы", "type": "text", "required": True},
            {"key": "work_description", "label": "Наименование выполненных работ", "type": "text", "required": True},
            {"key": "project_docs", "label": "Проектная документация, по которой выполнены работы", "type": "text", "required": True},
            {"key": "materials", "label": "Применённые материалы (с документами о качестве)", "type": "table", "required": True,
             "columns": ["Наименование", "Документ о качестве", "Дата", "Номер"]},
            {"key": "work_start_date", "label": "Дата начала работ", "type": "date", "required": True},
            {"key": "work_end_date", "label": "Дата окончания работ", "type": "date", "required": True},
            {"key": "signatures", "label": "Подписи представителей", "type": "signatures", "required": True,
             "signers": [
                 "Представитель заказчика",
                 "Представитель лица, выполняющего работы",
                 "Представитель лица, осуществляющего строительство",
                 "Представитель лица, осуществляющего строительный контроль",
             ]},
        ],
    },
    "aook": {
        "name": "Акт освидетельствования ответственных конструкций",
        "form": "Приказ Минстроя № 344/пр, Приложение № 4",
        "status": TemplateStatus.ACTIVE,
        "replaces": "РД-11-02-2006 (ОТМЕНЁН)",
        "valid_until": "01.09.2029",
        "fields": [
            {"key": "location", "label": "Место составления акта", "type": "text", "required": True},
            {"key": "date", "label": "Дата составления", "type": "date", "required": True},
            {"key": "object_name", "label": "Наименование объекта", "type": "text", "required": True},
            {"key": "contractor_name", "label": "Наименование лица, выполняющего работы", "type": "text", "required": True},
            {"key": "construction_name", "label": "Наименование ответственной конструкции", "type": "text", "required": True},
            {"key": "project_docs", "label": "Проектная документация", "type": "text", "required": True},
            {"key": "work_description", "label": "Описание выполненных работ", "type": "text", "required": True},
            {"key": "materials", "label": "Применённые материалы", "type": "table", "required": True,
             "columns": ["Наименование", "Документ о качестве", "Дата", "Номер"]},
            {"key": "work_start_date", "label": "Дата начала работ", "type": "date", "required": True},
            {"key": "work_end_date", "label": "Дата окончания работ", "type": "date", "required": True},
            {"key": "inspection_results", "label": "Результаты освидетельствования", "type": "text", "required": True},
            {"key": "signatures", "label": "Подписи представителей", "type": "signatures", "required": True,
             "signers": [
                 "Представитель заказчика",
                 "Представитель лица, выполняющего работы",
                 "Представитель лица, осуществляющего строительство",
                 "Представитель лица, осуществляющего строительный контроль",
             ]},
        ],
    },
    "aogf": {
        "name": "Акт освидетельствования геодезической разбивочной основы",
        "form": "Приказ Минстроя № 344/пр, Приложение № 1",
        "status": TemplateStatus.ACTIVE,
        "fields": [
            {"key": "location", "label": "Место составления", "type": "text", "required": True},
            {"key": "date", "label": "Дата составления", "type": "date", "required": True},
            {"key": "object_name", "label": "Наименование объекта", "type": "text", "required": True},
            {"key": "geodetic_data", "label": "Данные геодезической основы", "type": "table", "required": True},
            {"key": "signatures", "label": "Подписи", "type": "signatures", "required": True},
        ],
    },
    "act_breakdown": {
        "name": "Акт разбивки осей объекта капитального строительства",
        "form": "Приказ Минстроя № 344/пр, Приложение № 2",
        "status": TemplateStatus.ACTIVE,
        "fields": [
            {"key": "location", "label": "Место составления", "type": "text", "required": True},
            {"key": "date", "label": "Дата составления", "type": "date", "required": True},
            {"key": "object_name", "label": "Наименование объекта", "type": "text", "required": True},
            {"key": "axes_data", "label": "Данные разбивки осей", "type": "table", "required": True},
            {"key": "signatures", "label": "Подписи", "type": "signatures", "required": True},
        ],
    },
    "aous": {
        "name": "Акт освидетельствования участков сетей ИТО",
        "form": "Приказ Минстроя № 344/пр, Приложение № 5",
        "status": TemplateStatus.ACTIVE,
        "note": "НЕ применяется для видов работ компании (нет инженерных систем)",
        "applicable": False,
        "fields": [
            {"key": "location", "label": "Место составления", "type": "text", "required": True},
            {"key": "date", "label": "Дата составления", "type": "date", "required": True},
            {"key": "object_name", "label": "Наименование объекта", "type": "text", "required": True},
            {"key": "network_section", "label": "Наименование участка сети ИТО", "type": "text", "required": True},
            {"key": "signatures", "label": "Подписи", "type": "signatures", "required": True},
        ],
    },
}

# Шаблоны журналов работ
JOURNAL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "general_journal": {
        "name": "Общий журнал учёта выполнения работ",
        "form": "Приказ Минстроя № 1026/пр",
        "status": TemplateStatus.ACTIVE,
        "replaces": "РД 11-05-2007 (форма КС-6, ОТМЕНЕНА с 01.09.2023)",
        "sections": 7,
        "section_names": [
            "Сведения об объекте",
            "Сведения о лицах, осуществляющих строительство",
            "Сведения о лицах, осуществляющих строительный контроль",
            "Сведения о выполнении работ",
            "Сведения о входном контроле",
            "Сведения об операционном контроле",
            "Сведения о приёмочном контроле",
        ],
    },
    "concrete_journal": {
        "name": "Журнал бетонных работ",
        "form": "СП 70.13330.2012, Приложение Ф",
        "status": TemplateStatus.ACTIVE,
        "columns": [
            "Дата/время укладки",
            "Место укладки (ось, отметка, ярус)",
            "Наименование конструкции",
            "Изготовитель бетонной смеси",
            "Марка бетона по проекту",
            "Объём уложенной смеси (м³)",
            "Температура воздуха/бетона",
            "Результаты контроля",
        ],
    },
    "welding_journal": {
        "name": "Журнал сварочных работ",
        "form": "СП 70.13330.2012, Приложение В",
        "status": TemplateStatus.ACTIVE,
        "sections": 4,
        "section_names": [
            "I. Сведения о сварщиках",
            "II. Сведения о сварочных материалах",
            "III. Сведения о сварочном оборудовании",
            "IV. Сведения о выполнении работ по сварке",
        ],
    },
    "mounting_journal": {
        "name": "Журнал работ по монтажу строительных конструкций",
        "form": "СП 70.13330.2012, Приложение А",
        "status": TemplateStatus.ACTIVE,
        "columns": [
            "Дата выполнения работ",
            "Исполнитель",
            "Наименование конструкций",
            "Марка конструкции",
            "Результаты контроля",
        ],
    },
    "anticorrosion_journal": {
        "name": "Журнал антикоррозионной защиты сварных соединений",
        "form": "СП 70.13330.2012, Приложение Г",
        "status": TemplateStatus.ACTIVE,
    },
    "monolithic_journal": {
        "name": "Журнал замоноличивания монтажных стыков",
        "form": "СП 70.13330.2012, Приложение Д",
        "status": TemplateStatus.ACTIVE,
    },
    "earthwork_journal": {
        "name": "Журнал производства земляных работ",
        "form": "ВСН 012-88, часть II",
        "status": TemplateStatus.ACTIVE,
    },
}

# Отменённые формы (для справки и контроля)
CANCELLED_TEMPLATES: Dict[str, Dict[str, str]] = {
    "rd_11_02_2006_aosr": {
        "name": "Акт скрытых работ (РД-11-02-2006)",
        "cancelled_date": "09.10.2023",
        "replaced_by": "Приказ № 344/пр, Приложение № 3",
    },
    "rd_11_05_2007_ks6": {
        "name": "Общий журнал работ (РД 11-05-2007, КС-6)",
        "cancelled_date": "01.09.2023",
        "replaced_by": "Приказ № 1026/пр (7 разделов вместо 5)",
    },
}


class DELO_TemplateLib(SkillBase):
    """
    Библиотека шаблонов документов ИД.

    Функции:
      - Получить шаблон по типу документа
      - Валидировать заполненные реквизиты
      - Проверить, что шаблон действующий (не отменённый)
      - Вернуть список всех доступных шаблонов
    """

    skill_id = "DELO_TemplateLib"
    description = "Библиотека шаблонов документов ИД"
    agent = "delo"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: template_type или action обязательны."""
        action = params.get("action", "get_template")
        if action == "get_template" and "template_type" not in params:
            return {"valid": False, "errors": ["Параметр 'template_type' обязателен для action='get_template'"]}
        if action == "validate" and "template_type" not in params and "filled_data" not in params:
            return {"valid": False, "errors": ["Параметры 'template_type' и 'filled_data' обязательны для validate"]}
        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Основной метод: получить шаблон, валидировать или перечислить.

        Args:
            action: Действие (get_template | validate | list | check_cancelled)
            template_type: Тип шаблона (aosr | aook | aogf | act_breakdown | aous |
                           general_journal | concrete_journal | welding_journal |
                           mounting_journal | anticorrosion_journal | monolithic_journal |
                           earthwork_journal)
            filled_data: Заполненные данные (для validate)
        """
        action = params.get("action", "get_template")

        if action == "get_template":
            return await self._get_template(params["template_type"])
        elif action == "validate":
            return await self._validate_template(params["template_type"], params.get("filled_data", {}))
        elif action == "list":
            return await self._list_templates(params.get("category", "all"))
        elif action == "check_cancelled":
            return await self._check_cancelled(params.get("template_name", ""))
        else:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[f"Неизвестное действие: {action}"],
            )

    async def _get_template(self, template_type: str) -> SkillResult:
        """Получить шаблон по типу."""
        # Поиск в актах
        if template_type in ACT_TEMPLATES:
            template = ACT_TEMPLATES[template_type]
            # Проверка на неприменимость
            if not template.get("applicable", True):
                return SkillResult(
                    status=SkillStatus.REJECTED,
                    skill_id=self.skill_id,
                    data=template,
                    warnings=[
                        f"Шаблон '{template['name']}' не применяется для видов работ компании. "
                        f"Компания не выполняет инженерные системы."
                    ],
                )
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={
                    **template,
                    "template_version": TEMPLATE_VERSION,
                    "template_date": TEMPLATE_DATE,
                },
            )

        # Поиск в журналах
        if template_type in JOURNAL_TEMPLATES:
            template = JOURNAL_TEMPLATES[template_type]
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={
                    **template,
                    "template_version": TEMPLATE_VERSION,
                    "template_date": TEMPLATE_DATE,
                },
            )

        return SkillResult(
            status=SkillStatus.ERROR,
            skill_id=self.skill_id,
            errors=[f"Неизвестный тип шаблона: '{template_type}'"],
        )

    async def _validate_template(
        self, template_type: str, filled_data: Dict[str, Any]
    ) -> SkillResult:
        """Валидировать заполненные данные шаблона."""
        # Получить шаблон
        template_result = await self._get_template(template_type)
        if not template_result.is_success:
            return template_result

        template = template_result.data
        fields = template.get("fields", [])

        # Проверка обязательных полей
        missing_fields = []
        warnings = []

        for field_def in fields:
            key = field_def["key"]
            required = field_def.get("required", False)

            if required and key not in filled_data:
                missing_fields.append(field_def["label"])
            elif key in filled_data and not filled_data[key]:
                if required:
                    missing_fields.append(field_def["label"])

        # Проверка использования отменённых форм
        if template_type in ("rd_11_02_2006_aosr", "rd_11_05_2007_ks6"):
            warnings.append(
                f"ВНИМАНИЕ: Используется отменённая форма! "
                f"См. CANCELLED_TEMPLATES для замены."
            )

        result_data = {
            "template_type": template_type,
            "template_name": template.get("name", ""),
            "missing_required_fields": missing_fields,
            "is_valid": len(missing_fields) == 0,
            "filled_fields_count": len(filled_data),
            "required_fields_count": sum(1 for f in fields if f.get("required", False)),
        }

        return SkillResult(
            status=SkillStatus.SUCCESS if result_data["is_valid"] else SkillStatus.PARTIAL,
            skill_id=self.skill_id,
            data=result_data,
            warnings=warnings,
        )

    async def _list_templates(self, category: str = "all") -> SkillResult:
        """Перечислить все доступные шаблоны."""
        result = {
            "template_version": TEMPLATE_VERSION,
            "template_date": TEMPLATE_DATE,
        }

        if category in ("all", "acts"):
            result["acts"] = {
                k: {"name": v["name"], "form": v["form"], "status": v["status"].value}
                for k, v in ACT_TEMPLATES.items()
            }

        if category in ("all", "journals"):
            result["journals"] = {
                k: {"name": v["name"], "form": v["form"], "status": v["status"].value}
                for k, v in JOURNAL_TEMPLATES.items()
            }

        if category in ("all", "cancelled"):
            result["cancelled"] = CANCELLED_TEMPLATES

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data=result,
        )

    async def _check_cancelled(self, template_name: str) -> SkillResult:
        """Проверить, не отменён ли указанный шаблон."""
        if not template_name:
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={"cancelled_templates": CANCELLED_TEMPLATES},
            )

        # Поиск по имени
        for key, info in CANCELLED_TEMPLATES.items():
            if template_name.lower() in info["name"].lower():
                return SkillResult(
                    status=SkillStatus.SUCCESS,
                    skill_id=self.skill_id,
                    data={
                        "is_cancelled": True,
                        "name": info["name"],
                        "cancelled_date": info["cancelled_date"],
                        "replaced_by": info["replaced_by"],
                    },
                    warnings=[f"Шаблон ОТМЕНЁН: {info['name']}"],
                )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={"is_cancelled": False, "name": template_name},
        )
