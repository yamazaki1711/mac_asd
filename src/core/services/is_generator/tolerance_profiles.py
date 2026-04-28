"""
tolerance_profiles — допуски геодезического контроля по СП 126.13330.2017
и связанным нормативным документам.

Расширяет DEFAULT_TOLERANCE_MM из deviation_calculator.py детальными
значениями по видам конструкций, классам точности и этапам строительства.

Использование:
    from src.core.services.is_generator.tolerance_profiles import (
        ToleranceProfile,
        SP126_PROFILES,
        get_tolerance,
    )

    # Получить допуск для конкретного вида конструкции
    tol = get_tolerance("СВАЯ_БУРОНАБИВНАЯ")  # → 50.0 мм
    tol = get_tolerance("КМ_ОСИ")              # → 5.0 мм

СП 126.13330.2017 «Геодезические работы в строительстве»:
    Таблица 5.1 — Допуски разбивочных работ
    Таблица 5.2 — Допуски передачи отметок

Связанные нормы:
    СП 70.13330.2012 — Несущие и ограждающие конструкции
    СП 45.13330.2017 — Земляные сооружения
    ГОСТ 26433.0-85  — Система обеспечения точности геометрических параметров

v12.0
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Структура профиля допуска ───────────────────────────────────────────────

@dataclass
class ToleranceProfile:
    """
    Профиль допуска для одного вида конструкций.

    Содержит нормативное значение допуска, ссылку на пункт СП/ГОСТ
    и опциональные уточнения по классам точности.
    """
    key: str                        # Ключ для lookup: "СВАЯ_БУРОНАБИВНАЯ"
    label: str                      # Человекочитаемое: "Буронабивные сваи"
    tolerance_mm: float             # Основной допуск в мм
    sp_reference: str = ""          # Ссылка на норму: "СП 126.13330.2017, табл. 5.1"
    class_precision: str = ""       # Класс точности: "I", "II", "III", "IV"
    note: str = ""                  # Примечание

    # Уточнённые допуски по подвидам (опционально)
    sub_profiles: dict[str, float] = field(default_factory=dict)
    # Пример: {"в плане": 50.0, "по высоте": 30.0, "наклон": 20.0}


# ─── Профили по СП 126.13330.2017 ───────────────────────────────────────────

SP126_PROFILES: list[ToleranceProfile] = [
    # ─── Разбивочные работы (табл. 5.1) ──────────────────────────────
    ToleranceProfile(
        key="ОСИ_ГЛАВНЫЕ",
        label="Главные оси здания/сооружения",
        tolerance_mm=5.0,
        sp_reference="СП 126.13330.2017, табл. 5.1, п.1",
        class_precision="I",
        note="Относительная погрешность не более 1:10000",
    ),
    ToleranceProfile(
        key="ОСИ_МОНТАЖНЫЕ",
        label="Монтажные оси и ориентиры",
        tolerance_mm=10.0,
        sp_reference="СП 126.13330.2017, табл. 5.1, п.2",
        class_precision="II",
        note="Для монтажа колонн, балок, панелей",
    ),
    ToleranceProfile(
        key="ОСИ_ДЕТАЛЬНЫЕ",
        label="Детальные оси для установки конструкций",
        tolerance_mm=3.0,
        sp_reference="СП 126.13330.2017, табл. 5.1, п.3",
        class_precision="I",
        note="Для ответственных конструкций",
    ),

    # ─── Передача отметок (табл. 5.2) ────────────────────────────────
    ToleranceProfile(
        key="ОТМЕТКИ_ИСХОДНЫЕ",
        label="Исходные отметки (реперы)",
        tolerance_mm=3.0,
        sp_reference="СП 126.13330.2017, табл. 5.2, п.1",
        class_precision="I",
    ),
    ToleranceProfile(
        key="ОТМЕТКИ_МОНТАЖНЫЕ",
        label="Монтажные горизонты",
        tolerance_mm=5.0,
        sp_reference="СП 126.13330.2017, табл. 5.2, п.2",
        class_precision="II",
    ),

    # ─── Фундаменты ──────────────────────────────────────────────────
    ToleranceProfile(
        key="ФУНДАМЕНТ_ЛЕНТОЧНЫЙ",
        label="Ленточные фундаменты",
        tolerance_mm=15.0,
        sp_reference="СП 70.13330.2012, табл. 4.3",
        sub_profiles={"ширина": 15.0, "смещение осей": 12.0, "отметка подошвы": 10.0},
    ),
    ToleranceProfile(
        key="ФУНДАМЕНТ_ПЛИТНЫЙ",
        label="Плитные фундаменты",
        tolerance_mm=12.0,
        sp_reference="СП 70.13330.2012, табл. 4.3",
        sub_profiles={"толщина": 10.0, "планность": 8.0},
    ),
    ToleranceProfile(
        key="РОСТВЕРК",
        label="Ростверки",
        tolerance_mm=10.0,
        sp_reference="СП 70.13330.2012, табл. 4.4",
        sub_profiles={"смещение осей": 10.0, "отметка верха": 5.0},
    ),

    # ─── Сваи ────────────────────────────────────────────────────────
    ToleranceProfile(
        key="СВАЯ_БУРОНАБИВНАЯ",
        label="Буронабивные сваи",
        tolerance_mm=50.0,
        sp_reference="СП 45.13330.2017, табл. 7.6",
        class_precision="III",
        sub_profiles={"в плане": 50.0, "по высоте": 30.0, "наклон": 20.0},
    ),
    ToleranceProfile(
        key="СВАЯ_ЗАБИВНАЯ",
        label="Забивные сваи",
        tolerance_mm=30.0,
        sp_reference="СП 45.13330.2017, табл. 7.4",
        class_precision="III",
        sub_profiles={"в плане": 30.0, "по высоте": 20.0},
    ),

    # ─── Шпунтовые ограждения ────────────────────────────────────────
    ToleranceProfile(
        key="ШПУНТ",
        label="Шпунтовое ограждение (в плане)",
        tolerance_mm=30.0,
        sp_reference="СП 45.13330.2017, табл. 7.8",
        class_precision="III",
        sub_profiles={"в плане": 30.0, "по высоте": 20.0, "наклон": 15.0},
    ),

    # ─── Металлоконструкции (КМ) ─────────────────────────────────────
    ToleranceProfile(
        key="КМ_ОСИ",
        label="Оси колонн металлических",
        tolerance_mm=5.0,
        sp_reference="СП 70.13330.2012, табл. 4.9",
        class_precision="I",
    ),
    ToleranceProfile(
        key="КМ_ОТМЕТКИ",
        label="Отметки опорных поверхностей КМ",
        tolerance_mm=5.0,
        sp_reference="СП 70.13330.2012, табл. 4.10",
        class_precision="I",
    ),
    ToleranceProfile(
        key="КМ_ВЕРТИКАЛЬНОСТЬ",
        label="Вертикальность колонн КМ",
        tolerance_mm=10.0,
        sp_reference="СП 70.13330.2012, табл. 4.11",
        class_precision="II",
        note="H/1000, но не более 15 мм",
    ),

    # ─── Бетонные/железобетонные (КЖ) ───────────────────────────────
    ToleranceProfile(
        key="КЖ_КОЛОННЫ",
        label="ЖБ колонны — смещение осей",
        tolerance_mm=8.0,
        sp_reference="СП 70.13330.2012, табл. 4.5",
        class_precision="II",
    ),
    ToleranceProfile(
        key="КЖ_ПЕРЕКРЫТИЯ",
        label="ЖБ перекрытия — отметки",
        tolerance_mm=5.0,
        sp_reference="СП 70.13330.2012, табл. 4.6",
        class_precision="I",
    ),
    ToleranceProfile(
        key="КЖ_СТЕНЫ",
        label="ЖБ стены — толщина",
        tolerance_mm=10.0,
        sp_reference="СП 70.13330.2012, табл. 4.7",
        class_precision="II",
        sub_profiles={"толщина": 10.0, "смещение осей": 8.0, "вертикальность": 10.0},
    ),

    # ─── Земляные работы ─────────────────────────────────────────────
    ToleranceProfile(
        key="ЗЕМЛЯНЫЕ_КОТЛОВАН",
        label="Котлован — отклонение отметок дна",
        tolerance_mm=50.0,
        sp_reference="СП 45.13330.2017, табл. 7.1",
        class_precision="III",
    ),
    ToleranceProfile(
        key="ЗЕМЛЯНЫЕ_ПЛАНИРОВКА",
        label="Планировка площадей",
        tolerance_mm=30.0,
        sp_reference="СП 45.13330.2017, табл. 7.2",
        class_precision="III",
    ),

    # ─── Дорожные работы ─────────────────────────────────────────────
    ToleranceProfile(
        key="ДОРОГА_ОСИ",
        label="Оси дороги",
        tolerance_mm=50.0,
        sp_reference="СП 78.13330.2012, табл. 5.1",
        class_precision="III",
    ),
    ToleranceProfile(
        key="ДОРОГА_ПРОФИЛЬ",
        label="Продольный профиль дороги",
        tolerance_mm=10.0,
        sp_reference="СП 78.13330.2012, табл. 5.2",
        class_precision="II",
    ),

    # ─── Обратная засыпка / уплотнение ──────────────────────────────
    ToleranceProfile(
        key="ОБРАТНАЯ_ЗАСЫПКА",
        label="Обратная засыпка — отметки",
        tolerance_mm=50.0,
        sp_reference="СП 45.13330.2017, табл. 7.3",
        class_precision="III",
    ),
]


# ─── Индекс для быстрого lookup ───────────────────────────────────────────────

_PROFILE_INDEX: dict[str, ToleranceProfile] = {}


def _build_index() -> None:
    """Строит индекс профилей по ключам."""
    global _PROFILE_INDEX
    for p in SP126_PROFILES:
        _PROFILE_INDEX[p.key] = p
        # Также индексируем по лейблу (uppercase) для fuzzy matching
        _PROFILE_INDEX[p.label.upper()] = p


_build_index()


def get_tolerance(key: str) -> float:
    """
    Возвращает допуск по ключу профиля.

    Поиск по:
      1. Точному ключу (СВАЯ_БУРОНАБИВНАЯ)
      2. Upper-case лейблу (БУРОНАБИВНЫЕ СВАИ)
      3. Partial match: ключ содержит искомую подстроку

    Fallback: DEFAULT_TOLERANCE_MM["_DEFAULT"] = 20.0 мм
    """
    # Точное совпадение по ключу
    if key in _PROFILE_INDEX:
        return _PROFILE_INDEX[key].tolerance_mm

    # Upper-case совпадение
    key_upper = key.upper()
    if key_upper in _PROFILE_INDEX:
        return _PROFILE_INDEX[key_upper].tolerance_mm

    # Partial match: ищем профиль, чей ключ содержит подстроку
    for k, profile in _PROFILE_INDEX.items():
        if key_upper in k:
            return profile.tolerance_mm

    # Fallback
    logger.debug(f"Профиль допуска не найден для '{key}' — используется 20.0 мм (default)")
    return 20.0


def get_profile(key: str) -> Optional[ToleranceProfile]:
    """Возвращает полный ToleranceProfile по ключу (или None)."""
    if key in _PROFILE_INDEX:
        return _PROFILE_INDEX[key]

    key_upper = key.upper()
    if key_upper in _PROFILE_INDEX:
        return _PROFILE_INDEX[key_upper]

    for k, profile in _PROFILE_INDEX.items():
        if key_upper in k:
            return profile

    return None


def build_tolerance_map() -> dict[str, float]:
    """
    Строит полный tolerance_map для DeviationCalculator
    из всех профилей СП 126.13330.2017.

    Использование:
        calc = DeviationCalculator(tolerance_map=build_tolerance_map())
    """
    result: dict[str, float] = {}
    for p in SP126_PROFILES:
        result[p.key] = p.tolerance_mm
        # Добавляем подвиды
        for sub_key, sub_tol in p.sub_profiles.items():
            result[f"{p.key}_{sub_key.upper().replace(' ', '_')}"] = sub_tol
    return result


def list_profiles() -> list[dict]:
    """Возвращает список всех профилей допусков (для API/documentation)."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "tolerance_mm": p.tolerance_mm,
            "sp_reference": p.sp_reference,
            "class_precision": p.class_precision,
            "sub_profiles": p.sub_profiles,
            "note": p.note,
        }
        for p in SP126_PROFILES
    ]
