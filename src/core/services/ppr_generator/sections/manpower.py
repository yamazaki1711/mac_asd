"""
PPR Generator — Раздел 6: Потребность в рабочих кадрах.

Формирует сводную ведомость потребности в рабочих кадрах
по профессиям и разрядам на основе данных из ТТК.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from ..schemas import PPRInput, TTKResult, SectionResult, TTKResource


def _parse_worker_entry(worker: TTKResource) -> Tuple[str, str]:
    """
    Парсит имя рабочего из ТТК в формат (профессия, разряд).

    Examples:
        "Экскаваторщик 6 разряда" → ("Экскаваторщик", "6")
        "Землекоп 3 разряда" → ("Землекоп", "3")
        "Геодезист" → ("Геодезист", "—")
        "Бетонщик 4 разряда" → ("Бетонщик", "4")
    """
    name = worker.name.strip()
    rank = "—"
    profession = name

    # Try to split on "разряда" or "разряд"
    for sep in (" разряда", " разряд"):
        if sep in name.lower():
            parts = name.lower().split(sep)
            tail = parts[-1].strip()
            profession_part = sep.join(parts[:-1]).strip()
            # Try to find the rank digit in the last bit before "разряда"
            words = profession_part.split()
            if words:
                last_word = words[-1]
                # Check if last word is a digit or starts with digit
                if last_word.isdigit():
                    rank = last_word
                    profession = " ".join(words[:-1]).strip()
                else:
                    # Try to extract from tail
                    tail_words = tail.split()
                    if tail_words:
                        for tw in tail_words:
                            if tw.isdigit():
                                rank = tw
                                break
            # Capitalize profession
            profession = profession.strip()
            if profession:
                profession = profession[0].upper() + profession[1:] if len(profession) > 1 else profession.upper()
            break

    return (profession, rank)


def generate_manpower(input: PPRInput, ttks: List[TTKResult]) -> SectionResult:
    """
    Генерирует раздел «Потребность в рабочих кадрах» (Раздел 6).

    Агрегирует всех рабочих из ttks.resources.workers, группирует
    по профессии и разряду, вычисляет суммарное количество.
    """
    # ── Агрегация рабочих: (профессия, разряд) → total_qty ──
    aggregated: Dict[Tuple[str, str], float] = defaultdict(float)

    for ttk in ttks:
        for worker in ttk.resources.workers:
            profession, rank = _parse_worker_entry(worker)
            key = (profession, rank)
            aggregated[key] += worker.quantity

    # ── Сортировка: сначала по профессии, потом по разряду ──
    sorted_entries: List[Tuple[Tuple[str, str], float]] = sorted(
        aggregated.items(),
        key=lambda kv: (kv[0][0].lower(), kv[0][1] != "—", kv[0][1]),
    )

    # ── Построение таблицы ──
    rows_md: List[str] = []
    table_data: List[List[Any]] = []

    if sorted_entries:
        rows_md.append(
            "| № | Профессия | Разряд | Кол-во, чел. |\n"
            "|---|-----------|--------|-------------|"
        )
        for i, ((prof, rank), qty) in enumerate(sorted_entries, 1):
            rows_md.append(f"| {i} | {prof} | {rank} | {qty} |")
            table_data.append([str(i), prof, rank, qty])

    manning_table = "\n".join(rows_md) if rows_md else (
        "*Данные по рабочим кадрам из ТТК отсутствуют.*"
    )

    # ── Суммарная численность рабочих ──
    total_workers = sum(qty for _, qty in sorted_entries)

    # ── Уникальные профессии ──
    unique_professions = sorted({p for (p, _), _ in sorted_entries})

    professions_list = "\n".join(
        f"- {p}" for p in unique_professions
    ) if unique_professions else "- *Нет данных*"

    # ── Content ──
    content = f"""## Раздел 6. Потребность в рабочих кадрах

### 6.1. Общие положения

Потребность в рабочих кадрах определена на основании
технологических карт на отдельные виды работ с учётом
совмещения профессий и поточного метода организации
строительства. Расчёт выполнен в соответствии с
СП 48.13330.2019 и МДС 12-46.2008.

Объект: **{input.object_name}**
Шифр проекта: **{input.project_code}**

### 6.2. Сводная ведомость рабочих кадров

{manning_table}

### 6.3. Итоговые показатели

| Показатель | Значение |
|------------|----------|
| Общая численность рабочих (пиковая) | **{total_workers}** чел. |
| Количество уникальных профессий | **{len(unique_professions)}** |
| Базовое количество ТТК (источников данных) | **{len(ttks)}** |

### 6.4. Структура бригад по профессиям

{professions_list}

### 6.5. Организация труда

- Бригады формируются по профессиональному признаку.
- Допускается совмещение профессий при условии наличия
  у рабочих соответствующей квалификации и аттестации.
- Инженерно-технические работники (ИТР): производитель
  работ, мастер (прораб), инженер ПТО, инженер-лаборант —
  назначаются приказом по организации.
- Медицинские осмотры и инструктажи проводятся в
  соответствии с ТК РФ и Приказом Минтруда № 988н/1420н.
- Рабочие, выполняющие работы с повышенной опасностью
  (стропальщики, сварщики, монтажники-высотники),
  проходят ежегодную аттестацию.
"""

    tables = [
        {
            "title": "Сводная ведомость рабочих кадров",
            "headers": ["№", "Профессия", "Разряд", "Кол-во, чел."],
            "rows": table_data,
        },
    ]

    return SectionResult(
        section_id="manpower",
        title="Раздел 6. Потребность в рабочих кадрах",
        content=content,
        page_count=max(1, len(content.split("\n")) // 38),
        tables=tables,
        metadata={
            "total_workers": total_workers,
            "unique_professions": len(unique_professions),
            "professions": unique_professions,
            "ttks_source": [t.work_type for t in ttks],
        },
    )
