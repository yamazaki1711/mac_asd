#!/usr/bin/env python3
"""Generate CORRECTED PTO inspection report for LOS project.
Based on manual page-by-page VLM analysis — NOT buggy agent pipeline."""
import os
from fpdf import FPDF

PROJECT = 'ЛОС — Шпунтовое ограждение (Петропавловск-Камчатский)'
OUT = 'data/inspection_report_LOS_v2.pdf'

# ═══════════════════════════════════════════════
# REAL DATA — from page-by-page VLM analysis
# ═══════════════════════════════════════════════

# Completeness matrix per 344/пр (13 mandatory positions)
MATRIX_344 = [
    ("1",  "Акт ГРО",                    "НЕТ", "Отсутствует полностью"),
    ("2",  "Разбивка осей",              "НЕТ", "Отсутствует"),
    ("3",  "АОСР (прил.3 к 344/пр)",     "ЧАСТ", "2 шт. есть, но ОБА НЕ ПОДПИСАНЫ — недействительны"),
    ("4",  "АООК (прил.4)",              "НЕТ", "Отсутствует"),
    ("5",  "АОУСИТО (прил.5)",           "НЕТ", "Отсутствует"),
    ("6",  "Замечания стройконтроля",    "НЕТ", "Отсутствуют"),
    ("7",  "Чертежи (проектные)",        "НЕТ", "Отсутствуют — только исполнительные схемы"),
    ("8",  "ИГС (ГОСТ Р 51872-2019)",    "НЕТ", "Отсутствует"),
    ("9",  "Исполнительные схемы",       "ЧАСТ", "2 шт.: ИЗМ_04 (погружение), ИЗМ_02 (демонтаж). Замечания: нет штампов, осей, масштаба"),
    ("10", "Акты испытаний",             "НЕТ", "Отсутствуют"),
    ("11", "Лабораторные заключения",    "НЕТ", "Отсутствуют"),
    ("12", "Входной контроль",           "ЧАСТ", "Сертификат №21514 от 21.11.22 упомянут в АОСР, но ФАЙЛ ОТСУТСТВУЕТ. ЖВК нет. Паспортов нет."),
    ("13", "ОЖР + спецжурналы",          "ЧАСТ", "Журнал погружения шпунта есть. ОЖР отсутствует."),
]

# Real issues found
ISSUES = [
    # CRITICAL — делают ИД недействительной
    {"doc": "АОСР №1-ПШ (погружение шпунта, 11.08.25)", "issue": "НЕ ПОДПИСАН — отсутствуют подписи всех сторон. Документ недействителен", "severity": "critical"},
    {"doc": "АОСР №2-ДШ (демонтаж шпунта, 17.11.25)", "issue": "НЕ ПОДПИСАН — отсутствуют подписи всех сторон. Документ недействителен", "severity": "critical"},
    {"doc": "Сертификат качества №21514 от 21.11.22", "issue": "Упомянут в АОСР (стр.2 погружения, 3 ссылки), но ФИЗИЧЕСКИ ОТСУТСТВУЕТ в пакете. Входной контроль не подтверждён", "severity": "critical"},
    {"doc": "Весь пакет", "issue": "Из 13 обязательных позиций 344/пр: 0 полностью готовы, 7 отсутствуют, 6 с замечаниями", "severity": "critical"},

    # HIGH — требуют исправления до приёмки
    {"doc": "АОСР_погружение, стр.2", "issue": "Стр.2 содержит ДРУГОЙ акт (разработка котлована) вместо приложений к основному акту. Нарушение структуры документа", "severity": "high"},
    {"doc": "АОСР_демонтаж, стр.2", "issue": "Стр.2 содержит ДРУГОЙ акт (устройство покрытия) вместо приложений к основному акту. Нарушение структуры документа", "severity": "high"},
    {"doc": "ИС Демонтаж (ИЗМ_02)", "issue": "ИС указана как «Приложение 1 к акту №1-ДШ», но акта №1-ДШ в пакете нет. Ссылка на несуществующий документ", "severity": "high"},
    {"doc": "ИС Демонтаж (ИЗМ_02)", "issue": "Не заполнен штамп по ГОСТ Р 21.101-2020: нет названия организации, подписей, дат", "severity": "high"},
    {"doc": "ИС Погружение (ИЗМ_04)", "issue": "Не заполнен штамп по ГОСТ Р 21.101-2020: нет названия организации, подписей, дат", "severity": "high"},
    {"doc": "Обе ИС", "issue": "Много изменений: ИЗМ_04 и ИЗМ_02. Где изм.01 и 03? Нарушение порядка внесения изменений", "severity": "high"},
    {"doc": "Весь пакет", "issue": "Отсутствуют паспорта качества на шпунт Л5-УМ и ЛС-УМ (входной контроль не подтверждён)", "severity": "high"},

    # MEDIUM
    {"doc": "АОСР_демонтаж, стр.2", "issue": "Исполнительная схема указана как «№ б/н» (без номера) — невозможно идентифицировать", "severity": "medium"},
    {"doc": "КС-2 погружение, КС-3, КС-6а", "issue": "Финансово-сметные документы не входят в состав ИД по 344/пр. Исключить из пакета", "severity": "medium"},
    {"doc": "Счет №27, УПД №27", "issue": "Бухгалтерские документы не относятся к ИД. Исключить", "severity": "medium"},
    {"doc": "Протокол разногласий", "issue": "Договорной документ, не относится к ИД. Исключить", "severity": "medium"},
    {"doc": "Договор РТК№170 от 19.05.25", "issue": "Договор подряда — не входит в состав ИД. Хранить отдельно", "severity": "medium"},
    {"doc": "Журнал погружения шпунта", "issue": "Только 48 записей из 100 шпунтин. Неполный. Нет подписей лиц, осуществляющих строительство", "severity": "medium"},
]

