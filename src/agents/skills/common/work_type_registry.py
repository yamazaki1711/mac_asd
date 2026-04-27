"""
MAC_ASD — Единый реестр видов работ (WorkTypeRegistry).

Единый источник истины (Single Source of Truth) для кросс-агентных
маппингов видов работ. Все агенты (ПТО, сметчик, юрист и др.)
обращаются к этому модулю для получения категорий сметных расценок,
юридических наименований работ и префиксов ФЕР.

Иерархия:
  WorkType (pto.work_spec) → реестр (настоящий модуль) → агенты
"""

from typing import Dict, List, Optional

# Реэкспорт WorkType и существующих констант из ПТО-модуля
from src.agents.skills.pto.work_spec import (
    WorkType,
    WORK_TYPE_CHAPTERS,
    WORK_TYPE_CATEGORIES,
)


# =============================================================================
# Кросс-агентные маппинги
# =============================================================================

# Соответствие вида работ → категория сметной расценки
# Используется агентом-сметчиком для подбора базовых расценок
WORK_TYPE_TO_SMETA_CATEGORY: Dict[WorkType, str] = {
    WorkType.EARTHWORK_EXCAVATION: "земляные",
    WorkType.EARTHWORK_BACKFILL: "земляные",
    WorkType.FOUNDATION_MONOLITHIC: "бетонные",
    WorkType.FOUNDATION_PRECAST: "монтажные",
    WorkType.FOUNDATION_PILE: "монтажные",
    WorkType.CONCRETE: "бетонные",
    WorkType.METAL_STRUCTURES: "монтажные",
    WorkType.MASONRY: "общестроительные",
    WorkType.FINISHING_FLOORS: "отделочные",
    WorkType.FINISHING_WALLS_CEILINGS: "отделочные",
    WorkType.FINISHING_WINDOWS_DOORS: "отделочные",
    WorkType.WATER_SUPPLY: "инженерные_системы",
    WorkType.SEWERAGE: "инженерные_системы",
    WorkType.EXTERNAL_NETWORKS_VK: "инженерные_системы",
    WorkType.HEATING: "инженерные_системы",
    WorkType.VENTILATION: "инженерные_системы",
    WorkType.AIR_CONDITIONING: "инженерные_системы",
    WorkType.ELECTRICAL_INTERNAL: "электромонтаж",
    WorkType.ELECTRICAL_EXTERNAL: "электромонтаж",
    WorkType.COMMUNICATION_NETWORKS: "слаботочные",
}

# Соответствие вида работ → юридическое наименование вида работ
# Используется юридическим агентом для формирования договоров и актов
WORK_TYPE_TO_LEGAL_WORK_TYPE: Dict[WorkType, str] = {
    WorkType.EARTHWORK_EXCAVATION: "земляные",
    WorkType.EARTHWORK_BACKFILL: "земляные",
    WorkType.FOUNDATION_MONOLITHIC: "бетонные",
    WorkType.FOUNDATION_PRECAST: "монтажные",
    WorkType.FOUNDATION_PILE: "монтажные",
    WorkType.CONCRETE: "бетонные",
    WorkType.METAL_STRUCTURES: "монтажные",
    WorkType.MASONRY: "общестроительные",
    WorkType.FINISHING_FLOORS: "отделочные",
    WorkType.FINISHING_WALLS_CEILINGS: "отделочные",
    WorkType.FINISHING_WINDOWS_DOORS: "отделочные",
    WorkType.WATER_SUPPLY: "инженерные_системы",
    WorkType.SEWERAGE: "инженерные_системы",
    WorkType.EXTERNAL_NETWORKS_VK: "инженерные_системы",
    WorkType.HEATING: "инженерные_системы",
    WorkType.VENTILATION: "инженерные_системы",
    WorkType.AIR_CONDITIONING: "инженерные_системы",
    WorkType.ELECTRICAL_INTERNAL: "электромонтаж",
    WorkType.ELECTRICAL_EXTERNAL: "электромонтаж",
    WorkType.COMMUNICATION_NETWORKS: "слаботочные",
}

