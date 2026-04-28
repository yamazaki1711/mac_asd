"""
PPR Generator — Section: General Data (Общие данные).

Раздел 1 Пояснительной записки ППР: характеристика объекта,
исходные данные, нормативная база, сроки строительства.
"""

from __future__ import annotations

from typing import List

from ..schemas import PPRInput, SectionResult, TTKResult

__all__ = ["generate_general_data"]


def generate_general_data(input: PPRInput, ttks: List[TTKResult]) -> SectionResult:
    """
    Генерирует раздел «1. Общие данные» Пояснительной записки ППР.

    Содержит:
      - Характеристику объекта строительства
      - Исходные данные для разработки ППР
      - Нормативную базу
      - Сроки строительства (из input.construction_schedule)
      - Климатический район и условия строительства
    """
    md = _build_content(input)
    return SectionResult(
        section_id="general_data",
        title="1. Общие данные",
        content=md,
        page_count=_estimate_pages(md),
    )


# ═══════════════════════════════════════════════════════════════════════
# Content builder
# ═══════════════════════════════════════════════════════════════════════

def _build_content(inp: PPRInput) -> str:
    parts: List[str] = []

    parts.append("## 1. Общие данные\n")
    parts.append(_object_characteristics(inp))
    parts.append(_source_data(inp))
    parts.append(_normative_base())
    parts.append(_construction_schedule(inp))
    parts.append(_climate_and_conditions(inp))

    return "\n\n".join(parts)


# ── 1.1 Характеристика объекта ────────────────────────────────────────

def _object_characteristics(inp: PPRInput) -> str:
    lines = [
        "### 1.1 Характеристика объекта строительства",
        "",
        f"| Параметр | Значение |",
        f"|---|---|",
        f"| Наименование объекта | **{inp.object_name}** |",
        f"| Шифр проекта | {inp.project_code} |",
        f"| Заказчик | {inp.customer.name} |",
        f"| ИНН заказчика | {inp.customer.inn or '—'} |",
        f"| Генеральный подрядчик | {inp.contractor.name} |",
        f"| ИНН подрядчика | {inp.contractor.inn or '—'} |",
    ]

    # Добавляем информацию о разработчике ППР
    dev = inp.developer
    if dev.organization:
        lines.append(f"| Разработчик ППР | {dev.organization} |")
    if dev.chief_engineer:
        lines.append(f"| Главный инженер проекта | {dev.chief_engineer} |")

    # Виды работ
    if inp.work_types:
        wt_list = ", ".join(wt.name for wt in inp.work_types)
        lines.append(f"| Виды работ | {wt_list} |")

    # Основные конструкции
    if inp.structural_solutions:
        ss_list = ", ".join(s.describe or s.drawing_code for s in inp.structural_solutions)
        lines.append(f"| Основные конструкции | {ss_list} |")

    lines.append("")
    return "\n".join(lines)


# ── 1.2 Исходные данные ───────────────────────────────────────────────

def _source_data(inp: PPRInput) -> str:
    lines = [
        "### 1.2 Исходные данные для разработки ППР",
        "",
        "Проект производства работ разработан на основании следующих исходных данных:",
        "",
    ]

    items = [
        "Задание на разработку ППР, утверждённое заказчиком",
        f"Проектная документация объекта «{inp.object_name}» (шифр {inp.project_code})",
        f"Рабочая документация (шифр {inp.project_code})",
        "Проект организации строительства (ПОС) в составе утверждённой проектной документации",
        "Строительный генеральный план",
    ]

    if inp.material_specs:
        items.append("Спецификации материалов и оборудования (разделы ПД/РД)")

    if inp.quality_requirements:
        items.append("Требования к контролю качества работ (входной, операционный, приёмочный)")

    for item in items:
        lines.append(f"- {item}")

    # Информация о разрешительной документации
    lines.append("")
    lines.extend([
        "**Разрешительная документация:**",
        "",
        "- Разрешение на строительство",
        "- Договор строительного подряда",
        "- Акт допуска на объект",
    ])

    lines.append("")
    return "\n".join(lines)


# ── 1.3 Нормативная база ──────────────────────────────────────────────

