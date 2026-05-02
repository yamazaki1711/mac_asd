#!/usr/bin/env python3
"""Generate comprehensive PTO inspection report for LOS project."""
import json, os
from fpdf import FPDF

# Load data
with open('data/vlm_analysis_LOS.json') as f:
    vlm = json.load(f)

# Data from LLM analysis (hardcoded from previous run)
llm_issues = [
    {"doc": "Журнал погружения шпунта", "issue": "Отсутствуют подписи ответственных лиц", "severity": "high"},
    {"doc": "ИС Погружение", "issue": "Отсутствует соответствующий АОСР согласно Приказу 344/пр", "severity": "critical"},
    {"doc": "ИС Демонтаж", "issue": "Отсутствует АОСР на работы по демонтажу", "severity": "critical"},
    {"doc": "Весь пакет", "issue": "Полное отсутствие документов входного контроля (паспорта, сертификаты на шпунт)", "severity": "critical"},
    {"doc": "Весь пакет", "issue": "Отсутствуют Акты приемки ответственных конструкций (АООК)", "severity": "high"},
    {"doc": "Весь пакет", "issue": "Финансовые документы (Счета, УПД, КС-2, КС-3) не входят в состав ИД по 344/пр — исключить", "severity": "medium"},
]

llm_recs = [
    "Разработать и подписать АОСР на погружение шпунта и демонтаж (форма 344/пр)",
    "Предоставить паспорта качества и сертификаты на используемый шпунт Л5-УМ",
    "Оформить АООК на устройство шпунтового ограждения",
    "Обеспечить подписи всех сторон в Журнале погружения шпунта",
    "Исключить финансовые документы из пакета ИД",
]

PROJECT = 'ЛОС — Шпунтовое ограждение'
OUT = 'data/inspection_report_LOS.pdf'

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
    def issue(self, sev, doc, text):
        colors = {'critical': (180,30,30), 'high': (200,120,0), 'medium': (150,150,0)}
        c = colors.get(sev, (100,100,100))
        self.set_font('D', 'B', 9); self.set_text_color(*c)
        self.cell(18, 5, f'[{sev.upper()}]')
        self.set_font('D', 'B', 9); self.set_text_color(50,50,50)
        self.cell(0, 5, doc, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 9); self.set_text_color(70,70,70)
        self.set_x(self.l_margin + 20)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 20, 5, text)
        self.ln(2)

pdf = R()

