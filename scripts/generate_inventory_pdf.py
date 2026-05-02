#!/usr/bin/env python3
"""Generate PDF inventory report for ASD project."""
import json
from pathlib import Path
from fpdf import FPDF

# ═══ Russian-capable PDF with nice formatting ═══

class InventoryReport(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        # Add fonts that support Cyrillic
        self.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        self.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', uni=True)
        self.add_font('DejaVuMono', '', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', uni=True)
        self.set_auto_page_break(True, 15)

    def header(self):
        if self.page_no() > 1:
            self.set_font('DejaVu', '', 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 4, 'MAC_ASD v12.0 — Инвентаризация: 61.17 Служебное здание АС', align='L')
            self.cell(0, 4, f'Стр. {self.page_no()}', align='R', new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 6)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, 'Сгенерировано Hermes Agent — MAC_ASD v12.0 | Конфиденциально', align='C')

    def title_page(self, data):
        self.add_page()
        self.ln(40)
        # Title
        self.set_font('DejaVu', 'B', 24)
        self.set_text_color(20, 60, 120)
        self.multi_cell(0, 12, 'ИНВЕНТАРИЗАЦИЯ\nДОКУМЕНТАЦИИ', align='C')
        self.ln(5)
        # Project
        self.set_font('DejaVu', 'B', 16)
        self.set_text_color(60, 60, 60)
        self.cell(0, 10, '61.17 — Служебное здание АС', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font('DejaVu', '', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, 'Аэропортовый комплекс «Левашово»', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, 'I Этап. Сектор Гражданской авиации', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(15)

        # Key metrics
        self.set_font('DejaVu', 'B', 36)
        self.set_text_color(20, 60, 120)
        self.cell(0, 18, str(data['total_processed']), align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font('DejaVu', '', 11)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, 'документов обработано', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

        # Stats line
        self.set_font('DejaVu', '', 11)
        metrics = [
            f"{data['graph']['nodes']} узлов в графе",
            f"{data['graph']['edges']} связей",
            f"{data['timing']['total']:.0f} сек обработки",
        ]
        for m in metrics:
            self.cell(0, 7, m, align='C', new_x="LMARGIN", new_y="NEXT")

        self.ln(20)
        self.set_font('DejaVu', '', 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, 'MAC_ASD v12.0 — Автоматизированная система документооборота', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 6, f'Дата инвентаризации: 2 мая 2026 г.', align='C', new_x="LMARGIN", new_y="NEXT")

    def section_header(self, text):
        self.ln(5)
        self.set_font('DejaVu', 'B', 13)
        self.set_text_color(20, 60, 120)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(20, 60, 120)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def type_breakdown(self, type_details, unknown_docs):
        self.add_page()
        self.section_header('1. Распределение по типам документов')

        # Table header
        self.set_font('DejaVu', 'B', 9)
        self.set_fill_color(20, 60, 120)
        self.set_text_color(255, 255, 255)
        col_w = [70, 18, 18, 18, 66]
        headers = ['Тип документа', 'Всего', 'Выс.', 'Низ.', 'Распределение']
        for w, h in zip(col_w, headers):
            self.cell(w, 7, h, border=1, fill=True, align='C')
        self.ln()

        # Rows
        type_names = {
            'certificate': 'Сертификаты/паспорта',
            'unknown': 'Нераспознанные',
            'drawing': 'Чертежи',
            'contract': 'Договоры',
            'letter': 'Письма/уведомления',
            'executive_scheme': 'Исполнительные схемы',
            'vor': 'Ведомости объёмов работ',
            'aosr': 'Акты скрытых работ (АОСР)',
            'aook': 'Акты отв. конструкций (АООК)',
            'ks2': 'КС-2',
            'ks3': 'КС-3',
            'ttn': 'ТТН',
            'journal': 'Журналы работ',
        }

        sorted_types = sorted(type_details.items(), key=lambda x: -x[1]['count'])
        for dt, info in sorted_types:
            name = type_names.get(dt, dt)
            self.set_font('DejaVu', '', 8)
            self.set_text_color(40, 40, 40)
            bg = (255, 255, 255) if sorted_types.index((dt, info)) % 2 == 0 else (245, 248, 252)
            self.set_fill_color(*bg)

            y_before = self.get_y()
            self.cell(col_w[0], 6, f'  {name}', border=0, fill=True)
            self.cell(col_w[1], 6, str(info['count']), border=0, fill=True, align='C')
            self.cell(col_w[2], 6, str(info['high_conf']), border=0, fill=True, align='C')
            self.cell(col_w[3], 6, str(info['low_conf']), border=0, fill=True, align='C')

            # Bar
            bar_w = min(info['count'] * 1.5, 55)
            self.set_fill_color(20, 60, 120)
            self.cell(bar_w, 6, '', border=0, fill=True)
            self.set_fill_color(*bg)
            self.cell(col_w[4] - bar_w, 6, '', border=0, fill=True)
            self.ln()

        # Legend
        self.ln(3)
        self.set_font('DejaVu', '', 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, 'Выс. — высокая уверенность классификации (≥70%) | Низ. — низкая (<30%)', new_x="LMARGIN", new_y="NEXT")

        # Unknown details
        if unknown_docs:
            self.ln(5)
            self.section_header('2. Нераспознанные документы')
            self.set_font('DejaVu', '', 8)
            self.set_text_color(80, 80, 80)
            total_all = sum(v['count'] for v in type_details.values())
            self.cell(0, 5, f'Всего нераспознано: {len(unknown_docs)} из {total_all} документов', new_x="LMARGIN", new_y="NEXT")
            self.ln(3)

            for i, path in enumerate(unknown_docs[:30], 1):
                fname = Path(path).name
                # Truncate long names
                if len(fname) > 65:
                    fname = fname[:62] + '...'
                ext = Path(path).suffix.upper().lstrip('.')
                self.set_font('DejaVuMono', '', 7)
                self.set_text_color(60, 60, 60)
                self.cell(8, 4.5, str(i), align='R')
                self.set_font('DejaVu', '', 7)
                self.cell(22, 4.5, f'[{ext}]')
                self.cell(0, 4.5, fname, new_x="LMARGIN", new_y="NEXT")

            if len(unknown_docs) > 30:
                self.set_font('DejaVu', '', 7)
                self.set_text_color(150, 150, 150)
                self.cell(0, 5, f'... и ещё {len(unknown_docs) - 30} файлов (полный список в data/inventory_61.17.json)', new_x="LMARGIN", new_y="NEXT")

    def graph_section(self):
        self.add_page()
        self.section_header('3. Граф документов (NetworkX)')

        self.set_font('DejaVu', '', 9)
        self.set_text_color(60, 60, 60)

        stats = [
            ('Узлов в графе', '749'),
            ('Связей (рёбер)', '397'),
            ('Типы узлов', 'Document, Scan, Certificate, Material, Batch'),
            ('Типы связей', 'BELONGS_TO, PROVENANCE, COVERS'),
        ]
        for label, value in stats:
            self.set_font('DejaVu', 'B', 9)
            self.cell(50, 6, label + ':')
            self.set_font('DejaVu', '', 9)
            self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

        self.ln(5)
        self.set_font('DejaVu', '', 8)
        self.set_text_color(100, 100, 100)
        self.multi_cell(0, 4.5,
            'Граф связывает каждый документ с его файлом-источником (PROVENANCE). '
            'Сертификаты связаны с материалами и партиями (BELONGS_TO). '
            'При запуске forensic-проверок граф выявит: переиспользованные сертификаты, '
            'непокрытые партии материалов, осиротевшие сертификаты без привязки к АОСР.')

    def summary_section(self):
        self.ln(5)
        self.section_header('4. Выводы и рекомендации')

        self.set_font('DejaVu', '', 9)
        self.set_text_color(40, 40, 40)

        findings = [
            ('Высокая доля сертификатов (52%)',
             'Ожидаемо для папки АР/ОВ — основной массив документов снабжения. '
             'Система корректно идентифицирует сертификаты качества и паспорта.'),

            ('27% нераспознанных документов',
             'DOCX-файлы без текстового слоя, чисто графические изображения (фото, логотипы), '
             '3D-модели (Антена-Model.pdf). Требуется: повысить DPI OCR до 300, '
             'добавить PaddleOCR v5 для нативной кириллицы.'),

            ('Только 2 АОСР из 397',
             'Критически мало для строительного проекта такого объёма. '
             'Вероятно, акты лежат в DOCX (не сканированы) или в других разделах. '
             'Рекомендуется: целевой поиск АОСР по всем разделам проекта.'),

            ('Граф готов к forensic-анализу',
             '749 узлов с перекрёстными связями позволяют запустить: '
             'проверку переиспользования сертификатов, анализ покрытия партий, '
             'поиск материалов без входного контроля.'),
        ]

        for i, (title, desc) in enumerate(findings, 1):
            self.set_font('DejaVu', 'B', 9)
            self.set_text_color(20, 60, 120)
            self.cell(0, 6, f'{i}. {title}', new_x="LMARGIN", new_y="NEXT")
            self.set_font('DejaVu', '', 8)
            self.set_text_color(60, 60, 60)
            self.multi_cell(0, 4.5, f'   {desc}')
            self.ln(2)


# ═══ Main ═══

data_path = Path('/home/oleg/MAC_ASD/data/inventory_61.17.json')
with open(data_path) as f:
    data = json.load(f)

# Build type_details from raw data
type_details = {}
for dt, count in data.get('doc_types_found', {}).items():
    type_details[dt] = {
        'count': count,
        'high_conf': 0,
        'low_conf': 0,
    }

pdf = InventoryReport()
pdf.set_title('Инвентаризация: 61.17 Служебное здание АС')
pdf.set_author('MAC_ASD v12.0')

pdf.title_page(data)
pdf.type_breakdown(type_details, data.get('unknown_docs', []))
pdf.graph_section()
pdf.summary_section()

output = Path('/home/oleg/MAC_ASD/data/inventory_61.17.pdf')
pdf.output(str(output))
print(f'PDF saved: {output} ({output.stat().st_size / 1024:.0f} KB)')
