"""
MAC_ASD v12.0 — PTO_WorkSpec Skill.

Ядро специализации агента ПТО. Определяет полный состав исполнительной
документации для ЛЮБОГО вида работ на ОКС любой сложности.

Источник: Пособие по исполнительной документации. Выпуск №2
         (Сарвартдинова Р.Н., ВАШ ФОРМАТ, 2026, 424 с.)

Нормативная база (2026):
  - Приказ Минстроя № 344/пр от 16.05.2023 (состав и порядок ведения ИД)
  - Приказ Минстроя № 1026/пр от 02.12.2022 (общий журнал работ)
  - СП 543.1325800.2024 (строительный контроль, Приложение А — перечень ИД)
  - ГОСТ Р 51872-2024 (исполнительные схемы)
  - ГОСТ Р 70108-2025 (электронная ИД)

Концепция v12.0: АСД — автономный комплекс по созданию (восстановлению)
полного комплекта ИД на ОКС ЛЮБОЙ сложности и ЛЮБЫХ видов работ.
Ограничения по видам работ УСТРАНЕНЫ.
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Work Type Definitions — полная номенклатура по Главе 5 Пособия
# =============================================================================

class WorkType(str, Enum):
    """Виды работ — полная номенклатура по Пособию 2026."""
    # Земляные работы (5.3)
    EARTHWORK_EXCAVATION = "земляные_выемки"            # 5.3.1
    EARTHWORK_BACKFILL = "земляные_обратная_засыпка"     # 5.3.2

    # Фундаменты (5.4)
    FOUNDATION_MONOLITHIC = "фундаменты_монолитные"      # 5.4.1
    FOUNDATION_PRECAST = "фундаменты_сборные"            # 5.4.2
    FOUNDATION_PILE = "фундаменты_свайные"               # 5.4.3

    # Бетонные работы (5.5)
    CONCRETE = "бетонные"                                 # 5.5

    # Металлоконструкции (5.6)
    METAL_STRUCTURES = "металлоконструкции"              # 5.6

    # Каменная кладка (5.7)
    MASONRY = "каменная_кладка"                           # 5.7

    # Отделочные работы (5.8)
    FINISHING_FLOORS = "отделка_полы"                     # 5.8.1
    FINISHING_WALLS_CEILINGS = "отделка_стены_потолки"   # 5.8.2
    FINISHING_WINDOWS_DOORS = "отделка_окна_двери"       # 5.8.3

    # Водоснабжение и водоотведение (5.9)
    WATER_SUPPLY = "водоснабжение"                        # 5.9.1
    SEWERAGE = "канализация"                              # 5.9.2
    EXTERNAL_NETWORKS_VK = "наружные_сети_вк"            # 5.9.3

    # ОВиК (5.10)
    HEATING = "отопление"                                 # 5.10.1
    VENTILATION = "вентиляция"                            # 5.10.2
    AIR_CONDITIONING = "кондиционирование"                # 5.10.3

    # Электромонтаж (5.11)
    ELECTRICAL_INTERNAL = "электромонтаж_внутренние"     # 5.11
    ELECTRICAL_EXTERNAL = "электромонтаж_наружные"       # 5.11

    # Сети связи (5.12)
    COMMUNICATION_NETWORKS = "сети_связи"                 # 5.12

    # Дополнительные виды работ (id-prosto.ru / Пособие, гл. 5)
    ANTICORROSIVE = "акз_огнезащита"                       # 5.6 / 10_anticorrosive
    HDD_DRILLING = "гнб_прокол"                             # 13_drilling
    FIRE_EXTINGUISHING = "пожаротушение"                   # 18_extinguishing
    PROCESS_PIPELINES = "технологические_трубопроводы"     # 19_pipelines
    PROCESS_EQUIPMENT = "технологическое_оборудование"     # 20_equipment
    TANKS = "резервуары"                                    # 21_tanks
    AUTOMATION = "системы_автоматизации"                   # 24_automatic
    FIRE_ALARM = "пожарная_сигнализация"                   # 25_fire-alarm
    ELEVATORS = "лифты"                                     # 27_elevators
    HEAT_PIPELINES = "тепловые_сети"                       # 28_heat-pipelines
    ROADS = "автомобильные_дороги"                         # 29_roads
    DEMOLITION = "демонтажные_работы"                      # 30_demolition
    STEAM_BOILER = "паровая_котельная"                     # 31_steam-boiler


# Группировка видов работ по категориям
WORK_TYPE_CATEGORIES: Dict[str, List[WorkType]] = {
    "earthwork": [WorkType.EARTHWORK_EXCAVATION, WorkType.EARTHWORK_BACKFILL, WorkType.HDD_DRILLING],
    "foundation": [WorkType.FOUNDATION_MONOLITHIC, WorkType.FOUNDATION_PRECAST, WorkType.FOUNDATION_PILE],
    "concrete": [WorkType.CONCRETE],
    "metal": [WorkType.METAL_STRUCTURES],
    "masonry": [WorkType.MASONRY],
    "finishing": [WorkType.FINISHING_FLOORS, WorkType.FINISHING_WALLS_CEILINGS, WorkType.FINISHING_WINDOWS_DOORS],
    "water_sewer": [WorkType.WATER_SUPPLY, WorkType.SEWERAGE, WorkType.EXTERNAL_NETWORKS_VK],
    "hvac": [WorkType.HEATING, WorkType.VENTILATION, WorkType.AIR_CONDITIONING, WorkType.HEAT_PIPELINES],
    "electrical": [WorkType.ELECTRICAL_INTERNAL, WorkType.ELECTRICAL_EXTERNAL],
    "communication": [WorkType.COMMUNICATION_NETWORKS],
    "fire_safety": [WorkType.FIRE_EXTINGUISHING, WorkType.FIRE_ALARM],
    "industrial": [WorkType.PROCESS_PIPELINES, WorkType.PROCESS_EQUIPMENT, WorkType.TANKS, WorkType.STEAM_BOILER],
    "automation": [WorkType.AUTOMATION],
    "transport": [WorkType.ELEVATORS, WorkType.ROADS],
    "special": [WorkType.ANTICORROSIVE, WorkType.DEMOLITION],
}

# Ссылки на разделы Пособия
WORK_TYPE_CHAPTERS: Dict[str, str] = {
    WorkType.EARTHWORK_EXCAVATION: "5.3.1",
    WorkType.EARTHWORK_BACKFILL: "5.3.2",
    WorkType.FOUNDATION_MONOLITHIC: "5.4.1",
    WorkType.FOUNDATION_PRECAST: "5.4.2",
    WorkType.FOUNDATION_PILE: "5.4.3",
    WorkType.CONCRETE: "5.5",
    WorkType.METAL_STRUCTURES: "5.6",
    WorkType.MASONRY: "5.7",
    WorkType.FINISHING_FLOORS: "5.8.1",
    WorkType.FINISHING_WALLS_CEILINGS: "5.8.2",
    WorkType.FINISHING_WINDOWS_DOORS: "5.8.3",
    WorkType.WATER_SUPPLY: "5.9.1",
    WorkType.SEWERAGE: "5.9.2",
    WorkType.EXTERNAL_NETWORKS_VK: "5.9.3",
    WorkType.HEATING: "5.10.1",
    WorkType.VENTILATION: "5.10.2",
    WorkType.AIR_CONDITIONING: "5.10.3",
    WorkType.ELECTRICAL_INTERNAL: "5.11",
    WorkType.ELECTRICAL_EXTERNAL: "5.11",
    WorkType.COMMUNICATION_NETWORKS: "5.12",
    WorkType.ANTICORROSIVE: "5.6",
    WorkType.HDD_DRILLING: "5.3.3",
    WorkType.FIRE_EXTINGUISHING: "5.13",
    WorkType.PROCESS_PIPELINES: "5.14",
    WorkType.PROCESS_EQUIPMENT: "5.15",
    WorkType.TANKS: "5.16",
    WorkType.AUTOMATION: "5.17",
    WorkType.FIRE_ALARM: "5.13",
    WorkType.ELEVATORS: "5.18",
    WorkType.HEAT_PIPELINES: "5.10.4",
    WorkType.ROADS: "5.19",
    WorkType.DEMOLITION: "5.20",
    WorkType.STEAM_BOILER: "5.21",
}


# =============================================================================
# Общие документы — применимы ко ВСЕМ видам работ
# =============================================================================

COMMON_JOURNAL_OJR = {
    "name": "Общий журнал работ",
    "form": "Приказ Минстроя № 1026/пр от 02.12.2022",
    "mandatory": True,
    "note": "Ведётся на ВСЕХ объектах. Форма РД 11-05-2007 (КС-6) ОТМЕНЕНА.",
}

COMMON_JOURNAL_JVK = {
    "name": "Журнал входного контроля и контроля качества получаемых деталей, материалов, изделий, конструкций и оборудования",
    "form": "СП 543.1325800.2024 / ГОСТ 24297-2013",
    "mandatory": True,
    "note": "Обязателен при использовании строительных материалов. Фиксирует результаты входного контроля.",
}

COMMON_ACT_AOSR = {
    "name": "Акт освидетельствования скрытых работ (АОСР)",
    "form": "Приказ Минстроя № 344/пр, Приложение № 3",
    "note": "Форма РД-11-02-2006 НЕДЕЙСТВИТЕЛЬНА с 01.09.2023",
}

COMMON_ACT_AOOUK = {
    "name": "Акт освидетельствования ответственных конструкций (АООК)",
    "form": "Приказ Минстроя № 344/пр, Приложение № 4",
}

COMMON_REGULATIONS = [
    {"code": "Приказ Минстроя № 344/пр от 16.05.2023", "note": "Состав и порядок ведения ИД — ОСНОВНОЙ ДОКУМЕНТ", "status": "действует"},
    {"code": "Приказ Минстроя № 1026/пр от 02.12.2022", "note": "Общий журнал работ", "status": "действует"},
    {"code": "СП 543.1325800.2024", "note": "Строительный контроль, Приложение А — перечень ИД", "status": "действует"},
    {"code": "ГОСТ Р 51872-2024", "note": "Исполнительные схемы", "status": "действует"},
    {"code": "ГОСТ Р 70108-2025", "note": "Электронная ИД", "status": "действует"},
]


# =============================================================================
# ЖУРНАЛЫ по видам работ
# =============================================================================

WORK_JOURNALS: Dict[str, List[Dict[str, Any]]] = {
    # ---- Земляные работы ----
    WorkType.EARTHWORK_EXCAVATION: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал производства земляных работ",
            "form": "ВСН 012-88, часть II",
            "mandatory": False,
            "conditional": "только для нефтегазового строительства!",
            "note": "Для общестроительных объектов НЕ требуется",
        },
    ],
    WorkType.EARTHWORK_BACKFILL: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал производства земляных работ",
            "form": "ВСН 012-88, часть II",
            "mandatory": False,
            "conditional": "только для нефтегазового строительства!",
        },
        {
            **COMMON_JOURNAL_JVK,
            "conditional": "при обратной засыпке с использованием строительных материалов (песок, щебень)",
        },
    ],

    # ---- Фундаменты ----
    WorkType.FOUNDATION_MONOLITHIC: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал бетонных работ",
            "form": "СП 70.13330.2012, Приложение Ф",
            "mandatory": True,
        },
        {
            "name": "Журнал ухода за бетоном / контроля температуры бетона",
            "form": "СП 70.13330.2012 / температурный лист",
            "mandatory": False,
            "conditional": "при зимнем бетонировании",
            "note": "Температурный лист при зимнем бетонировании обязателен",
        },
        COMMON_JOURNAL_JVK,
    ],
    WorkType.FOUNDATION_PRECAST: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал работ по монтажу строительных конструкций",
            "form": "СП 70.13330.2012, Приложение А",
            "mandatory": True,
        },
        {
            "name": "Журнал замоноличивания монтажных стыков и узлов",
            "form": "СП 70.13330.2012, Приложение Д",
            "mandatory": True,
            "conditional": "при наличии замоноличивания",
        },
        COMMON_JOURNAL_JVK,
    ],
    WorkType.FOUNDATION_PILE: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал погружения (забивки) свай",
            "form": "СП 45.13330.2017 / СП 70.13330.2012",
            "mandatory": True,
            "conditional": "для забивных/вибропогруженных свай",
        },
        {
            "name": "Журнал изготовления буронабивных свай",
            "form": "СП 45.13330.2017",
            "mandatory": True,
            "conditional": "для буронабивных свай",
        },
        {
            "name": "Журнал производства антикоррозионных работ",
            "form": "СП 70.13330.2012, Приложение И",
            "mandatory": False,
            "conditional": "при изготовлении металлических свай на площадке",
        },
        {
            "name": "Журнал полевого испытания грунтов динамической нагрузкой",
            "form": "ГОСТ 5686-2020",
            "mandatory": False,
            "conditional": "для забивных свай",
        },
        {
            "name": "Журнал полевого испытания грунтов статическими вдавливающими, выдергивающими и горизонтальными нагрузками",
            "form": "ГОСТ 5686-2020",
            "mandatory": False,
            "conditional": "при статических испытаниях",
        },
        COMMON_JOURNAL_JVK,
    ],

    # ---- Бетонные работы ----
    WorkType.CONCRETE: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал бетонных работ",
            "form": "СП 70.13330.2012, Приложение Ф",
            "mandatory": True,
        },
        {
            "name": "Журнал ухода за бетоном / контроля температуры бетона",
            "form": "СП 70.13330.2012 / температурный лист",
            "mandatory": False,
            "conditional": "при зимнем бетонировании",
        },
        COMMON_JOURNAL_JVK,
    ],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал работ по монтажу строительных конструкций",
            "form": "СП 70.13330.2012, Приложение А",
            "mandatory": True,
            "note": "Колонны, балки, фермы, ригели и прочие МК",
        },
        {
            "name": "Журнал сварочных работ",
            "form": "СП 70.13330.2012, Приложение В",
            "mandatory": False,
            "conditional": "при сварных монтажных соединениях (заводские НЕ учитываем!)",
            "sections": 4,
            "section_detail": "I-Сварщики, II-Материалы, III-Оборудование, IV-Работы",
        },
        {
            "name": "Журнал антикоррозионной защиты сварных соединений",
            "form": "СП 70.13330.2012, Приложение Г",
            "mandatory": False,
            "conditional": "при наличии сварных соединений с антикоррозийной защитой",
        },
        {
            "name": "Журнал производства антикоррозионных работ",
            "form": "СП 70.13330.2012, Приложение И",
            "mandatory": False,
            "conditional": "при антикоррозийной защите МК (отдельный от журнала защиты сварных соединений)",
            "note": "Отдельный журнал — НЕ то же самое, что журнал антикоррозийной защиты сварных соединений!",
        },
        {
            "name": "Журнал выполнения монтажных соединений на болтах с контролируемым натяжением",
            "form": "СП 70.13330.2012, Приложение Ж",
            "mandatory": False,
            "conditional": "при болтах с контролируемым натяжением",
        },
        {
            "name": "Журнал контрольной тарировки динамометрических ключей",
            "form": "СП 70.13330.2012",
            "mandatory": False,
            "conditional": "при болтах с контролируемым натяжением",
        },
        COMMON_JOURNAL_JVK,
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал испытаний на строительной площадке / журнал инструментального контроля",
            "form": "СП 70.13330.2012",
            "mandatory": False,
            "conditional": "при проведении инструментального контроля",
        },
        COMMON_JOURNAL_JVK,
    ],

    # ---- Отделочные работы ----
    WorkType.FINISHING_FLOORS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
        {
            "name": "Журнал бетонных работ",
            "form": "СП 70.13330.2012, Приложение Ф",
            "mandatory": False,
            "conditional": "при устройстве бетонных полов",
        },
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],

    # ---- Водоснабжение и водоотведение ----
    WorkType.WATER_SUPPLY: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    WorkType.SEWERAGE: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],

    # ---- ОВиК ----
    WorkType.HEATING: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    WorkType.VENTILATION: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    WorkType.AIR_CONDITIONING: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],

    # ---- Электромонтаж ----
    WorkType.ELECTRICAL_INTERNAL: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
        {
            "name": "Кабельный журнал (до 1 кВ)",
            "form": "И 1.13-07",
            "mandatory": True,
        },
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
        {
            "name": "Кабельный журнал (до 1 кВ)",
            "form": "И 1.13-07",
            "mandatory": True,
        },
        {
            "name": "Журнал прокладки кабеля (1-35 кВ)",
            "form": "И 1.13-07",
            "mandatory": False,
            "conditional": "при кабельных линиях 1-35 кВ",
        },
        {
            "name": "Журнал монтажа кабельных муфт напряжением выше 1000 В",
            "form": "И 1.13-07",
            "mandatory": False,
            "conditional": "при напряжении выше 1000 В",
        },
    ],

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- АКЗ и огнезащита ----
    WorkType.ANTICORROSIVE: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал производства антикоррозионных работ",
            "form": "СП 70.13330.2012, Приложение И",
            "mandatory": True,
        },
        COMMON_JOURNAL_JVK,
    ],
    # ---- ГНБ ----
    WorkType.HDD_DRILLING: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал производства земляных работ при ГНБ",
            "form": "ВСН 012-88, часть II",
            "mandatory": False,
        },
        COMMON_JOURNAL_JVK,
    ],
    # ---- Пожаротушение ----
    WorkType.FIRE_EXTINGUISHING: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Технологические трубопроводы ----
    WorkType.PROCESS_PIPELINES: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал по сварке трубопроводов",
            "form": "ГОСТ 32569-2013",
            "mandatory": True,
            "conditional": "для трубопроводов I и II категории",
        },
        {
            "name": "Журнал учёта и проверки качества контрольных сварных соединений",
            "form": "ГОСТ 32569-2013",
            "mandatory": True,
        },
        {
            "name": "Журнал сборки разъёмных соединений трубопроводов",
            "form": "ГОСТ 32569-2013",
            "mandatory": False,
            "conditional": "при давлении P > 10 МПа",
        },
        {
            "name": "Журнал термической обработки сварных соединений",
            "form": "ГОСТ 32569-2013",
            "mandatory": False,
            "conditional": "при термообработке",
        },
        COMMON_JOURNAL_JVK,
    ],
    # ---- Технологическое оборудование ----
    WorkType.PROCESS_EQUIPMENT: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Резервуары ----
    WorkType.TANKS: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал пооперационного контроля монтажно-сварочных работ при сооружении резервуара",
            "form": "СП 365.1325800.2017",
            "mandatory": True,
        },
        {
            "name": "Журнал работ по монтажу строительных конструкций (лестницы, площадки, кронштейны)",
            "form": "СП 70.13330.2012, Приложение А",
            "mandatory": True,
        },
        {
            "name": "Журнал сварочных работ (лестницы, площадки, кронштейны)",
            "form": "СП 70.13330.2012, Приложение В",
            "mandatory": True,
        },
        COMMON_JOURNAL_JVK,
    ],
    # ---- Системы автоматизации ----
    WorkType.AUTOMATION: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Пожарная сигнализация ----
    WorkType.FIRE_ALARM: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Лифты ----
    WorkType.ELEVATORS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Тепловые сети ----
    WorkType.HEAT_PIPELINES: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Журнал сварочных работ",
            "form": "СП 70.13330.2012, Приложение В",
            "mandatory": False,
            "conditional": "при сварных соединениях",
        },
        COMMON_JOURNAL_JVK,
    ],
    # ---- Автомобильные дороги ----
    WorkType.ROADS: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Демонтажные работы ----
    WorkType.DEMOLITION: [
        COMMON_JOURNAL_OJR,
        COMMON_JOURNAL_JVK,
    ],
    # ---- Паровая котельная ----
    WorkType.STEAM_BOILER: [
        COMMON_JOURNAL_OJR,
        {
            "name": "Сварочный журнал",
            "form": "ГОСТ 32569-2013",
            "mandatory": True,
        },
        {
            "name": "Журнал термической обработки сварных соединений",
            "form": "ГОСТ 32569-2013",
            "mandatory": False,
            "conditional": "при термообработке",
        },
        COMMON_JOURNAL_JVK,
    ],
}


# =============================================================================
# АОСР (Акты освидетельствования скрытых работ)
# =============================================================================

WORK_HIDDEN_ACTS: Dict[str, List[Dict[str, Any]]] = {
    # ---- Земляные ----
    WorkType.EARTHWORK_EXCAVATION: [
        {"name": "Снятие растительного слоя грунта", "mandatory": True},
        {"name": "Вертикальная планировка территории", "mandatory": False, "conditional": "если выполнялись такие работы"},
        {"name": "Разработка грунта (устройство выемки)", "mandatory": True},
        {"name": "Устройство дренажей", "mandatory": False, "conditional": "если выполнялись такие работы"},
        {"name": "Устройство крепления стенок выемки", "mandatory": False, "conditional": "если выполнялись такие работы"},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        {"name": "Возведение и уплотнение земляного полотна", "mandatory": True, "note": "С приложением протокола уплотнения и ИС с точками отбора проб"},
        {"name": "Обратная засыпка пазух котлована (траншей)", "mandatory": True, "note": "С ИС и протоколом уплотнения, с ИГС"},
        {"name": "Устройство слоев насыпи", "mandatory": True},
    ],

    # ---- Фундаменты ----
    WorkType.FOUNDATION_MONOLITHIC: [
        {"name": "Устройство котлована", "mandatory": True, "note": "Подробнее в разделе 5.3"},
        {"name": "Устройство оснований под фундаменты (бетонное, песчаное, щебеночное, естественное)", "mandatory": True},
        {"name": "Армирование (устройство армокаркаса)", "mandatory": True},
        {"name": "Монтаж закладных изделий и анкерных болтов", "mandatory": True},
        {"name": "Устройство опалубки", "mandatory": False, "note": "По требованию, необязательно по общим нормам"},
        {"name": "Бетонирование", "mandatory": True},
        {"name": "Гидроизоляция", "mandatory": True},
    ],
    WorkType.FOUNDATION_PRECAST: [
        {"name": "Устройство котлована", "mandatory": True},
        {"name": "Устройство оснований под фундаменты", "mandatory": True},
        {"name": "Монтаж сборных железобетонных конструкций фундаментов", "mandatory": True},
        {"name": "Замоноличивание монтажных стыков и узлов", "mandatory": True, "note": "Можно объединить с актом на монтаж"},
        {"name": "Гидроизоляция", "mandatory": True},
    ],
    WorkType.FOUNDATION_PILE: [
        # Буронабивные
        {"name": "Бурение скважин под сваи", "mandatory": True, "conditional": "для буронабивных свай"},
        {"name": "Армирование свай", "mandatory": True, "conditional": "для буронабивных свай"},
        {"name": "Бетонирование свай", "mandatory": True, "conditional": "для буронабивных свай"},
        # Забивные / вибропогруженные
        {"name": "Изготовление металлических свай (на площадке)", "mandatory": False, "conditional": "при изготовлении на площадке"},
        {"name": "Антикоррозийная защита металлических свай", "mandatory": False, "conditional": "при изготовлении на площадке"},
        {"name": "Погружение испытательных (пробных) свай", "mandatory": True, "conditional": "для забивных/вибропогруженных"},
        {"name": "Погружение остальных свай по проекту", "mandatory": True, "conditional": "для забивных/вибропогруженных"},
        {"name": "Заполнение полости свай", "mandatory": False, "conditional": "при наличии требования"},
        {"name": "Срубка свай", "mandatory": True, "conditional": "для забивных свай"},
        {"name": "Монтаж оголовков свай", "mandatory": True, "conditional": "при наличии оголовков"},
        # Ростверк
        {"name": "Армирование ростверка", "mandatory": True, "conditional": "при наличии ростверка"},
        {"name": "Бетонирование ростверка", "mandatory": True, "conditional": "при наличии ростверка"},
    ],

    # ---- Бетонные ----
    WorkType.CONCRETE: [
        {"name": "Армирование (устройство армокаркаса)", "mandatory": True},
        {"name": "Монтаж закладных изделий и анкерных болтов", "mandatory": True},
        {"name": "Устройство опалубки", "mandatory": False, "note": "Необязательно по общим нормам (практика: оформляют)"},
        {"name": "Бетонирование", "mandatory": True},
        {"name": "Гидроизоляция", "mandatory": True},
    ],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        {"name": "Устройство подливки под базы колонн", "mandatory": True},
        {"name": "Монтаж металлоконструкций (колонны, балки, фермы, связи)", "mandatory": False, "note": "Необязательно — достаточно АООК"},
        {"name": "Антикоррозийная защита сварных соединений", "mandatory": True},
        {"name": "Подготовка поверхности МК под покраску (пескоструй, обезжиривание)", "mandatory": True},
        {"name": "Грунтовка металлоконструкций", "mandatory": True},
        {"name": "Монтаж узлов на высокопрочных болтах", "mandatory": False, "conditional": "при болтах с контролируемым натяжением"},
        {"name": "Покраска металлоконструкций", "mandatory": True},
        {"name": "Нанесение огнезащитного материала на МК", "mandatory": False, "conditional": "при наличии огнезащиты"},
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [
        # Трехслойные стены
        {"name": "Кладка внутреннего слоя с армированием сеткой", "mandatory": True, "conditional": "трехслойная стена"},
        {"name": "Устройство теплоизоляции", "mandatory": True, "conditional": "трехслойная стена"},
        {"name": "Кладка облицовочного слоя", "mandatory": True, "conditional": "трехслойная стена"},
        {"name": "Устройство гибких связей (анкеров)", "mandatory": True, "conditional": "трехслойная стена"},
        # Двухслойные / однослойные
        {"name": "Устройство стены с армированием сеткой и монтажом закладных изделий", "mandatory": True, "conditional": "двухслойная/однослойная стена"},
        # Перегородки
        {"name": "Устройство перегородок с армированием и закладными", "mandatory": True, "conditional": "перегородки"},
        # Для всех типов
        {"name": "Установка перемычек", "mandatory": True},
        {"name": "Антикоррозийная защита МК перемычек и закладных деталей", "mandatory": True},
        {"name": "Устройство монолитных поясов (армирование)", "mandatory": False, "conditional": "при наличии монолитных поясов"},
        {"name": "Устройство монолитных поясов (бетонирование)", "mandatory": False, "conditional": "при наличии монолитных поясов"},
        {"name": "Устройство деформационных / антисейсмических швов", "mandatory": False, "conditional": "при наличии"},
        {"name": "Гидропароизоляция кладки", "mandatory": False, "conditional": "при наличии"},
        # Усиление кладки
        {"name": "Монтаж металлических обойм", "mandatory": False, "conditional": "при усилении кладки"},
        {"name": "Оштукатуривание металлических обойм", "mandatory": False, "conditional": "при усилении кладки"},
        {"name": "Установка металлических тяжей", "mandatory": False, "conditional": "при усилении кладки"},
        {"name": "Армирование обоймы", "mandatory": False, "conditional": "при усилении кладки"},
        {"name": "Бетонирование ЖБ обоймы", "mandatory": False, "conditional": "при усилении кладки"},
    ],

    # ---- Отделка: полы ----
    WorkType.FINISHING_FLOORS: [
        {"name": "Подготовка грунтовых оснований под полы", "mandatory": True},
        {"name": "Устройство бетонного подстилающего слоя и выравнивающих стяжек", "mandatory": True},
        {"name": "Грунтование поверхности пола", "mandatory": True},
        {"name": "Устройство звукоизоляции пола (послойно)", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство теплоизоляции пола (послойно)", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство гидроизоляции пола", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство защитного полимерного покрытия пола", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство покрытий из рулонных и штучных полимерных материалов", "mandatory": False, "conditional": "при наличии"},
        {"name": "Укладка лаг в полах", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство наливного пола", "mandatory": False, "conditional": "при наличии"},
        {"name": "Антисептическая обработка древесины", "mandatory": False, "conditional": "при деревянных полах"},
    ],
    # ---- Отделка: стены и потолки ----
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"name": "Грунтование поверхностей стен, потолков", "mandatory": True},
        {"name": "Оштукатуривание стен, потолков", "mandatory": False, "conditional": "при штукатурных работах"},
        {"name": "Покраска стен, потолков", "mandatory": False, "conditional": "при малярных работах (скрытая — под последующую отделку)"},
        {"name": "Монтаж металлического каркаса для облицовки стен", "mandatory": True, "conditional": "при облицовке панелями/ГКЛ"},
        {"name": "Монтаж металлического каркаса для подвесного потолка", "mandatory": True, "conditional": "при подвесном потолке"},
        {"name": "Обшивка стен/перегородок гипсокартонными листами", "mandatory": True, "conditional": "при ГКЛ"},
        {"name": "Монтаж звукоизоляции стен/перегородок", "mandatory": False, "conditional": "при наличии"},
        {"name": "Проклейка швов в ГКЛ перегородках серпянкой", "mandatory": True, "conditional": "при ГКЛ"},
        {"name": "Заделка швов", "mandatory": True, "conditional": "при ГКЛ"},
    ],
    # ---- Отделка: окна и двери ----
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"name": "Крепление оконных и дверных коробок (рам)", "mandatory": True},
        {"name": "Конопатка или запенивание оконных и дверных блоков", "mandatory": True},
        {"name": "Герметизация оконных и дверных блоков", "mandatory": True},
        {"name": "Грунтование оконных и дверных откосов", "mandatory": True},
        {"name": "Штукатурка оконных и дверных откосов", "mandatory": False, "conditional": "при оштукатуривании откосов"},
        {"name": "Шпатлевание оконных и дверных откосов", "mandatory": False, "conditional": "при шпатлевании откосов"},
    ],

    # ---- Водоснабжение ----
    WorkType.WATER_SUPPLY: [
        {"name": "Монтаж трубопроводов", "mandatory": True, "note": "Можно оформлять по этажам, посистемно или на участок"},
        {"name": "Устройство проходов через стены и перекрытия (гильзы)", "mandatory": True, "note": "Обычно один акт на все системы"},
        {"name": "Антикоррозийная обработка трубопроводов", "mandatory": True, "note": "Грунтовка и покраска — разные акты"},
        {"name": "Монтаж теплоизоляции трубопроводов", "mandatory": False, "conditional": "при наличии теплоизоляции"},
    ],
    WorkType.SEWERAGE: [
        {"name": "Монтаж трубопроводов канализации", "mandatory": True},
        {"name": "Устройство проходов через стены и перекрытия (гильзы)", "mandatory": True},
        {"name": "Устройство фасадных (доборных) элементов", "mandatory": False, "conditional": "при наличии"},
        {"name": "Монтаж водосточных систем", "mandatory": False, "conditional": "при внутренних водостоках"},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        # Прокладка в траншее
        {"name": "Разработка траншеи", "mandatory": True},
        {"name": "Устройство основания под трубопроводы", "mandatory": True},
        {"name": "Укладка трубопровода в траншею", "mandatory": True},
        {"name": "Антикоррозийное покрытие труб (огрунтовка, покраска)", "mandatory": False, "conditional": "при стальных трубах"},
        {"name": "Тепловая изоляция трубопровода", "mandatory": False, "conditional": "при наличии"},
        {"name": "Обратная засыпка траншеи", "mandatory": True},
        # Устройство колодцев, камер
        {"name": "Разработка котлована под колодец", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "Устройство основания колодцев", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "Монтаж колодцев", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "Гидроизоляция колодцев/камер", "mandatory": True, "conditional": "при устройстве колодцев/камер"},
        {"name": "Герметизация мест прохода труб через стенки колодцев", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "Заделка стыков", "mandatory": True, "conditional": "при устройстве колодцев"},
    ],

    # ---- ОВиК ----
    WorkType.HEATING: [
        {"name": "Монтаж трубопроводов системы отопления", "mandatory": True, "note": "По участкам или посистемно"},
        {"name": "Обеспыливание, обезжиривание трубопроводов перед антикоррозийной покраской", "mandatory": True},
        {"name": "Огрунтовка стальных трубопроводов", "mandatory": True},
        {"name": "Покраска стальных трубопроводов", "mandatory": True},
        {"name": "Монтаж теплоизоляции", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство отверстий в стенах, плитах", "mandatory": True},
        {"name": "Устройство проходов труб через стены и перекрытия (гильзы, герметизация)", "mandatory": True},
    ],
    WorkType.VENTILATION: [
        {"name": "Монтаж воздуховодов", "mandatory": True, "note": "По этажам или посистемно"},
        {"name": "Теплоизоляция / огнезащита воздуховодов", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство отверстий в стенах, плитах", "mandatory": True},
        {"name": "Герметизация (заделка) мест проходов воздуховодов через стены и перекрытия", "mandatory": True},
        {"name": "Монтаж узлов проходов", "mandatory": False, "conditional": "при наличии"},
    ],
    WorkType.AIR_CONDITIONING: [
        {"name": "Монтаж трасс хладонопроводов в теплоизоляции", "mandatory": True},
        {"name": "Монтаж лотков", "mandatory": False, "conditional": "при наличии"},
        {"name": "Монтаж межблочного кабеля", "mandatory": True},
        {"name": "Устройство отверстий в стенах, плитах", "mandatory": True},
        {"name": "Герметизация мест проходов труб через стены и перекрытия", "mandatory": True},
        {"name": "Монтаж оборудования", "mandatory": True},
        {"name": "Монтаж узлов проходов", "mandatory": False, "conditional": "при наличии"},
    ],

    # ---- Электромонтаж внутренние ----
    WorkType.ELECTRICAL_INTERNAL: [
        {"name": "Монтаж кабеленесущих систем (лотки)", "mandatory": True, "note": "Отдельно, до акта на прокладку кабеля"},
        {"name": "Пробивка штробы под кабель", "mandatory": False, "conditional": "при скрытой прокладке"},
        {"name": "Прокладка кабеля (в траншее / штробе / на лотках / в трубах)", "mandatory": True},
        {"name": "Устройство проходов кабеля через стены и перекрытия", "mandatory": True},
        {"name": "Монтаж заземления / молниезащиты", "mandatory": False, "conditional": "при наличии"},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        {"name": "Устройство траншеи для прокладки кабеля или заземляющего устройства", "mandatory": True},
        {"name": "Устройство основания под кабель", "mandatory": True},
        {"name": "Монтаж трубопроводов / лотков", "mandatory": False, "conditional": "при наличии"},
        {"name": "Пробивка штробы под кабель", "mandatory": False, "conditional": "при необходимости"},
        {"name": "Прокладка кабеля (в траншее / штробе / на лотках / в трубах)", "mandatory": True},
        {"name": "Монтаж разделительного кирпича в траншее", "mandatory": False, "conditional": "при требовании проекта"},
        {"name": "Монтаж плит для закрытия кабеля (ПЗК)", "mandatory": False, "conditional": "при требовании проекта"},
        {"name": "Обратная засыпка траншей с послойным уплотнением / заделка штробы", "mandatory": True},
        {"name": "Монтаж заземляющего устройства / молниезащиты", "mandatory": False, "conditional": "при наличии"},
    ],

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [
        {"name": "Прокладка кабеля связи", "mandatory": True},
        {"name": "Устройство проходов через стены и перекрытия", "mandatory": True},
        {"name": "Монтаж оборудования связи", "mandatory": True},
    ],
    # ---- АКЗ и огнезащита ----
    WorkType.ANTICORROSIVE: [
        {"name": "Подготовка поверхности (абразивоструйная очистка)", "mandatory": True},
        {"name": "Нанесение антикоррозионного покрытия (грунтовка)", "mandatory": True},
        {"name": "Нанесение финишного покрытия (покраска)", "mandatory": True},
        {"name": "Нанесение огнезащитного состава", "mandatory": False, "conditional": "при наличии огнезащиты"},
        {"name": "Контроль толщины покрытия", "mandatory": True},
    ],
    # ---- ГНБ ----
    WorkType.HDD_DRILLING: [
        {"name": "Бурение пилотной скважины", "mandatory": True},
        {"name": "Расширение скважины", "mandatory": True},
        {"name": "Протаскивание трубопровода в скважину", "mandatory": True},
        {"name": "Восстановление/рекультивация участка", "mandatory": True},
        {"name": "Сварка стыков полиэтиленовых труб", "mandatory": False, "conditional": "при ПЭ трубах"},
    ],
    # ---- Пожаротушение ----
    WorkType.FIRE_EXTINGUISHING: [
        {"name": "Монтаж трубопроводов пожаротушения", "mandatory": True},
        {"name": "Монтаж спринклерных/дренчерных оросителей", "mandatory": True},
        {"name": "Монтаж насосной станции пожаротушения", "mandatory": True},
        {"name": "Устройство проходов через стены и перекрытия", "mandatory": True},
        {"name": "Огнезащита трубопроводов пожаротушения", "mandatory": False, "conditional": "при наличии"},
    ],
    # ---- Технологические трубопроводы ----
    WorkType.PROCESS_PIPELINES: [
        {"name": "Монтаж трубопроводов", "mandatory": True},
        {"name": "Сварка стыков трубопроводов", "mandatory": False, "conditional": "при сварных соединениях"},
        {"name": "Контроль сварных соединений (ВИК, УЗК, радиография)", "mandatory": False, "conditional": "при сварных соединениях I-II кат."},
        {"name": "Антикоррозионная защита трубопроводов", "mandatory": True},
        {"name": "Теплоизоляция трубопроводов", "mandatory": False, "conditional": "при наличии"},
        {"name": "Устройство проходов через стены и перекрытия", "mandatory": True},
        {"name": "Монтаж опор и подвесок трубопроводов", "mandatory": True},
    ],
    # ---- Технологическое оборудование ----
    WorkType.PROCESS_EQUIPMENT: [
        {"name": "Монтаж фундаментов под оборудование", "mandatory": True},
        {"name": "Установка технологического оборудования", "mandatory": True},
        {"name": "Центровка и выверка оборудования", "mandatory": True},
        {"name": "Подливка под оборудование", "mandatory": True},
    ],
    # ---- Резервуары ----
    WorkType.TANKS: [
        {"name": "Устройство основания под резервуар", "mandatory": True},
        {"name": "Монтаж днища резервуара", "mandatory": True},
        {"name": "Монтаж стенок резервуара", "mandatory": True},
        {"name": "Монтаж крыши резервуара", "mandatory": True},
        {"name": "Контроль сварных соединений (радиография)", "mandatory": True},
        {"name": "Вакуумное испытание днища", "mandatory": True},
        {"name": "Гидравлическое испытание резервуара", "mandatory": True},
        {"name": "Антикоррозийная защита резервуара", "mandatory": True},
    ],
    # ---- Системы автоматизации ----
    WorkType.AUTOMATION: [
        {"name": "Монтаж шкафов автоматизации", "mandatory": True},
        {"name": "Прокладка контрольных кабелей", "mandatory": True},
        {"name": "Монтаж датчиков и КИПиА", "mandatory": True},
        {"name": "Устройство проходов через стены и перекрытия", "mandatory": True},
    ],
    # ---- Пожарная сигнализация ----
    WorkType.FIRE_ALARM: [
        {"name": "Прокладка кабелей пожарной сигнализации", "mandatory": True},
        {"name": "Монтаж пожарных извещателей", "mandatory": True},
        {"name": "Монтаж оповещателей (СОУЭ)", "mandatory": False, "conditional": "при наличии СОУЭ"},
        {"name": "Монтаж приборов приёмно-контрольных (ППК)", "mandatory": True},
        {"name": "Устройство проходов через стены и перекрытия", "mandatory": True},
    ],
    # ---- Лифты ----
    WorkType.ELEVATORS: [
        {"name": "Монтаж направляющих кабины и противовеса", "mandatory": True},
        {"name": "Монтаж лебёдки и отводных блоков", "mandatory": True},
        {"name": "Монтаж кабины лифта", "mandatory": True},
        {"name": "Монтаж противовеса", "mandatory": True},
        {"name": "Монтаж дверей шахты", "mandatory": True},
        {"name": "Монтаж ограждения шахты", "mandatory": True},
        {"name": "Монтаж электрооборудования лифта", "mandatory": True},
    ],
    # ---- Тепловые сети ----
    WorkType.HEAT_PIPELINES: [
        {"name": "Разработка траншеи", "mandatory": True},
        {"name": "Устройство оснований под трубопроводы", "mandatory": True},
        {"name": "Монтаж трубопроводов теплосети", "mandatory": True},
        {"name": "Монтаж компенсаторов и неподвижных опор", "mandatory": True},
        {"name": "Антикоррозионная защита трубопроводов", "mandatory": True},
        {"name": "Тепловая изоляция трубопроводов", "mandatory": True},
        {"name": "Обратная засыпка траншеи", "mandatory": True},
        {"name": "Устройство колодцев/камер", "mandatory": False, "conditional": "при наличии камер"},
    ],
    # ---- Автомобильные дороги ----
    WorkType.ROADS: [
        {"name": "Снятие растительного слоя и планировка", "mandatory": True},
        {"name": "Устройство земляного полотна", "mandatory": True},
        {"name": "Устройство подстилающего слоя из песка", "mandatory": True},
        {"name": "Устройство основания из щебня", "mandatory": True},
        {"name": "Розлив битума (подгрунтовка)", "mandatory": True},
        {"name": "Устройство асфальтобетонного покрытия (нижний слой)", "mandatory": True},
        {"name": "Устройство асфальтобетонного покрытия (верхний слой)", "mandatory": True},
        {"name": "Установка бортового камня", "mandatory": True},
        {"name": "Нанесение дорожной разметки", "mandatory": False, "conditional": "при наличии в проекте"},
    ],
    # ---- Демонтажные работы ----
    WorkType.DEMOLITION: [
        {"name": "Демонтаж строительных конструкций", "mandatory": True},
        {"name": "Демонтаж инженерных систем", "mandatory": True},
        {"name": "Демонтаж фундаментов", "mandatory": False, "conditional": "при демонтаже фундаментов"},
        {"name": "Демонтаж оборудования", "mandatory": False, "conditional": "при демонтаже оборудования"},
    ],
    # ---- Паровая котельная ----
    WorkType.STEAM_BOILER: [
        {"name": "Монтаж котлов", "mandatory": True},
        {"name": "Монтаж трубопроводов пара и конденсата", "mandatory": True},
        {"name": "Сварка трубопроводов пара", "mandatory": True},
        {"name": "Контроль сварных соединений (ВИК, УЗК)", "mandatory": True},
        {"name": "Монтаж дымовой трубы", "mandatory": True},
        {"name": "Монтаж вспомогательного оборудования", "mandatory": True},
        {"name": "Теплоизоляция котлов и трубопроводов", "mandatory": True},
        {"name": "Гидравлическое испытание котлов", "mandatory": True},
    ],
}


# =============================================================================
# АООК (Акты освидетельствования ответственных конструкций)
# =============================================================================

WORK_RESPONSIBLE_ACTS: Dict[str, List[Dict[str, Any]]] = {
    # ---- Земляные работы ----
    WorkType.EARTHWORK_EXCAVATION: [],  # АООК не предусмотрен
    WorkType.EARTHWORK_BACKFILL: [],     # АООК не предусмотрен

    # ---- Фундаменты ----
    WorkType.FOUNDATION_MONOLITHIC: [
        {"name": "АООК на фундамент", "mandatory": True, "note": "Составляется после набора бетоном необходимой прочности, с приложением протокола"},
    ],
    WorkType.FOUNDATION_PRECAST: [
        {"name": "АООК на фундамент", "mandatory": True, "note": "После замоноличивания стыков и набора прочности"},
    ],
    WorkType.FOUNDATION_PILE: [
        {"name": "АООК на свайный фундамент", "mandatory": True, "note": "На весь фундамент или по захваткам"},
    ],

    # ---- Бетонные работы ----
    WorkType.CONCRETE: [
        {"name": "АООК на конструкции", "mandatory": True, "note": "После набора проектной прочности бетона"},
    ],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        {"name": "АООК на металлоконструкции", "mandatory": True, "note": "Основной документ для МК. АОСР на монтаж — необязателен. Можно на весь каркас или по захваткам"},
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [
        {"name": "АООК на несущий каркас", "mandatory": True, "note": "Ненесущие стены — только после АООК на каркас (п. 9.4.1 СП 70)"},
    ],

    # ---- Отделочные работы ----
    WorkType.FINISHING_FLOORS: [],           # АООК не предусмотрен
    WorkType.FINISHING_WALLS_CEILINGS: [],   # АООК не предусмотрен
    WorkType.FINISHING_WINDOWS_DOORS: [],    # АООК не предусмотрен

    # ---- Водоснабжение и водоотведение ----
    WorkType.WATER_SUPPLY: [],     # АООК не предусмотрен; приёмка — актами испытаний
    WorkType.SEWERAGE: [],         # АООК не предусмотрен
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"name": "АОУСИТО (акт освидетельствования участков сетей ИТО)", "mandatory": True, "note": "На участки сетей инженерно-технического обеспечения"},
    ],

    # ---- ОВиК ----
    WorkType.HEATING: [],           # АООК не предусмотрен; приёмка — актами испытаний
    WorkType.VENTILATION: [],       # АООК не предусмотрен
    WorkType.AIR_CONDITIONING: [],  # АООК не предусмотрен

    # ---- Электромонтаж ----
    WorkType.ELECTRICAL_INTERNAL: [],   # АООК не предусмотрен; приёмка — актами готовности и ПНР
    WorkType.ELECTRICAL_EXTERNAL: [],   # АООК не предусмотрен

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [],  # АООК не предусмотрен
    # ---- Новые виды работ ----
    WorkType.ANTICORROSIVE: [],
    WorkType.HDD_DRILLING: [],
    WorkType.FIRE_EXTINGUISHING: [],
    WorkType.PROCESS_PIPELINES: [
        {"name": "АООК на участок трубопровода", "mandatory": True, "note": "На участки трубопроводов I и II категории (ГОСТ 32569-2013)"},
    ],
    WorkType.PROCESS_EQUIPMENT: [
        {"name": "АООК на технологическое оборудование", "mandatory": True, "note": "После монтажа, центровки и подливки"},
    ],
    WorkType.TANKS: [
        {"name": "АООК на резервуар", "mandatory": True, "note": "После гидроиспытаний и контроля сварных соединений"},
    ],
    WorkType.AUTOMATION: [],
    WorkType.FIRE_ALARM: [],
    WorkType.ELEVATORS: [
        {"name": "АООК на лифтовую установку", "mandatory": True, "note": "После полного монтажа и декларирования соответствия ТР ТС 011/2011"},
    ],
    WorkType.HEAT_PIPELINES: [
        {"name": "АОУСИТО (акт освидетельствования участков сетей ИТО)", "mandatory": True, "note": "На участки тепловых сетей"},
    ],
    WorkType.ROADS: [
        {"name": "АООК на конструктивные слои дорожной одежды", "mandatory": True, "note": "На все конструктивные слои (основание, покрытие)"},
    ],
    WorkType.DEMOLITION: [],
    WorkType.STEAM_BOILER: [
        {"name": "АООК на паровую котельную", "mandatory": True, "note": "После гидроиспытаний и комплексного опробования"},
    ],
}


# =============================================================================
# Акты приёмки, испытаний и другие акты (не АОСР/АООК)
# =============================================================================

WORK_ACCEPTANCE_ACTS: Dict[str, List[Dict[str, Any]]] = {
    WorkType.EARTHWORK_EXCAVATION: [
        {"name": "Акт приёмки оснований", "mandatory": True, "note": "Составляется при участии геолога. Форма свободная или на основе АОСР (п. 11.13 СП 45)"},
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        {"name": "Акт приёмки оснований", "mandatory": True, "conditional": "при наличии оснований под последующие конструкции", "note": "Форма свободная или на основе АОСР"},
    ],
    WorkType.FOUNDATION_MONOLITHIC: [
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True},
    ],
    WorkType.FOUNDATION_PRECAST: [
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True},
    ],
    WorkType.FOUNDATION_PILE: [
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True},
        {"name": "Сводная ведомость забитых свай", "mandatory": True},
        {"name": "Акт освидетельствования и приёмки скважины сваи", "mandatory": True, "conditional": "для буронабивных"},
        {"name": "Акт освидетельствования и приёмки сваи", "mandatory": True},
    ],
    WorkType.CONCRETE: [
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True, "conditional": "при отсутствии разбивочного акта на предыдущих этапах"},
    ],
    WorkType.METAL_STRUCTURES: [
        {"name": "Акт разбивки осей ОКС на местности", "mandatory": True, "conditional": "при отсутствии разбивочного акта на предыдущих этапах"},
        {"name": "Акт приёмки металлоконструкций каркаса", "mandatory": False, "note": "Если не оформлен АООК — можно оформить акт приёмки свободной формы (п. 8.7 СП 543)"},
    ],
    WorkType.MASONRY: [
        {"name": "Акт приёмки выполненных работ на кладку", "mandatory": False, "note": "Форма свободная, согласованная с участниками (п. 8.7 СП 543). Применяется для ненесущих стен и перегородок, где АООК не требуется"},
    ],
    WorkType.FINISHING_FLOORS: [
        {"name": "Акт приёмки выполненных работ / акт приёмки готовых поверхностей", "mandatory": True, "note": "На финишные покрытия (плитка, рулонные, паркет, ламинат). Форма свободная, согласованная с участниками (п. 8.7 СП 543)"},
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"name": "Акт приёмки готовых поверхностей", "mandatory": True, "note": "На финишные покрытия. Форма свободная (п. 8.7 СП 543)"},
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"name": "Акт освидетельствования выполненных работ на монтаж оконных блоков, витражей, дверей, ворот, подоконников", "mandatory": True, "note": "Форма не регламентирована, согласовывается с участниками"},
    ],
    WorkType.WATER_SUPPLY: [
        {"name": "Акт гидростатического или манометрического испытания на герметичность", "mandatory": True, "note": "Опрессовка ДО монтажа теплоизоляции. Давление 1.5 рабочего, ≥0.2 МПа, 10 мин (п. 7.2.2 СП 73)"},
        {"name": "Акт промывки (продувки) системы", "mandatory": True},
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
        {"name": "Акт приёмки внутренних систем горячего и холодного водоснабжения", "mandatory": True},
    ],
    WorkType.SEWERAGE: [
        {"name": "Акт монтажа с приложением ведомости смонтированного оборудования", "mandatory": True, "note": "На ванны, умывальники, сан. приборы"},
        {"name": "Акт о проведении испытания систем канализации и водостоков", "mandatory": True, "note": "Пролив водой, расход ≥75% расчетного"},
        {"name": "Акт приёмки системы и выпусков внутренней канализации", "mandatory": True},
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
        {"name": "Акт приёмки системы и выпусков водостока здания", "mandatory": False, "conditional": "при внутренних водостоках"},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"name": "Акт разбивки осей", "mandatory": True},
        {"name": "Акт приёмочного гидравлического/пневматического испытания безнапорного трубопровода на герметичность", "mandatory": True},
        {"name": "Акт приёмочного гидравлического/пневматического испытания напорного трубопровода на прочность и герметичность", "mandatory": True},
        {"name": "Акт промывки и дезинфекции (хозяйственно-питьевой водопровод)", "mandatory": False, "conditional": "для хозяйственно-питьевого водоснабжения"},
        {"name": "Акт приёмочного испытания ёмкостного сооружения на водонепроницаемость", "mandatory": False, "conditional": "при наличии ёмкостей"},
        {"name": "Акт приёмки наружного водопровода/канализации", "mandatory": True},
        {"name": "Акт ВИК сварных швов (100% длины)", "mandatory": False, "conditional": "при стальном трубопроводе"},
        {"name": "Заключение (протокол) по НК сварных швов", "mandatory": False, "conditional": "при стальном трубопроводе"},
    ],
    WorkType.HEATING: [
        {"name": "Акт гидростатического или манометрического испытания на герметичность", "mandatory": True, "note": "После промывки, ДО теплоизоляции. Давление 1.5 рабочего, ≥0.2 МПа, ≥5 мин, падение ≤0.02 МПа"},
        {"name": "Акт промывки (продувки) системы", "mandatory": True},
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
        {"name": "Акт приёмки внутренней системы отопления", "mandatory": True},
    ],
    WorkType.VENTILATION: [
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
        {"name": "Акт передачи систем для пусконаладочных работ", "mandatory": True},
        {"name": "Акт об окончании ПНР", "mandatory": True},
        {"name": "Акт комплексного опробования систем пожарной безопасности", "mandatory": False, "conditional": "для систем противодымной вентиляции"},
        {"name": "Акт приёмки оборудования после комплексного опробования", "mandatory": True},
        {"name": "Акт приёмки систем приточно-вытяжной вентиляции", "mandatory": True},
    ],
    WorkType.AIR_CONDITIONING: [
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
        {"name": "Акт гидростатического или манометрического испытания на герметичность", "mandatory": True},
        {"name": "Акт об окончании ПНР", "mandatory": True},
        {"name": "Акт приёмки системы кондиционирования воздуха", "mandatory": True},
    ],
    WorkType.ELECTRICAL_INTERNAL: [
        {"name": "Акт готовности строительной части помещений к э/м работам", "mandatory": True, "note": "До начала работ"},
        {"name": "Акт технической готовности электромонтажных работ", "mandatory": True},
        {"name": "Акт проверки осветительной сети на правильность зажигания", "mandatory": True},
        {"name": "Акт проверки осветительной сети на функционирование автоматов", "mandatory": True},
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт передачи оборудования для ПНР", "mandatory": True},
        {"name": "Акт сдачи-приёмки ПНР", "mandatory": True},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        {"name": "Акт технической готовности э/м работ", "mandatory": True},
        {"name": "Акт осмотра канализации из труб перед закрытием", "mandatory": True, "note": "При устройстве электропроводок (И 1.13-07 п. 5.1)"},
        {"name": "Акт осмотра кабельной канализации в траншее и каналах перед закрытием", "mandatory": True, "note": "При устройстве кабельных линий (И 1.13-07 п. 6.1)"},
        {"name": "Акт приёмки траншей, каналов, тоннелей и блоков под монтаж кабелей", "mandatory": True},
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт передачи оборудования для ПНР", "mandatory": True},
        {"name": "Акт сдачи-приёмки ПНР", "mandatory": True},
        {"name": "Акт о приёмке и монтаже силового трансформатора", "mandatory": False, "conditional": "при наличии"},
    ],
    WorkType.COMMUNICATION_NETWORKS: [
        {"name": "Акт приёмки систем связи", "mandatory": True},
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
    ],
    # ---- Новые виды работ ----
    WorkType.ANTICORROSIVE: [
        {"name": "Акт приёмки выполненных антикоррозионных работ", "mandatory": True, "note": "Форма свободная, на основе АОСР/АООК"},
        {"name": "Протокол измерения толщины покрытия", "mandatory": True},
        {"name": "Протокол адгезии покрытия", "mandatory": True},
    ],
    WorkType.HDD_DRILLING: [
        {"name": "Акт приёмки пилотной скважины", "mandatory": True},
        {"name": "Акт приёмки расширенной скважины", "mandatory": True},
        {"name": "Акт приёмки протаскивания трубопровода в скважину", "mandatory": True},
    ],
    WorkType.FIRE_EXTINGUISHING: [
        {"name": "Акт гидростатического испытания трубопроводов пожаротушения", "mandatory": True},
        {"name": "Акт индивидуального испытания насосной станции", "mandatory": True},
        {"name": "Акт комплексного опробования системы пожаротушения", "mandatory": True},
        {"name": "Акт приёмки автоматической системы пожаротушения в эксплуатацию", "mandatory": True},
    ],
    WorkType.PROCESS_PIPELINES: [
        {"name": "Акт гидравлического испытания трубопровода на прочность и герметичность", "mandatory": True},
        {"name": "Акт ВИК сварных швов", "mandatory": False, "conditional": "при сварных соединениях"},
        {"name": "Заключение по неразрушающему контролю (УЗК, радиография)", "mandatory": False, "conditional": "для трубопроводов I-II категории"},
        {"name": "Акт продувки/промывки трубопровода", "mandatory": True},
        {"name": "Акт приёмки технологического трубопровода", "mandatory": True},
    ],
    WorkType.PROCESS_EQUIPMENT: [
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт приёмки фундаментов под монтаж оборудования", "mandatory": True},
        {"name": "Акт индивидуального испытания оборудования", "mandatory": True},
    ],
    WorkType.TANKS: [
        {"name": "Акт приёмки основания под резервуар", "mandatory": True},
        {"name": "Заключение по радиографическому контролю сварных швов", "mandatory": True},
        {"name": "Акт вакуумного испытания днища", "mandatory": True},
        {"name": "Акт гидравлического испытания резервуара", "mandatory": True},
        {"name": "Акт испытания крыши резервуара", "mandatory": True},
        {"name": "Акт приёмки резервуара в эксплуатацию", "mandatory": True},
    ],
    WorkType.AUTOMATION: [
        {"name": "Акт готовности строительной части к монтажу систем автоматизации", "mandatory": True},
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт передачи систем для ПНР", "mandatory": True},
        {"name": "Акт об окончании ПНР", "mandatory": True},
        {"name": "Акт приёмки системы автоматизации", "mandatory": True},
    ],
    WorkType.FIRE_ALARM: [
        {"name": "Акт входного контроля оборудования ПС", "mandatory": True},
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт измерения сопротивления изоляции электропроводок", "mandatory": True},
        {"name": "Акт окончания монтажных работ", "mandatory": True},
        {"name": "Акт проведения ПНР", "mandatory": True},
        {"name": "Акт комплексного опробования системы пожарной сигнализации", "mandatory": True},
        {"name": "Акт приёмки системы ПС в эксплуатацию", "mandatory": True},
    ],
    WorkType.ELEVATORS: [
        {"name": "Акт готовности строительной части шахты лифта", "mandatory": True},
        {"name": "Акт приёмки-передачи лифтового оборудования в монтаж", "mandatory": True},
        {"name": "Акт полного технического освидетельствования лифта", "mandatory": True},
        {"name": "Декларация соответствия ТР ТС 011/2011", "mandatory": True},
        {"name": "Акт приёмки лифта в эксплуатацию", "mandatory": True},
    ],
    WorkType.HEAT_PIPELINES: [
        {"name": "Акт разбивки осей трассы", "mandatory": True},
        {"name": "Акт гидравлического испытания трубопровода на прочность и герметичность", "mandatory": True},
        {"name": "Акт ВИК сварных швов", "mandatory": False, "conditional": "при сварных соединениях"},
        {"name": "Акт тепловых испытаний тепловой сети", "mandatory": True},
        {"name": "Акт приёмки тепловой сети в эксплуатацию", "mandatory": True},
    ],
    WorkType.ROADS: [
        {"name": "Акт разбивки осей дороги", "mandatory": True},
        {"name": "Акт освидетельствования земляного полотна", "mandatory": True},
        {"name": "Акт освидетельствования подстилающего слоя", "mandatory": True},
        {"name": "Акт освидетельствования основания (щебень)", "mandatory": True},
        {"name": "Протокол лабораторных испытаний кернов (вырубок)", "mandatory": True},
        {"name": "Акт освидетельствования покрытия (нижний слой)", "mandatory": True},
        {"name": "Акт освидетельствования покрытия (верхний слой)", "mandatory": True},
        {"name": "Акт приёмки выполненных дорожных работ", "mandatory": True},
    ],
    WorkType.DEMOLITION: [
        {"name": "Акт обследования строительных конструкций перед демонтажем", "mandatory": True},
        {"name": "Акт завершения демонтажных работ", "mandatory": True},
    ],
    WorkType.STEAM_BOILER: [
        {"name": "Акт приёмки-передачи оборудования в монтаж", "mandatory": True},
        {"name": "Акт ВИК сварных швов котла", "mandatory": True},
        {"name": "Заключение по неразрушающему контролю сварных швов", "mandatory": True},
        {"name": "Акт гидравлического испытания котла", "mandatory": True},
        {"name": "Акт парового опробования котла", "mandatory": True},
        {"name": "Акт комплексного опробования котельной", "mandatory": True},
        {"name": "Акт приёмки паровой котельной в эксплуатацию", "mandatory": True},
    ],
}


# =============================================================================
# ИСПОЛНИТЕЛЬНЫЕ СХЕМЫ / ЧЕРТЕЖИ
# =============================================================================

WORK_EXECUTIVE_SCHEMES: Dict[str, List[Dict[str, Any]]] = {
    WorkType.EARTHWORK_EXCAVATION: [
        {"name": "ИГС разбивки осей ОКС на местности", "mandatory": True},
        {"name": "ИС на устройство дренажа", "mandatory": False, "conditional": "при наличии дренажа"},
        {"name": "ИГС на устройство вертикальной планировки", "mandatory": False, "conditional": "при вертикальной планировке"},
        {"name": "ИГС вертикальных отметок и габаритов выемки (котлована, траншеи)", "mandatory": True},
        {"name": "ИС на крепление стенок выемки", "mandatory": False, "conditional": "при креплении стенок"},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        {"name": "ИГС на устройство обратной засыпки", "mandatory": True},
        {"name": "ИГС на возведение земляного полотна", "mandatory": False, "conditional": "при устройстве земляного полотна"},
    ],
    WorkType.FOUNDATION_MONOLITHIC: [
        {"name": "ИГС разбивки осей ОКС", "mandatory": True},
        {"name": "ИГС на котлован", "mandatory": True},
        {"name": "ИГС на устройство бетонной подготовки", "mandatory": True},
        {"name": "ИС на армирование фундаментов", "mandatory": False, "note": "Необязательно по общим нормам"},
        {"name": "ИГС фундаментов", "mandatory": True},
        {"name": "ИС анкерных болтов, закладных деталей, технологических отверстий", "mandatory": True},
    ],
    WorkType.FOUNDATION_PRECAST: [
        {"name": "ИГС разбивки осей ОКС", "mandatory": True},
        {"name": "ИГС на котлован", "mandatory": True},
        {"name": "ИГС на устройство бетонной подготовки", "mandatory": True},
        {"name": "ИГС фундаментов", "mandatory": True},
    ],
    WorkType.FOUNDATION_PILE: [
        {"name": "ИГС разбивки осей ОКС", "mandatory": True},
        {"name": "ИГС свайного основания", "mandatory": True},
        {"name": "ИГС планово-высотного положения свай до срубки", "mandatory": True},
        {"name": "ИГС планово-высотного положения свай после срубки", "mandatory": True},
        {"name": "ИГС на ростверк", "mandatory": True, "conditional": "при наличии ростверка"},
    ],
    WorkType.CONCRETE: [
        {"name": "ИГС разбивки осей ОКС", "mandatory": True},
        {"name": "ИС на армирование", "mandatory": False, "note": "Необязательно"},
        {"name": "ИС на опалубку", "mandatory": False, "note": "Необязательно"},
        {"name": "ИС на бетонирование конструкций", "mandatory": True},
        {"name": "ИС анкерных болтов, закладных деталей, технологических отверстий", "mandatory": True},
        {"name": "Поясная (поэтажная) ИГС планово-высотного положения колонн каркасных зданий", "mandatory": True, "conditional": "для каркасных зданий"},
        {"name": "Поэтажные ИГС несущих стен, пилонов, диафрагм жесткости", "mandatory": True, "conditional": "для многоэтажных зданий"},
        {"name": "Поэтажные ИГС монолитных плит перекрытия (с термовкладышами, тех. отверстиями)", "mandatory": True, "conditional": "при наличии в РД"},
        {"name": "Высотная ИГС площадок опирания ригелей, панелей, перекрытий и покрытий", "mandatory": True, "conditional": "при наличии"},
        {"name": "ИГС отклонений от вертикали/проектного наклона (скользящая опалубка, лифтовые шахты)", "mandatory": True, "conditional": "при скользящей опалубке"},
    ],
    WorkType.METAL_STRUCTURES: [
        {"name": "ИГС разбивки осей ОКС", "mandatory": True},
        {"name": "Схема колонн: отклонения отметок опорных поверхностей", "mandatory": True},
        {"name": "Схема колонн: смещение осей колонн относительно разбивочных", "mandatory": True},
        {"name": "Схема колонн: отклонение по вертикали в верхнем и нижнем сечениях", "mandatory": True},
        {"name": "Схема ферм/ригелей/балок: отметки опорных узлов, смещение с осей", "mandatory": True},
        {"name": "Схема ферм/ригелей/балок: расстояния между осями по верхним поясам", "mandatory": True},
        {"name": "Схема подкрановых балок: смещения от разбивочных осей", "mandatory": False, "conditional": "при наличии"},
        {"name": "Схема подкрановых балок: смещение опорного ребра", "mandatory": False, "conditional": "при наличии"},
        {"name": "Схема монорельсов: разность отметок ездового пояса", "mandatory": False, "conditional": "при наличии"},
        {"name": "Схема сварных соединений", "mandatory": False, "note": "Необязательно, по требованию"},
    ],
    WorkType.MASONRY: [
        {"name": "Поэтажная ИГС кладки наружных и внутренних несущих стен (смещение осей)", "mandatory": True},
        {"name": "ИГС отклонения поверхностей и углов кладки от вертикали", "mandatory": True},
        {"name": "Поэтажная ИГС ненесущих стен / перегородок", "mandatory": True},
        {"name": "ИГС на устройство монолитных поясов", "mandatory": False, "conditional": "при наличии"},
        {"name": "ИС на перемычки", "mandatory": False, "note": "Необязательно"},
        {"name": "ИС на деформационные / антисейсмические швы", "mandatory": False, "note": "Необязательно"},
        {"name": "ИС на устройство обоймы", "mandatory": False, "conditional": "при усилении кладки"},
    ],
    WorkType.FINISHING_FLOORS: [
        {"name": "ИС на устройство грунтового основания под полы", "mandatory": True},
        {"name": "ИС на устройство наливного пола (с нивелировкой)", "mandatory": False, "conditional": "при наливных полах"},
        {"name": "ИС на устройство покрытий полов послойно", "mandatory": True},
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"name": "ИС по видам работ (штукатурка, шпатлевка, окраска, плитка, подвесные потолки и др.)", "mandatory": True},
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"name": "ИС на монтаж оконных блоков, подоконников, витражей, дверей", "mandatory": True},
    ],
    WorkType.WATER_SUPPLY: [
        {"name": "Комплект исполнительных чертежей (планы, аксонометрии)", "mandatory": True, "note": "По СП 543 отдельные ИС НЕ требуются — только комплект чертежей. Но при акте на часть системы — приложить схему участка"},
    ],
    WorkType.SEWERAGE: [
        {"name": "Комплект исполнительных чертежей (планы, аксонометрии)", "mandatory": True, "note": "Аналогично водоснабжению"},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"name": "ИГС на траншею", "mandatory": True},
        {"name": "ИС на устройство основания", "mandatory": True},
        {"name": "ИС монтажа трубопровода", "mandatory": True},
        {"name": "Схема продольного профиля уложенного трубопровода", "mandatory": True, "note": "Обязательно! Оформляет геодезист"},
        {"name": "ИГС на котлован (для колодцев)", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "ИС на основание (для колодцев)", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "ИС на монтаж колодца", "mandatory": True, "conditional": "при устройстве колодцев"},
        {"name": "ИГС монолитных конструкций", "mandatory": True, "conditional": "при монолитных камерах — см. бетонные работы"},
    ],
    WorkType.HEATING: [
        {"name": "Комплект исполнительных чертежей (поэтажные схемы + аксонометрии)", "mandatory": True},
    ],
    WorkType.VENTILATION: [
        {"name": "Комплект исполнительных чертежей (поэтажные схемы + аксонометрии)", "mandatory": True},
    ],
    WorkType.AIR_CONDITIONING: [
        {"name": "Комплект исполнительных чертежей (поэтажные схемы + аксонометрии)", "mandatory": True},
    ],
    WorkType.ELECTRICAL_INTERNAL: [
        {"name": "Комплект рабочих чертежей с надписями о соответствии", "mandatory": True, "note": "Привести в соответствие с фактом, показать привязки, добавить условные обозначения"},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        {"name": "ИГС разбивки и закрепления оси кабельной линии", "mandatory": True},
        {"name": "ИГС разбивки и закрепления оси воздушной линии", "mandatory": False, "conditional": "при воздушных линиях"},
        {"name": "ИГС разбивки опор освещения", "mandatory": False, "conditional": "при наружном освещении"},
        {"name": "ИГС траншеи под кабель", "mandatory": True},
        {"name": "ИС кабельной канализации", "mandatory": False, "conditional": "при наличии"},
        {"name": "ИС и продольные профили подземных сетей ИТО", "mandatory": True},
        {"name": "ИГС наземных и надземных сетей ИТО", "mandatory": False, "conditional": "при наличии"},
        {"name": "ИГС подземных сетей и сооружений", "mandatory": True},
        {"name": "ИГС сооружений защиты от электрокоррозии", "mandatory": False, "conditional": "при наличии"},
    ],
    WorkType.COMMUNICATION_NETWORKS: [
        {"name": "Комплект исполнительных чертежей", "mandatory": True},
    ],
}


# =============================================================================
# СЕРТИФИКАТЫ, ПРОТОКОЛЫ, ПАСПОРТА
# =============================================================================

WORK_CERTIFICATES: Dict[str, List[Dict[str, Any]]] = {
    WorkType.EARTHWORK_EXCAVATION: [
        {"name": "Протокол испытания грунтов", "mandatory": True},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        {"name": "Протокол испытания вынутого грунта на пригодность к обратной засыпке", "mandatory": True, "note": "При использовании вынутого грунта"},
        {"name": "Протокол испытаний уплотнения грунта", "mandatory": True, "note": "С приложением схемы с точками отбора проб"},
        {"name": "Документы на песок, щебень (при обратной засыпке инертными)", "mandatory": False, "conditional": "при засыпке песком/щебнем"},
    ],
    WorkType.FOUNDATION_MONOLITHIC: [
        {"name": "Протокол испытания бетона на прочность в конструкциях (промежуточный и проектный возраст)", "mandatory": True},
        {"name": "Протокол испытания контрольных образцов бетона на прочность", "mandatory": True},
        {"name": "Протокол испытания бетона на морозостойкость/водонепроницаемость/истираемость", "mandatory": False, "conditional": "если установлено проектом"},
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.FOUNDATION_PRECAST: [
        {"name": "Документы оценки соответствия, паспорта на ЖБК", "mandatory": True},
    ],
    WorkType.FOUNDATION_PILE: [
        {"name": "Протокол испытания контрольных образцов бетона на прочность", "mandatory": True, "conditional": "для буронабивных свай и ростверков"},
        {"name": "Протокол испытания бетона на прочность в конструкциях", "mandatory": True, "conditional": "для буронабивных свай и ростверков"},
        {"name": "Документы оценки соответствия, паспорта", "mandatory": True},
    ],
    WorkType.CONCRETE: [
        {"name": "Протокол испытания бетона на прочность в конструкциях (промежуточный и проектный возраст)", "mandatory": True},
        {"name": "Протокол испытания контрольных образцов бетона на прочность", "mandatory": True},
        {"name": "Протокол испытания бетона на морозостойкость/водонепроницаемость/истираемость", "mandatory": False, "conditional": "если установлено проектом"},
        {"name": "Протокол испытаний на растяжение механических соединений", "mandatory": False, "conditional": "при механических соединениях арматуры"},
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.METAL_STRUCTURES: [
        {"name": "Акт ВИК (визуальный и измерительный контроль) сварных швов", "mandatory": True, "note": "На 100% длины сварных швов"},
        {"name": "Заключение (протокол) по НК (УЗК, радиография, капиллярный, магнитопорошковый)", "mandatory": True},
        {"name": "Акт приёмки защитного покрытия", "mandatory": True},
        {"name": "Протокол испытаний огнезащитного покрытия", "mandatory": False, "conditional": "при огнезащите"},
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.MASONRY: [
        {"name": "Протокол проверки фактической прочности раствора в кладке", "mandatory": False, "conditional": "только при зимней кладке (п. 9.16.2 СП 70.13330.2012)", "note": "При перегрузках нижележащих конструкций в период оттаивания"},
        {"name": "Документы оценки соответствия, паспорта", "mandatory": True},
    ],
    WorkType.FINISHING_FLOORS: [
        {"name": "Документы, подтверждающие качество материалов (протоколы, паспорта, сертификаты/декларации, СГР)", "mandatory": True},
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"name": "Документы, подтверждающие качество материалов", "mandatory": True},
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"name": "Документы, подтверждающие качество материалов", "mandatory": True},
    ],
    WorkType.WATER_SUPPLY: [
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.SEWERAGE: [
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"name": "Протокол испытаний уплотнения грунта (основание и обратная засыпка)", "mandatory": True},
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.HEATING: [
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.VENTILATION: [
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.AIR_CONDITIONING: [
        {"name": "Документы оценки соответствия, технические паспорта", "mandatory": True},
    ],
    WorkType.ELECTRICAL_INTERNAL: [
        {"name": "Протокол измерения сопротивления изоляции", "mandatory": True},
        {"name": "Протокол измерения сопротивления цепи «фаза-нуль»", "mandatory": True},
        {"name": "Протокол проверки работоспособности автоматических выключателей", "mandatory": True},
        {"name": "Протокол замера сопротивления заземляющего устройства", "mandatory": False, "conditional": "при наличии заземления"},
        {"name": "Протокол проверки цепи между заземлителями и заземляемыми элементами", "mandatory": False, "conditional": "при наличии заземления"},
        {"name": "Протокол измерения сопротивления грунта", "mandatory": False, "conditional": "при необходимости"},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        {"name": "Протокол измерения сопротивления изоляции", "mandatory": True},
        {"name": "Протокол измерения сопротивления цепи «фаза-нуль»", "mandatory": True},
        {"name": "Протокол проверки работоспособности автоматических выключателей", "mandatory": True},
        {"name": "Протокол замера сопротивления заземляющего устройства", "mandatory": True},
        {"name": "Протокол проверки цепи между заземлителями и заземляемыми элементами", "mandatory": True},
        {"name": "Протокол измерения сопротивления грунта", "mandatory": True},
        {"name": "Протокол осмотра и проверки сопротивления изоляции кабелей на барабане перед прокладкой", "mandatory": False, "conditional": "для кабельных линий 1-220 кВ (на практике — на все)", "note": "И 1.13-07 п. 6.1 формально для 1-220 кВ"},
        {"name": "Протокол прогрева кабелей при низких температурах", "mandatory": False, "conditional": "при прокладке в зимних условиях"},
    ],
    WorkType.COMMUNICATION_NETWORKS: [
        {"name": "Протоколы испытаний систем связи", "mandatory": True},
        {"name": "Документы оценки соответствия", "mandatory": True},
    ],
}


# =============================================================================
# ДОПОЛНИТЕЛЬНЫЕ ДОКУМЕНТЫ (ведомости, паспорта систем и т.д.)
# =============================================================================

WORK_ADDITIONAL_DOCS: Dict[str, List[Dict[str, Any]]] = {
    # ---- Земляные работы ----
    WorkType.EARTHWORK_EXCAVATION: [
        {"name": "Ведомость объёмов земляных работ", "mandatory": False, "note": "Форма свободная. Помогает зафиксировать объёмы для актов"},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        {"name": "Ведомость объёмов земляных работ", "mandatory": False, "note": "Форма свободная"},
    ],

    # ---- Фундаменты ----
    WorkType.FOUNDATION_MONOLITHIC: [],
    WorkType.FOUNDATION_PRECAST: [],
    WorkType.FOUNDATION_PILE: [],

    # ---- Бетонные работы ----
    WorkType.CONCRETE: [],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        {"name": "Ведомость монтажных сварных швов", "mandatory": False, "note": "Форма свободная. Рекомендуется при большом объёме сварки"},
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [],

    # ---- Отделочные работы ----
    WorkType.FINISHING_FLOORS: [
        {"name": "Ведомость объёмов работ", "mandatory": True, "note": "По СП 543.1325800.2024"},
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"name": "Ведомость объёмов работ", "mandatory": True, "note": "По СП 543.1325800.2024"},
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"name": "Ведомость объёмов работ", "mandatory": False, "note": "Форма свободная. По требованию заказчика"},
    ],

    # ---- Водоснабжение и водоотведение ----
    WorkType.WATER_SUPPLY: [
        {"name": "Ведомость смонтированных материалов, изделий и оборудования", "mandatory": False, "note": "Форма свободная. Помогает зафиксировать работы без АОСР"},
    ],
    WorkType.SEWERAGE: [
        {"name": "Ведомость смонтированных материалов, изделий и оборудования", "mandatory": False, "note": "Форма свободная"},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"name": "Ведомость смонтированных материалов, изделий и оборудования", "mandatory": False, "note": "Форма свободная"},
    ],

    # ---- ОВиК ----
    WorkType.HEATING: [
        {"name": "Ведомость смонтированных материалов, изделий и оборудования", "mandatory": False, "note": "Форма свободная"},
    ],
    WorkType.VENTILATION: [
        {"name": "Паспорт системы вентиляции", "mandatory": True, "note": "С результатами аэродинамических испытаний. К паспорту — схема с точками замеров"},
        {"name": "Технический отчет по испытаниям систем вентиляции", "mandatory": True},
        {"name": "Протокол испытания огнезащиты", "mandatory": False, "conditional": "по требованию"},
        {"name": "Ведомость смонтированных материалов", "mandatory": False, "note": "Форма свободная"},
    ],
    WorkType.AIR_CONDITIONING: [
        {"name": "Паспорт системы вентиляции (кондиционирования)", "mandatory": True},
        {"name": "Ведомость смонтированных материалов", "mandatory": False, "note": "Форма свободная"},
    ],

    # ---- Электромонтаж ----
    WorkType.ELECTRICAL_INTERNAL: [
        {"name": "Ведомость изменений и отступлений от проекта", "mandatory": True, "note": "Приложение 1 к акту тех. готовности"},
        {"name": "Ведомость технической документации", "mandatory": True, "note": "Приложение 2"},
        {"name": "Ведомость э/м недоделок, не препятствующих комплексному опробованию", "mandatory": True, "note": "Приложение 3"},
        {"name": "Ведомость смонтированного электрооборудования", "mandatory": True, "note": "Приложение 4. Только оборудование, не все материалы"},
        {"name": "Паспорт заземляющего устройства", "mandatory": False, "conditional": "при наличии заземления", "note": "С приложением исполнительной схемы"},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        {"name": "Ведомость изменений и отступлений от проекта", "mandatory": True},
        {"name": "Ведомость технической документации", "mandatory": True},
        {"name": "Ведомость э/м недоделок", "mandatory": True},
        {"name": "Ведомость смонтированного электрооборудования", "mandatory": True},
        {"name": "Паспорт заземляющего устройства (с ИС)", "mandatory": True},
        {"name": "Паспорт воздушной линии электропередачи", "mandatory": False, "conditional": "при воздушных линиях"},
        {"name": "Акт замеров фактических габаритов от проводов ВЛ до пересекаемого объекта", "mandatory": False, "conditional": "при воздушных линиях"},
    ],

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [
        {"name": "Ведомость смонтированного оборудования связи", "mandatory": False, "note": "Форма свободная"},
    ],
}


# =============================================================================
# НОРМАТИВНЫЕ ССЫЛКИ по видам работ
# =============================================================================

WORK_REGULATIONS: Dict[str, List[Dict[str, str]]] = {
    WorkType.EARTHWORK_EXCAVATION: [
        *COMMON_REGULATIONS,
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения, основания и фундаменты (изм. 1-5)", "status": "действует"},
        {"code": "СП 22.13330.2016", "note": "Основания зданий и сооружений", "status": "действует"},
        {"code": "СП 407.1325800.2024", "note": "Земляные работы. Гидромеханизация", "status": "действует"},
    ],
    WorkType.EARTHWORK_BACKFILL: [
        *COMMON_REGULATIONS,
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения, основания и фундаменты", "status": "действует"},
        {"code": "СП 22.13330.2016", "note": "Основания зданий и сооружений", "status": "действует"},
    ],
    WorkType.FOUNDATION_MONOLITHIC: [
        *COMMON_REGULATIONS,
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения, основания и фундаменты", "status": "действует"},
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции (изм. 1-7)", "status": "действует"},
        {"code": "СП 435.1325800.2018", "note": "Конструкции бетонные и ЖБ монолитные", "status": "действует"},
    ],
    WorkType.FOUNDATION_PRECAST: [
        *COMMON_REGULATIONS,
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения, основания и фундаменты", "status": "действует"},
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции", "status": "действует"},
    ],
    WorkType.FOUNDATION_PILE: [
        *COMMON_REGULATIONS,
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения, основания и фундаменты", "status": "действует"},
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции", "status": "действует"},
        {"code": "СП 24.13330.2021", "note": "Свайные фундаменты", "status": "действует"},
        {"code": "ГОСТ 5686-2020", "note": "Грунты. Методы полевых испытаний сваями", "status": "действует"},
    ],
    WorkType.CONCRETE: [
        *COMMON_REGULATIONS,
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции (изм. 1-7)", "status": "действует"},
        {"code": "СП 435.1325800.2018", "note": "Конструкции бетонные и ЖБ монолитные", "status": "действует"},
        {"code": "ГОСТ 18105-2018", "note": "Бетоны. Правила контроля и оценки качества", "status": "действует"},
    ],
    WorkType.METAL_STRUCTURES: [
        *COMMON_REGULATIONS,
        {"code": "СП 16.13330.2017", "note": "Стальные конструкции", "status": "действует"},
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции", "status": "действует"},
        {"code": "ГОСТ 23118-2019", "note": "Конструкции стальные строительные. Общие технические условия", "status": "действует"},
    ],
    WorkType.MASONRY: [
        *COMMON_REGULATIONS,
        {"code": "СП 70.13330.2012", "note": "Несущие и ограждающие конструкции", "status": "действует"},
        {"code": "СП 427.1325800.2018", "note": "Каменные и армокаменные конструкции. Методы усиления", "status": "действует"},
        {"code": "СП 15.13330.2020", "note": "Каменные и армокаменные конструкции (нормы проектирования)", "status": "действует"},
    ],
    WorkType.FINISHING_FLOORS: [
        *COMMON_REGULATIONS,
        {"code": "СП 29.13330.2021", "note": "Полы", "status": "действует"},
    ],
    WorkType.FINISHING_WALLS_CEILINGS: [
        *COMMON_REGULATIONS,
        {"code": "СП 71.13330.2017", "note": "Изоляционные и отделочные покрытия", "status": "действует"},
    ],
    WorkType.FINISHING_WINDOWS_DOORS: [
        *COMMON_REGULATIONS,
        {"code": "СП 71.13330.2017", "note": "Изоляционные и отделочные покрытия", "status": "действует"},
    ],
    WorkType.WATER_SUPPLY: [
        *COMMON_REGULATIONS,
        {"code": "СП 73.13330.2016", "note": "Внутренние санитарно-технические системы зданий", "status": "действует"},
        {"code": "СП 30.13330.2020", "note": "Внутренний водопровод и канализация зданий", "status": "действует"},
    ],
    WorkType.SEWERAGE: [
        *COMMON_REGULATIONS,
        {"code": "СП 73.13330.2016", "note": "Внутренние санитарно-технические системы зданий", "status": "действует"},
        {"code": "СП 30.13330.2020", "note": "Внутренний водопровод и канализация зданий", "status": "действует"},
    ],
    WorkType.EXTERNAL_NETWORKS_VK: [
        *COMMON_REGULATIONS,
        {"code": "СП 31.13330.2021", "note": "Водоснабжение. Наружные сети и сооружения", "status": "действует"},
        {"code": "СП 32.13330.2018", "note": "Канализация. Наружные сети и сооружения", "status": "действует"},
        {"code": "СП 129.13330.2019", "note": "Наружные сети водоснабжения и канализации", "status": "действует"},
        {"code": "СП 45.13330.2017", "note": "Земляные сооружения", "status": "действует"},
    ],
    WorkType.HEATING: [
        *COMMON_REGULATIONS,
        {"code": "СП 73.13330.2016", "note": "Внутренние санитарно-технические системы зданий", "status": "действует"},
        {"code": "СП 60.13330.2020", "note": "Отопление, вентиляция и кондиционирование воздуха", "status": "действует"},
    ],
    WorkType.VENTILATION: [
        *COMMON_REGULATIONS,
        {"code": "СП 73.13330.2016", "note": "Внутренние санитарно-технические системы зданий", "status": "действует"},
        {"code": "СП 60.13330.2020", "note": "Отопление, вентиляция и кондиционирование воздуха", "status": "действует"},
    ],
    WorkType.AIR_CONDITIONING: [
        *COMMON_REGULATIONS,
        {"code": "СП 73.13330.2016", "note": "Внутренние санитарно-технические системы зданий", "status": "действует"},
        {"code": "СП 60.13330.2020", "note": "Отопление, вентиляция и кондиционирование воздуха", "status": "действует"},
    ],
    WorkType.ELECTRICAL_INTERNAL: [
        *COMMON_REGULATIONS,
        {"code": "И 1.13-07", "note": "Инструкция по оформлению приемо-сдаточной документации по э/м работам", "status": "действует"},
        {"code": "ПУЭ-7", "note": "Правила устройства электроустановок", "status": "действует"},
    ],
    WorkType.ELECTRICAL_EXTERNAL: [
        *COMMON_REGULATIONS,
        {"code": "И 1.13-07", "note": "Инструкция по оформлению приемо-сдаточной документации по э/м работам", "status": "действует"},
        {"code": "ПУЭ-7", "note": "Правила устройства электроустановок", "status": "действует"},
    ],
    WorkType.COMMUNICATION_NETWORKS: [
        *COMMON_REGULATIONS,
    ],
}


# =============================================================================
# ТЕХНОЛОГИЧЕСКАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ (порядок оформления документов)
# =============================================================================

WORK_TECH_SEQUENCES: Dict[str, List[Dict[str, str]]] = {
    # ---- Земляные: выемка ----
    WorkType.EARTHWORK_EXCAVATION: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС на разбивку осей"},
        {"step": "2", "work": "Снятие растительного слоя", "documents": "АОСР + ИГС вертикальной планировки (если выполнялась)"},
        {"step": "3", "work": "Вертикальная планировка территории", "documents": "АОСР + ИГС (если выполнялась)"},
        {"step": "4", "work": "Разработка грунта (выемка)", "documents": "АОСР + ИГС выемки (котлована/траншеи)"},
        {"step": "5", "work": "Устройство крепления стенок (при необходимости)", "documents": "АОСР + ИС на крепление"},
        {"step": "6", "work": "Устройство дренажа (при необходимости)", "documents": "АОСР + ИС на дренаж"},
        {"step": "7", "work": "Приёмка оснований", "documents": "Акт приёмки оснований (с участием геолога)"},
    ],

    # ---- Земляные: обратная засыпка ----
    WorkType.EARTHWORK_BACKFILL: [
        {"step": "1", "work": "Возведение и уплотнение земляного полотна", "documents": "АОСР + ИГС + протокол уплотнения"},
        {"step": "2", "work": "Обратная засыпка пазух котлована (траншей)", "documents": "АОСР + ИГС + протокол уплотнения + ИГС"},
        {"step": "3", "work": "Устройство слоёв насыпи", "documents": "АОСР + ИГС"},
    ],

    # ---- Фундаменты: монолитные ----
    WorkType.FOUNDATION_MONOLITHIC: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС на разбивку осей"},
        {"step": "2", "work": "Устройство котлована", "documents": "АОСР + ИГС на котлован + Акт приёмки оснований"},
        {"step": "3", "work": "Устройство бетонной подготовки", "documents": "АОСР + ИГС на бетонную подготовку"},
        {"step": "4", "work": "Армирование фундаментов", "documents": "АОСР + ИС на армирование (необяз.)"},
        {"step": "5", "work": "Установка анкерных болтов", "documents": "АОСР + ИС на анкерные болты"},
        {"step": "6", "work": "Устройство опалубки", "documents": "АОСР (необяз.) + ИС (необяз.)"},
        {"step": "7", "work": "Бетонирование фундаментов", "documents": "АОСР + протокол промежуточной прочности + АООК + протокол проектной прочности"},
        {"step": "8", "work": "Гидроизоляция фундаментов", "documents": "АОСР + ИС (необяз.)"},
    ],

    # ---- Фундаменты: сборные ----
    WorkType.FOUNDATION_PRECAST: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС на разбивку"},
        {"step": "2", "work": "Устройство котлована", "documents": "АОСР + ИГС на котлован + Акт приёмки оснований"},
        {"step": "3", "work": "Устройство бетонной подготовки", "documents": "АОСР + ИГС на бетонную подготовку"},
        {"step": "4", "work": "Монтаж сборных ЖБК фундаментов", "documents": "АОСР + ИГС фундаментов"},
        {"step": "5", "work": "Замоноличивание монтажных стыков и узлов", "documents": "АОСР + журнал замоноличивания"},
        {"step": "6", "work": "Гидроизоляция фундаментов", "documents": "АОСР"},
        {"step": "7", "work": "АООК на фундамент", "documents": "АООК (после набора прочности замоноличивания)"},
    ],

    # ---- Фундаменты: свайные ----
    WorkType.FOUNDATION_PILE: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС на разбивку"},
        {"step": "2", "work": "Погружение испытательных свай с динамическими испытаниями", "documents": "АОСР + ИГС + журнал испытаний"},
        {"step": "3", "work": "Погружение остальных свай по проекту", "documents": "АОСР + ИГС"},
        {"step": "4", "work": "Статические испытания свай", "documents": "Журнал испытаний"},
        {"step": "5", "work": "Срубка свай", "documents": "АОСР + ИГС"},
        {"step": "6", "work": "Устройство ростверков", "documents": "АОСР + ИГС (как для ЖБК)"},
    ],

    # ---- Бетонные работы ----
    WorkType.CONCRETE: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС"},
        {"step": "2", "work": "Армирование конструкций", "documents": "АОСР + ИС на армирование (необяз.)"},
        {"step": "3", "work": "Установка закладных изделий и анкерных болтов", "documents": "АОСР + ИС на закладные"},
        {"step": "4", "work": "Устройство опалубки", "documents": "АОСР (необяз.) + ИС (необяз.)"},
        {"step": "5", "work": "Бетонирование конструкций", "documents": "АОСР + журнал бетонных работ + протокол промежуточной прочности"},
        {"step": "6", "work": "Снятие опалубки", "documents": "При наборе распалубочной прочности (по протоколу)"},
        {"step": "7", "work": "Гидроизоляция (при наличии)", "documents": "АОСР"},
        {"step": "8", "work": "АООК на конструкции", "documents": "АООК + протокол проектной прочности"},
    ],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        {"step": "1", "work": "Геодезическая разбивка осей", "documents": "Акт разбивки осей + ИГС"},
        {"step": "2", "work": "Устройство подливки под базы колонн", "documents": "АОСР + ИГС отметок опорных поверхностей"},
        {"step": "3", "work": "Монтаж колонн", "documents": "Журнал монтажа + ИГС смещения осей и вертикальности"},
        {"step": "4", "work": "Монтаж балок, ферм, ригелей, связей", "documents": "Журнал монтажа + ИГС отметок и смещений"},
        {"step": "5", "work": "Сварка монтажных соединений", "documents": "Журнал сварочных работ + АОСР на сварку (если требуется)"},
        {"step": "6", "work": "Монтаж на высокопрочных болтах (при наличии)", "documents": "Журнал болтовых соединений + журнал тарировки ключей"},
        {"step": "7", "work": "Антикоррозийная защита сварных соединений", "documents": "АОСР + журнал антикоррозионной защиты сварных соединений"},
        {"step": "8", "work": "Подготовка поверхности, грунтовка, покраска МК", "documents": "АОСР (подготовка + грунтовка + покраска — отдельные акты) + журнал антикоррозионных работ"},
        {"step": "9", "work": "Огнезащита МК (при наличии)", "documents": "АОСР + протокол испытания огнезащитного покрытия"},
        {"step": "10", "work": "АООК на металлоконструкции", "documents": "АООК + акт ВИК + заключение НК"},
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [
        {"step": "1", "work": "Кладка внутреннего слоя с армированием (трёхслойная)", "documents": "АОСР + поэтажная ИГС (для трёхслойных стен)"},
        {"step": "2", "work": "Устройство гибких связей (анкеров)", "documents": "АОСР (для трёхслойных стен)"},
        {"step": "3", "work": "Устройство теплоизоляции", "documents": "АОСР (для трёхслойных стен)"},
        {"step": "4", "work": "Кладка облицовочного слоя", "documents": "АОСР + ИГС (для трёхслойных стен)"},
        {"step": "5", "work": "Установка перемычек", "documents": "АОСР + ИС на перемычки (необяз.)"},
        {"step": "6", "work": "Антикоррозийная защита МК перемычек и закладных", "documents": "АОСР"},
        {"step": "7", "work": "Устройство монолитных поясов (при наличии)", "documents": "АОСР (армирование) + АОСР (бетонирование) + ИГС"},
        {"step": "8", "work": "АООК на несущий каркас", "documents": "АООК — на каждом этаже после перекрытий и анкеровки"},
    ],

    # ---- Отделка: полы ----
    WorkType.FINISHING_FLOORS: [
        {"step": "1", "work": "Подготовка грунтового основания", "documents": "АОСР + ИС на грунтовое основание"},
        {"step": "2", "work": "Устройство бетонного подстилающего слоя / стяжки", "documents": "АОСР + ИС (при бетонных полах — журнал бетонных работ)"},
        {"step": "3", "work": "Грунтование поверхности", "documents": "АОСР"},
        {"step": "4", "work": "Устройство звуко-/тепло-/гидроизоляции (послойно)", "documents": "АОСР на каждый слой (при наличии)"},
        {"step": "5", "work": "Устройство финишного покрытия", "documents": "АОСР (если скрытое) + ИС на покрытие + Акт приёмки готовых поверхностей"},
    ],

    # ---- Отделка: стены и потолки ----
    WorkType.FINISHING_WALLS_CEILINGS: [
        {"step": "1", "work": "Грунтование поверхностей", "documents": "АОСР"},
        {"step": "2", "work": "Монтаж металлического каркаса (ГКЛ/панели)", "documents": "АОСР + ИС (при облицовке/подвесном потолке)"},
        {"step": "3", "work": "Звукоизоляция (при наличии)", "documents": "АОСР"},
        {"step": "4", "work": "Обшивка ГКЛ / заделка швов", "documents": "АОСР + ИС"},
        {"step": "5", "work": "Оштукатуривание (при наличии)", "documents": "АОСР (скрытая под последующую отделку)"},
        {"step": "6", "work": "Покраска (скрытая)", "documents": "АОСР + ИС по видам работ + Акт приёмки готовых поверхностей"},
    ],

    # ---- Отделка: окна и двери ----
    WorkType.FINISHING_WINDOWS_DOORS: [
        {"step": "1", "work": "Крепление оконных и дверных коробок", "documents": "АОСР"},
        {"step": "2", "work": "Конопатка / запенивание", "documents": "АОСР"},
        {"step": "3", "work": "Герметизация блоков", "documents": "АОСР"},
        {"step": "4", "work": "Грунтование откосов", "documents": "АОСР"},
        {"step": "5", "work": "Штукатурка / шпатлёвка откосов", "documents": "АОСР (при наличии) + ИС + Акт освидетельствования"},
    ],

    # ---- Водоснабжение ----
    WorkType.WATER_SUPPLY: [
        {"step": "1", "work": "Монтаж трубопроводов", "documents": "АОСР + ЖВК (материалы)"},
        {"step": "2", "work": "Устройство проходов через стены и перекрытия (гильзы)", "documents": "АОСР (обычно один акт на все системы)"},
        {"step": "3", "work": "Антикоррозийная обработка (огрунтовка)", "documents": "АОСР (отдельно от покраски!)"},
        {"step": "4", "work": "Покраска трубопроводов", "documents": "АОСР"},
        {"step": "5", "work": "Гидростатическое испытание на герметичность (опрессовка)", "documents": "Акт (ДО теплоизоляции!)"},
        {"step": "6", "work": "Монтаж теплоизоляции (при наличии)", "documents": "АОСР"},
        {"step": "7", "work": "Промывка (продувка) системы", "documents": "Акт промывки"},
        {"step": "8", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "9", "work": "Приёмка системы", "documents": "Акт приёмки + комплект исполнительных чертежей"},
    ],

    # ---- Канализация ----
    WorkType.SEWERAGE: [
        {"step": "1", "work": "Монтаж трубопроводов канализации", "documents": "АОСР + ЖВК"},
        {"step": "2", "work": "Устройство проходов через стены и перекрытия (гильзы)", "documents": "АОСР"},
        {"step": "3", "work": "Монтаж водосточных систем (при наличии)", "documents": "АОСР (при внутренних водостоках)"},
        {"step": "4", "work": "Испытание систем канализации и водостоков (пролив)", "documents": "Акт (расход >= 75% расчётного)"},
        {"step": "5", "work": "Монтаж санитарных приборов", "documents": "Акт монтажа + ведомость оборудования"},
        {"step": "6", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "7", "work": "Приёмка системы", "documents": "Акт приёмки + комплект исполнительных чертежей"},
    ],

    # ---- Наружные сети ВК ----
    WorkType.EXTERNAL_NETWORKS_VK: [
        {"step": "1", "work": "Геодезическая разбивка оси сетей", "documents": "Акт разбивки + ИГС"},
        {"step": "2", "work": "Разработка траншеи", "documents": "АОСР + ИГС на траншею"},
        {"step": "3", "work": "Устройство основания", "documents": "АОСР + ИС на основание"},
        {"step": "4", "work": "Укладка трубопровода", "documents": "АОСР + ИС монтажа + схема продольного профиля"},
        {"step": "5", "work": "Антикоррозийное покрытие / теплоизоляция", "documents": "АОСР (при необходимости)"},
        {"step": "6", "work": "Предварительное испытание на герметичность", "documents": "Акт (до засыпки, открытые стыки)"},
        {"step": "7", "work": "Обратная засыпка", "documents": "АОСР + протокол уплотнения"},
        {"step": "8", "work": "Приёмочное испытание", "documents": "Акт приёмочного испытания (с заказчиком)"},
        {"step": "9", "work": "Промывка / дезинфекция", "documents": "Акт промывки / дезинфекции"},
    ],

    # ---- Отопление ----
    WorkType.HEATING: [
        {"step": "1", "work": "Монтаж трубопроводов системы отопления", "documents": "АОСР + ЖВК (материалы)"},
        {"step": "2", "work": "Устройство отверстий в стенах и плитах", "documents": "АОСР"},
        {"step": "3", "work": "Устройство проходов через стены и перекрытия (гильзы)", "documents": "АОСР + герметизация"},
        {"step": "4", "work": "Обеспыливание, обезжиривание перед покраской", "documents": "АОСР"},
        {"step": "5", "work": "Огрунтовка стальных трубопроводов", "documents": "АОСР"},
        {"step": "6", "work": "Покраска стальных трубопроводов", "documents": "АОСР"},
        {"step": "7", "work": "Промывка (продувка) системы", "documents": "Акт промывки (ДО опрессовки!)"},
        {"step": "8", "work": "Гидростатическое испытание на герметичность", "documents": "Акт (ДО теплоизоляции!)"},
        {"step": "9", "work": "Монтаж теплоизоляции (при наличии)", "documents": "АОСР"},
        {"step": "10", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "11", "work": "Приёмка системы", "documents": "Акт приёмки + комплект исполнительных чертежей"},
    ],

    # ---- Вентиляция ----
    WorkType.VENTILATION: [
        {"step": "1", "work": "Монтаж воздуховодов", "documents": "АОСР + ЖВК (материалы)"},
        {"step": "2", "work": "Устройство отверстий в стенах и плитах", "documents": "АОСР"},
        {"step": "3", "work": "Герметизация мест проходов воздуховодов", "documents": "АОСР"},
        {"step": "4", "work": "Теплоизоляция / огнезащита воздуховодов (при наличии)", "documents": "АОСР"},
        {"step": "5", "work": "Монтаж узлов проходов (при наличии)", "documents": "АОСР"},
        {"step": "6", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "7", "work": "Передача для ПНР", "documents": "Акт передачи"},
        {"step": "8", "work": "Окончание ПНР", "documents": "Акт об окончании ПНР"},
        {"step": "9", "work": "Комплексное опробование (при противопожарной вентиляции)", "documents": "Акт комплексного опробования"},
        {"step": "10", "work": "Приёмка системы", "documents": "Акт приёмки + паспорт системы + тех. отчёт + комплект чертежей"},
    ],

    # ---- Кондиционирование ----
    WorkType.AIR_CONDITIONING: [
        {"step": "1", "work": "Монтаж трасс хладонопроводов в теплоизоляции", "documents": "АОСР + ЖВК"},
        {"step": "2", "work": "Монтаж межблочного кабеля", "documents": "АОСР"},
        {"step": "3", "work": "Устройство отверстий в стенах", "documents": "АОСР"},
        {"step": "4", "work": "Герметизация мест проходов", "documents": "АОСР"},
        {"step": "5", "work": "Монтаж лотков (при наличии)", "documents": "АОСР"},
        {"step": "6", "work": "Монтаж оборудования", "documents": "АОСР + акт приёмки-передачи в монтаж"},
        {"step": "7", "work": "Испытание на герметичность", "documents": "Акт"},
        {"step": "8", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "9", "work": "Окончание ПНР", "documents": "Акт об окончании ПНР"},
        {"step": "10", "work": "Приёмка системы", "documents": "Акт приёмки + паспорт системы + комплект чертежей"},
    ],

    # ---- Электромонтаж: внутренние ----
    WorkType.ELECTRICAL_INTERNAL: [
        {"step": "1", "work": "Готовность строительной части к э/м работам", "documents": "Акт готовности строительной части (ДО начала работ!)"},
        {"step": "2", "work": "Приёмка оборудования в монтаж", "documents": "Акт приёмки-передачи оборудования в монтаж"},
        {"step": "3", "work": "Монтаж кабеленесущих систем (лотки)", "documents": "АОСР (отдельно, ДО прокладки кабеля)"},
        {"step": "4", "work": "Пробивка штробы (при скрытой прокладке)", "documents": "АОСР"},
        {"step": "5", "work": "Прокладка кабеля", "documents": "АОСР + кабельный журнал"},
        {"step": "6", "work": "Устройство проходов кабеля через стены и перекрытия", "documents": "АОСР"},
        {"step": "7", "work": "Монтаж заземления / молниезащиты (при наличии)", "documents": "АОСР + паспорт заземляющего устройства"},
        {"step": "8", "work": "Протоколы испытаний", "documents": "Протокол изоляции + фаза-нуль + АВ + заземление"},
        {"step": "9", "work": "Проверка освещения", "documents": "Акт проверки зажигания + акт проверки автоматов"},
        {"step": "10", "work": "Техническая готовность э/м работ", "documents": "Акт тех. готовности + 4 приложения (ведомости)"},
        {"step": "11", "work": "Передача для ПНР", "documents": "Акт передачи"},
        {"step": "12", "work": "Сдача-приёмка ПНР", "documents": "Акт сдачи-приёмки ПНР"},
    ],

    # ---- Электромонтаж: наружные ----
    WorkType.ELECTRICAL_EXTERNAL: [
        {"step": "1", "work": "Геодезическая разбивка оси КЛ / ВЛ", "documents": "ИГС разбивки оси"},
        {"step": "2", "work": "Устройство траншеи", "documents": "АОСР + ИГС траншеи"},
        {"step": "3", "work": "Устройство основания под кабель", "documents": "АОСР"},
        {"step": "4", "work": "Прокладка кабеля", "documents": "АОСР + кабельный журнал + журнал прокладки (1-35 кВ)"},
        {"step": "5", "work": "Монтаж разделительного кирпича / ПЗК (по проекту)", "documents": "АОСР"},
        {"step": "6", "work": "Осмотр кабельной канализации перед закрытием", "documents": "Акт осмотра (И 1.13-07 п. 6.1)"},
        {"step": "7", "work": "Обратная засыпка траншеи", "documents": "АОСР"},
        {"step": "8", "work": "Монтаж заземляющего устройства / молниезащиты", "documents": "АОСР + паспорт заземляющего устройства + ИГС"},
        {"step": "9", "work": "Протоколы испытаний", "documents": "Протокол изоляции + фаза-нуль + АВ + заземление + грунт"},
        {"step": "10", "work": "Техническая готовность э/м работ", "documents": "Акт тех. готовности + ведомости"},
        {"step": "11", "work": "Приёмка траншей/каналов/блоков под монтаж", "documents": "Акт приёмки"},
        {"step": "12", "work": "Передача для ПНР и сдача", "documents": "Акт передачи + Акт сдачи-приёмки ПНР"},
    ],

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [
        {"step": "1", "work": "Прокладка кабеля связи", "documents": "АОСР + ЖВК (материалы)"},
        {"step": "2", "work": "Устройство проходов через стены и перекрытия", "documents": "АОСР"},
        {"step": "3", "work": "Монтаж оборудования связи", "documents": "АОСР + акт приёмки-передачи в монтаж"},
        {"step": "4", "work": "Индивидуальное испытание оборудования", "documents": "Акт"},
        {"step": "5", "work": "Приёмка систем связи", "documents": "Акт приёмки + комплект исполнительных чертежей"},
    ],
}


# =============================================================================
# ПРАВИЛА ДАТИРОВКИ
# =============================================================================

WORK_DATE_RULES: Dict[str, List[Dict[str, str]]] = {
    # ---- Земляные: выемка ----
    WorkType.EARTHWORK_EXCAVATION: [
        {
            "rule": "Дата АОСР на земляные работы = дата освидетельствования, а не дата выполнения работ",
            "source": "Приказ Минстроя № 344/пр",
        },
        {
            "rule": "Акт приёмки оснований составляется при участии геолога, дата — дата фактической приёмки",
            "source": "СП 45.13330.2017 п. 11.13",
        },
        {
            "rule": "ИГС на выемку оформляется после достижения проектных отметок, до начала последующих работ",
            "source": "ГОСТ Р 51872-2024",
        },
    ],

    # ---- Земляные: обратная засыпка ----
    WorkType.EARTHWORK_BACKFILL: [
        {
            "rule": "АОСР на обратную засыпку оформляется ДО начала последующих работ на данном участке",
            "source": "Приказ Минстроя № 344/пр",
        },
        {
            "rule": "Протокол уплотнения грунта — дата отбора проб должна совпадать с датой засыпки слоя в ОЖР",
            "source": "СП 45.13330.2017",
        },
        {
            "rule": "ИГС с точками отбора проб прилагается к протоколу уплотнения",
            "source": "Пособие 5.3.2",
        },
    ],

    # ---- Фундаменты: монолитные ----
    WorkType.FOUNDATION_MONOLITHIC: [
        {
            "rule": "Дата АОСР на бетонирование = дата протокола испытания бетона на прочность в промежуточном возрасте (~7 суток), НЕ дата заливки",
            "source": "Пособие 5.4.1; СП 435.1325800.2018",
            "example": "Бетонирование 29.06.2025 → протокол 06.07.2025 → дата АОСР = 06.07.2025",
        },
        {
            "rule": "Дата в документе качества на бетонную смесь должна соответствовать дате выполнения работ в АОСР",
            "source": "Пособие 5.5",
        },
        {
            "rule": "Даты должны соответствовать: ОЖР, журнал бетонных работ, ЖВК, документ качества на бетон",
            "source": "Пособие 5.5",
        },
        {
            "rule": "АООК подписывается после набора бетоном необходимой прочности (прикладывается протокол). Но не обязательно 28 суток — можно разрешить нагрузку до 100% проектной",
            "source": "Пособие 5.4.1; таблица 10.1 СП 435.1325800.2018",
        },
    ],

    # ---- Фундаменты: сборные ----
    WorkType.FOUNDATION_PRECAST: [
        {
            "rule": "Дата АОСР на монтаж СБК = дата фактического освидетельствования (после выверки положения)",
            "source": "СП 70.13330.2012",
        },
        {
            "rule": "Дата акта на замоноличивание — после набора прочности замоноличивания (по протоколу)",
            "source": "СП 70.13330.2012",
        },
        {
            "rule": "АООК на фундамент — после завершения замоноличивания и набора прочности",
            "source": "Пособие 5.4.2",
        },
    ],

    # ---- Фундаменты: свайные ----
    WorkType.FOUNDATION_PILE: [
        {
            "rule": "Дата АОСР на погружение сваи = дата освидетельствования после погружения",
            "source": "СП 24.13330.2021",
        },
        {
            "rule": "ИГС свай до и после срубки — раздельные схемы, разные даты",
            "source": "Пособие 5.4.3",
        },
        {
            "rule": "Срубка свай — только после оформления ИГС планово-высотного положения ДО срубки",
            "source": "СП 45.13330.2017",
        },
        {
            "rule": "АООК на свайный фундамент — после завершения всех работ по сваям и ростверку",
            "source": "Пособие 5.4.3",
        },
    ],

    # ---- Бетонные работы ----
    WorkType.CONCRETE: [
        {
            "rule": "Дата АОСР на бетонирование = дата протокола промежуточной прочности (~7 суток), НЕ дата заливки",
            "source": "Пособие 5.5; ГОСТ 18105-2018",
        },
        {
            "rule": "Объединение конструкций в одном АОСР: один этаж/ярус, один класс бетона, одна технология, заливка <=1 недели",
            "source": "ГОСТ 18105-2018 п. 8.1.3",
        },
        {
            "rule": "В журнале бетонных работ объединять конструкции НЕЛЬЗЯ",
            "source": "СП 435.1325800.2018 п. 15.4",
        },
        {
            "rule": "АООК — после набора проектной прочности (28 сут или по протоколу раннего нагружения)",
            "source": "СП 435.1325800.2018",
        },
    ],

    # ---- Металлоконструкции ----
    WorkType.METAL_STRUCTURES: [
        {
            "rule": "АОСР на антикоррозийную защиту: огрунтовка и покраска — РАЗНЫЕ акты, НЕ объединять",
            "source": "Пособие 5.6; СП 70.13330.2012",
        },
        {
            "rule": "Подготовка поверхности (пескоструй, обезжиривание) — отдельный АОСР до огрунтовки",
            "source": "Пособие 5.6",
        },
        {
            "rule": "АООК на МК можно оформлять на весь каркас или по захваткам (ярусам)",
            "source": "Пособие 5.6",
        },
        {
            "rule": "Визуальный и измерительный контроль (ВИК) — на 100% длины сварных швов, оформляется до АООК",
            "source": "СП 70.13330.2012",
        },
        {
            "rule": "Заключение по НК (УЗК и др.) — дата не позднее даты АООК",
            "source": "СП 70.13330.2012",
        },
    ],

    # ---- Каменная кладка ----
    WorkType.MASONRY: [
        {
            "rule": "Акты на кладку — на каждый этаж отдельно, можно по захваткам",
            "source": "СП 70.13330.2012 п. 9.1.8",
        },
        {
            "rule": "Кладка следующего этажа — только после перекрытий, анкеровки стен, замоноличивания швов между плитами",
            "source": "СП 70.13330.2012 п. 9.1.8",
        },
        {
            "rule": "Ненесущие стены — только после АООК на несущий каркас",
            "source": "СП 70.13330.2012 п. 9.4.1",
        },
        {
            "rule": "При зимней кладке — протокол фактической прочности раствора (при оттаивании возможна перегрузка)",
            "source": "СП 70.13330.2012 п. 9.16.2",
        },
    ],

    # ---- Отделка: полы ----
    WorkType.FINISHING_FLOORS: [
        {
            "rule": "АОСР на каждый слой пола оформляется до устройства следующего слоя",
            "source": "СП 29.13330.2021",
        },
        {
            "rule": "Акт приёмки готовых поверхностей — после устройства финишного покрытия",
            "source": "СП 543.1325800.2024 п. 8.7",
        },
        {
            "rule": "При бетонных полах — дата АОСР на стяжку = дата протокола прочности (аналогично бетонным работам)",
            "source": "СП 29.13330.2021",
        },
    ],

    # ---- Отделка: стены и потолки ----
    WorkType.FINISHING_WALLS_CEILINGS: [
        {
            "rule": "АОСР на грунтование — до начала последующих отделочных работ",
            "source": "СП 71.13330.2017",
        },
        {
            "rule": "Оштукатуривание — скрытая работа под последующую отделку (покраску, плитку, обои)",
            "source": "Пособие 5.8.2",
        },
        {
            "rule": "Акт приёмки готовых поверхностей — на финишные покрытия (форму согласовывают участники)",
            "source": "СП 543.1325800.2024 п. 8.7",
        },
    ],

    # ---- Отделка: окна и двери ----
    WorkType.FINISHING_WINDOWS_DOORS: [
        {
            "rule": "АОСР на крепление коробок — до конопатки/запенивания",
            "source": "Пособие 5.8.3",
        },
        {
            "rule": "Конопатка/запенивание — отдельный АОСР до герметизации",
            "source": "Пособие 5.8.3",
        },
        {
            "rule": "Акт освидетельствования на монтаж — форма не регламентирована, согласовывается с участниками",
            "source": "Пособие 5.8.3; СП 543 п. 8.7",
        },
    ],

    # ---- Водоснабжение ----
    WorkType.WATER_SUPPLY: [
        {
            "rule": "Опрессовка ДО монтажа теплоизоляции",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "Гидростатическое: давление 1.5 рабочего. 10 мин. Падение <=0.05 МПа. Без утечек",
            "source": "СП 73.13330.2016 п. 7.2.2",
        },
        {
            "rule": "Огрунтовка и покраска — РАЗНЫЕ АОСР, не объединять",
            "source": "Пособие 5.9.1",
        },
        {
            "rule": "Акт на гильзы — обычно один на все системы (ВК, отопление, канализация)",
            "source": "Пособие 5.9.1",
        },
    ],

    # ---- Канализация ----
    WorkType.SEWERAGE: [
        {
            "rule": "Испытание канализации — пролив водой, расход >= 75% расчётного",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "Акт приёмки системы — после испытаний и индивидуальных испытаний оборудования",
            "source": "СП 73.13330.2016",
        },
    ],

    # ---- Наружные сети ВК ----
    WorkType.EXTERNAL_NETWORKS_VK: [
        {
            "rule": "Предварительное испытание: до засыпки, с открытыми стыками. Допускается без заказчика",
            "source": "СП 129.13330.2019 п. 10.1.2",
        },
        {
            "rule": "Приёмочное испытание: после полной засыпки, с заказчиком и эксплуатационной организацией",
            "source": "СП 129.13330.2019 п. 10.1.2",
        },
        {
            "rule": "АОСР оформляются ДО обратной засыпки (по участкам)",
            "source": "Пособие 5.9.3",
        },
        {
            "rule": "Схема продольного профиля — обязательно! Оформляет геодезист",
            "source": "Пособие 5.9.3; ГОСТ Р 51872-2024",
        },
    ],

    # ---- Отопление ----
    WorkType.HEATING: [
        {
            "rule": "Опрессовка: ПОСЛЕ промывки, ДО монтажа теплоизоляции",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "Давление = 1.5 рабочего, но не менее 0.2 МПа. Время >=5 мин. Падение <=0.02 МПа",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "Обеспыливание и обезжиривание — ДО огрунтовки; огрунтовка — ДО покраски. Все отдельные АОСР",
            "source": "Пособие 5.10.1",
        },
    ],

    # ---- Вентиляция ----
    WorkType.VENTILATION: [
        {
            "rule": "ПНР проводится после индивидуальных испытаний оборудования",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "Паспорт вентиляции — с результатами аэродинамических испытаний и схемой точек замеров",
            "source": "СП 60.13330.2020",
        },
        {
            "rule": "Комплексное опробование противопожарной вентиляции — обязательный акт",
            "source": "ФЗ-123; СП 7.13130.2013",
        },
    ],

    # ---- Кондиционирование ----
    WorkType.AIR_CONDITIONING: [
        {
            "rule": "Испытание на герметичность — после монтажа хладонопроводов, до пусконаладки",
            "source": "СП 73.13330.2016",
        },
        {
            "rule": "ПНР — после индивидуальных испытаний оборудования",
            "source": "СП 73.13330.2016",
        },
    ],

    # ---- Электромонтаж: внутренние ----
    WorkType.ELECTRICAL_INTERNAL: [
        {
            "rule": "Акт готовности строительной части — ДО начала э/м работ! Без него работы начинать нельзя",
            "source": "И 1.13-07",
        },
        {
            "rule": "Протоколы испытаний (изоляция, фаза-нуль, АВ) — дата = дата измерений, ДО акта тех. готовности",
            "source": "И 1.13-07; ПУЭ-7",
        },
        {
            "rule": "Акт тех. готовности + 4 приложения — после завершения монтажа и протоколов",
            "source": "И 1.13-07",
        },
        {
            "rule": "Передача для ПНР — после акта тех. готовности",
            "source": "И 1.13-07",
        },
    ],

    # ---- Электромонтаж: наружные ----
    WorkType.ELECTRICAL_EXTERNAL: [
        {
            "rule": "Акт осмотра кабельной канализации перед закрытием — ДО засыпки!",
            "source": "И 1.13-07 п. 6.1",
        },
        {
            "rule": "Протокол осмотра и проверки изоляции кабеля на барабане — ДО прокладки",
            "source": "И 1.13-07 п. 6.1",
        },
        {
            "rule": "ИГС подземных сетей — после засыпки, с привязками",
            "source": "ГОСТ Р 51872-2024; И 1.13-07",
        },
        {
            "rule": "Паспорт заземляющего устройства — обязательный документ с ИГС",
            "source": "ПУЭ-7; И 1.13-07",
        },
    ],

    # ---- Сети связи ----
    WorkType.COMMUNICATION_NETWORKS: [
        {
            "rule": "АОСР на прокладку кабеля — до закрытия (засыпки, заделки)",
            "source": "СП 543.1325800.2024",
        },
        {
            "rule": "Испытания систем связи — после монтажа оборудования",
            "source": "СП 543.1325800.2024",
        },
    ],
}


# =============================================================================
# ТРЕБОВАНИЯ ВХОДНОГО КОНТРОЛЯ (общие для всех, п. 7.1.4 СП 543)
# =============================================================================

WORK_INPUT_CONTROL: Dict[str, Any] = {
    "chapter": "5.2",
    "who_conducts": "Лицо, осуществляющее строительство (подрядчик)",
    "primary_document": "Журнал входного контроля материалов (ЖВК)",
    "act_not_required": True,
    "act_note": "Акты входного контроля общими нормами не требуются (кроме АОРПИ в нефтегазе)",
    "required_documents": [
        {
            "name": "Паспорт качества",
            "mandatory": True,
            "note": "Основной документ изготовителя (поставщика)",
        },
        {
            "name": "Сертификат соответствия / Декларация о соответствии",
            "mandatory": False,
            "conditional": "если продукция в Перечне ПП РФ от 23.12.2021 №2425",
        },
        {
            "name": "Сертификат пожарной безопасности",
            "mandatory": False,
            "conditional": "если продукция в Перечне Распоряжения Правительства РФ от 29.12.2020 №3646-р",
        },
        {
            "name": "Свидетельство о государственной регистрации (СГР)",
            "mandatory": False,
            "conditional": "если продукция в Приложении 1 к решению КТС от 28.05.2010 №299",
        },
        {
            "name": "Отказное / информационное письмо",
            "mandatory": False,
            "conditional": "если продукция не подпадает под обязательное подтверждение соответствия",
        },
    ],
    "rules": [
        "Просроченные сертификаты допустимы, если продукция выпущена в период действия сертификата (ч. 3 ст. 23 ФЗ №184-ФЗ)",
        "При отсутствии маркировки или сопроводительных документов — запрет использования до подтверждения соответствия ПД и РД (п. 7.1.9, 7.1.10 СП 543)",
        "Сторонняя лаборатория для испытаний должна быть аккредитованной (п. 7 ПП №468 от 21.06.2010)",
        "Заказчик проверяет полноту и сроки входного контроля (п. 6 ПП №468)",
    ],
}


# =============================================================================
# PTO_WorkSpec Skill
# =============================================================================

class PTO_WorkSpec(SkillBase):
    """
    Навык специализации ПТО по видам работ.

    Определяет полный состав ИД для ЛЮБОГО вида работ на ОКС:
    - Перечень актов скрытых работ (АОСР)
    - Акты ответственных конструкций (АООК)
    - Акты приёмки, испытаний
    - Необходимые журналы работ и их формы
    - Исполнительные схемы и чертежи
    - Сертификаты, протоколы, паспорта
    - Нормативные ссылки
    - Технологическая последовательность
    - Правила датировки
    - Требования входного контроля

    Источник: Пособие по ИД, Выпуск №2 (Сарвартдинова, 2026).
    """

    skill_id = "PTO_WorkSpec"
    description = "Определяет полный состав ИД по виду работ (все виды работ на ОКС)"
    agent = "pto"

    SUPPORTED_WORK_TYPES = {wt.value for wt in WorkType}

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: work_type обязателен."""
        errors = []
        if "work_type" not in params:
            errors.append("Параметр 'work_type' обязателен")
        return {"valid": len(errors) == 0, "errors": errors}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Определить полный состав ИД для вида работ.

        Args:
            work_type: Вид работ (строка из WorkType)
            include_regulations: Включить нормативные ссылки (default True)
            include_tech_sequence: Включить технологическую последовательность (default True)
            include_date_rules: Включить правила датировки (default True)

        Returns:
            SkillResult с полным составом ИД
        """
        work_type = params["work_type"]
        include_regs = params.get("include_regulations", True)
        include_tech = params.get("include_tech_sequence", True)
        include_dates = params.get("include_date_rules", True)

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
        result_data: Dict[str, Any] = {
            "work_type": work_type,
            "chapter": WORK_TYPE_CHAPTERS.get(work_type, ""),
            "category": self._get_category(work_type),
            "journals": WORK_JOURNALS.get(work_type, []),
            "hidden_works_acts": WORK_HIDDEN_ACTS.get(work_type, []),
            "responsible_acts": WORK_RESPONSIBLE_ACTS.get(work_type, []),
            "acceptance_acts": WORK_ACCEPTANCE_ACTS.get(work_type, []),
            "executive_schemes": WORK_EXECUTIVE_SCHEMES.get(work_type, []),
            "certificates": WORK_CERTIFICATES.get(work_type, []),
            "additional_docs": WORK_ADDITIONAL_DOCS.get(work_type, []),
            "input_control": WORK_INPUT_CONTROL,
            "act_forms": {
                "aosr": COMMON_ACT_AOSR,
                "aook": COMMON_ACT_AOOUK,
            },
        }

        if include_regs:
            result_data["regulations"] = WORK_REGULATIONS.get(work_type, [])

        if include_tech:
            result_data["tech_sequence"] = WORK_TECH_SEQUENCES.get(work_type, [])

        if include_dates:
            result_data["date_rules"] = WORK_DATE_RULES.get(work_type, [])

        # Подсчёт
        total_acts = len(result_data["hidden_works_acts"])
        mandatory_acts = sum(1 for a in result_data["hidden_works_acts"] if a.get("mandatory", True))
        total_journals = len(result_data["journals"])
        mandatory_journals = sum(1 for j in result_data["journals"] if j.get("mandatory", True))
        result_data["summary"] = {
            "total_journals": total_journals,
            "mandatory_journals": mandatory_journals,
            "total_hidden_acts": total_acts,
            "mandatory_hidden_acts": mandatory_acts,
            "total_responsible_acts": len(result_data["responsible_acts"]),
            "total_acceptance_acts": len(result_data["acceptance_acts"]),
            "total_executive_schemes": len(result_data["executive_schemes"]),
            "total_certificates": len(result_data["certificates"]),
            "total_additional_docs": len(result_data["additional_docs"]),
        }

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data=result_data,
        )

    async def list_work_types(self) -> SkillResult:
        """Вернуть иерархический список всех видов работ."""
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "categories": WORK_TYPE_CATEGORIES,
                "all_work_types": sorted(self.SUPPORTED_WORK_TYPES),
                "total": len(self.SUPPORTED_WORK_TYPES),
            },
        )

    async def get_tech_sequence(self, work_type: str) -> SkillResult:
        """Вернуть технологическую последовательность для вида работ."""
        if work_type not in self.SUPPORTED_WORK_TYPES:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[f"Неизвестный вид работ: '{work_type}'"],
            )
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "tech_sequence": WORK_TECH_SEQUENCES.get(work_type, []),
                "note": "Если последовательность не указана, ориентируйтесь на технологический порядок работ",
            },
        )

    async def get_date_rules(self, work_type: str) -> SkillResult:
        """Вернуть правила датировки для вида работ."""
        if work_type not in self.SUPPORTED_WORK_TYPES:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[f"Неизвестный вид работ: '{work_type}'"],
            )
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "date_rules": WORK_DATE_RULES.get(work_type, []),
                "general_rules": [
                    "Дата АОСР = дата освидетельствования, а не дата выполнения работ",
                    "Дата акта должна быть не позже начала последующих работ",
                ],
            },
        )

    async def get_input_control(self) -> SkillResult:
        """Вернуть требования входного контроля (общие для всех видов работ)."""
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data=WORK_INPUT_CONTROL,
        )

    @staticmethod
    def _get_category(work_type: str) -> str:
        """Определить категорию вида работ."""
        for category, types in WORK_TYPE_CATEGORIES.items():
            if work_type in types:
                return category
        return "unknown"
