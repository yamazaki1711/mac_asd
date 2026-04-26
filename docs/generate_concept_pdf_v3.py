#!/usr/bin/env python3
"""
MAC ASD v11.3.0 — Навыки агентов и рабочие процессы (v3).
Генерация PDF через ReportLab — БЕЗ HTML/Playwright обложки.
Все шрифты TrueType, никаких Type 3 bitmap.
"""

import sys, os, hashlib
sys.path.insert(0, '/home/z/my-project/skills/pdf/scripts')

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    KeepTogether, CondPageBreak, PageBreak, Flowable
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import SimpleDocTemplate
from reportlab.graphics.shapes import Drawing, Line, Circle, Rect
from reportlab.graphics import renderPDF

# ━━━ Fonts ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Основные шрифты для русского текста — Calibri (отличная кириллица)
pdfmetrics.registerFont(TTFont('Calibri', '/usr/share/fonts/truetype/english/calibri-regular.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-Bold', '/usr/share/fonts/truetype/english/calibri-bold.ttf'))
# Моноширинный шрифт (код) — Sarasa Mono SC (кириллица + CJK)
pdfmetrics.registerFont(TTFont('SarasaMonoSC', '/usr/share/fonts/truetype/chinese/SarasaMonoSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('SarasaMonoSC-Bold', '/usr/share/fonts/truetype/chinese/SarasaMonoSC-Bold.ttf'))
# Fallback для CJK-символов (если появятся китайские иероглифы)
pdfmetrics.registerFont(TTFont('NotoSansSC', '/usr/share/fonts/truetype/chinese/SarasaMonoSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))

registerFontFamily('Calibri', normal='Calibri', bold='Calibri-Bold')
registerFontFamily('SarasaMonoSC', normal='SarasaMonoSC', bold='SarasaMonoSC-Bold')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold')

from pdf import install_font_fallback
install_font_fallback()

# ━━━ Palette ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCENT           = colors.HexColor('#2e93b4')
ACCENT_LIGHT     = colors.HexColor('#d0eef6')
TEXT_PRIMARY      = colors.HexColor('#22211f')
TEXT_MUTED        = colors.HexColor('#8a8881')
BG_PAGE          = colors.HexColor('#f5f4f4')
BG_SECTION       = colors.HexColor('#efeeed')
TABLE_STRIPE     = colors.HexColor('#efefed')
HEADER_FILL      = colors.HexColor('#584f33')
COVER_BLOCK      = colors.HexColor('#7b7258')
BORDER           = colors.HexColor('#c5bfac')

TABLE_HEADER_COLOR = HEADER_FILL
TABLE_HEADER_TEXT  = colors.white
TABLE_ROW_EVEN     = colors.white
TABLE_ROW_ODD      = TABLE_STRIPE

# ━━━ Page setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAGE_W, PAGE_H = A4
LEFT_MARGIN = 2.0 * cm
RIGHT_MARGIN = 2.0 * cm
TOP_MARGIN = 2.2 * cm
BOTTOM_MARGIN = 2.2 * cm
AVAILABLE_WIDTH = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN

# ━━━ Styles ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
H1_STYLE = ParagraphStyle(
    'H1', fontName='Calibri-Bold', fontSize=20, leading=28,
    spaceBefore=24, spaceAfter=12, textColor=TEXT_PRIMARY
)
H2_STYLE = ParagraphStyle(
    'H2', fontName='Calibri-Bold', fontSize=16, leading=22,
    spaceBefore=18, spaceAfter=8, textColor=ACCENT
)
H3_STYLE = ParagraphStyle(
    'H3', fontName='Calibri-Bold', fontSize=13, leading=18,
    spaceBefore=12, spaceAfter=6, textColor=HEADER_FILL
)
BODY_STYLE = ParagraphStyle(
    'Body', fontName='Calibri', fontSize=10.5, leading=18,
    spaceBefore=0, spaceAfter=6, alignment=TA_LEFT,
    textColor=TEXT_PRIMARY, firstLineIndent=21
)
BODY_NO_INDENT = ParagraphStyle(
    'BodyNoIndent', fontName='Calibri', fontSize=10.5, leading=18,
    spaceBefore=0, spaceAfter=6, alignment=TA_LEFT,
    textColor=TEXT_PRIMARY
)
BULLET_STYLE = ParagraphStyle(
    'Bullet', fontName='Calibri', fontSize=10.5, leading=18,
    spaceBefore=2, spaceAfter=4, alignment=TA_LEFT,
    textColor=TEXT_PRIMARY,
    leftIndent=24, bulletIndent=12
)
CODE_STYLE = ParagraphStyle(
    'Code', fontName='SarasaMonoSC', fontSize=9, leading=14,
    spaceBefore=4, spaceAfter=4, alignment=TA_LEFT,
    textColor=colors.HexColor('#333333'),
    leftIndent=12, backColor=colors.HexColor('#f0f0ec')
)
CAPTION_STYLE = ParagraphStyle(
    'Caption', fontName='Calibri', fontSize=9, leading=13,
    spaceBefore=3, spaceAfter=6, alignment=TA_CENTER,
    textColor=TEXT_MUTED
)
TABLE_HEADER_STYLE = ParagraphStyle(
    'TH', fontName='Calibri-Bold', fontSize=10, leading=14,
    alignment=TA_CENTER, textColor=TABLE_HEADER_TEXT
)
TABLE_CELL_STYLE = ParagraphStyle(
    'TC', fontName='Calibri', fontSize=9.5, leading=14,
    alignment=TA_LEFT, textColor=TEXT_PRIMARY
)
TABLE_CELL_CENTER = ParagraphStyle(
    'TCC', fontName='Calibri', fontSize=9.5, leading=14,
    alignment=TA_CENTER, textColor=TEXT_PRIMARY
)
TOC_H1 = ParagraphStyle(
    'TOC1', fontName='Calibri-Bold', fontSize=13, leading=22,
    leftIndent=20
)
TOC_H2 = ParagraphStyle(
    'TOC2', fontName='Calibri', fontSize=11, leading=18,
    leftIndent=40
)

# ━━━ ReportLab Cover Page ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class CoverPage(Flowable):
    """Full-page cover rendered entirely in ReportLab — no HTML/Type3 fonts."""
    def __init__(self, width, height):
        Flowable.__init__(self)
        self.width = width
        self.height = height

    def wrap(self, aW, aH):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height

        # Background
        c.setFillColor(BG_PAGE)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Decorative accent line (top)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(3)
        c.line(72, h - 50, 192, h - 50)

        # Decorative vertical line (left)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(2)
        c.saveState()
        c.setFillColor(ACCENT)
        c.setFillAlpha(0.3)
        c.rect(58, h - 260, 2, 180, fill=1, stroke=0)
        c.restoreState()

        # Decorative circle (bottom right)
        c.saveState()
        c.setStrokeColor(ACCENT)
        c.setLineWidth(2)
        c.setFillAlpha(0.15)
        c.circle(w - 80, 160, 45, fill=0, stroke=1)
        c.restoreState()

        # Kicker: "Концептуальный документ"
        c.setFont('Calibri', 13)
        c.setFillColor(TEXT_MUTED)
        c.drawString(72, h - 90, 'К О Н Ц Е П Т У А Л Ь Н Ы Й   Д О К У М Е Н Т')

        # Hero: "MAC ASD"
        c.setFont('Calibri-Bold', 40)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(72, h - 150, 'MAC ASD')

        # Hero: "v11.3.0" in accent color
        c.setFillColor(ACCENT)
        c.drawString(72 + c.stringWidth('MAC ASD ', 'Calibri-Bold', 40), h - 150, 'v11.3.0')

        # Subtitle
        c.setFont('Calibri-Bold', 22)
        c.setFillColor(HEADER_FILL)
        c.drawString(72, h - 190, 'Навыки агентов и рабочие процессы')

        # Summary block
        summary_y = h - 270
        c.setFillColor(ACCENT_LIGHT)
        c.setFillAlpha(0.2)
        c.roundRect(72, summary_y - 10, 440, 80, 4, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.rect(72, summary_y - 10, 3, 80, fill=1, stroke=0)

        c.setFont('Calibri', 14)
        c.setFillColor(TEXT_PRIMARY)
        c.setFillAlpha(1.0)
        c.drawString(88, summary_y + 50, 'Детальное описание функционала семи ИИ-агентов')
        c.drawString(88, summary_y + 28, '(Hermes, ПТО, Сметчик, Юрист, Закупщик,')
        c.drawString(88, summary_y + 6, 'Логист, Делопроизводитель) и проектирование')
        c.drawString(88, summary_y - 16, 'двух ключевых рабочих процессов.')

        # Bottom meta block
        meta_top = 110
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.line(72, meta_top + 14, w - 72, meta_top + 14)

        meta_labels = ['Версия', 'Дата', 'Платформа', 'Архитектура']
        meta_values = ['v11.3.0', 'Апрель 2026', 'Mac Studio M4 Max 128GB / MLX', 'LangGraph + LLMEngine + pgvector']

        y = meta_top - 4
        for label, value in zip(meta_labels, meta_values):
            c.setFont('Calibri', 10)
            c.setFillColor(TEXT_MUTED)
            c.drawString(72, y, label.upper())

            if label == 'Версия':
                # Version tag with accent background
                tw = c.stringWidth(value, 'Calibri-Bold', 11)
                c.setFillColor(ACCENT)
                c.roundRect(w - 72 - tw - 16, y - 3, tw + 16, 16, 3, fill=1, stroke=0)
                c.setFont('Calibri-Bold', 11)
                c.setFillColor(colors.white)
                c.drawString(w - 72 - tw - 8, y, value)
            else:
                c.setFont('Calibri-Bold', 12)
                c.setFillColor(TEXT_PRIMARY)
                c.drawString(w - 72 - c.stringWidth(value, 'Calibri-Bold', 12), y, value)
            y -= 22


# ━━━ Helpers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_table(data, col_ratios=None, header_rows=1):
    col_widths = [r * AVAILABLE_WIDTH for r in col_ratios] if col_ratios else None
    t = Table(data, colWidths=col_widths, hAlign='CENTER')
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, header_rows - 1), TABLE_HEADER_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), TABLE_HEADER_TEXT),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    for i in range(header_rows, len(data)):
        bg = TABLE_ROW_EVEN if (i - header_rows) % 2 == 0 else TABLE_ROW_ODD
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style_cmds))
    return t