RECOMMENDATIONS = [
    "[КРИТИЧЕСКОЕ] Подписать АОСР №1-ПШ от 11.08.2025 (погружение шпунта) — представители застройщика, ЛОС, проектировщика, стройконтроля",
    "[КРИТИЧЕСКОЕ] Подписать АОСР №2-ДШ от 17.11.2025 (демонтаж шпунта) — все 4 подписи",
    "[КРИТИЧЕСКОЕ] Предоставить оригинал сертификата качества №21514 от 21.11.2022 на шпунт. Без него — материалы не подтверждены, АОСР неполные",
    "[ВЫСОКОЕ] Разделить многостраничные АОСР: стр.1 — целевой акт, стр.2 — приложения. Удалить чужие акты (котлован, покрытие) из файлов",
    "[ВЫСОКОЕ] Оформить штампы на обеих ИС по ГОСТ Р 21.101-2020: организация, подписи, даты",
    "[ВЫСОКОЕ] Предоставить паспорта качества на шпунт Л5-УМ (погружение) и ЛС-УМ (демонтаж)",
    "[ВЫСОКОЕ] Привести нумерацию изменений ИС в порядок: объяснить отсутствие изм.01, 03",
    "[СРЕДНЕЕ] Дополнить журнал погружения шпунта недостающими записями (52 шт.) и подписями",
    "[СРЕДНЕЕ] Исключить из пакета ИД: Договор, КС-2, КС-3, КС-6а, Счет, УПД, Протокол разногласий",
    "[СРЕДНЕЕ] Присвоить номер исполнительной схеме демонтажа (сейчас «№ б/н»)",
    "[ПЛАНОВОЕ] Разработать отсутствующие документы: Акт ГРО, разбивка осей, АООК, АОУСИТО, ИГС, акты испытаний, лаб. заключения, ОЖР",
]

FILES_FOUND = [
    ("В ИД (после исключения)", "6", "АОСР×2, ИС×2, Журнал погружения, Сертификат (упомянут)"),
    ("Исключить из ИД", "6", "Договор, КС-2, КС-3, КС-6а, Счет, УПД, Протокол разногласий"),
    ("Всего в папке", "12", ""),
]

# ═══════════════════════════════════════════════
# PDF GENERATION
# ═══════════════════════════════════════════════

