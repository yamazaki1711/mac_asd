"""
PPR Generator — Раздел 7: Потребность в технике.

Формирует сводную ведомость потребности в строительных
машинах, механизмах и оборудовании на основе данных из ТТК.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from ..schemas import PPRInput, TTKResult, SectionResult, TTKResource


def _estimate_machine_hours(machine_name: str, ttks: List[TTKResult]) -> float:
    """
    Грубая оценка машино-часов: суммирует ttk.total_machine_hours
    пропорционально доле данной машины среди всех машин ТТК.
    """
    total = 0.0
    for ttk in ttks:
        matching = [m for m in ttk.resources.machines if m.name == machine_name]
        for m in matching:
            # Если в ТТК несколько машин, распределяем пропорционально
            share = 1.0 / max(len(ttk.resources.machines), 1)
            total += ttk.total_machine_hours * share * m.quantity
    return round(total, 1)


def generate_machinery(input: PPRInput, ttks: List[TTKResult]) -> SectionResult:
    """
    Генерирует раздел «Потребность в технике» (Раздел 7).

    Агрегирует все машины и механизмы из ttks.resources.machines,
    группирует по наименованию, вычисляет суммарное количество.
    """
    # ── Агрегация машин: name → (qty, unit) ──
    aggregated: Dict[str, Tuple[float, str]] = {}
    for ttk in ttks:
        for machine in ttk.resources.machines:
            name = machine.name.strip()
            if name in aggregated:
                prev_qty, unit = aggregated[name]
                aggregated[name] = (prev_qty + machine.quantity, unit)
            else:
                aggregated[name] = (machine.quantity, machine.unit)

    # ── Сортировка по наименованию ──
    sorted_entries: List[Tuple[str, Tuple[float, str]]] = sorted(
        aggregated.items(), key=lambda kv: kv[0].lower()
    )

    # ── Построение таблицы ──
    rows_md: List[str] = []
    table_data: List[List[Any]] = []

    if sorted_entries:
        rows_md.append(
            "| № | Наименование машин и механизмов | Марка / тип | "
            "Кол-во | Ед. | Маш.-час (расч.) | Примечание |\n"
            "|---|--------------------------------|-------------|"
            "--------|-----|------------------|------------|"
        )
        for i, (name, (qty, unit)) in enumerate(sorted_entries, 1):
            # Estimate machine-hours for this entry
            mh = _estimate_machine_hours(name, ttks)
            mh_str = str(mh) if mh > 0 else "—"

            # Try to extract brand/mark from name (e.g., "Экскаватор Hitachi ZX200" → "Hitachi ZX200")
            brand = "по проекту"
            words = name.split()
            # If name looks like "тип Brand Model", take Brand part
            for j, w in enumerate(words):
                if w[0].isupper() and len(w) > 1 and j > 0:
                    brand = " ".join(words[j:])
                    # Limit brand length
                    if len(brand) > 30:
                        brand = brand[:27] + "..."
                    break

            # Determine note
            note = "Основная машина"

            rows_md.append(
                f"| {i} | {name} | {brand} | {qty} | {unit} | {mh_str} | {note} |"
            )
            table_data.append([str(i), name, brand, str(qty), unit, mh_str, note])

    machinery_table = "\n".join(rows_md) if rows_md else (
        "*Данные по строительной технике из ТТК отсутствуют.*"
    )

    # ── Суммарные показатели ──
    total_machines = sum(qty for qty, _ in aggregated.values())
    total_machine_hours = round(sum(
        t.total_machine_hours for t in ttks
    ), 1)

    # ── Группировка по типам ──
    type_groups: Dict[str, List[str]] = defaultdict(list)
    for name in aggregated:
        lower = name.lower()
        if any(kw in lower for kw in ("экскаватор", "бульдозер", "погрузчик", "грейдер", "скрепер", "каток")):
            type_groups["Землеройная техника"].append(name)
        elif any(kw in lower for kw in ("кран", "автокран", "башенный", "манипулятор", "подъёмник", "лебёдка")):
            type_groups["Грузоподъёмная техника"].append(name)
        elif any(kw in lower for kw in ("автосамосвал", "самосвал", "бортовой", "тягач", "полуприцеп")):
            type_groups["Автотранспорт"].append(name)
        elif any(kw in lower for kw in ("бетон", "раствор", "вибро", "компрессор", "опалуб")):
            type_groups["Бетонное оборудование"].append(name)
        elif any(kw in lower for kw in ("свар", "резак", "шлиф")):
            type_groups["Сварочное оборудование"].append(name)
        else:
            type_groups["Прочая техника"].append(name)

    type_groups_lines: List[str] = []
    for group_name, items in sorted(type_groups.items()):
        if items:
            type_groups_lines.append(f"**{group_name}**:")
            for item in sorted(items):
                qty, _ = aggregated[item]
                type_groups_lines.append(f"  - {item} — {qty} ед.")

    type_groups_md = "\n".join(type_groups_lines) if type_groups_lines else "*Нет данных*"

    # ── Content ──
    content = f"""## Раздел 7. Потребность в строительных машинах и механизмах