def p(text, style=None):
    return Paragraph(text, style or BODY_STYLE)

def bullet(text):
    return Paragraph(f'<bullet>&bull;</bullet> {text}', BULLET_STYLE)

def safe_keep(elements):
    MAX_H = PAGE_H * 0.4
    total = sum(el.wrap(AVAILABLE_WIDTH, PAGE_H)[1] for el in elements)
    if total <= MAX_H:
        return [KeepTogether(elements)]
    elif len(elements) >= 2:
        return [KeepTogether(elements[:2])] + list(elements[2:])
    return list(elements)

# ━━━ TOC DocTemplate ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

def add_heading(text, style, level=0):
    key = 'h_%s' % hashlib.md5(text.encode()).hexdigest()[:8]
    pp = Paragraph('<a name="%s"/>%s' % (key, f'<b>{text}</b>'), style)
    pp.bookmark_name = text
    pp.bookmark_level = level
    pp.bookmark_text = text
    pp.bookmark_key = key
    return pp

H1_ORPHAN = (PAGE_H - TOP_MARGIN - BOTTOM_MARGIN) * 0.15

def add_h1(text):
    return [CondPageBreak(H1_ORPHAN), add_heading(text, H1_STYLE, level=0)]

def add_h2(text):
    return [add_heading(text, H2_STYLE, level=1)]

def add_h3(text):
    return [add_heading(text, H3_STYLE, level=2)]


