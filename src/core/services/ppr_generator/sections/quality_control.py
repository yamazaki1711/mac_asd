"""
PPR Generator — Раздел 5: Контроль качества.

Формирует сводный раздел по контролю качества строительно-монтажных
работ: входной, операционный, приёмочный контроль, оформление
скрытых работ и исполнительной документации.
"""
from __future__ import annotations

from typing import List

from ..schemas import PPRInput, TTKResult, SectionResult


def generate_quality_control(input: PPRInput, ttks: List[TTKResult]) -> SectionResult:
    """
    Генерирует раздел «Контроль качества» (Раздел 5 ПЗ).

    Агрегирует данные контроля качества из всех ТТК,
    а также глобальные требования к качеству из ПОС/ПД.
    """
    # ── Сбор операционного контроля из ТТК ──
    op_control_rows: List[str] = []
    for ttk in ttks:
        for qc in ttk.quality.operational_control:
            op_control_rows.append(
                f"| {ttk.work_type} | {qc.parameter} | {qc.tolerance} | "
                f"{qc.method} | {qc.instrument or '—'} | "
                f"{qc.frequency or '—'} | {qc.gost_ref or '—'} |"
            )

    op_control_table: str
    if op_control_rows:
        header = (
            "| Вид работ | Параметр | Допуск | Метод контроля | "
            "Прибор | Периодичность | Норматив |\n"
            "|-----------|----------|--------|---------------|"
            "--------|--------------|----------|"
        )
        op_control_table = header + "\n" + "\n".join(op_control_rows)
    else:
        op_control_table = "*Операционный контроль не задан в ТТК.*"

    # ── Сбор скрытых работ из ТТК ──
    hidden_works: List[str] = []
    for ttk in ttks:
        for hw in ttk.quality.隐蔽_works_certification:
            if hw not in hidden_works:
                hidden_works.append(hw)

    # ── Входной контроль из ТТК ──
    incoming_items: List[str] = []
    for ttk in ttks:
        for item in ttk.quality.incoming_control:
            if item not in incoming_items:
                incoming_items.append(f"- {item}")

    incoming_text = "\n".join(incoming_items) if incoming_items else (
        "- Проверка паспортов, сертификатов соответствия "
        "и качества на поступающие материалы (согласно ГОСТ, СП)"
    )

    # ── Приёмочный контроль из ТТК ──
    acceptance_items: List[str] = []
    for ttk in ttks:
        for item in ttk.quality.acceptance_control:
            if item not in acceptance_items:
                acceptance_items.append(f"- {item}")

    acceptance_text = "\n".join(acceptance_items) if acceptance_items else (
        "- Приёмочный контроль конструкций и работ в соответствии "
        "с проектной документацией и СП 48.13330.2019"
    )

    # ── Глобальные требования к качеству из ПД ──
    qr_items: List[str] = []
    for qr in input.quality_requirements:
        qr_items.append(
            f"| {qr.parameter} | {qr.tolerance or 'по проекту'} | "
            f"{qr.control_method or 'инструментальный'} | "
            f"{qr.gost_ref or 'СП 48.13330'} |"
        )

    qr_table: str
    if qr_items:
        qr_header = (
            "| Параметр | Допуск | Метод контроля | Норматив |\n"
            "|----------|--------|----------------|----------|"
        )
        qr_table = qr_header + "\n" + "\n".join(qr_items)
    else:
        qr_table = "*Глобальные требования к качеству не заданы в ПД.*"

    # ── Content ──
    content = f"""## Раздел 5. Контроль качества строительно-монтажных работ

### 5.1. Общие положения

Контроль качества строительно-монтажных работ на объекте
**{input.object_name}** осуществляется в соответствии с:

- СП 48.13330.2019 «Организация строительства»;
- Градостроительным кодексом РФ;
- Проектной и рабочей документацией (шифр: **{input.project_code}**);
- Технологическими картами на отдельные виды работ.

Контроль качества включает три стадии: **входной**, **операционный**
и **приёмочный** (оценка соответствия).

### 5.2. Входной контроль

Входной контроль поступающих на объект материалов,
изделий и конструкций выполняет служба качества подрядчика
при участии технического надзора заказчика. Контролируются:

{incoming_text}

Результаты входного контроля регистрируются в **журнале
входного контроля** (форма по ГОСТ 24297).

### 5.3. Операционный контроль

Операционный контроль выполняется в процессе производства
работ и после завершения каждой технологической операции
производителем работ (мастером/прорабом) с привлечением
строительной лаборатории (при необходимости).

{op_control_table}

### 5.4. Приёмочный контроль

Приёмочный контроль (оценка соответствия) выполняется
при приёмке законченных конструктивных элементов, видов
работ и объекта в целом комиссией в составе представителей:

- технического надзора заказчика;
- авторского надзора проектной организации;
- подрядчика (производитель работ);
- строительной лаборатории (при необходимости).

Состав приёмочного контроля:

{acceptance_text}

### 5.5. Оформление скрытых работ

К скрытым работам относятся работы, результат которых
не может быть проверен после выполнения последующих.
Оформление актов освидетельствования скрытых работ
производится по форме, установленной Приказом
Ростехнадзора от 26.12.2006 № 1128 (РД-11-02-2006).

**Перечень скрытых работ, подлежащих освидетельствованию:**

{chr(10).join(f'- {hw}' for hw in hidden_works) if hidden_works else '- Определяется по мере производства работ'}

### 5.6. Глобальные требования к качеству (ПД)

{qr_table}

### 5.7. Исполнительная документация

В процессе строительства ведётся следующий комплект
исполнительной документации:

- Общий журнал работ (форма КС-6);
- Журнал входного контроля материалов и конструкций;
- Журнал бетонных работ;
- Журнал сварочных работ;
- Журнал антикоррозионной защиты;
- Акты освидетельствования скрытых работ;
- Акты промежуточной приёмки ответственных конструкций;
- Исполнительные геодезические схемы;
- Паспорта и сертификаты на материалы и изделия.
"""

    # ── Build tables for SectionResult ──
    op_rows_data = []
    for ttk in ttks:
        for qc in ttk.quality.operational_control:
            op_rows_data.append([
                ttk.work_type,
                qc.parameter,
                qc.tolerance,
                qc.method,
                qc.instrument or "—",
                qc.frequency or "—",
                qc.gost_ref or "—",
            ])

    tables = [
        {
            "title": "Сводная таблица операционного контроля",
            "headers": [
                "Вид работ", "Параметр", "Допуск",
                "Метод контроля", "Прибор", "Периодичность", "Норматив",
            ],
            "rows": op_rows_data,
        },
        {
            "title": "Глобальные требования к качеству (ПД)",
            "headers": ["Параметр", "Допуск", "Метод контроля", "Норматив"],
            "rows": [
                [qr.parameter, qr.tolerance or "по проекту",
                 qr.control_method or "инструментальный",
                 qr.gost_ref or "СП 48.13330"]
                for qr in input.quality_requirements
            ],
        },
    ]

    return SectionResult(
        section_id="quality_control",
        title="Раздел 5. Контроль качества строительно-монтажных работ",
        content=content,
        page_count=max(3, len(content.split("\n")) // 35),
        tables=tables,
        metadata={
            "operational_checks_count": sum(
                len(t.quality.operational_control) for t in ttks
            ),
            "hidden_works_count": len(hidden_works),
            "quality_reqs_from_pd": len(input.quality_requirements),
            "ttks_referenced": len(ttks),
        },
    )
