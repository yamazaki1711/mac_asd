#!/usr/bin/env python3
"""Generate PDF inventory for LOS project with forensic findings."""
import json, os, glob
from pathlib import Path
from fpdf import FPDF

# Find latest inventory JSON
files = sorted(glob.glob('/home/oleg/MAC_ASD/data/inventory_LOS_test_*.json'))
DATA = Path(files[-1])
OUT = Path('/home/oleg/MAC_ASD/data/inventory_LOS.pdf')
PROJECT = 'ЛОС — Шпунтовое ограждение'

with open(DATA) as f:
    data = json.load(f)

# Get forensic findings directly from graph
import sys; sys.path.insert(0, '/home/oleg/MAC_ASD')
from src.core.graph_service import graph_service
forensic_raw = graph_service.run_all_forensic_checks()
forensic_findings = forensic_raw if isinstance(forensic_raw, list) else []

class R(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('D', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('D', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
        self.set_auto_page_break(True, 15)
    def hdr(self):
        if self.page_no() > 1:
            self.set_font('D', '', 7); self.set_text_color(120,120,120)
            self.cell(0,4,f'MAC_ASD v12.0 — Инвентаризация: {PROJECT}', align='L'); self.ln(5)

pdf = R()
pdf.set_title(f'Инвентаризация: {PROJECT}')

# ═══ Title ═══
pdf.add_page(); pdf.ln(30)
pdf.set_font('D','B',22); pdf.set_text_color(30,30,30)
pdf.cell(0,12,'MAC ASD v12.0', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font('D','',16)
pdf.cell(0,10,'Отчёт об инвентаризации', align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font('D','B',14); pdf.set_text_color(0,70,150)
pdf.cell(0,10,PROJECT, align='C', new_x="LMARGIN", new_y="NEXT")
pdf.ln(20)

# Stats
pdf.set_text_color(30,30,30); pdf.set_font('D','',11)
types = data.get('doc_types_found', {})
total = sum(types.values())
stats = [
    ('Файлов', str(total)),
    ('Узлов графа', str(data.get('nodes','?'))),
    ('Связей', str(data.get('edges','?'))),
    ('Время', f"{data.get('elapsed_sec',0):.1f} сек"),
    ('Ошибок', str(data.get('errors',0))),
    ('Forensic-находок', str(len(forensic_findings))),
]
for l,v in stats:
    pdf.set_font('D','B',11); pdf.cell(45,8,l+':', align='R')
    pdf.set_font('D','',11); pdf.cell(0,8,v, new_x="LMARGIN", new_y="NEXT")

# ═══ Type breakdown ═══
pdf.add_page()
pdf.set_font('D','B',16); pdf.set_text_color(0,70,150)
pdf.cell(0,10,'Распределение типов документов', new_x="LMARGIN", new_y="NEXT"); pdf.ln(5)

mx = max(types.values()) if types else 1
for dt, cnt in sorted(types.items(), key=lambda x:-x[1]):
    pct = cnt/total*100 if total else 0; bw = int(cnt/mx*100)
    pdf.set_font('D','',10); pdf.cell(45,6,dt, align='R')
    g = 70+bw if bw<130 else 200
    pdf.set_fill_color(0,g,200-bw); pdf.cell(bw+2,6,'',fill=True); pdf.cell(3,6,'')
    pdf.set_font('D','B',10); pdf.cell(15,6,str(cnt),align='R')
    pdf.set_font('D','',9); pdf.set_text_color(100,100,100)
    pdf.cell(0,6,f'  ({pct:.0f}%)', new_x="LMARGIN", new_y="NEXT")

# Unknown
unknown = data.get('unknown_docs',[])
if unknown:
    pdf.ln(8)
    pdf.set_font('D','B',12); pdf.set_text_color(180,50,50)
    pdf.cell(0,8,f'⚠ Нераспознано ({len(unknown)})', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('D','',8); pdf.set_text_color(80,80,80)
    for fn in unknown:
        pdf.cell(0,5,f'  • {Path(fn).name}', new_x="LMARGIN", new_y="NEXT")

# ═══ Forensic ═══
pdf.add_page()
pdf.set_font('D','B',16); pdf.set_text_color(0,70,150)
pdf.cell(0,10,'Forensic-проверки', new_x="LMARGIN", new_y="NEXT"); pdf.ln(5)

crit = sum(1 for f in forensic_findings if str(f.severity) in ('ForensicSeverity.CRITICAL','CRITICAL'))
high = sum(1 for f in forensic_findings if str(f.severity) in ('ForensicSeverity.HIGH','HIGH'))
med  = sum(1 for f in forensic_findings if str(f.severity) in ('ForensicSeverity.MEDIUM','MEDIUM'))

pdf.set_font('D','',11); pdf.set_text_color(30,30,30)
pdf.cell(0,7,f'Всего находок: {len(forensic_findings)}  |  Критических: {crit}  |  Высоких: {high}  |  Средних: {med}', new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)

if forensic_findings:
    for f in forensic_findings:
        sev = str(f.severity).split('.')[-1]
        colors = {'CRITICAL': (180,30,30), 'HIGH': (200,120,0), 'MEDIUM': (150,150,0)}
        c = colors.get(sev, (100,100,100))
        pdf.set_font('D','B',10); pdf.set_text_color(*c)
        pdf.cell(22,6,f'[{sev}]')
        pdf.set_font('D','',9); pdf.set_text_color(50,50,50)
        desc = str(f.description) if hasattr(f,'description') else str(f)
        pdf.multi_cell(0,5,desc[:200])
        pdf.ln(2)
else:
    pdf.set_font('D','',10); pdf.set_text_color(0,130,0)
    pdf.cell(0,7,'✓ Нарушений не обнаружено', new_x="LMARGIN", new_y="NEXT")

pdf.ln(8)
pdf.set_font('D','B',11); pdf.set_text_color(0,70,150)
pdf.cell(0,7,'Интерпретация находок', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('D','',9); pdf.set_text_color(80,80,80)
pdf.multi_cell(0,5,'«Сертификат-сирота» — нормальная ситуация для малых проектов, где мало АОСР. Система честно сообщает о разрыве цепочки сертификат→АОСР→материал. В реальном проекте каждый сертификат должен быть привязан к акту освидетельствования.')

# Save
pdf.output(str(OUT))
print(f'PDF: {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)')
print(f'MEDIA:{OUT}')