class R(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('D', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('D', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
        self.set_auto_page_break(True, 15)

    def section(self, title):
        self.set_font('D', 'B', 14)
        self.set_text_color(0, 70, 150)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 70, 150)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def issue_block(self, sev, doc, text):
        colors = {'critical': (180, 30, 30), 'high': (200, 120, 0), 'medium': (150, 150, 0)}
        c = colors.get(sev, (100, 100, 100))
        self.set_font('D', 'B', 9)
        self.set_text_color(*c)
        self.cell(22, 5, f'[{sev.upper()}]')
        self.set_font('D', 'B', 9)
        self.set_text_color(50, 50, 50)
        self.cell(0, 5, doc, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 9)
        self.set_text_color(70, 70, 70)
        self.set_x(self.l_margin + 24)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 24, 5, text)
        self.ln(2)

    def matrix_row(self, num, pos, status, note):
        self.set_font('D', '', 8)
        self.set_text_color(50, 50, 50)
        y_before = self.get_y()
        self.cell(8, 6, num, border=0)
        self.cell(42, 6, pos, border=0)
        # Status with color
        if status == 'НЕТ':
            self.set_text_color(180, 30, 30)
        elif status == 'ЧАСТ':
            self.set_text_color(200, 120, 0)
        else:
            self.set_text_color(0, 130, 0)
        self.cell(10, 6, status, border=0)
        self.set_text_color(50, 50, 50)
        self.set_x(self.l_margin + 64)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 64, 5, note)
        # Draw row separator
        self.set_draw_color(220, 220, 220)
        y_after = self.get_y()
        self.line(self.l_margin, y_after, self.w - self.r_margin, y_after)


pdf = R()

# ═══════════════════ PAGE 1: TITLE ═══════════════════
pdf.add_page()
pdf.ln(35)
pdf.set_font('D', 'B', 24)
pdf.set_text_color(30, 30, 30)
pdf.cell(0, 14, 'MAC ASD v12.0', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font('D', '', 16)
pdf.cell(0, 10, 'АКТ ПРОВЕРКИ ИСПОЛНИТЕЛЬНОЙ ДОКУМЕНТАЦИИ', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_draw_color(0, 70, 150)
pdf.set_line_width(0.5)
pdf.line(50, pdf.get_y(), pdf.w - 50, pdf.get_y())
pdf.ln(8)
pdf.set_font('D', 'B', 14)
pdf.set_text_color(0, 70, 150)
pdf.cell(0, 10, PROJECT, align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(15)

crit = sum(1 for i in ISSUES if i['severity'] == 'critical')
high = sum(1 for i in ISSUES if i['severity'] == 'high')
med = sum(1 for i in ISSUES if i['severity'] == 'medium')
missing = sum(1 for m in MATRIX_344 if m[2] == 'НЕТ')

meta = [
    ('Объект', 'Реконструкция порта Петропавловск-Камчатский'),
    ('Вид работ', 'Погружение / демонтаж шпунта Л5-УМ, ЛС-УМ'),
    ('Проверил', 'Hermes Agent (ручной VLM-анализ всех страниц)'),
    ('Метод', 'Gemma 4 31B Cloud (VLM) + pdftoppm + ручная верификация'),
    ('Дата проверки', '02.05.2026'),
    ('Файлов в папке', '12'),
    ('В ИД (после фильтрации)', '6'),
    ('Позиций 344/пр', f'13: 0 OK, {missing} НЕТ, {13-missing} ЧАСТ'),
    ('Выявлено замечаний', str(len(ISSUES))),
    ('Критических / высоких / средних', f'{crit} / {high} / {med}'),
]
for label, value in meta:
    pdf.set_font('D', 'B', 11)
    pdf.cell(55, 8, label + ':', align='R')
    pdf.set_font('D', '', 11)
    pdf.cell(0, 8, value, new_x="LMARGIN", new_y="NEXT")

# ═══════════════════ PAGE 2: MATRIX 344/пр ═══════════════════
pdf.add_page()
pdf.section('1. Матрица комплектности по Приказу 344/пр')
pdf.set_font('D', '', 9)
pdf.set_text_color(100, 100, 100)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5,
    text='Приказ Минстроя РФ от 16.05.2023 №344/пр устанавливает 13 обязательных позиций состава ИД. '
         'Ниже — статус каждой позиции для объекта ЛОС.')
pdf.ln(5)

# Header
pdf.set_font('D', 'B', 8)
pdf.set_text_color(50, 50, 50)
pdf.cell(8, 6, '№', border=0)
pdf.cell(42, 6, 'Позиция 344/пр', border=0)
pdf.cell(10, 6, '', border=0)
pdf.cell(0, 6, 'Статус', new_x="LMARGIN", new_y="NEXT", border=0)
pdf.set_draw_color(0, 70, 150)
pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
pdf.ln(3)

for num, pos, status, note in MATRIX_344:
    pdf.matrix_row(num, pos, status, note)

# Summary
pdf.ln(5)
pdf.set_font('D', 'B', 10)
pdf.set_text_color(180, 30, 30)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=6,
    text=f'ИТОГО: из 13 позиций — 0 полностью готовы, {missing} отсутствуют, {13-missing} требуют доработки. '
         f'Пакет ИД НЕ ПРИГОДЕН для сдачи-приёмки.')

# ═══════════════════ PAGES 3-4: ISSUES ═══════════════════
pdf.add_page()
pdf.section('2. Исчерпывающий список замечаний')
pdf.set_font('D', '', 9)
pdf.set_text_color(100, 100, 100)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5,
    text='Ручной анализ каждого PDF через VLM (Gemma 4 31B Cloud). '
         'Проверены ВСЕ страницы ВСЕХ документов, включая сканированные (без текстового слоя).')