# Соответствие вида работ → префикс(ы) кодов ФЕР
# Используется агентом-сметчиком для привязки расценок к сборникам ФЕР
WORK_TYPE_TO_FER_PREFIX: Dict[WorkType, str] = {
    WorkType.EARTHWORK_EXCAVATION: "ФЕР01",
    WorkType.EARTHWORK_BACKFILL: "ФЕР01",
    WorkType.FOUNDATION_MONOLITHIC: "ФЕР06,ФЕР08",
    WorkType.FOUNDATION_PRECAST: "ФЕР07",
    WorkType.FOUNDATION_PILE: "ФЕР05",
    WorkType.CONCRETE: "ФЕР06",
    WorkType.METAL_STRUCTURES: "ФЕР09",
    WorkType.MASONRY: "ФЕР08",
    WorkType.FINISHING_FLOORS: "ФЕР11",
    WorkType.FINISHING_WALLS_CEILINGS: "ФЕР15",
    WorkType.FINISHING_WINDOWS_DOORS: "ФЕР10",
    WorkType.WATER_SUPPLY: "ФЕР16",
    WorkType.SEWERAGE: "ФЕР16",
    WorkType.EXTERNAL_NETWORKS_VK: "ФЕР22",
    WorkType.HEATING: "ФЕР18",
    WorkType.VENTILATION: "ФЕР20",
    WorkType.AIR_CONDITIONING: "ФЕР20",
    WorkType.ELECTRICAL_INTERNAL: "ФЕР46",
    WorkType.ELECTRICAL_EXTERNAL: "ФЕР46",
    WorkType.COMMUNICATION_NETWORKS: "ФЕР46",
}


# =============================================================================
# Обратные индексы для быстрого поиска
# =============================================================================

# Русское название → WorkType (строится автоматически из значений enum)
_RUSSIAN_TO_WORK_TYPE: Dict[str, WorkType] = {wt.value: wt for wt in WorkType}

# Категория ПТО → список WorkType (из WORK_TYPE_CATEGORIES)
_CATEGORY_TO_WORK_TYPES: Dict[str, List[WorkType]] = {}
for _cat, _wt_list in WORK_TYPE_CATEGORIES.items():
    for _wt in _wt_list:
        _CATEGORY_TO_WORK_TYPES.setdefault(_cat, []).append(_wt)


# =============================================================================
# Служебные функции
# =============================================================================

def get_smeta_category(work_type: str) -> str:
    """Возвращает категорию сметной расценки для вида работ.

    Args:
        work_type: Значение WorkType (enum value, русский текст
                   или имя константы, например «EARTHWORK_EXCAVATION»).

    Returns:
        Категория сметной расценки (например «бетонные», «монтажные»).

    Raises:
        ValueError: Если вид работ не найден.
    """
    wt = _resolve_to_work_type(work_type)
    if wt is None:
        raise ValueError(f"Неизвестный вид работ: {work_type!r}")
    return WORK_TYPE_TO_SMETA_CATEGORY[wt]


def get_legal_work_type(work_type: str) -> str:
    """Возвращает юридическое наименование вида работ.

    Args:
        work_type: Значение WorkType (см. get_smeta_category).

    Returns:
        Юридическое наименование (например «инженерные_системы»).

    Raises:
        ValueError: Если вид работ не найден.
    """
    wt = _resolve_to_work_type(work_type)
    if wt is None:
        raise ValueError(f"Неизвестный вид работ: {work_type!r}")
    return WORK_TYPE_TO_LEGAL_WORK_TYPE[wt]


def get_fer_prefix(work_type: str) -> str:
    """Возвращает префикс(ы) кодов ФЕР для вида работ.

    Args:
        work_type: Значение WorkType (см. get_smeta_category).

    Returns:
        Префикс ФЕР (например «ФЕР01», «ФЕР06,ФЕР08»).

    Raises:
        ValueError: Если вид работ не найден.
    """
    wt = _resolve_to_work_type(work_type)
    if wt is None:
        raise ValueError(f"Неизвестный вид работ: {work_type!r}")
    return WORK_TYPE_TO_FER_PREFIX[wt]