# ━━━ DOCUMENT CONTENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_content():
    story = []

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 1: ВВЕДЕНИЕ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('1. Введение'))

    story.append(p(
        'MAC ASD v11.3.0 (Multi-Agent Construction AI System for Automated Subcontracting Decisions) '
        'представляет собой мультиагентную систему искусственного интеллекта, спроектированную для '
        'автоматизации принятия решений в сфере строительного субподряда. Система объединяет семь '
        'специализированных ИИ-агентов, каждый из которых обладает уникальным набором навыков (skills), '
        'ориентированных на конкретные аспекты строительного процесса. Архитектура системы построена на '
        'базе LangGraph StateGraph, обеспечивающей оркестрацию взаимодействия агентов через центральный '
        'узел-маршрутизатор Hermes, а LLMEngine с поддержкой профиля mac_studio (MLX) '
        'позволяет запускать все модели локально на Mac Studio M4 Max 128GB без зависимости от внешних API.'
    ))

    story.append(p(
        'Настоящий концептуальный документ преследует двоякую цель: во-первых, детально описать функционал '
        'каждого из семи агентов, включая полный перечень навыков, входных и выходных данных, а также '
        'инструменты MCP, которые каждый агент использует; во-вторых, спроектировать два ключевых '
        'рабочих процесса (workflow) системы - режим поиска подходящих лотов и режим сопровождения '
        'строительства - с пошаговым описанием маршрутизации, ветвлений и условий перехода между '
        'агентами. Только после утверждения данных концептов следует приступать к дальнейшей разработке.'
    ))

    story.append(p(
        'Система функционирует в двух основных режимах. Режим поиска лотов (Lot Search) охватывает '
        'полный цикл от мониторинга тендерных площадок до формирования вердикта о целесообразности '
        'участия в торгах. Режим сопровождения строительства (Construction Support) активируется '
        'после победы в тендере и обеспечивает поддержку на всех этапах реализации проекта: от '
        'контроля объемов работ до генерации исполнительной документации и претензионной работы. '
        'Оба режима разделяют единую инфраструктуру - базу данных PostgreSQL с pgvector, '
        'RAG-сервис с гибридным поиском, Obsidian Wiki для хранения правил и базу ловушек '
        'подрядчика (БЛС) для юридического анализа. В перспективе БЛС будет расширена до полноценной '
        'нормативной базы, включающей ГК РФ, ГрК РФ, ГОСТ/СНиП и арбитражную практику.'
    ))

    # Таблица: обзор агентов
    story.append(Spacer(1, 12))
    agent_overview = [
        [Paragraph('<b>Агент</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Роль</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Модель (Mac Studio)</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Ключевая специализация</b>', TABLE_HEADER_STYLE)],
        [Paragraph('Hermes', TABLE_CELL_CENTER),
         Paragraph('Оркестратор / PM', TABLE_CELL_STYLE),
         Paragraph('Llama 3.3 70B 4-bit', TABLE_CELL_CENTER),
         Paragraph('Маршрутизация, координация, принятие решений', TABLE_CELL_STYLE)],
        [Paragraph('ПТО', TABLE_CELL_CENTER),
         Paragraph('Инженер ПТО', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('ВОР, чертежи, спецификации, визуальный анализ', TABLE_CELL_STYLE)],
        [Paragraph('Сметчик', TABLE_CELL_CENTER),
         Paragraph('Сметный расчет', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('ФЕР/ТЕР, калькуляция, НМЦК, рентабельность', TABLE_CELL_STYLE)],
        [Paragraph('Юрист', TABLE_CELL_CENTER),
         Paragraph('Юридическая экспертиза', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('БЛС (21 ловушка), контракты, протоколы разногласий', TABLE_CELL_STYLE)],
        [Paragraph('Закупщик', TABLE_CELL_CENTER),
         Paragraph('Закупки и тендеры', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('НМЦК, анализ рынка, КП, поставщики', TABLE_CELL_STYLE)],
        [Paragraph('Логист', TABLE_CELL_CENTER),
         Paragraph('Логистика и снабжение', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('Поставщики, цены, сроки доставки, трекинг', TABLE_CELL_STYLE)],
        [Paragraph('Делопроизводитель', TABLE_CELL_CENTER),
         Paragraph('Документооборот', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('Регистрация, классификация, ИД, архив', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(agent_overview, col_ratios=[0.14, 0.17, 0.22, 0.47]))
    story.append(Paragraph('Таблица 1. Обзор агентов MAC ASD v11.3.0', CAPTION_STYLE))
    story.append(Spacer(1, 18))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 2: HERMES
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('2. Hermes - Оркестратор (PM)'))

    story.extend(add_h2('2.1. Общая характеристика'))
    story.append(p(
        'Hermes является центральным узлом системы и выполняет функции менеджера проекта (PM). '
        'Этот агент построен на базе Llama 3.3 70B - крупнейшей модели в системе, что обусловлено '
        'необходимостью сложного логического вывода, маршрутизации и координации. Hermes не выполняет '
        'узкоспециализированные задачи сам, а делегирует их профильным агентам, отслеживая ход '
        'выполнения и принимая решения о следующих шагах. В текущей реализации используется линейный '
        'пайплайн (if/elif), однако целевая архитектура предусматривает LLM-роутинг, при котором '
        'Hermes анализирует текущее состояние графа AgentState и принимает решение о следующем '
        'действии на основе контекста, а не жестко заданных правил.'
    ))

    story.extend(add_h2('2.2. Навыки (Skills)'))

    hermes_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_ROUTING', TABLE_CELL_STYLE),
         Paragraph('Интеллектуальная маршрутизация: анализ AgentState и определение следующего узла графа. Заменяет жесткий routing_map на LLM-решение.', TABLE_CELL_STYLE),
         Paragraph('AgentState, wiki-правила Hermes_Core', TABLE_CELL_STYLE),
         Paragraph('next_step (имя узла)', TABLE_CELL_STYLE)],
        [Paragraph('SK_VERDICT', TABLE_CELL_STYLE),
         Paragraph('Формирование итогового вердикта по тендеру: анализ данных от всех агентов и выдача решения "подавать / не подавать" с обоснованием.', TABLE_CELL_STYLE),
         Paragraph('intermediate_data от ПТО, Сметчика, Юриста, Логиста', TABLE_CELL_STYLE),
         Paragraph('VerdictReport (решение + обоснование + метрики)', TABLE_CELL_STYLE)],
        [Paragraph('SK_PRIORITIZE', TABLE_CELL_STYLE),
         Paragraph('Приоритизация задач: при наличии нескольких лотов или задач определяет порядок обработки на основе ожидаемой рентабельности.', TABLE_CELL_STYLE),
         Paragraph('Список лотов/задач, исторические данные', TABLE_CELL_STYLE),
         Paragraph('Приоритизированная очередь', TABLE_CELL_STYLE)],
        [Paragraph('SK_ESCALATE', TABLE_CELL_STYLE),
         Paragraph('Эскалация проблем: при выявлении критических рисков или неразрешимых противоречий инициирует запрос к человеку-оператору.', TABLE_CELL_STYLE),
         Paragraph('Флаги критических рисков от Юриста/Сметчика', TABLE_CELL_STYLE),
         Paragraph('EscalationRequest (описание + контекст)', TABLE_CELL_STYLE)],
        [Paragraph('SK_CONTEXT_SWITCH', TABLE_CELL_STYLE),
         Paragraph('Переключение между режимами: переход от поиска лотов к сопровождению строительства при подписании контракта.', TABLE_CELL_STYLE),
         Paragraph('Событие contract_signed / ks11_signed', TABLE_CELL_STYLE),
         Paragraph('Переключение режима EventManager', TABLE_CELL_STYLE)],
        [Paragraph('SK_REFLECTION_TRIGGER', TABLE_CELL_STYLE),
         Paragraph('Инициация цикла рефлексии: по завершении пайплайна запускает reflection_node для анализа логов и оптимизации wiki-правил.', TABLE_CELL_STYLE),
         Paragraph('is_complete=True', TABLE_CELL_STYLE),
         Paragraph('Вызов reflection_node', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(hermes_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 2. Навыки агента Hermes', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('2.3. Роль в рабочих процессах'))
    story.append(p(
        'В режиме поиска лотов Hermes координирует последовательную обработку каждого тендера: '
        'после регистрации документов Делопроизводителем он направляет их Закупщику для оценки НМЦК, '
        'затем ПТО для извлечения ВОР, далее Логисту для поиска поставщиков, Сметчику для расчета '
        'стоимости и Юристу для проверки рисков. По завершении всех этапов Hermes формирует '
        'итоговый вердикт. В режиме сопровождения строительства Hermes отслеживает этапы проекта, '
        'инициирует генерацию исполнительной документации, отслеживает сроки оплаты и при '
        'необходимости запускает претензионный процесс. Ключевое отличие от текущей линейной '
        'реализации - способность динамически перепрыгивать через этапы или возвращаться к '
        'предыдущим при обнаружении ошибок.'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 3: ПТО
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('3. ПТО - Инженер производственно-технического отдела'))

    story.extend(add_h2('3.1. Общая характеристика'))
    story.append(p(
        'Агент ПТО является единственным в системе, оснащенным возможностями визуального анализа '
        '(vision). Он построен на базе Qwen3.5 27B - мультимодальной модели, способной '
        'обрабатывать как текстовые документы, так и изображения (чертежи, схемы, скан-копии). '
        'Это критически важно для строительной отрасли, где значительная часть информации содержится '
        'в графических материалах. Агент ПТО работает в тесной связке с ParserEngine, который '
        'обеспечивает двухэтапный конвейер обработки PDF: Stage 1 (извлечение текста через PyMuPDF) '
        'и Stage 2 (Vision OCR для сканированных страниц). Температура '
        'вывода установлена на 0.2 - минимальная креативность для точного извлечения данных.'
    ))

    story.extend(add_h2('3.2. Навыки (Skills)'))

    pto_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_VOR_EXTRACT', TABLE_CELL_STYLE),
         Paragraph('Извлечение ВОР из тендерной документации. Парсинг таблиц, спецификаций, сметных приложений. Формирование структурированного JSON.', TABLE_CELL_STYLE),
         Paragraph('PDF/DOCX тендерной документации', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON: [{section, position, unit, quantity, code}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_DRAWING_ANALYZE', TABLE_CELL_STYLE),
         Paragraph('Визуальный анализ строительных чертежей: распознавание размеров, марок арматуры, сечений, узлов через Vision API.', TABLE_CELL_STYLE),
         Paragraph('Изображение чертежа (base64)', TABLE_CELL_STYLE),
         Paragraph('Описание чертежа + извлеченные параметры JSON', TABLE_CELL_STYLE)],
        [Paragraph('SK_SPEC_PARSE', TABLE_CELL_STYLE),
         Paragraph('Парсинг спецификаций оборудования и материалов: извлечение наименований, ГОСТ/ТУ, количеств, марок.', TABLE_CELL_STYLE),
         Paragraph('Таблицы спецификаций (PDF/XLSX)', TABLE_CELL_STYLE),
         Paragraph('Specification JSON', TABLE_CELL_STYLE)],
        [Paragraph('SK_OCR_FALLBACK', TABLE_CELL_STYLE),
         Paragraph('OCR-обработка сканированных документов: активируется автоматически, когда PyMuPDF не может извлечь текст.', TABLE_CELL_STYLE),
         Paragraph('Пустая страница PDF (scan)', TABLE_CELL_STYLE),
         Paragraph('Распознанный текст + структура', TABLE_CELL_STYLE)],
        [Paragraph('SK_VOLUME_COMPARE', TABLE_CELL_STYLE),
         Paragraph('Сверка объемов: сравнение ВОР из тендера с фактическими объемами по актам КС-2.', TABLE_CELL_STYLE),
         Paragraph('ВОР (из тендера) + КС-2 (факт)', TABLE_CELL_STYLE),
         Paragraph('Отчет о расхождениях', TABLE_CELL_STYLE)],
        [Paragraph('SK_EXEC_DOC_GEN', TABLE_CELL_STYLE),
         Paragraph('Генерация исполнительной документации: АОСР, акты приемки, журналы работ на основе ВОР и данных о выполнении.', TABLE_CELL_STYLE),
         Paragraph('ВОР + данные о выполнении + шаблоны', TABLE_CELL_STYLE),
         Paragraph('Исполнительная документация (PDF/DOCX)', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(pto_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 3. Навыки агента ПТО', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('3.3. Инструменты MCP'))
    story.append(p(
        'Агент ПТО использует следующие MCP-инструменты: asd_parse_pdf (двухэтапный конвейер '
        'через ParserEngine с Vision OCR fallback), asd_parse_xlsx (парсинг табличных данных '
        'через openpyxl), asd_vision_analyze (прямая отправка изображения в Vision модель через '
        'llm_engine.vision) и asd_compare_volumes (сверка объемов ВОР vs КС-2). Все инструменты '
        'работают через единую точку входа LLMEngine, что обеспечивает прозрачную работу '
        'через MLX-бэкенд на Mac Studio.'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 4: СМЕТЧИК
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('4. Сметчик - Специалист по сметному расчету'))

    story.extend(add_h2('4.1. Общая характеристика'))
    story.append(p(
        'Агент Сметчик построен на базе Qwen3.5 27B и отвечает за финансовую оценку проектов. '
        'Температура вывода 0.1 - самая низкая в системе, что обеспечивает максимальную '
        'точность и воспроизводимость расчетов. Сметчик работает с нормативными базами ФЕР/ТЕР '
        '(Федеральные / Территориальные единичные расценки), применяет коэффициенты пересчета '
        'в текущие цены, рассчитывает накладные расходы и сметную прибыль. Ключевая задача - '
        'формирование полной картины себестоимости для принятия решения о рентабельности участия '
        'в тендере или контроля затрат в ходе строительства.'
    ))

    story.extend(add_h2('4.2. Навыки (Skills)'))

    smeta_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_FER_CALC', TABLE_CELL_STYLE),
         Paragraph('Расчет по ФЕР/ТЕР: применение единичных расценок к позициям ВОР, расчет прямых затрат с учетом территориальных коэффициентов.', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON + нормативная база ФЕР/ТЕР', TABLE_CELL_STYLE),
         Paragraph('Локальная смета JSON', TABLE_CELL_STYLE)],
        [Paragraph('SK_NMCK_ANALYZE', TABLE_CELL_STYLE),
         Paragraph('Анализ НМЦК: оценка адекватности, сравнение с расчетной себестоимостью, определение маржинальности.', TABLE_CELL_STYLE),
         Paragraph('НМЦК из тендера + расчетная себестоимость', TABLE_CELL_STYLE),
         Paragraph('NMCKReport', TABLE_CELL_STYLE)],
        [Paragraph('SK_MAT_COST', TABLE_CELL_STYLE),
         Paragraph('Калькуляция материальных затрат: расчет стоимости материалов на основе ВОР и данных от Логиста.', TABLE_CELL_STYLE),
         Paragraph('ВОР + данные от Логиста (цены, КП)', TABLE_CELL_STYLE),
         Paragraph('Материальная смета', TABLE_CELL_STYLE)],
        [Paragraph('SK_LABOR_COST', TABLE_CELL_STYLE),
         Paragraph('Расчет трудозатрат и ФОТ: определение потребности в рабочей силе, расчет зарплат по тарифным сеткам.', TABLE_CELL_STYLE),
         Paragraph('ВОР + тарифные сетки + нормативы НР/СП', TABLE_CELL_STYLE),
         Paragraph('Трудозатраты + ФОТ + НР + СП', TABLE_CELL_STYLE)],
        [Paragraph('SK_PROFIT_MODEL', TABLE_CELL_STYLE),
         Paragraph('Моделирование рентабельности: расчет сценариев (оптимистичный, реалистичный, пессимистичный) с учетом рисков.', TABLE_CELL_STYLE),
         Paragraph('Полная смета + риски от Юриста + сроки от Логиста', TABLE_CELL_STYLE),
         Paragraph('ProfitModel', TABLE_CELL_STYLE)],
        [Paragraph('SK_ACT_COST', TABLE_CELL_STYLE),
         Paragraph('Формирование актов КС-2/КС-3: расчет стоимости выполненных работ, применение текущих индексов.', TABLE_CELL_STYLE),
         Paragraph('Данные о выполнении + сметная база', TABLE_CELL_STYLE),
         Paragraph('КС-2/КС-3 данные (JSON)', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(smeta_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 4. Навыки агента Сметчик', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 5: ЮРИСТ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('5. Юрист - Специалист по юридической экспертизе'))

    story.extend(add_h2('5.1. Общая характеристика'))
    story.append(p(
        'Агент Юрист - единственный полностью функциональный агент в текущей реализации (v11.3.0). '
        'Он построен на базе Qwen3.5 27B с температурой 0.1 и специализируется на выявлении '
        'юридических рисков в строительных контрактах. Уникальной особенностью Юриста является '
        'интеграция с БЛС (Базой Ловушек Подрядчика) - структурированной базой рисков, пополняемой '
        'из Telegram-каналов, судебной практики и внутреннего опыта. На данный момент БЛС содержит '
        '21 ловушку, охватывающую штрафные санкции, ограничения ответственности, гарантийные '
        'обязательства и нетипичные условия контрактов. БЛС хранится в PostgreSQL с векторными '
        'эмбеддингами (pgvector + bge-m3), что позволяет осуществлять семантический поиск '
        'аналогичных ситуаций через RAG. Модель Map-Reduce используется для анализа многостраничных '
        'контрактов: документ разбивается на чанки, каждый анализируется отдельно (map), затем '
        'результаты агрегируются (reduce).'
    ))

    story.extend(add_h2('5.2. Навыки (Skills)'))

    legal_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_CONTRACT_REVIEW', TABLE_CELL_STYLE),
         Paragraph('Анализ контракта с применением Map-Reduce: разбиение на чанки, поиск ловушек через БЛС (RAG), агрегация. Выявление штрафных санкций, неустоек, ограничений ответственности с указанием статей ГК РФ.', TABLE_CELL_STYLE),
         Paragraph('Текст контракта + БЛС (RAG-поиск)', TABLE_CELL_STYLE),
         Paragraph('LegalFindings: [{trap, risk_level, clause, mitigation, law_ref}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_BLS_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Семантический поиск в БЛС: поиск аналогичных рисковых ситуаций по векторному сходству через pgvector + RAG-сервис.', TABLE_CELL_STYLE),
         Paragraph('Фрагмент контракта (query)', TABLE_CELL_STYLE),
         Paragraph('Top-K релевантных ловушек из БЛС', TABLE_CELL_STYLE)],
        [Paragraph('SK_PROTOCOL_DRAFT', TABLE_CELL_STYLE),
         Paragraph('Формирование протокола разногласий: генерация юридически корректного DOCX с 4-колоночной таблицей, полными реквизитами сторон (ООО, ОГРН, ИНН, адрес, представитель) и блоком подписей. Основание: ст. 445 ГК РФ, Пленум ВС РФ N 49.', TABLE_CELL_STYLE),
         Paragraph('LegalFindings + реквизиты сторон', TABLE_CELL_STYLE),
         Paragraph('Протокол разногласий (DOCX) с реквизитами и подписями', TABLE_CELL_STYLE)],
        [Paragraph('SK_COMPLIANCE', TABLE_CELL_STYLE),
         Paragraph('Проверка соответствия: сверка условий контракта с требованиями ГрК РФ, ГОСТ, СНиП, постановлениями Правительства.', TABLE_CELL_STYLE),
         Paragraph('Условия контракта + нормативная база', TABLE_CELL_STYLE),
         Paragraph('ComplianceReport: [{violation, law, severity}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_CLAIM_DRAFT', TABLE_CELL_STYLE),
         Paragraph('Подготовка претензий: формирование досудебных претензий при нарушении сроков оплаты, неисполнении обязательств, некачественных работах.', TABLE_CELL_STYLE),
         Paragraph('Нарушение + данные контракта + БЛС', TABLE_CELL_STYLE),
         Paragraph('Претензия (DOCX) + расчет неустойки', TABLE_CELL_STYLE)],
        [Paragraph('SK_BLS_INGEST', TABLE_CELL_STYLE),
         Paragraph('Пополнение БЛС: обработка сообщений из Telegram-каналов строительной юридической тематики, извлечение новых рисков, создание эмбеддингов.', TABLE_CELL_STYLE),
         Paragraph('Telegram сообщения', TABLE_CELL_STYLE),
         Paragraph('Новые записи в legal_traps таблицу', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(legal_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 5. Навыки агента Юрист', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('5.3. БЛС: База ловушек подрядчика (v11.3.0)'))
    story.append(p(
        'БЛС представляет собой структурированную базу типовых рисковых условий, встречающихся '
        'в строительных контрактах. На текущий момент база содержит 21 ловушку, сгруппированную '
        'по категориям: штрафные санкции (5), ограничения ответственности (4), гарантийные '
        'обязательства (3), нетипичные условия (4), финансовые риски (3), согласовательные '
        'риски (2). Каждая ловушка содержит: название, описание риска, категорию, уровень '
        'риска (critical/high/medium), ссылку на норму права (статья ГК РФ/ГрК РФ), '
        'рекомендацию по митигации и формулировку для протокола разногласий. Три новые '
        'ловушки добавлены в v11.3.0: согласование субподрядчиков с Заказчиком (ст. 706 ГК РФ), '
        'безлимитная компенсация расходов при просрочке (ст. 15, 393 ГК РФ) и приоритет '
        'корпоративных политик Заказчика (ст. 421, 424 ГК РФ).'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 6: ЗАКУПЩИК
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('6. Закупщик - Специалист по тендерам и закупкам'))

    story.extend(add_h2('6.1. Общая характеристика'))
    story.append(p(
        'Агент Закупщик построен на базе Qwen3.5 27B с температурой 0.2 и отвечает за '
        'начальный этап работы с тендерами. Его главная задача - оценка целесообразности участия '
        'в торгах до того, как будут задействованы более ресурсоемкие агенты (ПТО, Сметчик). '
        'Закупщик анализирует извещения о проведении закупок, оценивает НМЦК, проверяет '
        'квалификационные требования и формирует предварительное заключение. В режиме сопровождения '
        'строительства Закупщик отвечает за мониторинг рынка материалов и услуг, сравнение цен '
        'и выбор поставщиков на основе данных от Логиста.'
    ))

    story.extend(add_h2('6.2. Навыки (Skills)'))

    procurement_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_TENDER_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Поиск тендеров: мониторинг тендерных площадок ( Zakatki, Sber А, TenderPro), фильтрация по профилю деятельности и региону.', TABLE_CELL_STYLE),
         Paragraph('Критерии поиска (регион, ОКПД2, бюджет)', TABLE_CELL_STYLE),
         Paragraph('Список тендеров с метаданными', TABLE_CELL_STYLE)],
        [Paragraph('SK_BID_STRATEGY', TABLE_CELL_STYLE),
         Paragraph('Разработка стратегии участия: анализ конкуренции, определение оптимальной цены предложения, оценка вероятности победы.', TABLE_CELL_STYLE),
         Paragraph('Данные тендера + исторические результаты', TABLE_CELL_STYLE),
         Paragraph('BidStrategy с рекомендуемой ценой', TABLE_CELL_STYLE)],
        [Paragraph('SK_NMCK_PRECHECK', TABLE_CELL_STYLE),
         Paragraph('Предварительная оценка НМЦК: быстрая проверка адекватности начальной цены до детального анализа Сметчиком.', TABLE_CELL_STYLE),
         Paragraph('НМЦК + ВОР (summary)', TABLE_CELL_STYLE),
         Paragraph('Предварительный вердикт: адекватна / занижена / завышена', TABLE_CELL_STYLE)],
        [Paragraph('SK_QUAL_CHECK', TABLE_CELL_STYLE),
         Paragraph('Проверка квалификационных требований: анализ соответствия компании требованиям закупочной документации.', TABLE_CELL_STYLE),
         Paragraph('Требования документации + профиль компании', TABLE_CELL_STYLE),
         Paragraph('QualReport: соответствие по каждому критерию', TABLE_CELL_STYLE)],
        [Paragraph('SK_MARKET_MONITOR', TABLE_CELL_STYLE),
         Paragraph('Мониторинг рынка: отслеживание цен на ключевые материалы и услуги, выявление трендов, формирование отчетов для Логиста.', TABLE_CELL_STYLE),
         Paragraph('Список материалов/услуг', TABLE_CELL_STYLE),
         Paragraph('MarketReport: текущие цены + тренды', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(procurement_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 6. Навыки агента Закупщик', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 7: ЛОГИСТ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('7. Логист - Специалист по логистике и снабжению'))

    story.extend(add_h2('7.1. Общая характеристика'))
    story.append(p(
        'Агент Логист построен на базе Qwen3.5 27B с температурой 0.2 и отвечает за обеспечение '
        'строительного объекта материалами, оборудованием и услугами. Логист работает в тесной '
        'связке с Закупщиком (получает требования) и Сметчиком (предоставляет цены для калькуляции). '
        'Уникальной особенностью Логиста является интеграция с Google Sheets для ведения реестра '
        'поставщиков и цен, а также рассылка запросов коммерческих предложений (КП) через '
        'Google Workspace API. Seed-данные включают 8 типовых позиций материалов с базовыми ценами.'
    ))

    story.extend(add_h2('7.2. Навыки (Skills)'))

    logistics_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_VENDOR_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Поиск поставщиков: запрос к базе поставщиков (Google Sheets), фильтрация по региону, специализации, рейтингу.', TABLE_CELL_STYLE),
         Paragraph('Спецификация материалов + регион', TABLE_CELL_STYLE),
         Paragraph('Список поставщиков с рейтингами', TABLE_CELL_STYLE)],
        [Paragraph('SK_PRICE_COMPARE', TABLE_CELL_STYLE),
         Paragraph('Сравнение цен: агрегация коммерческих предложений от разных поставщиков, расчет средних и минимальных цен.', TABLE_CELL_STYLE),
         Paragraph('КП от поставщиков', TABLE_CELL_STYLE),
         Paragraph('PriceComparison: [{material, vendors, prices, avg, min}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_RFQ_BROADCAST', TABLE_CELL_STYLE),
         Paragraph('Рассылка запросов КП: автоматическая отправка запросов на коммерческие предложения выбранным поставщикам через Google Workspace.', TABLE_CELL_STYLE),
         Paragraph('Спецификация + список поставщиков', TABLE_CELL_STYLE),
         Paragraph('Статус рассылки, подтверждения', TABLE_CELL_STYLE)],
        [Paragraph('SK_DELIVERY_TRACK', TABLE_CELL_STYLE),
         Paragraph('Отслеживание доставок: мониторинг статуса заказов, расчет ожидаемых дат поставки, уведомления о задержках.', TABLE_CELL_STYLE),
         Paragraph('Номера заказов / накладные', TABLE_CELL_STYLE),
         Paragraph('DeliveryStatus по каждому заказу', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(logistics_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 7. Навыки агента Логист', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 8: ДЕЛОПРОИЗВОДИТЕЛЬ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('8. Делопроизводитель - Специалист по документообороту'))

    story.extend(add_h2('8.1. Общая характеристика'))
    story.append(p(
        'Агент Делопроизводитель построен на базе Qwen3.5 27B и отвечает за регистрацию, '
        'классификацию, хранение и маршрутизацию документов в системе. Он является точкой входа '
        'для всех входящих документов: тендерная документация, договоры, акты, претензии, '
        'письма - все проходит через Делопроизводителя, который определяет тип документа, '
        'извлекает ключевые метаданные и направляет соответствующему агенту. Делопроизводитель '
        'также отвечает за формирование исходящих документов: письма, уведомления, акты приема-передачи. '
        'В режиме сопровождения строительства Делопроизводитель формирует комплексы исполнительной '
        'документации, отслеживает комплектность и обеспечивает архивирование.'
    ))

    story.extend(add_h2('8.2. Навыки (Skills)'))

    delo_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_DOC_REGISTER', TABLE_CELL_STYLE),
         Paragraph('Регистрация документов: присвоение входящего номера, определение типа документа (договор, акт, претензия, письмо), извлечение метаданных (дата, контрагент, предмет).', TABLE_CELL_STYLE),
         Paragraph('Входящий документ (PDF/DOCX)', TABLE_CELL_STYLE),
         Paragraph('DocRecord: {reg_num, type, date, counterparty, subject}', TABLE_CELL_STYLE)],
        [Paragraph('SK_DOC_CLASSIFY', TABLE_CELL_STYLE),
         Paragraph('Классификация документов: автоматическое распределение по категориям (тендерная документация, договорная, исполнительная, претензионная), определение приоритета обработки.', TABLE_CELL_STYLE),
         Paragraph('DocRecord', TABLE_CELL_STYLE),
         Paragraph('Категория + приоритет + маршрут', TABLE_CELL_STYLE)],
        [Paragraph('SK_LETTER_GEN', TABLE_CELL_STYLE),
         Paragraph('Генерация писем: формирование официальных писем по шаблонам (сопроводительные, уведомительные, запросы, ответы на претензии) с автозаполнением реквизитов.', TABLE_CELL_STYLE),
         Paragraph('Тип письма + данные контекста', TABLE_CELL_STYLE),
         Paragraph('Письмо (DOCX)', TABLE_CELL_STYLE)],
        [Paragraph('SK_ID_COMPLETENESS', TABLE_CELL_STYLE),
         Paragraph('Проверка комплектности ИД: сверка списка исполнительной документации с требованиями проекта (перечень актов, сертификатов, паспортов, протоколов). Формирование реестра недостающих документов.', TABLE_CELL_STYLE),
         Paragraph('Список ИД + требования проекта', TABLE_CELL_STYLE),
         Paragraph('CompletenessReport: [{doc_type, status, missing}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_ARCHIVE', TABLE_CELL_STYLE),
         Paragraph('Архивирование: систематизация завершенных комплектов документов, формирование описей, обеспечение версионности и целостности.', TABLE_CELL_STYLE),
         Paragraph('Завершенный проект/этап', TABLE_CELL_STYLE),
         Paragraph('Архивный комплект + опись', TABLE_CELL_STYLE)],
        [Paragraph('SK_DEADLINE_TRACK', TABLE_CELL_STYLE),
         Paragraph('Отслеживание сроков: мониторинг дедлайнов по контрактам, претензиям, ответам на письма, подаче КС-2/КС-3. Автоматические уведомления о приближающихся сроках.', TABLE_CELL_STYLE),
         Paragraph('Данные контрактов + текущая дата', TABLE_CELL_STYLE),
         Paragraph('DeadlineAlerts: [{event, deadline, days_left}]', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(delo_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 8. Навыки агента Делопроизводитель', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 9: WORKFLOW — ПОИСК ЛОТОВ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('9. Workflow: Поиск подходящих лотов'))

    story.extend(add_h2('9.1. Общее описание'))
    story.append(p(
        'Режим поиска лотов активируется при появлении нового тендера и охватывает полный цикл '
        'от регистрации документации до формирования вердикта о целесообразности участия. Workflow '
        'реализован как LangGraph StateGraph с последовательным прохождением через агентов: '
        'Делопроизводитель (регистрация) - Закупщик (предварительная оценка) - ПТО (извлечение ВОР) '
        '- Логист (поиск поставщиков) - Сметчик (расчет себестоимости) - Юрист (анализ рисков) '
        '- Hermes (вердикт). Каждый этап добавляет данные в AgentState, которые используются '
        'последующими агентами.'
    ))

    story.extend(add_h2('9.2. Пошаговое описание'))

    lot_search_steps = [
        [Paragraph('<b>Шаг</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Агент</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Действие</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выходные данные</b>', TABLE_HEADER_STYLE)],
        [Paragraph('1', TABLE_CELL_CENTER),
         Paragraph('Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Регистрация тендерной документации, классификация, извлечение метаданных', TABLE_CELL_STYLE),
         Paragraph('DocRecord + текст извещения', TABLE_CELL_STYLE)],
        [Paragraph('2', TABLE_CELL_CENTER),
         Paragraph('Закупщик', TABLE_CELL_STYLE),
         Paragraph('Предварительная оценка НМЦК, проверка квалификационных требований', TABLE_CELL_STYLE),
         Paragraph('NMCKPrecheck + QualReport', TABLE_CELL_STYLE)],
        [Paragraph('3', TABLE_CELL_CENTER),
         Paragraph('ПТО', TABLE_CELL_STYLE),
         Paragraph('Извлечение ВОР из тендерной документации, парсинг спецификаций', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON + Specification JSON', TABLE_CELL_STYLE)],
        [Paragraph('4', TABLE_CELL_CENTER),
         Paragraph('Логист', TABLE_CELL_STYLE),
         Paragraph('Поиск поставщиков, рассылка КП, сбор ценовых предложений', TABLE_CELL_STYLE),
         Paragraph('PriceComparison + VendorList', TABLE_CELL_STYLE)],
        [Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Сметчик', TABLE_CELL_STYLE),
         Paragraph('Расчет себестоимости по ФЕР/ТЕР, моделирование рентабельности', TABLE_CELL_STYLE),
         Paragraph('Локальная смета + ProfitModel', TABLE_CELL_STYLE)],
        [Paragraph('6', TABLE_CELL_CENTER),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Анализ проекта договора, выявление рисков через БЛС', TABLE_CELL_STYLE),
         Paragraph('LegalFindings + ComplianceReport', TABLE_CELL_STYLE)],
        [Paragraph('7', TABLE_CELL_CENTER),
         Paragraph('Hermes', TABLE_CELL_STYLE),
         Paragraph('Формирование итогового вердикта: подавать / не подавать', TABLE_CELL_STYLE),
         Paragraph('VerdictReport', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(lot_search_steps, col_ratios=[0.06, 0.18, 0.46, 0.30]))
    story.append(Paragraph('Таблица 9. Workflow поиска лотов: пошаговое описание', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 10: WORKFLOW — СОПРОВОЖДЕНИЕ СТРОИТЕЛЬСТВА
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('10. Workflow: Сопровождение строительства'))

    story.extend(add_h2('10.1. Общее описание'))
    story.append(p(
        'Режим сопровождения строительства активируется после подписания контракта и охватывает '
        'все этапы реализации проекта: от контроля выполнения объемов работ до генерации '
        'исполнительной документации и претензионной работы. Данный режим управляется EventManager, '
        'который отслеживает события (подписание актов, наступление сроков оплаты, выявление '
        'дефектов) и инициирует соответствующие действия агентов. Строительный процесс следует '
        'установленному порядку: от получения разрешения на строительство до ввода объекта в '
        'эксплуатацию, с формированием полного комплекта исполнительной документации на каждом этапе.'
    ))

    story.extend(add_h2('10.2. Ключевые процессы'))

    construction_steps = [
        [Paragraph('<b>Процесс</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Инициатор</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Участники</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('Контроль объемов', TABLE_CELL_STYLE),
         Paragraph('EventManager (событие КС-2)', TABLE_CELL_STYLE),
         Paragraph('ПТО, Сметчик', TABLE_CELL_STYLE),
         Paragraph('Отчет о расхождениях ВОР/КС-2', TABLE_CELL_STYLE)],
        [Paragraph('Формирование КС-2/КС-3', TABLE_CELL_STYLE),
         Paragraph('Сметчик (по графику)', TABLE_CELL_STYLE),
         Paragraph('Сметчик, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Акты КС-2/КС-3 (DOCX/PDF)', TABLE_CELL_STYLE)],
        [Paragraph('Контроль оплаты', TABLE_CELL_STYLE),
         Paragraph('EventManager (срок оплаты)', TABLE_CELL_STYLE),
         Paragraph('Hermes, Юрист', TABLE_CELL_STYLE),
         Paragraph('Напоминание / претензия', TABLE_CELL_STYLE)],
        [Paragraph('Претензионная работа', TABLE_CELL_STYLE),
         Paragraph('Юрист (нарушение условий)', TABLE_CELL_STYLE),
         Paragraph('Юрист, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Претензия (DOCX) + расчет неустойки', TABLE_CELL_STYLE)],
        [Paragraph('Генерация ИД', TABLE_CELL_STYLE),
         Paragraph('ПТО (завершение этапа)', TABLE_CELL_STYLE),
         Paragraph('ПТО, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Комплект ИД: АОСР, акты, журналы', TABLE_CELL_STYLE)],
        [Paragraph('Проверка комплектности', TABLE_CELL_STYLE),
         Paragraph('Делопроизводитель (перед сдачей)', TABLE_CELL_STYLE),
         Paragraph('Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('CompletenessReport', TABLE_CELL_STYLE)],
        [Paragraph('Протокол разногласий', TABLE_CELL_STYLE),
         Paragraph('Юрист (ловушки в договоре)', TABLE_CELL_STYLE),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Протокол (DOCX) с реквизитами и подписями', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(construction_steps, col_ratios=[0.18, 0.25, 0.27, 0.30]))
    story.append(Paragraph('Таблица 10. Ключевые процессы режима сопровождения', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 11: ИНФРАСТРУКТУРА
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('11. Инфраструктура и технологии'))

    story.extend(add_h2('11.1. Аппаратная платформа'))
    story.append(p(
        'Система развернута на Mac Studio M4 Max с 128 ГБ оперативной памяти. Все ИИ-модели '
        'работают локально через MLX-бэкенд, что исключает зависимость от внешних API и '
        'обеспечивает полную конфиденциальность данных. Модель Llama 3.3 70B в 4-битной '
        'квантовании занимает примерно 38 ГБ VRAM, Qwen3.5 27B 4-bit - около 16 ГБ, '
        'а bge-m3-mlx-4bit (эмбеддинги) - около 2 ГБ. Суммарное потребление памяти моделями '
        'составляет порядка 56 ГБ, что оставляет достаточный запас для операционной системы '
        'и рабочих данных. LLMEngine управляет загрузкой и выгрузкой моделей, оптимизируя '
        'использование RAM через профили mac_studio.'
    ))

    story.extend(add_h2('11.2. Стек технологий'))

    tech_stack = [
        [Paragraph('<b>Компонент</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Технология</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Назначение</b>', TABLE_HEADER_STYLE)],
        [Paragraph('LLM Engine', TABLE_CELL_STYLE),
         Paragraph('MLX + llama.cpp', TABLE_CELL_STYLE),
         Paragraph('Локальный инференс LLM на Apple Silicon', TABLE_CELL_STYLE)],
        [Paragraph('Оркестрация', TABLE_CELL_STYLE),
         Paragraph('LangGraph StateGraph', TABLE_CELL_STYLE),
         Paragraph('Управление рабочими процессами и маршрутизация', TABLE_CELL_STYLE)],
        [Paragraph('База данных', TABLE_CELL_STYLE),
         Paragraph('PostgreSQL + pgvector', TABLE_CELL_STYLE),
         Paragraph('Хранение данных и векторный поиск (RAG)', TABLE_CELL_STYLE)],
        [Paragraph('Эмбеддинги', TABLE_CELL_STYLE),
         Paragraph('bge-m3-mlx-4bit', TABLE_CELL_STYLE),
         Paragraph('Мультимодальные эмбеддинги для RAG', TABLE_CELL_STYLE)],
        [Paragraph('RAG', TABLE_CELL_STYLE),
         Paragraph('Гибридный (dense + sparse)', TABLE_CELL_STYLE),
         Paragraph('Семантический + лексический поиск', TABLE_CELL_STYLE)],
        [Paragraph('Wiki', TABLE_CELL_STYLE),
         Paragraph('Obsidian + Markdown', TABLE_CELL_STYLE),
         Paragraph('Хранение правил и процедур агентов', TABLE_CELL_STYLE)],
        [Paragraph('MCP', TABLE_CELL_STYLE),
         Paragraph('Model Context Protocol', TABLE_CELL_STYLE),
         Paragraph('Регистрация и вызов инструментов агентами', TABLE_CELL_STYLE)],
        [Paragraph('Документы', TABLE_CELL_STYLE),
         Paragraph('python-docx, PyMuPDF, ReportLab', TABLE_CELL_STYLE),
         Paragraph('Генерация и парсинг DOCX/PDF', TABLE_CELL_STYLE)],
        [Paragraph('Интеграции', TABLE_CELL_STYLE),
         Paragraph('Google Workspace API, SerpAPI', TABLE_CELL_STYLE),
         Paragraph('Почта, таблицы, веб-поиск', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(tech_stack, col_ratios=[0.20, 0.35, 0.45]))
    story.append(Paragraph('Таблица 11. Стек технологий MAC ASD v11.3.0', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 12: ДОРОЖНАЯ КАРТА
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('12. Дорожная карта разработки'))

    story.append(p(
        'На основе утвержденных концептов навыков агентов и рабочих процессов предлагается '
        'следующая последовательность разработки, учитывающая зависимости между компонентами '
        'и приоритеты бизнес-логики. Юрист уже реализован (v11.3.0), следующие приоритеты - '
        'ПТО Vision и Логист с интеграцией поставщиков.'
    ))

    roadmap = [
        [Paragraph('<b>Пакет</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Содержание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Агенты</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Статус</b>', TABLE_HEADER_STYLE)],
        [Paragraph('P1', TABLE_CELL_CENTER),
         Paragraph('Юрист: Map-Reduce, БЛС (21 ловушка), протоколы разногласий с реквизитами, ст. 445 ГК РФ', TABLE_CELL_STYLE),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Готово (v11.3.0)', TABLE_CELL_STYLE)],
        [Paragraph('P2', TABLE_CELL_CENTER),
         Paragraph('ПТО Vision: SK_VOR_EXTRACT, SK_DRAWING_ANALYZE, ParserEngine', TABLE_CELL_STYLE),
         Paragraph('ПТО', TABLE_CELL_STYLE),
         Paragraph('Следующий', TABLE_CELL_STYLE)],
        [Paragraph('P3', TABLE_CELL_CENTER),
         Paragraph('Логист: SK_VENDOR_SEARCH, SK_PRICE_COMPARE, SK_RFQ_BROADCAST', TABLE_CELL_STYLE),
         Paragraph('Логист', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P4', TABLE_CELL_CENTER),
         Paragraph('Сметчик: SK_FER_CALC, SK_NMCK_ANALYZE, SK_PROFIT_MODEL', TABLE_CELL_STYLE),
         Paragraph('Сметчик', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P5', TABLE_CELL_CENTER),
         Paragraph('Закупщик: SK_TENDER_SEARCH, SK_BID_STRATEGY', TABLE_CELL_STYLE),
         Paragraph('Закупщик', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P6', TABLE_CELL_CENTER),
         Paragraph('Делопроизводитель: SK_DOC_REGISTER, SK_ID_COMPLETENESS, шаблоны писем', TABLE_CELL_STYLE),
         Paragraph('Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P7', TABLE_CELL_CENTER),
         Paragraph('Hermes LLM-роутинг: замена routing_map на SK_ROUTING', TABLE_CELL_STYLE),
         Paragraph('Hermes', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P8', TABLE_CELL_CENTER),
         Paragraph('Workflow поиска лотов: интеграция всех агентов в единый пайплайн', TABLE_CELL_STYLE),
         Paragraph('Все', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P9', TABLE_CELL_CENTER),
         Paragraph('Workflow сопровождения: EventManager, претензии, ИД', TABLE_CELL_STYLE),
         Paragraph('Все', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P10', TABLE_CELL_CENTER),
         Paragraph('Расширение БЛС: ГК РФ, ГрК РФ, ГОСТ/СНиП, арбитражная практика', TABLE_CELL_STYLE),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Перспектива', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(roadmap, col_ratios=[0.08, 0.45, 0.17, 0.30]))
    story.append(Paragraph('Таблица 12. Дорожная карта разработки', CAPTION_STYLE))

    return story


# ━━━ BUILD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OUTPUT = '/home/z/my-project/download/MAC_ASD_v11_PTO_Delo_Skills_Rework_v3.pdf'

doc = TocDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=LEFT_MARGIN,
    rightMargin=RIGHT_MARGIN,
    topMargin=TOP_MARGIN,
    bottomMargin=BOTTOM_MARGIN,
    title='MAC ASD v11.3.0 - Навыки агентов и рабочие процессы',
    author='Z.ai',
    creator='Z.ai',
    subject='Концептуальный документ MAC ASD v11.3.0',
)

story = []

# ━━━ Cover Page (ReportLab, NO HTML/Type3) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cover must be slightly smaller than frame to avoid LayoutError
cover = CoverPage(AVAILABLE_WIDTH - 12, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN - 12)
story.append(cover)
story.append(PageBreak())

# ━━━ TOC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
toc = TableOfContents()
toc.levelStyles = [TOC_H1, TOC_H2]
story.append(Paragraph('<b>Содержание</b>', ParagraphStyle(
    'TOCTitle', fontName='Calibri-Bold', fontSize=22, leading=30,
    alignment=TA_CENTER, spaceBefore=40, spaceAfter=20, textColor=TEXT_PRIMARY
)))
story.append(toc)
story.append(PageBreak())

# ━━━ Content ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
story.extend(build_content())

# ━━━ Build ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
doc.multiBuild(story)
print(f'PDF generated: {OUTPUT}')