pdf.ln(5)

for i in ISSUES:
    pdf.issue_block(i['severity'], i['doc'], i['issue'])

# ═══════════════════ PAGE 5: RECOMMENDATIONS ═══════════════════
pdf.add_page()
pdf.section('3. Предписание подрядчику')

pdf.set_font('D', '', 10)
pdf.set_text_color(50, 50, 50)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=6,
    text='Для приведения ИД в соответствие требованиям 344/пр и Градостроительного кодекса РФ необходимо:')
pdf.ln(5)

for i, r in enumerate(RECOMMENDATIONS, 1):
    is_crit = '[КРИТИЧЕСКОЕ]' in r
    is_high = '[ВЫСОКОЕ]' in r
    pdf.set_font('D', 'B', 10)
    if is_crit:
        pdf.set_text_color(180, 30, 30)
    elif is_high:
        pdf.set_text_color(200, 120, 0)
    else:
        pdf.set_text_color(30, 30, 30)
    pdf.cell(10, 6, f'{i}.')
    pdf.set_font('D', '', 10)
    pdf.set_text_color(50, 50, 50)
    pdf.set_x(pdf.l_margin + 10)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 10, h=6, text=r)
    pdf.ln(2)

# ═══════════════════ PAGE 6: VLM ANALYSIS ═══════════════════
pdf.add_page()
pdf.section('4. VLM-анализ исполнительных схем')
pdf.set_font('D', '', 9)
pdf.set_text_color(100, 100, 100)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5,
    text='Gemma 4 31B Cloud проанализировала обе схемы. Извлечённый текст и выявленные нарушения:')
pdf.ln(5)

# IS Pogruzhenie
pdf.set_font('D', 'B', 12)
pdf.set_text_color(0, 70, 150)
pdf.cell(0, 8, '4.1. ИС Погружение шпунта (ИЗМ_04)', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

is_p_data = [
    ("Документ:", "Исполнительная схема погружения шпунта Л5-УМ"),
    ("Изменение:", "04 (множественные правки — вопрос к изм.01-03)"),
    ("Данные:", "100 шпунтин, координаты T1-T4, отметки: проект 2.440, факт 2.458–2.540"),
    ("Дата:", "Не указана на схеме"),
    ("Привязка:", "Не указана — нет ссылки на АОСР"),
    ("НАРУШЕНИЕ:", "Штамп по ГОСТ Р 21.101-2020 не заполнен: нет организации, подписей, дат"),
    ("НАРУШЕНИЕ:", "Отсутствует масштаб схемы"),
    ("НАРУШЕНИЕ:", "Нет привязки к строительным осям здания/сооружения"),
    ("Вердикт:", "НА ДОРАБОТКУ — 4 нарушения"),
]

for label, text in is_p_data:
    if 'НАРУШЕНИЕ' in label:
        pdf.set_font('D', 'B', 9)
        pdf.set_text_color(180, 30, 30)
    elif 'Вердикт' in label:
        pdf.set_font('D', 'B', 11)
        pdf.set_text_color(180, 30, 30)
    else:
        pdf.set_font('D', '', 9)
        pdf.set_text_color(50, 50, 50)
    pdf.set_x(pdf.l_margin + 5)
    pdf.cell(28, 5, label)
    pdf.set_font('D', '', 9)
    pdf.set_text_color(70, 70, 70)
    if 'НАРУШЕНИЕ' in label or 'Вердикт' in label:
        pdf.set_font('D', 'B', 9)
    pdf.set_x(pdf.l_margin + 35)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 35, h=5, text=text)