def list_all_work_types() -> List[Dict]:
    """Возвращает полный перечень видов работ с кросс-ссылками.

    Returns:
        Список словарей, каждый из которых содержит:
          - enum_name: имя константы WorkType
          - russian: русское наименование (значение enum)
          - smeta_category: категория сметной расценки
          - legal_work_type: юридическое наименование
          - fer_prefix: префикс(ы) ФЕР
          - chapter: ссылка на раздел Пособия
          - category_key: ключ категории ПТО
    """
    result: List[Dict] = []
    for wt in WorkType:
        # Найти ключ категории, в которую входит данный вид работ
        cat_key = next(
            (k for k, v in WORK_TYPE_CATEGORIES.items() if wt in v),
            None,
        )
        result.append({
            "enum_name": wt.name,
            "russian": wt.value,
            "smeta_category": WORK_TYPE_TO_SMETA_CATEGORY[wt],
            "legal_work_type": WORK_TYPE_TO_LEGAL_WORK_TYPE[wt],
            "fer_prefix": WORK_TYPE_TO_FER_PREFIX[wt],
            "chapter": WORK_TYPE_CHAPTERS.get(wt, ""),
            "category_key": cat_key,
        })
    return result


def resolve_work_type(input_str: str) -> Optional[str]:
    """Пытается разрешить произвольную строку в значение WorkType.

    Поддерживаемые форматы ввода:
      - Имя константы enum: «EARTHWORK_EXCAVATION»
      - Русское наименование: «земляные_выемки»
      - Ключ категории ПТО: «earthwork», «foundation» и т.д.
        (возвращает первый вид работ из категории)
      - Категория сметной расценки: «бетонные», «монтажные»
        (возвращает первый вид работ с данной категорией)
      - Префикс ФЕР: «ФЕР01»
        (возвращает первый вид работ с данным префиксом)

    Args:
        input_str: Строка для разрешения.

    Returns:
        Значение WorkType (русский текст) или None, если не найдено.
    """
    # 1. Точное совпадение с именем константы enum
    upper = input_str.strip().upper()
    for wt in WorkType:
        if wt.name == upper:
            return wt.value

    # 2. Точное совпадение с русским значением enum
    stripped = input_str.strip()
    if stripped in _RUSSIAN_TO_WORK_TYPE:
        return _RUSSIAN_TO_WORK_TYPE[stripped].value

    # 3. Совпадение с ключом категории ПТО
    lower = stripped.lower()
    if lower in WORK_TYPE_CATEGORIES:
        return WORK_TYPE_CATEGORIES[lower][0].value

    # 4. Совпадение с категорией сметной расценки
    for wt, cat in WORK_TYPE_TO_SMETA_CATEGORY.items():
        if cat == stripped:
            return wt.value

    # 5. Совпадение с юридическим наименованием
    for wt, legal in WORK_TYPE_TO_LEGAL_WORK_TYPE.items():
        if legal == stripped:
            return wt.value

    # 6. Вхождение префикса ФЕР
    for wt, prefix in WORK_TYPE_TO_FER_PREFIX.items():
        for p in prefix.split(","):
            if p.strip() == stripped:
                return wt.value

    return None


# =============================================================================
# Внутренняя функция разрешения
# =============================================================================

def _resolve_to_work_type(input_str: str) -> Optional[WorkType]:
    """Внутренняя функция: преобразует строку в объект WorkType."""
    # Попытка по имени константы
    upper = input_str.strip().upper()
    for wt in WorkType:
        if wt.name == upper:
            return wt

    # Попытка по русскому значению
    stripped = input_str.strip()
    if stripped in _RUSSIAN_TO_WORK_TYPE:
        return _RUSSIAN_TO_WORK_TYPE[stripped]

    return None
