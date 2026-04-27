#!/usr/bin/env python3
"""
MAC ASD v11.3.0 — Навыки агентов и рабочие процессы (v4).
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

    story.append(p(
        'Ключевым нововведением версии v11.3.0 является VerdictEngine - взвешенная модель принятия '
        'решений, которая агрегирует заключения всех агентов с учётом их весовых коэффициентов и '
        'правил вето. Кроме того, в данной версии расширена база ловушек подрядчика (БЛС) с 21 до '
        '58 ловушек, распределённых по 10 категориям, включая новую категорию "Процедурные ловушки". '
        'Также добавлены механизмы отката (rollback strategy) к предыдущим этапам при обнаружении '
        'ошибок, обработки неполных данных (partial data handling) на основе confidence_score от '
        'агентов, а также параллельное выполнение независимых веток рабочих процессов для '
        'оптимизации времени обработки тендеров.'
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
         Paragraph('Маршрутизация, VerdictEngine, координация, откат', TABLE_CELL_STYLE)],
        [Paragraph('ПТО', TABLE_CELL_CENTER),
         Paragraph('Инженер ПТО', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('ВОР, чертежи, спецификации, фотофиксация, визуальный анализ', TABLE_CELL_STYLE)],
        [Paragraph('Сметчик', TABLE_CELL_CENTER),
         Paragraph('Сметный расчет', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('ФЕР/ТЕР версионирование, калькуляция, НМЦК, NPV, рентабельность', TABLE_CELL_STYLE)],
        [Paragraph('Юрист', TABLE_CELL_CENTER),
         Paragraph('Юридическая экспертиза', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('БЛС (58 ловушек, 10 категорий), арбитраж, контракты', TABLE_CELL_STYLE)],
        [Paragraph('Закупщик', TABLE_CELL_CENTER),
         Paragraph('Закупки и тендеры', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('НМЦК, анализ рынка, КП, история заказчиков', TABLE_CELL_STYLE)],
        [Paragraph('Логист', TABLE_CELL_CENTER),
         Paragraph('Логистика и снабжение', TABLE_CELL_STYLE),
         Paragraph('Qwen3.5 27B 4-bit', TABLE_CELL_CENTER),
         Paragraph('Поставщики, рейтинги, цены, сроки доставки, трекинг', TABLE_CELL_STYLE)],
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
    story.append(p(
        'В версии v11.3.0 Hermes дополнен VerdictEngine - взвешенной моделью принятия решений, '
        'которая агрегирует заключения всех агентов с учётом их экспертных весов и правил вето. '
        'Это позволяет формировать обоснованный вердикт даже при противоречивых заключениях агентов, '
        'например, когда Юрист фиксирует критический риск, а Сметчик подтверждает высокую '
        'рентабельность. VerdictEngine разрешает такие конфликты через систему весов и жёстких '
        'правил вето, обеспечивая прозрачность и воспроизводимость принимаемых решений. Дополнительно '
        'Hermes получил навыки отката к предыдущим этапам и работы с неполными данными, что '
        'повышает устойчивость системы к ошибкам и нештатным ситуациям.'
    ))

    story.extend(add_h2('2.2. Навыки (Skills)'))

    hermes_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_ROUTING', TABLE_CELL_STYLE),
         Paragraph('Интеллектуальная маршрутизация: анализ AgentState и определение следующего узла графа. Заменяет жесткий routing_map на LLM-решение с учётом параллельных веток.', TABLE_CELL_STYLE),
         Paragraph('AgentState, wiki-правила Hermes_Core', TABLE_CELL_STYLE),
         Paragraph('next_step (имя узла или параллельная ветка)', TABLE_CELL_STYLE)],
        [Paragraph('SK_VERDICT', TABLE_CELL_STYLE),
         Paragraph('Формирование итогового вердикта по тендеру через VerdictEngine: взвешенная агрегация заключений агентов с учётом весовых коэффициентов и правил вето. Выдача решения "подавать / не подавать" с обоснованием.', TABLE_CELL_STYLE),
         Paragraph('intermediate_data от ПТО, Сметчика, Юриста, Логиста, Закупщика', TABLE_CELL_STYLE),
         Paragraph('VerdictReport (решение + обоснование + метрики + веса)', TABLE_CELL_STYLE)],
        [Paragraph('SK_PRIORITIZE', TABLE_CELL_STYLE),
         Paragraph('Приоритизация задач: при наличии нескольких лотов или задач определяет порядок обработки на основе ожидаемой рентабельности и рисков.', TABLE_CELL_STYLE),
         Paragraph('Список лотов/задач, исторические данные', TABLE_CELL_STYLE),
         Paragraph('Приоритизированная очередь', TABLE_CELL_STYLE)],
        [Paragraph('SK_ESCALATE', TABLE_CELL_STYLE),
         Paragraph('Эскалация проблем: при выявлении критических рисков или неразрешимых противоречий инициирует запрос к человеку-оператору. Формирует полный контекст для принятия решения.', TABLE_CELL_STYLE),
         Paragraph('Флаги критических рисков от Юриста/Сметчика', TABLE_CELL_STYLE),
         Paragraph('EscalationRequest (описание + контекст + рекомендация)', TABLE_CELL_STYLE)],
        [Paragraph('SK_CONTEXT_SWITCH', TABLE_CELL_STYLE),
         Paragraph('Переключение между режимами: переход от поиска лотов к сопровождению строительства при подписании контракта. Сохраняет состояние для возможного отката.', TABLE_CELL_STYLE),
         Paragraph('Событие contract_signed / ks11_signed', TABLE_CELL_STYLE),
         Paragraph('Переключение режима EventManager', TABLE_CELL_STYLE)],
        [Paragraph('SK_REFLECTION_TRIGGER', TABLE_CELL_STYLE),
         Paragraph('Инициация цикла рефлексии: по завершении пайплайна запускает reflection_node для анализа логов и оптимизации wiki-правил.', TABLE_CELL_STYLE),
         Paragraph('is_complete=True', TABLE_CELL_STYLE),
         Paragraph('Вызов reflection_node', TABLE_CELL_STYLE)],
        [Paragraph('SK_ROLLBACK', TABLE_CELL_STYLE),
         Paragraph('Инициация отката к предыдущему этапу при обнаружении ошибок или критических расхождений. Сохранение intermediate_data в revision_history для аудита и восстановления состояния графа.', TABLE_CELL_STYLE),
         Paragraph('rollback_trigger (флаг ошибки) + текущий AgentState', TABLE_CELL_STYLE),
         Paragraph('AgentState с восстановленными данными + revision_history запись', TABLE_CELL_STYLE)],
        [Paragraph('SK_PARTIAL_DATA', TABLE_CELL_STYLE),
         Paragraph('Принятие решения о работе с неполными данными на основе confidence_score от агентов. Если данные недостаточны, но confidence > порога, процесс продолжается с пометкой о неполноте.', TABLE_CELL_STYLE),
         Paragraph('confidence_scores от агентов + wiki-правила', TABLE_CELL_STYLE),
         Paragraph('Решение: продолжить / запросить доп. данные / эскалировать', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(hermes_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 2. Навыки агента Hermes', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('2.3. VerdictEngine - Weighted Decision Model'))
    story.append(p(
        'VerdictEngine является ключевым компонентом Hermes, обеспечивающим взвешенную агрегацию '
        'заключений всех агентов для формирования итогового вердикта по тендеру. Модель основана на '
        'трёх механизмах: весовые коэффициенты агентов, жёсткие правила вето (hard veto) и мягкая '
        'эскалация (soft escalation). Весовые коэффициенты отражают экспертную значимость заключения '
        'каждого агента: Юрист имеет наибольший вес (0.30), поскольку юридические риски могут '
        'полностью обнулить рентабельность проекта; Сметчик следует за ним (0.25), так как '
        'финансовая оценка определяет экономическую целесообразность; ПТО (0.20) обеспечивает '
        'техническую экспертизу; Логист (0.15) и Закупщик (0.10) дополняют модель операционными '
        'данными. Сумма весов равна 1.0.'
    ))

    verdict_weights = [
        [Paragraph('<b>Агент</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вес</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Правило вето</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Тип эскалации</b>', TABLE_HEADER_STYLE)],
        [Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('0.30', TABLE_CELL_CENTER),
         Paragraph('Veto при >=1 CRITICAL ловушке', TABLE_CELL_STYLE),
         Paragraph('Hard veto - вердикт "не подавать"', TABLE_CELL_STYLE)],
        [Paragraph('Сметчик', TABLE_CELL_STYLE),
         Paragraph('0.25', TABLE_CELL_CENTER),
         Paragraph('Veto при марже < 5%', TABLE_CELL_STYLE),
         Paragraph('Hard veto - вердикт "не подавать"', TABLE_CELL_STYLE)],
        [Paragraph('ПТО', TABLE_CELL_STYLE),
         Paragraph('0.20', TABLE_CELL_CENTER),
         Paragraph('Нет жёсткого вето', TABLE_CELL_STYLE),
         Paragraph('Soft escalation при расхождениях > 10%', TABLE_CELL_STYLE)],
        [Paragraph('Логист', TABLE_CELL_STYLE),
         Paragraph('0.15', TABLE_CELL_CENTER),
         Paragraph('Нет жёсткого вето', TABLE_CELL_STYLE),
         Paragraph('Soft escalation при срывах сроков поставки', TABLE_CELL_STYLE)],
        [Paragraph('Закупщик', TABLE_CELL_STYLE),
         Paragraph('0.10', TABLE_CELL_CENTER),
         Paragraph('Нет жёсткого вето', TABLE_CELL_STYLE),
         Paragraph('Soft escalation при отсутствии КП', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(verdict_weights, col_ratios=[0.14, 0.10, 0.36, 0.40]))
    story.append(Paragraph('Таблица 3. Веса агентов в VerdictEngine', CAPTION_STYLE))
    story.append(Spacer(1, 8))

    story.append(p(
        'Алгоритм принятия решения работает следующим образом. Сначала проверяются жёсткие правила '
        'вето: если Юрист выявил хотя бы одну ловушку уровня CRITICAL, вердикт автоматически '
        'формируется как "не подавать" независимо от заключений остальных агентов. Аналогично, если '
        'Сметчик фиксирует маржу ниже 5%, тендер отклоняется. При отсутствии вето вычисляется '
        'взвешенный рейтинг: каждый агент выставляет числовую оценку (0-100), которая умножается на '
        'вес агента, после чего суммы агрегируются. Итоговый балл выше порога (70) ведёт к вердикту '
        '"подавать", ниже порога (40) - "не подавать", в промежутке - "подавать с оговорками" (soft '
        'escalation). Мягкая эскалация означает, что система рекомендует участие, но требует '
        'внимания к отмеченным рискам и, как правило, ручного подтверждения от оператора.'
    ))

    story.extend(add_h2('2.4. Роль в рабочих процессах'))
    story.append(p(
        'В режиме поиска лотов Hermes координирует обработку каждого тендера с поддержкой параллельных '
        'веток и отката. После регистрации документов Делопроизводителем и предварительной оценки '
        'Закупщиком, Hermes направляет данные ПТО для извлечения ВОР. При наличии достаточных данных '
        'Логист и Сметчик запускаются параллельно, что сокращает общее время обработки тендера. '
        'Юрист может работать асинхронно после Закупщика, не блокируя финансовую и техническую '
        'оценку. При обнаружении ошибок или критических расхождений Hermes инициирует откат через '
        'SK_ROLLBACK, восстанавливая состояние из revision_history.'
    ))
    story.append(p(
        'В режиме сопровождения строительства Hermes отслеживает этапы проекта, инициирует генерацию '
        'исполнительной документации, отслеживает сроки оплаты и при необходимости запускает '
        'претензионный процесс. Ключевое отличие от текущей линейной реализации - способность '
        'динамически перепрыгивать через этапы или возвращаться к предыдущим при обнаружении '
        'ошибок. Параллельные ветки позволяют одновременно проверять комплектность документов '
        'и формировать акты КС-2/КС-3, а эскалационная лестница для неоплаченных счетов '
        'автоматизирует процесс от напоминаний до подачи иска в арбитражный суд.'
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
        'и Stage 2 (Vision OCR для сканированных страниц). Температура вывода установлена на 0.2 - '
        'минимальная креативность для точного извлечения данных.'
    ))
    story.append(p(
        'В версии v11.3.0 ПТО получил confidence_score для каждой позиции ВОР, что позволяет Hermes '
        'принимать решение о работе с неполными данными через SK_PARTIAL_DATA. ParserEngine Stage 2 '
        'обновлён: теперь используется Qwen3.5-VL для оптического распознавания текста в сочетании с '
        'PaddleOCR для обнаружения и парсинга табличных структур. Если confidence_score позиции ВОР '
        'ниже порога 0.7, ПТО автоматически формирует флаг для ручной проверки, сохраняя извлечённые '
        'данные с пометкой о низком качестве распознавания. Это значительно снижает риск ошибок в '
        'расчётах, основанных на некорректно извлечённых данных, и обеспечивает прозрачный аудит '
        'качества OCR для каждой позиции.'
    ))

    story.extend(add_h2('3.2. Навыки (Skills)'))

    pto_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_VOR_EXTRACT', TABLE_CELL_STYLE),
         Paragraph('Извлечение ВОР из тендерной документации с confidence_score. Парсинг таблиц, спецификаций, сметных приложений. Захват сносок типа "включая доставку", влияющих на расчёт Логиста. Формирование структурированного JSON.', TABLE_CELL_STYLE),
         Paragraph('PDF/DOCX тендерной документации', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON: [{section, position, unit, quantity, code, confidence, footnotes}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_DRAWING_ANALYZE', TABLE_CELL_STYLE),
         Paragraph('Визуальный анализ строительных чертежей: распознавание размеров, марок арматуры, сечений, узлов через Vision API с confidence_score.', TABLE_CELL_STYLE),
         Paragraph('Изображение чертежа (base64)', TABLE_CELL_STYLE),
         Paragraph('Описание чертежа + извлеченные параметры JSON + confidence', TABLE_CELL_STYLE)],
        [Paragraph('SK_SPEC_PARSE', TABLE_CELL_STYLE),
         Paragraph('Парсинг спецификаций оборудования и материалов: извлечение наименований, ГОСТ/ТУ, количеств, марок через PaddleOCR для таблиц.', TABLE_CELL_STYLE),
         Paragraph('Таблицы спецификаций (PDF/XLSX)', TABLE_CELL_STYLE),
         Paragraph('Specification JSON + confidence', TABLE_CELL_STYLE)],
        [Paragraph('SK_OCR_FALLBACK', TABLE_CELL_STYLE),
         Paragraph('OCR-обработка сканированных документов через Qwen3.5-VL + PaddleOCR. Активируется автоматически, когда PyMuPDF не может извлечь текст. При confidence < 0.7 формирует флаг для ручной проверки.', TABLE_CELL_STYLE),
         Paragraph('Пустая страница PDF (scan)', TABLE_CELL_STYLE),
         Paragraph('Распознанный текст + структура + confidence + manual_review_flag', TABLE_CELL_STYLE)],
        [Paragraph('SK_VOLUME_COMPARE', TABLE_CELL_STYLE),
         Paragraph('Сверка объемов: сравнение ВОР из тендера с фактическими объемами по актам КС-2. При критических расхождениях > 10% генерирует флаг для EventManager.', TABLE_CELL_STYLE),
         Paragraph('ВОР (из тендера) + КС-2 (факт)', TABLE_CELL_STYLE),
         Paragraph('Отчет о расхождениях + flag для EventManager при >10%', TABLE_CELL_STYLE)],
        [Paragraph('SK_PHOTO_VERIFY', TABLE_CELL_STYLE),
         Paragraph('Сверка фотофиксации с актами выполненных работ: сравнение фотоотчёта с позициями КС-2, проверка соответствия заявленных и визуально подтверждённых объёмов.', TABLE_CELL_STYLE),
         Paragraph('Фотоотчёт (base64) + КС-2 данные', TABLE_CELL_STYLE),
         Paragraph('PhotoVerificationReport: [{position, claimed, verified, discrepancy}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_EXEC_DOC_GEN', TABLE_CELL_STYLE),
         Paragraph('Генерация исполнительной документации: АОСР, акты приемки, журналы работ на основе ВОР и данных о выполнении. Автоматическая подстановка данных из ВОР.', TABLE_CELL_STYLE),
         Paragraph('ВОР + данные о выполнении + шаблоны', TABLE_CELL_STYLE),
         Paragraph('Исполнительная документация (PDF/DOCX)', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(pto_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 4. Навыки агента ПТО', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('3.3. Инструменты MCP'))
    story.append(p(
        'Агент ПТО использует следующие MCP-инструменты: asd_parse_pdf (двухэтапный конвейер '
        'через ParserEngine с Qwen3.5-VL + PaddleOCR для Vision OCR fallback), asd_parse_xlsx '
        '(парсинг табличных данных через openpyxl), asd_vision_analyze (прямая отправка изображения '
        'в Vision модель через llm_engine.vision с возвратом confidence_score), asd_compare_volumes '
        '(сверка объемов ВОР vs КС-2 с генерацией флагов при расхождениях > 10%) и '
        'asd_photo_verify (сверка фотофиксации с позициями актов). Все инструменты работают через '
        'единую точку входа LLMEngine, что обеспечивает прозрачную работу через MLX-бэкенд на '
        'Mac Studio. При confidence_score ниже 0.7 инструменты автоматически устанавливают флаг '
        'manual_review_flag для маршрутизации на ручную проверку.'
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
    story.append(p(
        'В версии v11.3.0 Сметчик получил поддержку версионирования ФЕР: система способна '
        'работать с несколькими версиями нормативной базы (ФЕР-2001, ФЕР-2017), автоматически '
        'определяя применимую версию на основе даты проектирования и региона. Также добавлен '
        'расчёт дисконтной ставки для NPV (Net Present Value) в модели рентабельности: '
        'SK_PROFIT_MODEL теперь учитывает вероятность задержки платежей от Заказчика, снижая '
        'приведённую стоимость будущих поступлений. Это критически важно для строительной отрасли, '
        'где задержки оплаты на 60-90 дней являются распространённой практикой и могут '
        'существенно снижать реальную рентабельность проекта.'
    ))

    story.extend(add_h2('4.2. Навыки (Skills)'))

    smeta_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_FER_CALC', TABLE_CELL_STYLE),
         Paragraph('Расчет по ФЕР/ТЕР с поддержкой версионирования: применение единичных расценок из ФЕР-2001 или ФЕР-2017 к позициям ВОР, расчет прямых затрат с учетом территориальных коэффициентов. Автоопределение версии ФЕР по дате проекта.', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON + нормативная база ФЕР/ТЕР + версия ФЕР', TABLE_CELL_STYLE),
         Paragraph('Локальная смета JSON с указанием версии ФЕР', TABLE_CELL_STYLE)],
        [Paragraph('SK_NMCK_ANALYZE', TABLE_CELL_STYLE),
         Paragraph('Анализ НМЦК: оценка адекватности, сравнение с расчетной себестоимостью, определение маржинальности. Формирует veto для VerdictEngine при марже < 5%.', TABLE_CELL_STYLE),
         Paragraph('НМЦК из тендера + расчетная себестоимость', TABLE_CELL_STYLE),
         Paragraph('NMCKReport + veto_flag (маржа < 5%)', TABLE_CELL_STYLE)],
        [Paragraph('SK_MAT_COST', TABLE_CELL_STYLE),
         Paragraph('Калькуляция материальных затрат: расчет стоимости материалов на основе ВОР и данных от Логиста. Учёт транспортных расходов из сносок ВОР.', TABLE_CELL_STYLE),
         Paragraph('ВОР + данные от Логиста (цены, КП) + footnotes', TABLE_CELL_STYLE),
         Paragraph('Материальная смета', TABLE_CELL_STYLE)],
        [Paragraph('SK_LABOR_COST', TABLE_CELL_STYLE),
         Paragraph('Расчет трудозатрат и ФОТ: определение потребности в рабочей силе, расчет зарплат по тарифным сеткам с учётом актуальной версии ФЕР.', TABLE_CELL_STYLE),
         Paragraph('ВОР + тарифные сетки + нормативы НР/СП', TABLE_CELL_STYLE),
         Paragraph('Трудозатраты + ФОТ + НР + СП', TABLE_CELL_STYLE)],
        [Paragraph('SK_PROFIT_MODEL', TABLE_CELL_STYLE),
         Paragraph('Моделирование рентабельности: расчет сценариев (оптимистичный, реалистичный, пессимистичный) с учётом вероятности задержки платежей (discount rate на NPV) и рисков от Юриста.', TABLE_CELL_STYLE),
         Paragraph('Полная смета + риски от Юриста + сроки от Логиста + discount_rate', TABLE_CELL_STYLE),
         Paragraph('ProfitModel с NPV + discount_rate', TABLE_CELL_STYLE)],
        [Paragraph('SK_ACT_COST', TABLE_CELL_STYLE),
         Paragraph('Формирование актов КС-2/КС-3: расчет стоимости выполненных работ, применение текущих индексов-дефляторов Минстроя.', TABLE_CELL_STYLE),
         Paragraph('Данные о выполнении + сметная база + индексы', TABLE_CELL_STYLE),
         Paragraph('КС-2/КС-3 данные (JSON)', TABLE_CELL_STYLE)],
        [Paragraph('SK_INDEX_UPDATE', TABLE_CELL_STYLE),
         Paragraph('Автоматическое применение индексов-дефляторов Минстроя к сметной базе. Переход от базовых цен ФЕР-2001/ФЕР-2017 к текущим ценам с учётом квартальных индексов.', TABLE_CELL_STYLE),
         Paragraph('Сметная база + квартальные индексы Минстроя', TABLE_CELL_STYLE),
         Paragraph('Скорректированная смета с индексами', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(smeta_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 5. Навыки агента Сметчик', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 5: ЮРИСТ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('5. Юрист - Специалист по юридической экспертизе'))

    story.extend(add_h2('5.1. Общая характеристика'))
    story.append(p(
        'Агент Юрист является одним из наиболее развитых агентов в текущей реализации (v11.3.0). '
        'Он построен на базе Qwen3.5 27B с температурой 0.1 и специализируется на выявлении '
        'юридических рисков в строительных контрактах. Уникальной особенностью Юриста является '
        'интеграция с БЛС (Базой Ловушек Подрядчика) - структурированной базой рисков, пополняемой '
        'из Telegram-каналов, RSS-ленты судебной практики и внутреннего опыта. На данный момент БЛС '
        'содержит 58 ловушек, распределённых по 10 категориям: платежи (8), штрафы (7), приёмка (6), '
        'объём работ (5), гарантии (5), субподряд (5), ответственность (6), корпоративные политики (5), '
        'расторжение (5), процедурные ловушки (6). БЛС хранится в PostgreSQL с векторными '
        'эмбеддингами (pgvector + bge-m3), что позволяет осуществлять семантический поиск '
        'аналогичных ситуаций через RAG.'
    ))
    story.append(p(
        'В версии v11.3.0 структура БЛС расширена новыми полями: precedent_id (ссылка на дело в '
        'картотеке арбитражных судов kad.arbitr.ru), mitigation_cost (оценочная стоимость митигации '
        'риска) и template_clause (готовая формулировка для протокола разногласий). Эти поля '
        'позволяют Юристу не только выявлять риски, но и количественно оценивать стоимость их '
        'митигации и сразу предлагать юридически выверенные формулировки для протокола разногласий. '
        'Модель Map-Reduce используется для анализа многостраничных контрактов: документ '
        'разбивается на чанки, каждый анализируется отдельно (map), затем результаты '
        'агрегируются (reduce). Добавлена новая категория - "Процедурные ловушки", охватывающая '
        'короткие сроки на согласования и каскадные сроки.'
    ))

    story.extend(add_h2('5.2. Навыки (Skills)'))

    legal_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_CONTRACT_REVIEW', TABLE_CELL_STYLE),
         Paragraph('Анализ контракта с применением Map-Reduce: разбиение на чанки, поиск ловушек через БЛС (RAG), агрегация. Выявление штрафных санкций, неустоек, ограничений ответственности с указанием статей ГК РФ. Анализ ОТСУТСТВУЮЩИХ условий (отсутствие оговорки о форс-мажоре = риск).', TABLE_CELL_STYLE),
         Paragraph('Текст контракта + БЛС (RAG-поиск)', TABLE_CELL_STYLE),
         Paragraph('LegalFindings: [{trap, risk_level, clause, mitigation, law_ref, precedent_id, mitigation_cost, template_clause, absent_condition}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_BLS_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Семантический поиск в БЛС: поиск аналогичных рисковых ситуаций по векторному сходству через pgvector + RAG-сервис. Возвращает precedent_id и mitigation_cost.', TABLE_CELL_STYLE),
         Paragraph('Фрагмент контракта (query)', TABLE_CELL_STYLE),
         Paragraph('Top-K релевантных ловушек + precedent_id + mitigation_cost', TABLE_CELL_STYLE)],
        [Paragraph('SK_PROTOCOL_DRAFT', TABLE_CELL_STYLE),
         Paragraph('Формирование протокола разногласий: генерация юридически корректного DOCX с 4-колоночной таблицей, реквизитами сторон и блоком подписей. Включает расчёт последствий (consequence calculation): что произойдёт, если протокол будет отклонён. Основание: ст. 445 ГК РФ.', TABLE_CELL_STYLE),
         Paragraph('LegalFindings + реквизиты сторон', TABLE_CELL_STYLE),
         Paragraph('Протокол разногласий (DOCX) + расчёт последствий отклонения', TABLE_CELL_STYLE)],
        [Paragraph('SK_COMPLIANCE', TABLE_CELL_STYLE),
         Paragraph('Проверка соответствия: сверка условий контракта с требованиями ГрК РФ, ГОСТ, СНиП, постановлениями Правительства.', TABLE_CELL_STYLE),
         Paragraph('Условия контракта + нормативная база', TABLE_CELL_STYLE),
         Paragraph('ComplianceReport: [{violation, law, severity}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_CLAIM_DRAFT', TABLE_CELL_STYLE),
         Paragraph('Подготовка претензий: формирование досудебных претензий при нарушении сроков оплаты, неисполнении обязательств, некачественных работах.', TABLE_CELL_STYLE),
         Paragraph('Нарушение + данные контракта + БЛС', TABLE_CELL_STYLE),
         Paragraph('Претензия (DOCX) + расчет неустойки', TABLE_CELL_STYLE)],
        [Paragraph('SK_BLS_INGEST', TABLE_CELL_STYLE),
         Paragraph('Пополнение БЛС: обработка сообщений из Telegram-каналов + RSS-ленты судебной практики. Векторный поиск для дедупликации (пропуск уже известных прецедентов). Создание эмбеддингов для новых записей.', TABLE_CELL_STYLE),
         Paragraph('Telegram сообщения + RSS судебной практики', TABLE_CELL_STYLE),
         Paragraph('Новые записи в legal_traps (deduplicated) + precedent_id', TABLE_CELL_STYLE)],
        [Paragraph('SK_ARBITRAGE_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Поиск аналогичных дел в картотеке арбитражных судов (kad.arbitr.ru). Векторный поиск по описанию спора для выявления прецедентов с исходами и суммами взысканий.', TABLE_CELL_STYLE),
         Paragraph('Описание спора / условия контракта', TABLE_CELL_STYLE),
         Paragraph('ArbitrageReport: [{case_number, court, outcome, amount, precedent_id}]', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(legal_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 6. Навыки агента Юрист', CAPTION_STYLE))
    story.append(Spacer(1, 12))

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
        'и выбор поставщиков на основе данных от Логиста. В версии v11.3.0 Закупщик получил '
        'навык проверки истории работы с Заказчиком, что позволяет оценивать платёжную дисциплину '
        'и наличие претензий ещё на этапе принятия решения об участии в тендере.'
    ))

    story.extend(add_h2('6.2. Навыки (Skills)'))

    procurement_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_TENDER_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Поиск тендеров: мониторинг тендерных площадок (Zakupki, Sber А, TenderPro), фильтрация по профилю деятельности и региону.', TABLE_CELL_STYLE),
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
        [Paragraph('SK_CUSTOMER_HISTORY', TABLE_CELL_STYLE),
         Paragraph('Проверка истории работы с Заказчиком: платил вовремя? были претензии? Источник данных: БЛС + собственная аналитика по прошлым контрактам. Влияет на discount_rate Сметчика.', TABLE_CELL_STYLE),
         Paragraph('ИНН/наименование Заказчика', TABLE_CELL_STYLE),
         Paragraph('CustomerHistoryReport: {payment_discipline, claims_count, avg_delay_days, risk_level}', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(procurement_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 7. Навыки агента Закупщик', CAPTION_STYLE))
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
        'Google Workspace API. Seed-данные включают 8 типовых позиций материалов с базовыми ценами. '
        'В версии v11.3.0 Логист получил навык автоматического обновления рейтингов поставщиков '
        'на основе фактических данных, а также интеграцию с 1C/ERP для синхронизации складских '
        'остатков и отслеживания статуса доставки КП.'
    ))

    story.extend(add_h2('7.2. Навыки (Skills)'))

    logistics_skills = [
        [Paragraph('<b>Навык</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Вход</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Выход</b>', TABLE_HEADER_STYLE)],
        [Paragraph('SK_SUPPLIER_SEARCH', TABLE_CELL_STYLE),
         Paragraph('Поиск поставщиков: запрос к базе поставщиков (Google Sheets), фильтрация по региону, специализации, рейтингу.', TABLE_CELL_STYLE),
         Paragraph('Спецификация материалов + регион', TABLE_CELL_STYLE),
         Paragraph('Список поставщиков с рейтингами', TABLE_CELL_STYLE)],
        [Paragraph('SK_PRICE_COMPARE', TABLE_CELL_STYLE),
         Paragraph('Сравнение цен: агрегация коммерческих предложений от разных поставщиков, расчет средних и минимальных цен.', TABLE_CELL_STYLE),
         Paragraph('КП от поставщиков', TABLE_CELL_STYLE),
         Paragraph('PriceComparison: [{material, vendors, prices, avg, min}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_DELIVERY_PLAN', TABLE_CELL_STYLE),
         Paragraph('Планирование доставок: составление графика поставок с учётом сроков строительства, логистических окон и наличия на складе.', TABLE_CELL_STYLE),
         Paragraph('ВОР + график работ + данные склада', TABLE_CELL_STYLE),
         Paragraph('DeliveryPlan: [{material, date, supplier, route}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_CERTIFICATE_COLLECT', TABLE_CELL_STYLE),
         Paragraph('Сбор сертификатов: автоматический запрос паспортов качества, сертификатов соответствия и санитарно-эпидемиологических заключений от поставщиков.', TABLE_CELL_STYLE),
         Paragraph('Список материалов + поставщики', TABLE_CELL_STYLE),
         Paragraph('CertificatePackage: [{material, cert_type, file}]', TABLE_CELL_STYLE)],
        [Paragraph('SK_RFQ_BROADCAST', TABLE_CELL_STYLE),
         Paragraph('Рассылка запросов КП: автоматическая отправка запросов на коммерческие предложения выбранным поставщикам. Отслеживает статус "получено/прочитано" для каждого КП.', TABLE_CELL_STYLE),
         Paragraph('Спецификация + список поставщиков', TABLE_CELL_STYLE),
         Paragraph('Статус рассылки + отслеживание "получено/прочитано"', TABLE_CELL_STYLE)],
        [Paragraph('SK_DELIVERY_TRACK', TABLE_CELL_STYLE),
         Paragraph('Отслеживание доставок: мониторинг статуса заказов, расчёт ожидаемых дат поставки, уведомления о задержках. Интеграция с 1C/ERP для синхронизации складских остатков в реальном времени.', TABLE_CELL_STYLE),
         Paragraph('Номера заказов / накладные + данные 1C/ERP', TABLE_CELL_STYLE),
         Paragraph('DeliveryStatus + складские остатки из 1C', TABLE_CELL_STYLE)],
        [Paragraph('SK_VENDOR_RATING', TABLE_CELL_STYLE),
         Paragraph('Автоматическое обновление рейтингов поставщиков на основе факта: срывы сроков, качество материалов, полнота комплектации. Источник: исторические КП + акты приемки.', TABLE_CELL_STYLE),
         Paragraph('Исторические КП + акты приемки + жалобы', TABLE_CELL_STYLE),
         Paragraph('VendorRating: [{supplier, score, on_time_rate, quality_rate}]', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(logistics_skills, col_ratios=[0.16, 0.40, 0.22, 0.22]))
    story.append(Paragraph('Таблица 8. Навыки агента Логист', CAPTION_STYLE))
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
        'документации, отслеживает комплектность и обеспечивает архивирование. Делопроизводитель '
        'является первым узлом в любом рабочем процессе и обеспечивает корректную маршрутизацию '
        'документов к профильным агентам.'
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
    story.append(Paragraph('Таблица 9. Навыки агента Делопроизводитель', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 9: WORKFLOW — ПОИСК ЛОТОВ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('9. Workflow: Поиск подходящих лотов'))

    story.extend(add_h2('9.1. Общее описание'))
    story.append(p(
        'Режим поиска лотов активируется при появлении нового тендера и охватывает полный цикл '
        'от регистрации документации до формирования вердикта о целесообразности участия. Workflow '
        'реализован как LangGraph StateGraph с последовательным и параллельным прохождением через '
        'агентов. Базовая последовательность: Делопроизводитель (регистрация) - Закупщик '
        '(предварительная оценка) - ПТО (извлечение ВОР) - Логист + Сметчик (параллельно) - '
        'Юрист (асинхронно после Закупщика) - Hermes (вердикт через VerdictEngine). Каждый этап '
        'добавляет данные в AgentState, которые используются последующими агентами. Ветвление '
        'позволяет оптимизировать время обработки: если НМЦК ниже 70% расчётной себестоимости, '
        'ПТО пропускается и вердикт формируется сразу с пометкой о заниженной цене.'
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
        [Paragraph('2.5', TABLE_CELL_CENTER),
         Paragraph('Закупщик', TABLE_CELL_STYLE),
         Paragraph('Проверка истории Заказчика через SK_CUSTOMER_HISTORY: платёжная дисциплина, претензии, средняя задержка платежей', TABLE_CELL_STYLE),
         Paragraph('CustomerHistoryReport (влияет на discount_rate Сметчика)', TABLE_CELL_STYLE)],
        [Paragraph('3', TABLE_CELL_CENTER),
         Paragraph('ПТО', TABLE_CELL_STYLE),
         Paragraph('Извлечение ВОР из тендерной документации, парсинг спецификаций. Условие: если НМЦК < 70% расчётной - шаг пропускается', TABLE_CELL_STYLE),
         Paragraph('ВОР JSON + Specification JSON + confidence', TABLE_CELL_STYLE)],
        [Paragraph('4 (парал.)', TABLE_CELL_CENTER),
         Paragraph('Логист + Сметчик', TABLE_CELL_STYLE),
         Paragraph('Параллельное выполнение: Логист ищет поставщиков и собирает КП, Сметчик рассчитывает себестоимость по ФЕР/ТЕР', TABLE_CELL_STYLE),
         Paragraph('PriceComparison + VendorList + Локальная смета + ProfitModel', TABLE_CELL_STYLE)],
        [Paragraph('5 (асинхр.)', TABLE_CELL_CENTER),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Анализ проекта договора, выявление рисков через БЛС. Запускается асинхронно после Закупщика, не блокирует шаг 3-4', TABLE_CELL_STYLE),
         Paragraph('LegalFindings + ComplianceReport + ArbitrageReport', TABLE_CELL_STYLE)],
        [Paragraph('6', TABLE_CELL_CENTER),
         Paragraph('Hermes', TABLE_CELL_STYLE),
         Paragraph('Формирование итогового вердикта через VerdictEngine: взвешенная агрегация с учётом весов и вето', TABLE_CELL_STYLE),
         Paragraph('VerdictReport (решение + обоснование + веса)', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(lot_search_steps, col_ratios=[0.07, 0.16, 0.47, 0.30]))
    story.append(Paragraph('Таблица 10. Workflow поиска лотов: пошаговое описание', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('9.3. Параллельные ветки'))
    story.append(p(
        'Архитектура v11.3.0 вводит параллельные ветки выполнения для оптимизации времени обработки '
        'тендеров. После завершения работы ПТО (шаг 3) запускаются параллельно Логист и Сметчик: '
        'Логист ищет поставщиков и собирает коммерческие предложения, а Сметчик параллельно '
        'рассчитывает себестоимость по нормативной базе ФЕР/ТЕР. Это сокращает общее время обработки '
        'на 30-40% по сравнению с последовательным выполнением. Юрист запускается асинхронно после '
        'Закупщика и работает параллельно с ПТО и последующими шагами, не блокируя техническую и '
        'финансовую оценку. Результаты Юриста агрегируются в AgentState и используются Hermes на '
        'этапе формирования вердикта. Условное ветвление: если Закупщик определяет, что НМЦК ниже '
        '70% расчётной себестоимости, ПТО пропускается и Hermes формирует вердикт "не подавать" '
        'с обоснованием о заниженной цене.'
    ))

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
        'эксплуатацию, с формированием полного комплекта исполнительной документации на каждом этапе. '
        'В версии v11.3.0 добавлена эскалационная лестница для неоплаченных счетов, автоматизация '
        'авансовых платежей и авто-сбор сертификатов из Google Drive.'
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
         Paragraph('Отчет о расхождениях ВОР/КС-2 + flag при >10%', TABLE_CELL_STYLE)],
        [Paragraph('Формирование КС-2/КС-3', TABLE_CELL_STYLE),
         Paragraph('Сметчик (по графику)', TABLE_CELL_STYLE),
         Paragraph('Сметчик, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Акты КС-2/КС-3 (DOCX/PDF)', TABLE_CELL_STYLE)],
        [Paragraph('Контроль оплаты', TABLE_CELL_STYLE),
         Paragraph('EventManager (срок оплаты)', TABLE_CELL_STYLE),
         Paragraph('Hermes, Юрист', TABLE_CELL_STYLE),
         Paragraph('Эскалационная лестница: напоминание -> претензия -> арбитраж', TABLE_CELL_STYLE)],
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
         Paragraph('Протокол (DOCX) + расчёт последствий отклонения', TABLE_CELL_STYLE)],
        [Paragraph('Авансовые платежи', TABLE_CELL_STYLE),
         Paragraph('EventManager (условие контракта)', TABLE_CELL_STYLE),
         Paragraph('Сметчик, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Счёт на аванс + контроль поступления', TABLE_CELL_STYLE)],
        [Paragraph('Сбор сертификатов', TABLE_CELL_STYLE),
         Paragraph('Логист (поставка материала)', TABLE_CELL_STYLE),
         Paragraph('Логист, ПТО', TABLE_CELL_STYLE),
         Paragraph('CertificatePackage (авто-загрузка из Google Drive)', TABLE_CELL_STYLE)],
        [Paragraph('Эскалация неоплаты', TABLE_CELL_STYLE),
         Paragraph('Hermes (3 напоминания без ответа)', TABLE_CELL_STYLE),
         Paragraph('Hermes, Юрист, Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('3 напоминания -> претензия -> арбитражный иск', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(construction_steps, col_ratios=[0.16, 0.22, 0.26, 0.36]))
    story.append(Paragraph('Таблица 11. Ключевые процессы режима сопровождения', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.append(p(
        'Эскалационная лестница для неоплаченных счетов работает автоматически: при наступлении '
        'срока оплаты EventManager фиксирует событие и инициирует первое напоминание через '
        'Делопроизводителя. Если оплата не поступает в течение 7 рабочих дней, отправляется '
        'второе напоминание с указанием сроков ответа. Третье напоминание сопровождается '
        'уведомлением о возможном применении штрафных санкций. Если после трёх напоминаний '
        'оплата не поступает, Юрист автоматически формирует досудебную претензию с расчётом '
        'неустойки. При отклонении претензии или отсутствии ответа в течение 30 дней система '
        'рекомендует подачу иска в арбитражный суд через SK_ARBITRAGE_SEARCH для поиска '
        'аналогичных дел. Авансовые платежи обрабатываются аналогично: Сметчик рассчитывает '
        'сумму аванса, Делопроизводитель формирует счёт, а EventManager отслеживает поступление.'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 11: AGENTSTATE SCHEMA
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('11. AgentState Schema'))

    story.extend(add_h2('11.1. Общая структура'))
    story.append(p(
        'AgentState является центральным объектом данных в системе MAC ASD, передаваемым между '
        'всеми узлами графа LangGraph. Каждое поле в AgentState отражает результат работы '
        'конкретного агента или системного компонента. Схема строго типизирована: обязательные '
        'поля (required) должны быть заполнены на соответствующем этапе, опциональные (optional) '
        'могут отсутствовать при определённых условиях (например, при пропуске ПТО). Версия v11.3.0 '
        'добавляет поля для поддержки отката (revision_history, rollback_triggers), работы с '
        'неполными данными (confidence_scores) и параллельного выполнения. Все составные объекты '
        '(LegalFindings, VerdictReport, ProfitModel) имеют строгие JSON-схемы, что обеспечивает '
        'совместимость между агентами и воспроизводимость результатов.'
    ))

    agent_state_fields = [
        [Paragraph('<b>Поле</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Тип</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Обязательное</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Описание</b>', TABLE_HEADER_STYLE)],
        [Paragraph('tender_id', TABLE_CELL_STYLE),
         Paragraph('str', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Уникальный идентификатор тендера', TABLE_CELL_STYLE)],
        [Paragraph('doc_record', TABLE_CELL_STYLE),
         Paragraph('DocRecord', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Результат регистрации Делопроизводителем', TABLE_CELL_STYLE)],
        [Paragraph('nmck_precheck', TABLE_CELL_STYLE),
         Paragraph('NMCKReport', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Предварительная оценка НМЦК от Закупщика', TABLE_CELL_STYLE)],
        [Paragraph('customer_history', TABLE_CELL_STYLE),
         Paragraph('CustomerHistoryReport', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('История работы с Заказчиком', TABLE_CELL_STYLE)],
        [Paragraph('vor_data', TABLE_CELL_STYLE),
         Paragraph('List[VORPosition]', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('ВОР JSON (может отсутствовать при пропуске ПТО)', TABLE_CELL_STYLE)],
        [Paragraph('price_comparison', TABLE_CELL_STYLE),
         Paragraph('PriceComparison', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Сравнение цен от Логиста', TABLE_CELL_STYLE)],
        [Paragraph('local_estimate', TABLE_CELL_STYLE),
         Paragraph('EstimateJSON', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Локальная смета от Сметчика', TABLE_CELL_STYLE)],
        [Paragraph('profit_model', TABLE_CELL_STYLE),
         Paragraph('ProfitModel', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Модель рентабельности с NPV и discount_rate', TABLE_CELL_STYLE)],
        [Paragraph('legal_findings', TABLE_CELL_STYLE),
         Paragraph('LegalFindings', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Юридические риски от Юриста', TABLE_CELL_STYLE)],
        [Paragraph('verdict_report', TABLE_CELL_STYLE),
         Paragraph('VerdictReport', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Итоговый вердикт от Hermes', TABLE_CELL_STYLE)],
        [Paragraph('confidence_scores', TABLE_CELL_STYLE),
         Paragraph('Dict[str, float]', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Оценки уверенности агентов (0.0 - 1.0)', TABLE_CELL_STYLE)],
        [Paragraph('revision_history', TABLE_CELL_STYLE),
         Paragraph('List[RevisionEntry]', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('История изменений состояния для отката', TABLE_CELL_STYLE)],
        [Paragraph('rollback_triggers', TABLE_CELL_STYLE),
         Paragraph('List[str]', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Флаги, инициирующие откат к предыдущему этапу', TABLE_CELL_STYLE)],
        [Paragraph('intermediate_data', TABLE_CELL_STYLE),
         Paragraph('Dict[str, Any]', TABLE_CELL_CENTER),
         Paragraph('Нет', TABLE_CELL_CENTER),
         Paragraph('Промежуточные данные от всех агентов', TABLE_CELL_STYLE)],
        [Paragraph('current_step', TABLE_CELL_STYLE),
         Paragraph('str', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Текущий узел графа (для маршрутизации)', TABLE_CELL_STYLE)],
        [Paragraph('is_complete', TABLE_CELL_STYLE),
         Paragraph('bool', TABLE_CELL_CENTER),
         Paragraph('Да', TABLE_CELL_CENTER),
         Paragraph('Флаг завершения пайплайна', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(agent_state_fields, col_ratios=[0.18, 0.18, 0.12, 0.52]))
    story.append(Paragraph('Таблица 12. Поля AgentState', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('11.2. JSON-схемы составных объектов'))
    story.append(p(
        'Составные объекты AgentState имеют строгие JSON-схемы, обеспечивающие совместимость '
        'между агентами. LegalFindings представляет собой массив объектов, каждый из которых '
        'содержит: trap (название ловушки), risk_level (critical/high/medium/low), clause '
        '(пункт контракта), mitigation (рекомендация по митигации), law_ref (ссылка на норму '
        'права), precedent_id (ссылка на kad.arbitr.ru), mitigation_cost (оценка стоимости '
        'митигации в рублях), template_clause (готовая формулировка для протокола) и '
        'absent_condition (флаг отсутствующего условия, например, оговорки о форс-мажоре). '
        'VerdictReport содержит: decision (подавать/не подавать/подавать с оговорками), '
        'justification (текстовое обоснование), weighted_score (итоговый взвешенный балл), '
        'agent_scores (оценки каждого агента), veto_triggered (флаг срабатывания вето) и '
        'escalation_notes (примечания при мягкой эскалации). ProfitModel включает: scenarios '
        '(оптимистичный, реалистичный, пессимистичный с NPV для каждого), discount_rate '
        '(ставка дисконтирования), payment_delay_probability (вероятность задержки платежей) '
        'и margin_percent (маржинальность по каждому сценарию).'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 12: БЛС — РАСШИРЕННАЯ СТРУКТУРА
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('12. БЛС - Расширенная структура'))

    story.extend(add_h2('12.1. Текущее состояние'))
    story.append(p(
        'БЛС (База Ловушек Подрядчика) в версии v11.3.0 содержит 58 ловушек, распределённых '
        'по 10 категориям. Это значительное расширение по сравнению с версией v11.3.0, которая '
        'содержала 21 ловушку в 6 категориях. Каждая ловушка представляет собой типовое рисковое '
        'условие, встречающееся в строительных контрактах, и содержит полное описание риска, '
        'уровень критичности, ссылку на норму права и рекомендацию по митигации. Категории '
        'ловушек охватывают все основные аспекты договорных отношений в строительстве: от '
        'платежных условий и штрафных санкций до процедурных ловушек и страхования. '
        'Распределение по категориям: платежи (8), штрафы (7), приёмка (6), объём работ (5), '
        'гарантии (5), субподряд (5), ответственность (6), корпоративные политики (5), '
        'расторжение (5), процедурные ловушки (6).'
    ))

    bls_categories = [
        [Paragraph('<b>Категория</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Кол-во</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Примеры</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Статьи ГК РФ</b>', TABLE_HEADER_STYLE)],
        [Paragraph('Платежи', TABLE_CELL_STYLE),
         Paragraph('8', TABLE_CELL_CENTER),
         Paragraph('Отсрочка оплаты, удержание гарантийного удержания, безлимитная компенсация', TABLE_CELL_STYLE),
         Paragraph('ст. 708, 711, 746', TABLE_CELL_STYLE)],
        [Paragraph('Штрафы', TABLE_CELL_STYLE),
         Paragraph('7', TABLE_CELL_CENTER),
         Paragraph('Неустойка > 0.1%/день, совокупная ответственность > 10%', TABLE_CELL_STYLE),
         Paragraph('ст. 330, 393, 395', TABLE_CELL_STYLE)],
        [Paragraph('Приёмка', TABLE_CELL_STYLE),
         Paragraph('6', TABLE_CELL_CENTER),
         Paragraph('Скрытые работы без акта, односторонняя приёмка, сокращённые сроки', TABLE_CELL_STYLE),
         Paragraph('ст. 720, 753', TABLE_CELL_STYLE)],
        [Paragraph('Объём работ', TABLE_CELL_STYLE),
         Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Уменьшение объёма без пересчёта, доп. работы без оплаты', TABLE_CELL_STYLE),
         Paragraph('ст. 709, 743', TABLE_CELL_STYLE)],
        [Paragraph('Гарантии', TABLE_CELL_STYLE),
         Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Расширенный гарантийный срок, ответственное хранение', TABLE_CELL_STYLE),
         Paragraph('ст. 723, 724, 755', TABLE_CELL_STYLE)],
        [Paragraph('Субподряд', TABLE_CELL_STYLE),
         Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Согласование субподрядчиков, запрет на субподряд', TABLE_CELL_STYLE),
         Paragraph('ст. 706', TABLE_CELL_STYLE)],
        [Paragraph('Ответственность', TABLE_CELL_STYLE),
         Paragraph('6', TABLE_CELL_CENTER),
         Paragraph('Безлимитная компенсация, приоритет корпоративных политик', TABLE_CELL_STYLE),
         Paragraph('ст. 15, 393, 421', TABLE_CELL_STYLE)],
        [Paragraph('Корп. политики', TABLE_CELL_STYLE),
         Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Приоритет внутренних регламентов Заказчика, обязательные процедуры', TABLE_CELL_STYLE),
         Paragraph('ст. 421, 424', TABLE_CELL_STYLE)],
        [Paragraph('Расторжение', TABLE_CELL_STYLE),
         Paragraph('5', TABLE_CELL_CENTER),
         Paragraph('Одностороннее расторжение без компенсации, короткие сроки уведомления', TABLE_CELL_STYLE),
         Paragraph('ст. 715, 717, 719', TABLE_CELL_STYLE)],
        [Paragraph('Процедурные', TABLE_CELL_STYLE),
         Paragraph('6', TABLE_CELL_CENTER),
         Paragraph('Короткие сроки согласования (3 дня), каскадные сроки, обязательные формы', TABLE_CELL_STYLE),
         Paragraph('ст. 445, 708', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(bls_categories, col_ratios=[0.14, 0.08, 0.44, 0.34]))
    story.append(Paragraph('Таблица 13. Категории БЛС v11.3.0 (58 ловушек, 10 категорий)', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.extend(add_h2('12.2. Новые поля'))
    story.append(p(
        'В версии v11.3.0 структура записей БЛС расширена тремя новыми полями, значительно '
        'повышающими практическую ценность базы. Поле precedent_id содержит ссылку на конкретное '
        'дело в картотеке арбитражных судов (kad.arbitr.ru), что позволяет Юристу не просто '
        'указывать на существование риска, но и подкреплять свою рекомендацию реальным '
        'судебным прецедентом с исходом и суммой взыскания. Поле mitigation_cost оценивает '
        'стоимость митигации риска в рублях, что позволяет Сметчику и Hermes количественно '
        'оценивать финансовые последствия каждого выявленного риска. Поле template_clause '
        'содержит готовую юридически выверенную формулировку для протокола разногласий, '
        'что сокращает время формирования протокола и повышает его качество. В совокупности '
        'эти поля превращают БЛС из простого справочника рисков в полноценный инструмент '
        'принятия решений с количественной оценкой и готовыми решениями.'
    ))

    story.extend(add_h2('12.3. Новая категория: Процедурные ловушки'))
    story.append(p(
        'Категория "Процедурные ловушки" является новой в v11.3.0 и охватывает риски, связанные '
        'со сроками и процедурами согласования документов. В строительной практике распространены '
        'ситуации, когда Заказчик устанавливает нереалистично короткие сроки на согласование '
        'документов (3-5 рабочих дней вместо стандартных 10-15), а при несоблюдении этих сроков '
        'подрядчик считается согласным с условиями Заказчика (молчание = согласие). Каскадные '
        'сроки - ещё одна распространённая ловушка: когда срок ответа на одно письмо зависит от '
        'срока получения другого, образуя цепочку, в которой просрочка на одном этапе ведёт к '
        'каскадному срыву всех последующих. Обязательные формы документов, не предусмотренные '
        'законодательством, но навязываемые Заказчиком, также относятся к этой категории. '
        'Всего в категории 6 ловушек, каждая из которых содержит ссылку на применимую статью '
        'ГК РФ и готовую формулировку для протокола разногласий.'
    ))

    story.extend(add_h2('12.4. Ingestion pipeline'))
    story.append(p(
        'Пополнение БЛС осуществляется через автоматизированный ingestion pipeline, объединяющий '
        'три источника данных. Первый источник - Telegram-каналы строительной юридической '
        'тематики, где юристы-практики обсуждают нетипичные условия контрактов и судебные '
        'прецеденты. Второй источник - RSS-лента судебной практики (kad.arbitr.ru), '
        'автоматически отслеживающая новые решения арбитражных судов по строительным спорам. '
        'Третий источник - внутренний опыт компании, вводимый вручную через веб-интерфейс. '
        'Ключевым элементом pipeline является дедупликация через векторный поиск: перед '
        'добавлением новой записи система проверяет, не является ли она дубликатом уже '
        'существующей ловушки, используя семантическое сходство эмбеддингов (bge-m3). '
        'Если сходство превышает порог 0.92, новая запись отклоняется как дубликат; '
        'в противном случае создаётся новая запись с автоматическим заполнением полей '
        'precedent_id, mitigation_cost и template_clause через LLM.'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 13: ИНФРАСТРУКТУРА И ТЕХНОЛОГИИ
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('13. Инфраструктура и технологии'))

    story.extend(add_h2('13.1. Аппаратная платформа'))
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
    story.append(p(
        'В версии v11.3.0 добавлена стратегия MLX offloading: при нехватке памяти для '
        'параллельной загрузки двух моделей (например, Llama 70B + Qwen 27B) LLMEngine '
        'автоматически выгружает менее приоритетную модель, сохраняя её состояние на диск, '
        'и загружает требуемую. Мониторинг памяти осуществляется через утилиту vm_stat и '
        'пользовательский агент systemd-memory, при критическом уровне свободной памяти '
        '(< 8 ГБ) инициируется принудительный gc.collect() для освобождения кэша Python. '
        'Это особенно актуально при параллельном выполнении веток рабочего процесса, когда '
        'одновременно могут потребоваться модели для Сметчика и Логиста.'
    ))

    story.extend(add_h2('13.2. Стек технологий'))

    tech_stack = [
        [Paragraph('<b>Компонент</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Технология</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Назначение</b>', TABLE_HEADER_STYLE)],
        [Paragraph('LLM Engine', TABLE_CELL_STYLE),
         Paragraph('MLX + llama.cpp', TABLE_CELL_STYLE),
         Paragraph('Локальный инференс LLM на Apple Silicon с offloading', TABLE_CELL_STYLE)],
        [Paragraph('Оркестрация', TABLE_CELL_STYLE),
         Paragraph('LangGraph StateGraph', TABLE_CELL_STYLE),
         Paragraph('Управление рабочими процессами, параллельные ветки, откат', TABLE_CELL_STYLE)],
        [Paragraph('База данных', TABLE_CELL_STYLE),
         Paragraph('PostgreSQL + pgvector', TABLE_CELL_STYLE),
         Paragraph('Хранение данных и векторный поиск (RAG)', TABLE_CELL_STYLE)],
        [Paragraph('Векторный индекс', TABLE_CELL_STYLE),
         Paragraph('FAISS (<1000 записей) / ivfflat pgvector', TABLE_CELL_STYLE),
         Paragraph('FAISS для малых коллекций, ivfflat для продакшена', TABLE_CELL_STYLE)],
        [Paragraph('Эмбеддинги', TABLE_CELL_STYLE),
         Paragraph('bge-m3-mlx-4bit', TABLE_CELL_STYLE),
         Paragraph('Мультимодальные эмбеддинги для RAG', TABLE_CELL_STYLE)],
        [Paragraph('RAG', TABLE_CELL_STYLE),
         Paragraph('Гибридный BM25 + bge-m3', TABLE_CELL_STYLE),
         Paragraph('BM25 для лексического, bge-m3 для семантического поиска; объединение через reciprocal rank fusion', TABLE_CELL_STYLE)],
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
         Paragraph('Google Workspace API, 1C/ERP, SerpAPI', TABLE_CELL_STYLE),
         Paragraph('Почта, таблицы, склад, веб-поиск', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(tech_stack, col_ratios=[0.18, 0.32, 0.50]))
    story.append(Paragraph('Таблица 14. Стек технологий MAC ASD v11.3.0', CAPTION_STYLE))
    story.append(Spacer(1, 12))

    story.append(p(
        'Гибридный поиск RAG работает следующим образом: лексический компонент (BM25) '
        'обеспечивает точное совпадение ключевых слов и юридических терминов (номера статей, '
        'названия ГОСТ), а семантический компонент (bge-m3) находит документы по смыслу, '
        'даже если они не содержат точных терминов из запроса. Результаты обоих методов '
        'объединяются через reciprocal rank fusion (RRF), что обеспечивает высокую точность '
        'как при поиске конкретных норм права, так и при поиске аналогичных рисковых ситуаций. '
        'Для векторного индекса используется двухуровневая стратегия: FAISS для коллекций '
        'менее 1000 записей (быстрый поиск в памяти), ivfflat-индекс pgvector для '
        'продакшен-баз с тысячами записей.'
    ))

    story.extend(add_h2('13.3. ParserEngine Stage 2'))
    story.append(p(
        'ParserEngine Stage 2 обеспечивает обработку сканированных документов и изображений, '
        'которые не могут быть обработаны через PyMuPDF на Stage 1. В версии v11.3.0 Stage 2 '
        'использует двухкомпонентную архитектуру: Qwen3.5-VL выполняет оптическое распознавание '
        'текста (OCR) на сканированных страницах, извлекая текстовое содержимое с учётом '
        'структуры документа, а PaddleOCR обеспечивает обнаружение и парсинг табличных структур, '
        'сохраняя ячейки, строки и столбцы в структурированном формате. Это особенно важно для '
        'ВОР и спецификаций, которые часто представлены в виде сложных многоуровневых таблиц. '
        'При confidence_score ниже порога 0.7 автоматически формируется флаг manual_review_flag, '
        'и данные помечаются как требующие ручной проверки. Это гарантирует, что ошибки OCR '
        'не приводят к некорректным расчётам в последующих этапах пайплайна.'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 14: ДОРОЖНАЯ КАРТА
    # ═══════════════════════════════════════════════════════════════════════
    story.extend(add_h1('14. Дорожная карта разработки'))

    story.append(p(
        'На основе утвержденных концептов навыков агентов и рабочих процессов предлагается '
        'следующая последовательность разработки, учитывающая зависимости между компонентами '
        'и приоритеты бизнес-логики. Версия v11.3.0 существенно пересматривает приоритеты: '
        'AgentState schema и JSON-схемы выделены в P1 как фундамент для всех последующих '
        'компонентов, а Hermes LLM-роутинг + VerdictEngine перенесены с P7 на P2, поскольку '
        'взвешенная модель принятия решений критически важна для корректной работы системы. '
        'Юрист уже реализован (v11.3.0), но его расширение запланировано на P5.'
    ))

    roadmap = [
        [Paragraph('<b>Пакет</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Содержание</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Агенты</b>', TABLE_HEADER_STYLE),
         Paragraph('<b>Статус</b>', TABLE_HEADER_STYLE)],
        [Paragraph('P1', TABLE_CELL_CENTER),
         Paragraph('AgentState schema + JSON-схемы (LegalFindings, VerdictReport, ProfitModel) + test fixtures (3 реальных тендера)', TABLE_CELL_STYLE),
         Paragraph('Все (фундамент)', TABLE_CELL_STYLE),
         Paragraph('Следующий', TABLE_CELL_STYLE)],
        [Paragraph('P2', TABLE_CELL_CENTER),
         Paragraph('Hermes LLM-роутинг + VerdictEngine (взвешенная модель, вето, эскалация). Бывший P7 - повышен!', TABLE_CELL_STYLE),
         Paragraph('Hermes', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P3', TABLE_CELL_CENTER),
         Paragraph('Сметчик: SK_FER_CALC (версионирование ФЕР), SK_INDEX_UPDATE, SK_PROFIT_MODEL (NPV + discount_rate), mock data, без интеграции Google Sheets', TABLE_CELL_STYLE),
         Paragraph('Сметчик', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P4', TABLE_CELL_CENTER),
         Paragraph('ПТО Vision: SK_VOR_EXTRACT (confidence), SK_PHOTO_VERIFY, ParserEngine Stage 2 (Qwen3.5-VL + PaddleOCR), 100 реальных чертежей, annotated dataset, VOR versioning', TABLE_CELL_STYLE),
         Paragraph('ПТО', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P5', TABLE_CELL_CENTER),
         Paragraph('Юрист БЛС expansion: цель 100 ловушек (не полный ГК РФ), SK_ARBITRAGE_SEARCH, ingestion pipeline (Telegram + RSS + dedup)', TABLE_CELL_STYLE),
         Paragraph('Юрист', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P6', TABLE_CELL_CENTER),
         Paragraph('Логист: SK_VENDOR_RATING, SK_DELIVERY_TRACK (1C/ERP), SK_RFQ_BROADCAST (отслеживание статуса)', TABLE_CELL_STYLE),
         Paragraph('Логист', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P7', TABLE_CELL_CENTER),
         Paragraph('Закупщик: SK_CUSTOMER_HISTORY, SK_BID_STRATEGY, интеграция с SK_CUSTOMER_HISTORY для discount_rate', TABLE_CELL_STYLE),
         Paragraph('Закупщик', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P8', TABLE_CELL_CENTER),
         Paragraph('Делопроизводитель: SK_DOC_REGISTER, SK_ID_COMPLETENESS, шаблоны писем', TABLE_CELL_STYLE),
         Paragraph('Делопроизводитель', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P9', TABLE_CELL_CENTER),
         Paragraph('Workflow поиска лотов: интеграция всех агентов, параллельные ветки, условное ветвление', TABLE_CELL_STYLE),
         Paragraph('Все', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P10', TABLE_CELL_CENTER),
         Paragraph('Workflow сопровождения: EventManager, эскалационная лестница, авансовые платежи, сертификаты', TABLE_CELL_STYLE),
         Paragraph('Все', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P11', TABLE_CELL_CENTER),
         Paragraph('Телеметрия и мониторинг: Prometheus + Grafana дашборды, метрики инференса, алерты на память', TABLE_CELL_STYLE),
         Paragraph('Инфра', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P12', TABLE_CELL_CENTER),
         Paragraph('Human-in-the-loop интерфейс: веб-UI для Hermes Escalation, подтверждение/отклонение вердиктов, ручной review при confidence < 0.7', TABLE_CELL_STYLE),
         Paragraph('Hermes + UI', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
        [Paragraph('P13', TABLE_CELL_CENTER),
         Paragraph('Regression testing: 50 реальных тендеров с эталонными вердиктами, автоматическое сравнение, CI/CD pipeline', TABLE_CELL_STYLE),
         Paragraph('QA', TABLE_CELL_STYLE),
         Paragraph('Планируется', TABLE_CELL_STYLE)],
    ]
    story.append(make_table(roadmap, col_ratios=[0.06, 0.48, 0.16, 0.30]))
    story.append(Paragraph('Таблица 15. Дорожная карта разработки v11.3.0', CAPTION_STYLE))

    return story


# ━━━ BUILD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OUTPUT = '/home/z/my-project/download/MAC_ASD_v11_PTO_Delo_Skills_Rework_v4.pdf'

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