def _normative_base() -> str:
    lines = [
        "### 1.3 Нормативная база",
        "",
        "ППР разработан в соответствии с требованиями следующих нормативных документов:",
        "",
        "| Шифр документа | Наименование |",
        "|---|---|",
        "| **СНиП 12-01-2004** | Организация строительства |",
        "| **СП 48.13330.2019** | Организация строительства. Актуализированная редакция СНиП 12-01-2004 |",
        "| **СНиП 12-03-2001** | Безопасность труда в строительстве. Часть 1. Общие требования |",
        "| **СНиП 12-04-2002** | Безопасность труда в строительстве. Часть 2. Строительное производство |",
        "| **СП 49.13330.2010** | Безопасность труда в строительстве |",
        "| **ГОСТ 21.1101-2013** | СПДС. Основные требования к проектной и рабочей документации |",
        "| **СП 70.13330.2012** | Несущие и ограждающие конструкции |",
        "| **СП 45.13330.2017** | Земляные сооружения, основания и фундаменты |",
        "| **СП 63.13330.2018** | Бетонные и железобетонные конструкции. Основные положения |",
        "| **СП 16.13330.2017** | Стальные конструкции |",
        "| **ГОСТ 12.3.002-2014** | ССБТ. Процессы производственные. Общие требования безопасности |",
        "",
        "Кроме того, при производстве работ руководствоваться:",
        "",
        "- " + " \\\n  ".join([
            "Федеральным законом № 384-ФЗ «Технический регламент о безопасности зданий и сооружений»",
            "Федеральным законом № 123-ФЗ «Технический регламент о требованиях пожарной безопасности»",
            "Постановлением Правительства РФ № 87 «О составе разделов проектной документации»",
            "Правилами противопожарного режима в Российской Федерации",
            "Отраслевыми типовыми технологическими картами",
        ]),
        "",
    ]
    return "\n".join(lines)


# ── 1.4 Сроки строительства ───────────────────────────────────────────

def _construction_schedule(inp: PPRInput) -> str:
    sched = inp.construction_schedule
    lines = [
        "### 1.4 Сроки строительства",
        "",
        f"| Показатель | Значение |",
        f"|---|---|",
        f"| Начало строительства | {sched.construction_start.strftime('%d.%m.%Y')} |",
        f"| Окончание строительства | {sched.construction_end.strftime('%d.%m.%Y')} |",
        f"| Общая продолжительность | {sched.total_duration_days} календарных дней |",
    ]

    if sched.stages:
        lines.append("")
        lines.append("**Этапы строительства:**")
        lines.append("")
        lines.append("| № п/п | Наименование этапа | Дата начала | Дата окончания | Продолж. (дн.) |")
        lines.append("|---|---|---|---|---|")
        for i, stage in enumerate(sched.stages, 1):
            duration = stage.duration_days or _days_between(stage.start_date, stage.end_date)
            lines.append(
                f"| {i} | {stage.name} | "
                f"{stage.start_date.strftime('%d.%m.%Y')} | "
                f"{stage.end_date.strftime('%d.%m.%Y')} | "
                f"{duration} |"
            )

    lines.append("")
    return "\n".join(lines)


# ── 1.5 Климатический район и условия строительства ───────────────────

def _climate_and_conditions(inp: PPRInput) -> str:
    lines = [
        "### 1.5 Климатический район и условия строительства",
        "",
        "Строительство ведётся на территории Российской Федерации.",
        "",
    ]

    # Собираем климатические данные из ТТК (если есть scope с climate_zone)
    climate_zones = set()
    for ttk in ttks_ref(inp, []):
        if ttk.scope.climate_zone:
            climate_zones.add(ttk.scope.climate_zone)

    if climate_zones:
        lines.append(f"**Климатический район:** {', '.join(sorted(climate_zones))}")
    else:
        lines.append("**Климатический район:** II (умеренно-континентальный, уточняется по СП 131.13330)")

    lines.extend([
        "",
        "**Характеристики площадки строительства:**",
        "",
    ])

    # Стеснённые условия и ограничения площадки
    if inp.site_constraints:
        lines.append("**Ограничения площадки:**")
        lines.append("")
        for c in inp.site_constraints:
            lines.append(f"- **{c.constraint_type}:** {c.description}")
            if c.zone_bounds:
                lines.append(f"  Границы зоны: {c.zone_bounds}")
        lines.append("")

    lines.extend([
        "**Условия производства работ:**",
        "",
        "- Подъездные пути: существующие автомобильные дороги, внутриплощадочные проезды",
        "- Водоснабжение: привозная вода / подключение к существующим сетям",
        "- Электроснабжение: от существующих сетей / дизель-генераторные установки",
        "- Водоотведение: организованный отвод поверхностных вод, дренаж",
        "- Связь: мобильная, при необходимости — радиофицированная",
        "",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _days_between(a, b):
    """Количество дней между двумя датами (не включая начальную, включая конечную)."""
    return max(1, (b - a).days)


def ttks_ref(inp: PPRInput, ttks: List[TTKResult]) -> List[TTKResult]:
    """Возвращает TTKResult — параметр зарезервирован для совместимости."""
    return ttks


def _estimate_pages(content: str) -> int:
    """Грубая оценка количества страниц: ~2500 знаков на страницу."""
    return max(1, (len(content) + 2499) // 2500)