pdf.ln(5)

# IS Demontazh
pdf.set_font('D', 'B', 12)
pdf.set_text_color(0, 70, 150)
pdf.cell(0, 8, '4.2. ИС Демонтаж шпунта (ИЗМ_02)', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

is_d_data = [
    ("Документ:", "Исполнительная схема демонтажа шпунта ЛС-УМ"),
    ("Изменение:", "02"),
    ("Данные:", "64 шпунтины, координаты T1-T4, M5, отметки: проект 2.440, факт 2.451–2.540"),
    ("Дата:", "17.11.2025 (из текста: «Приложение 1 к акту №1-ДШ от 17.11.2025»)"),
    ("Привязка:", "К акту №1-ДШ — но сам акт №1-ДШ ОТСУТСТВУЕТ в пакете!"),
    ("НАРУШЕНИЕ:", "Ссылка на несуществующий документ (акт №1-ДШ)"),
    ("НАРУШЕНИЕ:", "Штамп по ГОСТ Р 21.101-2020 не заполнен"),
    ("НАРУШЕНИЕ:", "Отсутствуют строительные оси здания/сооружения"),
    ("НАРУШЕНИЕ:", "Не указан масштаб"),
    ("Вердикт:", "НА ДОРАБОТКУ — 4 нарушения"),
]

for label, text in is_d_data:
    if 'НАРУШЕНИЕ' in label:
        pdf.set_font('D', 'B', 9)
        pdf.set_text_color(180, 30, 30)
    elif 'Вердикт' in label:
        pdf.set_font('D', 'B', 11)
        pdf.set_text_color(180, 30, 30)
    else:
        pdf.set_font('D', '', 9)
        pdf.set_text_color(50, 50, 50)
    pdf.set_x(pdf.l_margin + 5)
    pdf.cell(28, 5, label)
    pdf.set_font('D', '', 9)
    pdf.set_text_color(70, 70, 70)
    if 'НАРУШЕНИЕ' in label or 'Вердикт' in label:
        pdf.set_font('D', 'B', 9)
    pdf.set_x(pdf.l_margin + 35)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 35, h=5, text=text)

# ═══════════════════ PAGE 7: FILE INVENTORY ═══════════════════
pdf.add_page()
pdf.section('5. Инвентаризация файлов')
pdf.set_font('D', '', 9)
pdf.set_text_color(100, 100, 100)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5,
    text='Полный список файлов в папке data/test_projects/LOS/ с результатами анализа.')
pdf.ln(5)

files_detail = [
    ("АОСР_погружение_ЛОС.pdf", "Акт №1-ПШ от 11.08.25, погружение шпунта Л5-УМ (100 шт). Стр.2 — чужой акт (котлован) с упоминанием сертификата №21514", "[!] Не подписан"),
    ("АОСР_демонтаж_ЛОС.pdf", "Акт №2-ДШ от 17.11.25, демонтаж шпунта ЛС-УМ (64 шт, 87.46 т). Стр.2 — чужой акт (покрытие)", "[!] Не подписан"),
    ("ИС Погружение_ИЗМ_04.pdf", "Схема погружения, 100 шпунтин, координаты T1-T4", "[!] 4 нарушения"),
    ("ИС Демонтаж_ИЗМ_02.pdf", "Схема демонтажа, 64 шпунтины, координаты T1-T4, M5", "[!] 4 нарушения"),
    ("Журнал погружения шпунта.pdf", "48 записей из 100, даты 11.06-03.07.2025", "[!] Неполный"),
    ("Договор РТК№170 от 19.05.25.pdf", "12 стр., скан (hp officejet)", "[X] Не ИД"),
    ("КС2 погружение.pdf", "2 стр., скан", "[X] Не ИД"),
    ("КС3 погружение.pdf", "1 стр., скан", "[X] Не ИД"),
    ("КС6а погружение.pdf", "3 стр., скан", "[X] Не ИД"),
    ("Счет №27_171125.pdf", "1 стр., скан", "[X] Не ИД"),
    ("УПД№27_171125.pdf", "1 стр., скан", "[X] Не ИД"),
    ("Протокол разногласий.pdf", "3 стр., скан (hp officejet)", "[X] Не ИД"),
]