### 7.1. Общие положения

Потребность в строительных машинах, механизмах и средствах
малой механизации определена на основании технологических
карт на отдельные виды работ, ПОС и проекта организации
строительства. Расчёт выполнен в соответствии с
СП 48.13330.2019 и МДС 12-46.2008.

Объект: **{input.object_name}**
Шифр проекта: **{input.project_code}**

### 7.2. Сводная ведомость строительных машин и механизмов

{machinery_table}

### 7.3. Итоговые показатели

| Показатель | Значение |
|------------|----------|
| Общее количество единиц техники | **{total_machines}** |
| Общие машино-часы (расчётные) | **{total_machine_hours}** маш.-ч |
| Количество уникальных типов техники | **{len(aggregated)}** |
| Базовое количество ТТК (источников данных) | **{len(ttks)}** |

### 7.4. Группировка по типам техники

{type_groups_md}

### 7.5. Организация эксплуатации

- Доставка строительной техники на объект осуществляется
  на низкорамных тралах и своим ходом (для самоходной техники).
- Ответственным за эксплуатацию строительных машин назначается
  механик (приказом по организации).
- Ежесменное техническое обслуживание (ЕТО) проводится
  машинистом перед началом работ с записью в журнале.
- Заправка ГСМ производится на стационарном посту заправки
  или с помощью передвижного топливозаправщика.
- Стоянка техники в нерабочее время — на спланированной
  площадке с твёрдым покрытием, ограждённой и освещённой.
- Ремонт и ТО выполняются силами передвижной ремонтной
  мастерской или на базе подрядчика.

### 7.6. Мероприятия по охране труда при эксплуатации машин

- Все машины и механизмы должны быть зарегистрированы
  в органах Ростехнадзора (при необходимости) и иметь
  разрешение на ввод в эксплуатацию.
- Машинисты и операторы строительных машин должны иметь
  удостоверения на право управления соответствующей техникой.
- Работа машин в охранных зонах ЛЭП, газопроводов и прочих
  коммуникаций производится по наряду-допуску.
- Звуковая и световая сигнализация — обязательна для всех
  машин, работающих на стройплощадке.
"""

    tables = [
        {
            "title": "Сводная ведомость строительных машин и механизмов",
            "headers": [
                "№", "Наименование машин и механизмов",
                "Марка / тип", "Кол-во", "Ед.",
                "Маш.-час (расч.)", "Примечание",
            ],
            "rows": table_data,
        },
    ]

    return SectionResult(
        section_id="machinery",
        title="Раздел 7. Потребность в строительных машинах и механизмах",
        content=content,
        page_count=max(2, len(content.split("\n")) // 35),
        tables=tables,
        metadata={
            "total_machines": total_machines,
            "total_machine_hours": total_machine_hours,
            "unique_machine_types": len(aggregated),
            "ttks_source": [t.work_type for t in ttks],
            "type_groups": {
                g: len(items) for g, items in type_groups.items() if items
            },
        },
    )