# ═══ PAGE 1: TITLE ═══
pdf.add_page()
pdf.ln(40)
pdf.set_font('D', 'B', 24); pdf.set_text_color(30,30,30)
pdf.cell(0, 14, 'MAC ASD v12.0', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font('D', '', 16)
pdf.cell(0, 10, 'АКТ ПРОВЕРКИ ИСПОЛНИТЕЛЬНОЙ ДОКУМЕНТАЦИИ', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_draw_color(0, 70, 150); pdf.set_line_width(0.5)
pdf.line(50, pdf.get_y(), pdf.w - 50, pdf.get_y())
pdf.ln(8)
pdf.set_font('D', 'B', 14); pdf.set_text_color(0, 70, 150)
pdf.cell(0, 10, PROJECT, align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(15)

# Meta
pdf.set_font('D', '', 11); pdf.set_text_color(30,30,30)
meta = [
    ('Объект', 'Реконструкция порта Петропавловск-Камчатский'),
    ('Вид работ', 'Погружение/демонтаж шпунта Л5-УМ'),
    ('Проверил', 'ПТО-агент (Gemma 4 31B + DeepSeek V4)'),
    ('Дата проверки', '02.05.2026'),
    ('Документов в пакете', '10 (после исключения фин. документов)'),
    ('Выявлено замечаний', str(len(llm_issues))),
    ('Критических', str(sum(1 for i in llm_issues if i['severity']=='critical'))),
]
for l, v in meta:
    pdf.set_font('D', 'B', 11); pdf.cell(50, 8, l + ':', align='R')
    pdf.set_font('D', '', 11); pdf.cell(0, 8, v, new_x="LMARGIN", new_y="NEXT")

# ═══ PAGE 2: LLM ISSUES ═══
pdf.add_page()
pdf.section('1. Замечания к составу ИД (Приказ 344/пр)')

pdf.set_font('D', '', 9); pdf.set_text_color(100,100,100)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5, text='ПТО-агент (DeepSeek V4 Pro) провёл классификацию документов и проверку комплектности. Ниже — исчерпывающий список замечаний.')
pdf.ln(5)

for i in llm_issues:
    pdf.issue(i['severity'], i['doc'], i['issue'])

# ═══ PAGE 3: RECOMMENDATIONS ═══
pdf.ln(5)
pdf.section('2. Предписание подрядчику')

pdf.set_font('D', '', 10); pdf.set_text_color(50,50,50)
pdf.cell(0, 6, 'Для приведения ИД в соответствие требованиям 344/пр необходимо:', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

for i, r in enumerate(llm_recs, 1):
    pdf.set_font('D', 'B', 10); pdf.set_text_color(30,30,30)
    pdf.cell(10, 6, f'{i}.')
    pdf.set_font('D', '', 10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=6, text=r)
    pdf.ln(1)

# ═══ PAGE 4: VLM — IS POGROJENIE ═══
pdf.add_page()
pdf.section('3. Проверка исполнительных схем (ГОСТ Р 51872-2019)')
pdf.set_font('D', '', 9); pdf.set_text_color(100,100,100)
pdf.cell(0, 5, 'VLM-агент (Gemma 4 31B Cloud) проверил оформление схем.', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)

pdf.set_font('D', 'B', 12); pdf.set_text_color(0, 70, 150)
pdf.cell(0, 8, '3.1. ИС Погружение шпунта (ИЗМ_04)', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

# Parse VLM output
vlm1 = vlm.get('pogruzhenie', '')
for line in vlm1.split('\n'):
    line = line.strip()
    if not line: continue
    if 'НАРУШЕНИЕ' in line:
        pdf.set_font('D', 'B', 9); pdf.set_text_color(180, 30, 30)
    elif 'СООТВЕТСТВУЕТ' in line:
        pdf.set_font('D', 'B', 9); pdf.set_text_color(0, 130, 0)
    elif 'Вердикт' in line and 'ДОРАБОТКУ' in line:
        pdf.set_font('D', 'B', 11); pdf.set_text_color(180, 30, 30)
    elif 'Вердикт' in line and 'ПРИНЯТЬ' in line:
        pdf.set_font('D', 'B', 11); pdf.set_text_color(0, 130, 0)
    else:
        pdf.set_font('D', '', 9); pdf.set_text_color(50, 50, 50)
    
    # Clean markdown
    line = line.replace('**', '').replace('*', '')
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=4.5, text=line[:200])

# ═══ PAGE 5: VLM — IS DEMONTAZH ═══
pdf.add_page()
pdf.set_font('D', 'B', 12); pdf.set_text_color(0, 70, 150)
pdf.cell(0, 8, '3.2. ИС Демонтаж шпунта (ИЗМ_02)', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

vlm2 = vlm.get('demontazh', '')
for line in vlm2.split('\n'):
    line = line.strip()
    if not line: continue
    if 'НАРУШЕНИЕ' in line:
        pdf.set_font('D', 'B', 9); pdf.set_text_color(180, 30, 30)
    elif 'СООТВЕТСТВУЕТ' in line:
        pdf.set_font('D', 'B', 9); pdf.set_text_color(0, 130, 0)
    elif 'Вердикт' in line and 'ДОРАБОТКУ' in line:
        pdf.set_font('D', 'B', 11); pdf.set_text_color(180, 30, 30)
    elif 'Вердикт' in line and 'ПРИНЯТЬ' in line:
        pdf.set_font('D', 'B', 11); pdf.set_text_color(0, 130, 0)
    else:
        pdf.set_font('D', '', 9); pdf.set_text_color(50, 50, 50)
    line = line.replace('**', '').replace('*', '')
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=4.5, text=line[:200])

# ═══ PAGE 6: SUMMARY ═══
pdf.add_page()
pdf.section('4. Итоговое заключение')

pdf.set_font('D', '', 10); pdf.set_text_color(50, 50, 50)

summary = f"""По результатам автоматизированной проверки пакета исполнительной документации 
по объекту «{PROJECT}» установлено:

1. Пакет НЕ соответствует требованиям Приказа Минстроя №344/пр.
   Выявлено {len(llm_issues)} замечаний, из них {sum(1 for i in llm_issues if i['severity']=='critical')} критических.

2. Критические замечания:
   • Отсутствуют АОСР на погружение и демонтаж шпунта
   • Отсутствуют документы входного контроля (паспорта, сертификаты)

3. Обе исполнительные схемы НЕ ПРИНЯТЫ — требуют доработки:
   • Штампы не заполнены, подписи отсутствуют
   • Нет ссылок на АОСР
   • ИС Демонтаж: отсутствуют оси здания
   • ИС Погружение: не указан масштаб

4. Финансовые документы (КС-2, КС-3, счета, УПД) подлежат исключению из пакета ИД.

РЕКОМЕНДАЦИЯ: Вернуть пакет подрядчику для устранения замечаний.
Повторная проверка — после предоставления недостающих документов."""

for line in summary.split('\n'):
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w=pdf.w - pdf.l_margin - pdf.r_margin, h=5.5, text=line)
    if line.strip(): pdf.ln(1)

# Save
pdf.output(OUT)
print(f'PDF: {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)')
