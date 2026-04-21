"""
MAC_ASD v11.3 — PTO_WorkSpec Skill.

Ядро специализации агента ПТО. Определяет состав исполнительной документации
для конкретного вида работ компании.

Специализация компании:
  ✅ Общестроительные, бетонные, земляные, сварочные, монтажные, шпунтовые
  ❌ Кабельные, слаботочные, вентиляция, водоснабжение, инженерные системы

Нормативная база (2026):
  - Приказ Минстроя № 344/пр (состав и порядок ведения ИД)
  - Приказ Минстроя № 1026/пр (общий журнал работ)
  - СП 70.13330.2012 (несущие и ограждающие конструкции)
  - СП 45.13330.2017 (земляные сооружения)
  - СП 543.1325800.2024 (строительный контроль)
  - ГОСТ Р 57365-2016/EN 12063 (шпунтовые стены)
  - СТО НОСТРОЙ 2.10.64-2012 (сварочные работы)
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Work Type Definitions
# =============================================================================

class WorkType(str, Enum):
    """Виды работ компании."""
    GENERAL = "общестроительные"
    CONCRETE = "бетонные"
    EARTHWORK = "земляные"
    WELDING = "сварочные"
    MOUNTING = "монтажные"
    SHEET_PILE = "шпунтовые"


class ExcludedWorkType(str, Enum):
    """Исключённые виды работ — НЕ обрабатываются агентом."""
    CABLE = "кабельные"
    LOW_CURRENT = "слаботочные"
    VENTILATION = "вентиляция"
    WATER_SUPPLY = "водоснабжение"
    ENGINEERING_SYSTEMS = "инженерные_системы"
    ELECTRICAL = "электромонтажные"


# =============================================================================
# Knowledge Base: Work Type → Document Requirements
# =============================================================================

# Журналы работ по видам
WORK_JOURNALS: Dict[str, List[Dict[str, str]]] = {
    WorkType.GENERAL: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Ведётся генподрядчиком, субподрядчик заполняет спец. разделы",
        },
    ],
    WorkType.CONCRETE: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Общий для всех видов работ",
        },
        {
            "name": "Журнал бетонных работ",
            "form": "СП 70.13330.2012, Приложение Ф",
            "sections": None,
            "note": "Дата/время укладки, изготовитель, объём, марка, температура",
        },
    ],
    WorkType.EARTHWORK: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Общий для всех видов работ",
        },
        {
            "name": "Журнал производства земляных работ",
            "form": "ВСН 012-88, часть II",
            "sections": None,
            "note": "Специализированный журнал для земляных работ",
        },
    ],
    WorkType.WELDING: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Общий для всех видов работ",
        },
        {
            "name": "Журнал сварочных работ",
            "form": "СП 70.13330.2012, Приложение В",
            "sections": 4,
            "section_detail": "I-Сварщики, II-Материалы, III-Оборудование, IV-Работы",
            "note": "Обязателен при любом объёме сварочных работ",
        },
        {
            "name": "Журнал антикоррозионной защиты сварных соединений",
            "form": "СП 70.13330.2012, Приложение Г",
            "sections": None,
            "note": "Ведётся совместно с журналом сварочных работ",
        },
    ],
    WorkType.MOUNTING: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Общий для всех видов работ",
        },
        {
            "name": "Журнал работ по монтажу строительных конструкций",
            "form": "СП 70.13330.2012, Приложение А",
            "sections": None,
            "note": "Дата, исполнитель, конструкции, результаты контроля",
        },
        {
            "name": "Журнал сварочных работ",
            "form": "СП 70.13330.2012, Приложение В",
            "sections": 4,
            "note": "При наличии сварки монтажных соединений",
        },
        {
            "name": "Журнал антикоррозионной защиты",
            "form": "СП 70.13330.2012, Приложение Г",
            "sections": None,
            "note": "При наличии антикоррозионной защиты",
        },
        {
            "name": "Журнал замоноличивания монтажных стыков",
            "form": "СП 70.13330.2012, Приложение Д",
            "sections": None,
            "note": "При наличии замоноличивания",
        },
    ],
    WorkType.SHEET_PILE: [
        {
            "name": "Общий журнал работ",
            "form": "Приказ Минстроя № 1026/пр",
            "sections": 7,
            "note": "Отдельного журнала для шпунта нет",
        },
        {
            "name": "Журнал сварочных работ",
            "form": "СП 70.13330.2012, Приложение В",
            "sections": 4,
            "note": "При сварке шпунтовых замков",
        },
        {
            "name": "Журнал антикоррозионной защиты",
            "form": "СП 70.13330.2012, Приложение Г",
            "sections": None,
            "note": "При антикоррозионной защите шпунта",
        },
    ],
}

# Акты скрытых работ (АОСР) по видам
WORK_HIDDEN_ACTS: Dict[str, List[Dict[str, str]]] = {
    WorkType.CONCRETE: [
        {"name": "Подготовка основания", "critical": False},
        {"name": "Устройство песчано-гравийной подготовки", "critical": False},
        {"name": "Устройство гидроизоляции основания", "critical": True},
        {"name": "Установка опалубки", "critical": False},
        {"name": "Установка и закрепление арматуры", "critical": True, "note": "Ключевой скрытый вид работ"},
        {"name": "Установка закладных деталей", "critical": False},
        {"name": "Устройство деформационных швов", "critical": True},
        {"name": "Устройство рабочих швов бетонирования", "critical": True},
        {"name": "Увлажнение основания перед бетонированием", "critical": False},
        {"name": "Укладка бетонной смеси", "critical": True},
        {"name": "Уход за бетоном", "critical": False},
    ],
    WorkType.EARTHWORK: [
        {"name": "Снятие растительного слоя грунта", "critical": False},
        {"name": "Корчёвка, выторфовывание", "critical": False},
        {"name": "Подготовка естественного основания", "critical": True},
        {"name": "Разработка котлована (до проектных отметок)", "critical": True},
        {"name": "Засыпка, выемка, уплотнение грунта", "critical": True},
        {"name": "Устройство дренажа", "critical": False, "note": "При наличии"},
        {"name": "Вертикальная планировка территории", "critical": False},
        {"name": "Устройство грунтовых подушек", "critical": True},
        {"name": "Уплотнение грунта (коэффициент уплотнения)", "critical": True},
        {"name": "Устройство обратной засыпки", "critical": True},
    ],
    WorkType.WELDING: [
        {"name": "Сварка (сварные соединения)", "critical": True},
        {"name": "Антикоррозионная защита сварных соединений", "critical": True},
        {"name": "Замоноличивание монтажных стыков", "critical": False},
    ],
    WorkType.MOUNTING: [
        {"name": "Установка стальных конструкций (скрытых)", "critical": True},
        {"name": "Опирание и закрепление конструкций", "critical": True},
        {"name": "Сварка монтажных соединений", "critical": True},
        {"name": "Антикоррозионная защита сварных соединений", "critical": True},
        {"name": "Замоноличивание монтажных стыков", "critical": False},
        {"name": "Установка закладных деталей", "critical": False},
        {"name": "Монтаж болтовых соединений (контролируемое натяжение)", "critical": True},
    ],
    WorkType.SHEET_PILE: [
        {"name": "Погружение шпунта", "critical": True},
        {"name": "Устройство шпунта Ларсена", "critical": True},
        {"name": "Устройство шпунтового ограждения", "critical": True},
        {"name": "Монтаж системы раскрепления (обвязки)", "critical": True},
        {"name": "Извлечение шпунтового ограждения", "critical": False},
        {"name": "Антикоррозионная защита шпунта", "critical": False},
    ],
}

# Сертификаты и документы о качестве по видам
WORK_CERTIFICATES: Dict[str, List[Dict[str, str]]] = {
    WorkType.CONCRETE: [
        {"name": "Паспорт на бетонную смесь", "mandatory": True},
        {"name": "Паспорт на арматуру", "mandatory": True},
        {"name": "Паспорт на закладные детали", "mandatory": False},
        {"name": "Протоколы испытания образцов бетона", "mandatory": True},
        {"name": "Документы о входном контроле", "mandatory": True},
    ],
    WorkType.EARTHWORK: [
        {"name": "Результаты лабораторных испытаний грунта", "mandatory": True},
        {"name": "Протоколы контроля уплотнения грунта", "mandatory": True},
    ],
    WorkType.WELDING: [
        {"name": "Сертификаты на сварочные материалы", "mandatory": True},
        {"name": "Удостоверения сварщиков", "mandatory": True, "note": "Копии с разрядом и видами сварки"},
        {"name": "Протоколы неразрушающего контроля (УЗК, ВИК)", "mandatory": True},
        {"name": "Заключения по НК сварных соединений", "mandatory": True},
        {"name": "Дефектная ведомость", "mandatory": False, "note": "При наличии дефектов"},
    ],
    WorkType.MOUNTING: [
        {"name": "Сертификаты на металлоконструкции", "mandatory": True},
        {"name": "Паспорта на ЖБК", "mandatory": True},
        {"name": "Сертификаты на болты (контролируемое натяжение)", "mandatory": False},
        {"name": "Сертификаты на сварочные материалы", "mandatory": True, "note": "При наличии сварки"},
    ],
    WorkType.SHEET_PILE: [
        {"name": "Сертификат на шпунт (марка стали, химсостав)", "mandatory": True},
        {"name": "Паспорт на шпунтовые профили", "mandatory": True},
        {"name": "Сертификаты на сварочные материалы", "mandatory": False, "note": "При сварке шпунта"},
    ],
}

# Исполнительные схемы по видам
WORK_EXECUTIVE_SCHEMES: Dict[str, List[str]] = {
    WorkType.CONCRETE: [],
    WorkType.EARTHWORK: [
        "Исполнительная геодезическая схема котлована/траншеи",
        "Исполнительная схема обратной засыпки",
    ],
    WorkType.WELDING: [],
    WorkType.MOUNTING: [
        "Исполнительная схема смонтированных конструкций (с отклонениями)",
    ],
    WorkType.SHEET_PILE: [
        "Исполнительная схема шпунтового ограждения котлована",
        "Исполнительная схема системы раскрепления",
    ],
}

# Нормативные ссылки по видам работ
WORK_REGULATIONS: Dict[str, List[Dict[str, str]]] = {
    WorkType.GENERAL: [
        {"code": "СП 48.13330.2019", "note": "Организация строительства (изм. 1, 2)", "status": "действует"},
        {"code": "Приказ Минстроя № 344/пр", "note": "Состав и порядок ведения ИД", "status": "действует"},
        {"code": "Приказ Минстроя № 1026/пр", "note": "Общий журнал работ", "status": "действует"},
        {"code": "СП 543.1325800.2024", "note": "Строительный контроль", "status": "действует"},
    ],
    WorkType.CONCRETE: [
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции (изм. 1-7)", "status": "действует"},
        {"code": "СП 435.1325800.2018", "note": "Конструкции бетонные и ЖБ монолитные", "status": "действует"},
    ],
    WorkType.EARTHWORK: [
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения (изм. 1-5)", "status": "действует"},
        {"code": "СП 22.13330.2016", "note": "Основания зданий и сооружений", "status": "действует"},
    ],
    WorkType.WELDING: [
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции", "status": "действует"},
        {"code": "СТО НОСТРОЙ 2.10.64-2012", "note": "Сварочные работы. Правила выполнения", "status": "действует"},
        {"code": "РД 34.15.132-96", "note": "Сварка и контроль качества", "status": "действует"},
    ],
    WorkType.MOUNTING: [
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции (изм. 1-7)", "status": "действует"},
    ],
    WorkType.SHEET_PILE: [
        {"code": "ГОСТ Р 57365-2016/EN 12063", "note": "Стены шпунтовые. Правила производства", "status": "действует"},
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения (раздел по шпунту)", "status": "действует"},
        {"code": "СП 381.1325800.2018", "note": "Сооружения подпорные", "status": "действует"},
        {"code": "СТО-ГК Трансстрой 019-2007", "note": "Шпунт Ларсена. Правила производства", "status": "действует"},
    ],
}

# Документы, генерация которых ЗАПРЕЩЕНА (исключённые виды работ)
EXCLUDED_DOCUMENTS: Dict[str, List[str]] = {
    ExcludedWorkType.CABLE: [
        "Кабельный журнал",
        "Акт на прокладку кабеля",
        "Акт испытания кабельных линий",
        "Протокол испытания кабеля",
    ],
    ExcludedWorkType.LOW_CURRENT: [
        "Акт испытания систем связи",
        "Акт испытания сигнализации",
        "Акт испытания видеонаблюдения",
        "Акт ввода в эксплуатацию слаботочных систем",
    ],
    ExcludedWorkType.VENTILATION: [
        "Акт испытания вентиляционных систем",
        "Паспорт вентиляционной системы",
        "Акт аэродинамических испытаний",
    ],
    ExcludedWorkType.WATER_SUPPLY: [
        "Акт испытания трубопроводов",
        "Акт промывки/дезинфекции",
        "Паспорт ВК систем",
        "Акт гидравлических испытаний",
    ],
    ExcludedWorkType.ELECTRICAL: [
        "Протокол испытания электроустановок",
        "Акт приёмки-передачи электрооборудования",
        "Акт проверки заземления",
    ],
}


class PTO_WorkSpec(SkillBase):
    """
    Навык специализации ПТО по видам работ.

    Определяет полный состав ИД для конкретного вида работ:
    - Перечень актов скрытых работ (АОСР)
    - Необходимые журналы работ и их формы
    - Сертификаты и документы о качестве
    - Исполнительные схемы
    - Нормативные ссылки

    Также проверяет, что запрашиваемый вид работ входит в специализацию компании.
    """

    skill_id = "PTO_WorkSpec"
    description = "Определяет состав ИД по виду работ компании"
    agent = "pto"

    # Поддерживаемые виды работ
    SUPPORTED_WORK_TYPES = {wt.value for wt in WorkType}

    # Исключённые виды работ
    EXCLUDED_WORK_TYPES = {ewt.value for ewt in ExcludedWorkType}

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: work_type обязателен."""
        errors = []
        if "work_type" not in params:
            errors.append("Параметр 'work_type' обязателен")
        return {"valid": len(errors) == 0, "errors": errors}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Определить состав ИД для вида работ.

        Args:
            work_type: Вид работ (строка из WorkType)
            include_regulations: Включить нормативные ссылки (default True)
            include_excluded_check: Проверить на исключённый вид работ (default True)

        Returns:
            SkillResult с полным составом ИД
        """
        work_type = params["work_type"]
        include_regs = params.get("include_regulations", True)
        include_excl = params.get("include_excluded_check", True)

        # Проверка на исключённый вид работ
        if include_excl and work_type in self.EXCLUDED_WORK_TYPES:
            excluded_docs = EXCLUDED_DOCUMENTS.get(work_type, [])
            return SkillResult(
                status=SkillStatus.REJECTED,
                skill_id=self.skill_id,
                data={
                    "work_type": work_type,
                    "reason": f"Вид работ '{work_type}' не входит в специализацию компании",
                    "excluded_documents": excluded_docs,
                    "supported_work_types": sorted(self.SUPPORTED_WORK_TYPES),
                },
                warnings=[
                    f"Запрос на '{work_type}' отклонён. "
                    f"Компания не выполняет данный вид работ."
                ],
            )

        # Проверка на неизвестный вид работ
        if work_type not in self.SUPPORTED_WORK_TYPES:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[
                    f"Неизвестный вид работ: '{work_type}'. "
                    f"Поддерживаемые: {sorted(self.SUPPORTED_WORK_TYPES)}"
                ],
            )

        # Сборка полного состава ИД
        result_data = {
            "work_type": work_type,
            "journals": WORK_JOURNALS.get(work_type, []),
            "hidden_works_acts": WORK_HIDDEN_ACTS.get(work_type, []),
            "certificates": WORK_CERTIFICATES.get(work_type, []),
            "executive_schemes": WORK_EXECUTIVE_SCHEMES.get(work_type, []),
            "act_form": {
                "name": "Акт освидетельствования скрытых работ (АОСР)",
                "form": "Приказ Минстроя № 344/пр, Приложение № 3",
                "note": "Форма РД-11-02-2006 НЕДЕЙСТВИТЕЛЬНА с 01.09.2023",
            },
            "general_journal_form": {
                "name": "Общий журнал учёта выполнения работ",
                "form": "Приказ Минстроя № 1026/пр",
                "sections": 7,
                "note": "Форма РД 11-05-2007 (КС-6) ОТМЕНЕНА",
            },
        }

        # Добавление нормативных ссылок
        if include_regs:
            result_data["regulations"] = WORK_REGULATIONS.get(work_type, [])

        # Подсчёт количества документов
        total_acts = len(result_data["hidden_works_acts"])
        critical_acts = sum(1 for a in result_data["hidden_works_acts"] if a.get("critical", False))
        result_data["summary"] = {
            "total_journals": len(result_data["journals"]),
            "total_hidden_acts": total_acts,
            "critical_hidden_acts": critical_acts,
            "total_certificates": len(result_data["certificates"]),
            "mandatory_certificates": sum(1 for c in result_data["certificates"] if c.get("mandatory", False)),
            "total_executive_schemes": len(result_data["executive_schemes"]),
            "total_documents": (
                len(result_data["journals"])
                + total_acts
                + len(result_data["certificates"])
                + len(result_data["executive_schemes"])
            ),
        }

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data=result_data,
        )

    async def list_work_types(self) -> SkillResult:
        """Вернуть список поддерживаемых и исключённых видов работ."""
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "supported": sorted(self.SUPPORTED_WORK_TYPES),
                "excluded": sorted(self.EXCLUDED_WORK_TYPES),
            },
        )

    async def check_compatibility(self, work_types: List[str]) -> SkillResult:
        """
        Проверить список видов работ на совместимость со специализацией.

        Args:
            work_types: Список видов работ для проверки

        Returns:
            SkillResult с разбивкой на supported/excluded/unknown
        """
        supported = []
        excluded = []
        unknown = []

        for wt in work_types:
            if wt in self.SUPPORTED_WORK_TYPES:
                supported.append(wt)
            elif wt in self.EXCLUDED_WORK_TYPES:
                excluded.append(wt)
            else:
                unknown.append(wt)

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "supported": supported,
                "excluded": excluded,
                "unknown": unknown,
                "all_compatible": len(excluded) == 0 and len(unknown) == 0,
            },
            warnings=[f"Исключённые: {excluded}"] if excluded else [],
        )