pdf.set_font('D', 'B', 8)
pdf.set_text_color(50, 50, 50)
pdf.cell(58, 5, 'Файл', border=0)
pdf.cell(0, 5, 'Статус', new_x="LMARGIN", new_y="NEXT", border=0)
pdf.set_draw_color(0, 70, 150)
pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
pdf.ln(3)

for fname, desc, status in files_detail:
    pdf.set_font('D', '', 7)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(58, 4, fname, border=0)
    pdf.set_font('D', 'B', 7)
    if '[X]' in status:
        pdf.set_text_color(130, 130, 130)
    elif '[!]' in status:
        pdf.set_text_color(200, 120, 0)
    pdf.cell(22, 4, status, border=0)
    pdf.set_font('D', '', 7)
    pdf.set_text_color(80, 80, 80)
    pdf.set_x(pdf.l_margin + 82)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin - 82, h=3.5, text=desc)
    pdf.set_draw_color(230, 230, 230)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1)

# ═══════════════════ PAGE 8: CONCLUSION ═══════════════════
pdf.add_page()
pdf.section('6. Итоговое заключение')

pdf.set_font('D', '', 10)
pdf.set_text_color(50, 50, 50)

conclusion = f"""По результатам автоматизированной проверки пакета исполнительной документации 
по объекту «{PROJECT}» установлено:

1. Пакет НЕ соответствует требованиям Приказа Минстроя РФ №344/пр.
   Из 13 обязательных позиций: 0 полностью готовы, {missing} отсутствуют, {13-missing} требуют доработки.

2. Выявлено {len(ISSUES)} замечаний, из них:
   • {crit} критических (делают ИД недействительной)
   • {high} высоких (требуют устранения до приёмки)
   • {med} средних

3. КЛЮЧЕВЫЕ НАХОДКИ:
   • Оба АОСР (№1-ПШ и №2-ДШ) НЕ ПОДПИСАНЫ — не имеют юридической силы
   • Сертификат качества №21514 от 21.11.2022 упомянут в АОСР, но ФИЗИЧЕСКИ ОТСУТСТВУЕТ
   • Обе ИС не соответствуют ГОСТ Р 21.101-2020 (нет штампов, осей, масштаба)
   • В АОСР обнаружены чужие акты на других страницах (нарушение структуры)
   • Полностью отсутствуют: Акт ГРО, разбивка осей, АООК, АОУСИТО, ИГС, акты испытаний, лаб. заключения, ОЖР

4. Финансово-сметные и договорные документы (6 файлов) по�лежат исключению из пакета ИД.

РЕКОМЕНДАЦИЯ: Вернуть пакет подрядчику для устранения замечаний.
Повторная проверка — после предоставления недостающих и исправленных документов.

Срок устранения критических замечаний: 10 рабочих дней.
"""

for line in conclusion.split('\n'):
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5.5, text=line)
    if line.strip():
        pdf.ln(1)

# Stamp line
pdf.ln(20)
pdf.set_font('D', '', 9)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 5, 'Проверка выполнена: Hermes Agent + Gemma 4 31B Cloud (VLM) + ручная верификация', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 5, 'MAC ASD v12.0 | 02.05.2026 | data/test_projects/LOS/', align='C', new_x="LMARGIN", new_y="NEXT")

# Save
pdf.output(OUT)
print(f'✅ PDF saved: {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)')
print(f'   Issues: {len(ISSUES)} ({crit} critical, {high} high, {med} medium)')
print(f'   344/пр matrix: 0 OK, {missing} НЕТ, {13-missing} ЧАСТ')
