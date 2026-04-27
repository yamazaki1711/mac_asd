#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAC ASD v11.3 — Architectural Response PDF Generator
ReportLab pipeline with HTML/Playwright cover
"""

import os
import sys
import hashlib
import subprocess
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm, cm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, CondPageBreak,
    HRFlowable
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus import SimpleDocTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ━━ Output paths ━━
OUTPUT_DIR = "/home/z/my-project/download"
BODY_PDF = os.path.join(OUTPUT_DIR, "body_v113.pdf")
COVER_HTML = os.path.join(OUTPUT_DIR, "cover_v113.html")
COVER_PDF = os.path.join(OUTPUT_DIR, "cover_v113.pdf")
FINAL_PDF = os.path.join(OUTPUT_DIR, "MAC_ASD_v113_Architectural_Response.pdf")

# ━━ Color Palette (auto-generated) ━━
ACCENT       = colors.HexColor('#5835c1')
TEXT_PRIMARY  = colors.HexColor('#1a1b1c')
TEXT_MUTED    = colors.HexColor('#7e858a')
BG_SURFACE   = colors.HexColor('#d5dadd')
BG_PAGE      = colors.HexColor('#f1f2f3')
TABLE_HEADER_COLOR = ACCENT
TABLE_HEADER_TEXT  = colors.white
TABLE_ROW_EVEN     = colors.white
TABLE_ROW_ODD      = BG_SURFACE

# ━━ Page dimensions ━━
PAGE_W, PAGE_H = A4
LEFT_MARGIN = 1.0 * inch
RIGHT_MARGIN = 1.0 * inch
TOP_MARGIN = 0.9 * inch
BOTTOM_MARGIN = 0.9 * inch
AVAILABLE_WIDTH = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
AVAILABLE_HEIGHT = PAGE_H - TOP_MARGIN - BOTTOM_MARGIN

# ━━ Font Registration ━━
pdfmetrics.registerFont(TTFont('Calibri', '/usr/share/fonts/truetype/english/calibri-regular.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-Bold', '/usr/share/fonts/truetype/english/calibri-bold.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))

registerFontFamily('Calibri', normal='Calibri', bold='Calibri-Bold', italic='Calibri', boldItalic='Calibri-Bold')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans')

# ━━ Styles ━━
FONT_BODY = 'Calibri'
FONT_HEADING = 'Calibri-Bold'
FONT_MONO = 'DejaVuSans'

style_title = ParagraphStyle(
    name='DocTitle', fontName=FONT_HEADING, fontSize=22,
    leading=28, alignment=TA_CENTER, textColor=TEXT_PRIMARY,
    spaceBefore=0, spaceAfter=6
)

style_h1 = ParagraphStyle(
    name='H1', fontName=FONT_HEADING, fontSize=18,
    leading=24, alignment=TA_LEFT, textColor=ACCENT,
    spaceBefore=18, spaceAfter=10
)

style_h2 = ParagraphStyle(
    name='H2', fontName=FONT_HEADING, fontSize=14,
    leading=20, alignment=TA_LEFT, textColor=TEXT_PRIMARY,
    spaceBefore=14, spaceAfter=8
)

style_h3 = ParagraphStyle(
    name='H3', fontName=FONT_HEADING, fontSize=12,
    leading=17, alignment=TA_LEFT, textColor=TEXT_PRIMARY,
    spaceBefore=10, spaceAfter=6
)

style_body = ParagraphStyle(
    name='Body', fontName=FONT_BODY, fontSize=10.5,
    leading=16, alignment=TA_LEFT, textColor=TEXT_PRIMARY,
    spaceBefore=0, spaceAfter=6, firstLineIndent=20
)

style_body_no_indent = ParagraphStyle(
    name='BodyNoIndent', fontName=FONT_BODY, fontSize=10.5,
    leading=16, alignment=TA_LEFT, textColor=TEXT_PRIMARY,
    spaceBefore=0, spaceAfter=6
)

style_code = ParagraphStyle(
    name='Code', fontName=FONT_MONO, fontSize=9,
    leading=14, alignment=TA_LEFT, textColor=colors.HexColor('#2d2d2d'),
    spaceBefore=4, spaceAfter=4,
    leftIndent=16, backColor=colors.HexColor('#f4f4f4'),
    borderPadding=6
)

style_toc_h1 = ParagraphStyle(
    name='TOCH1', fontName=FONT_HEADING, fontSize=13,
    leading=22, leftIndent=20, textColor=TEXT_PRIMARY
)

style_toc_h2 = ParagraphStyle(
    name='TOCH2', fontName=FONT_BODY, fontSize=11,
    leading=18, leftIndent=40, textColor=TEXT_MUTED
)

# Table styles
style_th = ParagraphStyle(
    name='TH', fontName=FONT_HEADING, fontSize=9.5,
    leading=13, alignment=TA_CENTER, textColor=TABLE_HEADER_TEXT
)

style_td = ParagraphStyle(
    name='TD', fontName=FONT_BODY, fontSize=9,
    leading=13, alignment=TA_LEFT, textColor=TEXT_PRIMARY
)

style_td_center = ParagraphStyle(
    name='TDCenter', fontName=FONT_BODY, fontSize=9,
    leading=13, alignment=TA_CENTER, textColor=TEXT_PRIMARY
)

style_caption = ParagraphStyle(
    name='Caption', fontName=FONT_BODY, fontSize=9,
    leading=13, alignment=TA_CENTER, textColor=TEXT_MUTED,
    spaceBefore=3, spaceAfter=6
)

# ━━ TocDocTemplate ━━
class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

# ━━ Helper Functions ━━
H1_ORPHAN_THRESHOLD = AVAILABLE_HEIGHT * 0.15

def add_heading(text, style, level=0):
    key = 'h_%s' % hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    p = Paragraph('<a name="%s"/>%s' % (key, text), style)
    p.bookmark_name = text
    p.bookmark_level = level
    p.bookmark_text = text
    p.bookmark_key = key
    return p

def add_major_section(text):
    return [
        CondPageBreak(H1_ORPHAN_THRESHOLD),
        add_heading(text, style_h1, level=0),
    ]

def P(text):
    """Body paragraph with first-line indent."""
    return Paragraph(text, style_body)

def PNI(text):
    """Body paragraph without indent."""
    return Paragraph(text, style_body_no_indent)

def make_table(data, col_ratios, caption_text=None):
    """Create a styled table with proportional column widths."""
    col_widths = [r * AVAILABLE_WIDTH for r in col_ratios]
    t = Table(data, colWidths=col_widths, hAlign='CENTER')
    
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), TABLE_HEADER_TEXT),
        ('GRID', (0, 0), (-1, -1), 0.5, TEXT_MUTED),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    # Alternating row colors
    for i in range(1, len(data)):
        bg = TABLE_ROW_EVEN if i % 2 == 1 else TABLE_ROW_ODD
        style_commands.append(('BACKGROUND', (0, i), (-1, i), bg))
    
    t.setStyle(TableStyle(style_commands))
    
    elements = [Spacer(1, 18), t]
    if caption_text:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(caption_text, style_caption))
    elements.append(Spacer(1, 18))
    return elements

def TH(text):
    return Paragraph('<b>%s</b>' % text, style_th)

def TD(text):
    return Paragraph(text, style_td)

def TDC(text):
    return Paragraph(text, style_td_center)

# ━━ Build Story ━━
story = []

# ── Table of Contents ──
story.append(Paragraph('<b>Содержание</b>', style_title))
story.append(Spacer(1, 12))

toc = TableOfContents()
toc.levelStyles = [style_toc_h1, style_toc_h2]
story.append(toc)

# Add a brief intro paragraph after TOC to fill the page
story.append(Spacer(1, 24))
story.append(Paragraph(
    'Настоящий документ представляет собой архитектурный ответ на ключевые вопросы, '
    'поднятые в рамках ревью MAC ASD v11.3. В документе подробно описана гибридная модель '
    'принятия решений Hermes, схема состояния AgentState v2, JSON-схемы для валидации данных, '
    'тестовые фикстуры и обновлённая дорожная карта внедрения.',
    ParagraphStyle(name='TOCIntro', fontName=FONT_BODY, fontSize=10.5,
                   leading=16, alignment=TA_LEFT, textColor=TEXT_MUTED,
                   firstLineIndent=20)
))
story.append(Spacer(1, 12))
story.append(Paragraph(
    'Все архитектурные решения обоснованы требованиями регулируемой среды 44-ФЗ, '
    'необходимостью обеспечения детерминированности и объяснимости принимаемых решений, '
    'а также практическим опытом эксплуатации предыдущих версий системы.',
    ParagraphStyle(name='TOCIntro2', fontName=FONT_BODY, fontSize=10.5,
                   leading=16, alignment=TA_LEFT, textColor=TEXT_MUTED,
                   firstLineIndent=20)
))
story.append(PageBreak())

# ══════════════════════════════════════════════════════════════
# SECTION 1: Hermes and Conflicting Signals
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('1. Ответ на ключевой вопрос: Hermes и конфликтующие сигналы'))

story.append(P(
    'Центральный архитектурный вопрос MAC ASD v11.3 формулируется следующим образом: как система должна принимать решение, '
    'когда пять независимых агентов дают конфликтующие сигналы? Чисто весовая модель (weighted scoring) привлекательна '
    'своей прозрачностью и детерминированностью: каждый агент получает вес, баллы суммируются, и порог определяет вердикт. '
    'Однако весовая модель слепа к качественной семантике сигналов. Например, юрист может вернуть verdict "dangerous" '
    'с весом 0.35, но весовая сумма всё равно даст GO, если три других агента дают высокие баллы. Это недопустимо '
    'для системы, работающей в реалиях 44-ФЗ, где правовые ловушки ведут к миллионным штрафам и уголовной ответственности. '
    'Чисто весовая модель не способна моделировать veto-условия, контекстные исключения и нелинейные зависимости между рисками.'
))

story.append(P(
    'С другой стороны, чисто промпт-based подход (LLM Reasoning) обладает семантической гибкостью: языковая модель '
    'может учесть нюансы, которые невозможно закодировать формулами. Однако промпт-based модель страдает от '
    'недетерминированности, галлюцинаций и невозможности формальной верификации. При одинаковых входных данных '
    'LLM может выдать разные вердикты на разных запусках, что неприемлемо для регулируемой среды. Кроме того, '
    'промпт-based модель не даёт объяснимой цепочки решений: аудитор не сможет воспроизвести, почему система '
    'приняла конкретное решение. Это критический недостаток для тендерных процедур, подлежащих проверке ФАС.'
))

story.append(P(
    'Поэтому в MAC ASD v11.3 принята <b>гибридная 3-этапная модель принятия решений Hermes</b>, объединяющая '
    'достоинства обоих подходов и устраняющая их недостатки. Модель работает в три этапа: (1) Weight Scoring — '
    'формальный расчёт взвешенного балла по предопределённым весам агентов; (2) Veto Override — проверка '
    'жёстких veto-правил, которые могут немедленно перевести вердикт в NO_GO независимо от суммарного балла; '
    '(3) LLM Reasoning — семантический анализ для пограничных случаев (grey zone), где формальный скоринг '
    'не даёт однозначного ответа. Такая архитектура гарантирует детерминированность для чётких случаев, '
    'безопасность через veto-правила и гибкость для пограничных ситуаций.'
))

story.append(Paragraph('<b>1.1 Таблица весов агентов по умолчанию</b>', style_h2))

weights_data = [
    [TH('Агент'), TH('Вес'), TH('Обоснование')],
    [TD('Юрист'), TDC('0.35'), TD('Правовые ловушки — главный риск')],
    [TD('Сметчик'), TDC('0.25'), TD('Рентабельность — критерий выживания')],
    [TD('ПТО'), TDC('0.20'), TD('Объёмы — основа калькуляции')],
    [TD('Закупщик'), TDC('0.12'), TD('Рыночная информация')],
    [TD('Логист'), TDC('0.08'), TD('Поставки')],
]
story.extend(make_table(weights_data, [0.20, 0.15, 0.65], 'Таблица 1. Веса агентов Hermes по умолчанию'))

story.append(Paragraph('<b>1.2 Формула скоринга</b>', style_h2))

story.append(PNI(
    'Взвешенный скоринг рассчитывается по формуле, где каждый агент отправляет нормализованный балл '
    'от 0.0 до 1.0, умножаемый на вес агента. Сумма весов равна 1.0. Результирующий score '
    'сравнивается с пороговыми значениями для определения предварительного вердикта:'
))

story.append(Paragraph(
    '<b>Score = Sum(w<sub>i</sub> * s<sub>i</sub>)</b>, где w<sub>i</sub> — вес агента, s<sub>i</sub> — нормализованный балл агента (0.0-1.0)',
    style_body_no_indent
))

score_thresholds_data = [
    [TH('Диапазон Score'), TH('Предварительный вердикт'), TH('Дальнейшее действие')],
    [TDC('Score >= 0.70'), TDC('GO'), TD('Проверка veto-правил; если veto нет — финальный GO')],
    [TDC('0.40 <= Score < 0.70'), TDC('CONDITIONAL_GO'), TD('Передача в LLM Reasoning (grey zone)')],
    [TDC('Score < 0.40'), TDC('NO_GO'), TD('Проверка veto-правил; финальный NO_GO')],
]
story.extend(make_table(score_thresholds_data, [0.25, 0.30, 0.45], 'Таблица 2. Пороговые значения скоринга'))

story.append(P(
    'После расчёта score и определения предварительного вердикта система проверяет veto-правила. '
    'Если хотя бы одно veto-правило срабатывает, вердикт принудительно устанавливается в NO_GO, '
    'независимо от значения score. Это гарантирует, что критические риски никогда не будут '
    'проигнорированы из-за высоких баллов других агентов. Только если veto-правила не срабатывают '
    'и вердикт попадает в grey zone (CONDITIONAL_GO), система переходит к этапу LLM Reasoning, '
    'где языковая модель анализирует полный контекст и принимает окончательное решение.'
))

# ══════════════════════════════════════════════════════════════
# SECTION 2: AgentState v2
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('2. AgentState v2 — Схема состояния'))

story.append(P(
    'AgentState v2 представляет собой полную переработку схемы состояния, используемой агентами '
    'MAC ASD для обмена данными в рамках рабочего процесса. Версия v1 использовала единый словарь '
    'intermediate_data для хранения всех промежуточных результатов, что приводило к неструктурированным '
    'данным, отсутствию типизации и невозможности формальной валидации. Версия v2 вводит типизированные '
    'подструктуры для каждого агента, обязательные поля аудита, историю ревизий и количественные оценки '
    'уверенности. Это критически важно для воспроизводимости решений и соответствия требованиям 44-ФЗ '
    'к документированию процедур.'
))

story.append(P(
    'Ключевые отличия AgentState v2 от v1 включают: (1) типизированные sub-структуры — вместо единого '
    'dict каждый агент получает собственный тип (VORResult, LegalResult, SmetaResult и т.д.), что '
    'обеспечивает статическую типизацию и автодополнение в IDE; (2) confidence_scores — словарь '
    'числовых оценок уверенности каждого агента от 0.0 до 1.0, используемый Hermes для взвешивания '
    'сигналов; (3) audit_trail — пошаговый журнал действий, записывающий каждый переход между узлами '
    'графа с временными метками; (4) revision_history — история ревизий состояния, позволяющая '
    'откатываться к предыдущим точкам при ошибках; (5) rollback_point — именованная точка отката, '
    'устанавливаемая перед критическими операциями.'
))

# AgentState v2 fields table
agentstate_data = [
    [TH('Поле'), TH('Тип'), TH('Req'), TH('Описание')],
    [TD('schema_version'), TD('str'), TDC('Да'), TD('"2.0"')],
    [TD('workflow_mode'), TD('str'), TDC('Да'), TD('"lot_search" / "construction_support"')],
    [TD('project_id'), TD('int'), TDC('Да'), TD('ID проекта в БД')],
    [TD('current_lot_id'), TD('Optional[str]'), TDC('Нет'), TD('ID тендерного лота')],
    [TD('task_description'), TD('str'), TDC('Да'), TD('Описание задачи')],
    [TD('messages'), TD('Annotated[List[Any], add_messages]'), TDC('Да'), TD('Накопление истории чата')],
    [TD('vor_result'), TD('Optional[VORResult]'), TDC('Нет'), TD('ПТО: извлечённая ВОР')],
    [TD('legal_result'), TD('Optional[LegalResult]'), TDC('Нет'), TD('Юрист: юридический анализ')],
    [TD('smeta_result'), TD('Optional[SmetaResult]'), TDC('Нет'), TD('Сметчик: расчёт стоимости')],
    [TD('procurement_result'), TD('Optional[ProcurementResult]'), TDC('Нет'), TD('Закупщик: анализ тендера')],
    [TD('logistics_result'), TD('Optional[LogisticsResult]'), TDC('Нет'), TD('Логист: поставки')],
    [TD('archive_result'), TD('Optional[ArchiveResult]'), TDC('Нет'), TD('Делопроизводитель: регистрация')],
    [TD('intermediate_data'), TD('Dict[str, Any]'), TDC('Да'), TD('Legacy (обратная совместимость)')],
    [TD('findings'), TD('List[Dict[str, Any]]'), TDC('Да'), TD('Найденные риски/ловушки')],
    [TD('confidence_scores'), TD('Dict[str, float]'), TDC('Да'), TD('Уверенность агентов (0.0-1.0)')],
    [TD('hermes_decision'), TD('Optional[HermesDecision]'), TDC('Нет'), TD('Структурированное решение Hermes')],
    [TD('current_step'), TD('str'), TDC('Да'), TD('Текущий шаг')],
    [TD('next_step'), TD('str'), TDC('Да'), TD('Следующий узел')],
    [TD('event_type'), TD('Optional[str]'), TDC('Нет'), TD('Тип события')],
    [TD('is_complete'), TD('bool'), TDC('Да'), TD('Флаг завершения')],
    [TD('audit_trail'), TD('List[StepLog]'), TDC('Да'), TD('Пошаговый аудит')],
    [TD('revision_history'), TD('List[RevisionEntry]'), TDC('Да'), TD('История ревизий')],
    [TD('rollback_point'), TD('Optional[str]'), TDC('Нет'), TD('Точка отката')],
    [TD('created_at'), TD('str'), TDC('Да'), TD('ISO 8601')],
    [TD('updated_at'), TD('str'), TDC('Да'), TD('ISO 8601')],
]
story.extend(make_table(agentstate_data, [0.22, 0.25, 0.08, 0.45], 'Таблица 3. Поля AgentState v2'))

story.append(Paragraph('<b>2.1 Функция миграции migrate_v1_to_v2()</b>', style_h2))

story.append(P(
    'Для обеспечения плавного перехода с v1 на v2 реализована функция миграции migrate_v1_to_v2(), '
    'которая преобразует старое состояние в новый формат. Функция извлекает данные из intermediate_data, '
    'распределяет их по типизированным sub-структурам, инициализирует новые поля (confidence_scores, '
    'audit_trail, revision_history) значениями по умолчанию и сохраняет оригинальные данные в '
    'intermediate_data для обратной совместимости. Миграция является односторонней: после преобразования '
    'возврат к v1 не поддерживается. Функция также устанавливает rollback_point на момент миграции, '
    'чтобы можно было идентифицировать точку перехода в истории ревизий.'
))

story.append(Paragraph(
    '<b>migrate_v1_to_v2(state_v1: dict) -&gt; AgentState:</b><br/>'
    '&nbsp;&nbsp;schema_version = "2.0"<br/>'
    '&nbsp;&nbsp;vor_result = state_v1.intermediate_data.get("vor")<br/>'
    '&nbsp;&nbsp;legal_result = state_v1.intermediate_data.get("legal")<br/>'
    '&nbsp;&nbsp;smeta_result = state_v1.intermediate_data.get("smeta")<br/>'
    '&nbsp;&nbsp;procurement_result = state_v1.intermediate_data.get("procurement")<br/>'
    '&nbsp;&nbsp;logistics_result = state_v1.intermediate_data.get("logistics")<br/>'
    '&nbsp;&nbsp;archive_result = state_v1.intermediate_data.get("archive")<br/>'
    '&nbsp;&nbsp;confidence_scores = {}<br/>'
    '&nbsp;&nbsp;audit_trail = []<br/>'
    '&nbsp;&nbsp;revision_history = [RevisionEntry(version="1.0", migrated_to="2.0")]<br/>'
    '&nbsp;&nbsp;rollback_point = "migration_v1_v2"',
    style_code
))

story.append(Paragraph('<b>2.2 Пример create_initial_state()</b>', style_h2))

story.append(P(
    'Для создания нового состояния v2 используется фабричная функция create_initial_state(), '
    'которая инициализирует все обязательные поля значениями по умолчанию и устанавливает '
    'временные метки. Функция принимает project_id, workflow_mode и task_description как '
    'обязательные параметры, а остальные поля заполняет безопасными значениями по умолчанию. '
    'Это гарантирует, что любое новое состояние валидно с точки зрения схемы v2 и не содержит '
    'null-значений в обязательных полях.'
))

story.append(Paragraph(
    '<b>create_initial_state(project_id, workflow_mode, task_description) -&gt; AgentState:</b><br/>'
    '&nbsp;&nbsp;return AgentState(<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;schema_version="2.0",<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;workflow_mode=workflow_mode,<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;project_id=project_id,<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;current_lot_id=None,<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;task_description=task_description,<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;messages=[],<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;intermediate_data={},<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;findings=[],<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;confidence_scores={},<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;current_step="START",<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;next_step="extract_vor",<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;is_complete=False,<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;audit_trail=[],<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;revision_history=[],<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;created_at=iso_now(),<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;updated_at=iso_now(),<br/>'
    '&nbsp;&nbsp;)',
    style_code
))

# ══════════════════════════════════════════════════════════════
# SECTION 3: JSON Schemas
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('3. JSON-схемы: VerdictReport, ProfitModel, AgentSignal, VetoRule'))

story.append(P(
    'Для обеспечения формальной валидации данных между агентами и компонентами Hermes в MAC ASD v11.3 '
    'введены строгие JSON-схемы. Каждая схема определяет обязательные и опциональные поля, типы данных, '
    'диапазоны значений и семантические ограничения. Схемы используются как на этапе генерации данных '
    '(агенты обязаны формировать корректные структуры), так и на этапе приёмки (Hermes валидирует входные '
    'данные перед обработкой). Это исключает целый класс ошибок, связанных с некорректными или неполными '
    'данными, и обеспечивает совместимость между версиями компонентов.'
))

story.append(Paragraph('<b>3.1 VerdictReport</b>', style_h2))

story.append(P(
    'VerdictReport — это итоговый структурированный отчёт о решении Hermes по тендеру. Он содержит '
    'финальный вердикт (GO / CONDITIONAL_GO / NO_GO), числовой score, детализацию по каждому агенту, '
    'список сработавших veto-правил и текстовое обоснование решения. VerdictReport является основным '
    'документом, который видит пользователь, и должен содержать всю информацию, необходимую для принятия '
    'окончательного решения об участии в тендере.'
))

verdict_fields_data = [
    [TH('Поле'), TH('Тип'), TH('Описание')],
    [TD('verdict'), TD('str'), TD('GO | CONDITIONAL_GO | NO_GO')],
    [TD('score'), TD('float'), TD('Итоговый взвешенный score (0.0-1.0)')],
    [TD('agent_signals'), TD('List[AgentSignal]'), TD('Сигналы от каждого агента')],
    [TD('veto_triggered'), TD('List[str]'), TD('Имена сработавших veto-правил')],
    [TD('reasoning'), TD('str'), TD('Текстовое обоснование от LLM (если grey zone)')],
    [TD('risk_level'), TD('str'), TD('LOW | MEDIUM | HIGH | CRITICAL')],
    [TD('timestamp'), TD('str'), TD('ISO 8601 момент принятия решения')],
]
story.extend(make_table(verdict_fields_data, [0.22, 0.28, 0.50], 'Таблица 4. Поля VerdictReport'))

story.append(Paragraph(
    '<b>Пример VerdictReport:</b><br/>'
    '{<br/>'
    '&nbsp;&nbsp;"verdict": "CONDITIONAL_GO",<br/>'
    '&nbsp;&nbsp;"score": 0.58,<br/>'
    '&nbsp;&nbsp;"agent_signals": [<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;{"agent": "legal", "score": 0.4, "confidence": 0.85, "verdict": "caution"},<br/>'
    '&nbsp;&nbsp;&nbsp;&nbsp;{"agent": "smeta", "score": 0.7, "confidence": 0.92, "verdict": "go"}<br/>'
    '&nbsp;&nbsp;],<br/>'
    '&nbsp;&nbsp;"veto_triggered": [],<br/>'
    '&nbsp;&nbsp;"reasoning": "Юрист выявляет нестандартные условия ...",<br/>'
    '&nbsp;&nbsp;"risk_level": "MEDIUM",<br/>'
    '&nbsp;&nbsp;"timestamp": "2026-04-20T14:30:00Z"<br/>'
    '}',
    style_code
))

story.append(Paragraph('<b>3.2 ProfitModel</b>', style_h2))

story.append(P(
    'ProfitModel описывает финансовую модель тендера, включая позиции ВОР (ведомость объёмов работ), '
    'расчёт маржинальности и условное ветвление для случаев, когда НМЦК составляет менее 70% от '
    'рыночной стоимости. Модель является ключевым входом для SmetaResult и используется Hermes для '
    'проверки veto-правила veto_nmck_below_70pct. Каждая позиция ВОР содержит описание, объём, '
    'единицу измерения, цену по НМЦК и расчётную рыночную цену. Маржинальность рассчитывается как '
    'отношение прибыли к выручке с учётом накладных расходов и налоговой нагрузки.'
))

profit_fields_data = [
    [TH('Поле'), TH('Тип'), TH('Описание')],
    [TD('nmck'), TD('float'), TD('Начальная максимальная цена контракта')],
    [TD('market_price'), TD('float'), TD('Расчётная рыночная стоимость')],
    [TD('nmck_to_market_ratio'), TD('float'), TD('Отношение НМЦК к рынку (порог: 0.70)')],
    [TD('profit_margin'), TD('float'), TD('Маржинальность (% от выручки)')],
    [TD('overhead_rate'), TD('float'), TD('Накладные расходы (%)')],
    [TD('tax_rate'), TD('float'), TD('Налоговая нагрузка (%)')],
    [TD('vor_positions'), TD('List[VORPosition]'), TD('Позиции ведомости объёмов работ')],
    [TD('is_nmck_critical'), TD('bool'), TD('НМЦК &lt; 70% рынка (ветвление логики)')],
]
story.extend(make_table(profit_fields_data, [0.25, 0.22, 0.53], 'Таблица 5. Поля ProfitModel'))

story.append(P(
    'Когда is_nmck_critical = True (НМЦК менее 70% от рынка), ProfitModel активирует дополнительный '
    'анализ: расчёт точки безубыточности, оценку риска незавершения и проверку возможности оптимизации '
    'затрат. Это условное ветвление реализовано через ветвящийся подграф в LangGraph, который при '
    'критическом НМЦК направляет выполнение через дополнительные узлы анализа перед формированием '
    'финального SmetaResult. Без этого ветвления система могла бы выдать GO на тендер, где '
    'финансовая модель изначально убыточна, что является одним из наиболее опасных сценариев.'
))

story.append(Paragraph('<b>3.3 AgentSignal</b>', style_h2))

story.append(P(
    'AgentSignal — это унифицированный формат сигнала, который каждый агент отправляет в Hermes Router '
    'по завершении своей работы. Сигнал содержит идентификатор агента, числовой балл (0.0-1.0), '
    'уверенность агента в своём заключении (0.0-1.0), текстовый вердикт и список обнаруженных рисков. '
    'Формат стандартизирован для обеспечения единообразной обработки в WeightedScoringEngine и '
    'VetoEngine. Каждый AgentSignal проходит валидацию на этапе приёмки: score и confidence обязаны '
    'находиться в диапазоне [0.0, 1.0], agent_id — совпадать с одним из пяти зарегистрированных '
    'агентов, а risks — содержать хотя бы один элемент при score ниже 0.5.'
))

signal_fields_data = [
    [TH('Поле'), TH('Тип'), TH('Описание')],
    [TD('agent_id'), TD('str'), TD('Идентификатор агента (legal, smeta, vor, procurement, logistics)')],
    [TD('score'), TD('float'), TD('Нормализованный балл (0.0-1.0)')],
    [TD('confidence'), TD('float'), TD('Уверенность агента (0.0-1.0)')],
    [TD('verdict'), TD('str'), TD('go | caution | dangerous | no_data')],
    [TD('risks'), TD('List[RiskItem]'), TD('Обнаруженные риски с уровнями критичности')],
    [TD('details'), TD('Optional[dict]'), TD('Дополнительные данные агента')],
]
story.extend(make_table(signal_fields_data, [0.22, 0.25, 0.53], 'Таблица 6. Поля AgentSignal'))

story.append(Paragraph('<b>3.4 VetoRule</b>', style_h2))

story.append(P(
    'VetoRule описывает формат veto-правила — жёсткого ограничения, которое при срабатывании '
    'принудительно устанавливает вердикт NO_GO. Каждое правило содержит уникальный идентификатор, '
    'условие срабатывания (выражение на DSL), целевой вердикт и приоритет. Правила проверяются '
    'в порядке убывания приоритета; первое сработавшее правило определяет вердикт. В текущей '
    'реализации определены четыре veto-правила, покрывающие наиболее критичные сценарии.'
))

veto_data = [
    [TH('ID правила'), TH('Условие'), TH('Вердикт')],
    [TD('veto_dangerous_verdict'), TD('legal verdict == "dangerous"'), TDC('NO_GO')],
    [TD('veto_margin_below_10'), TD('profit_margin &lt; 10%'), TDC('NO_GO')],
    [TD('veto_critical_traps_3plus'), TD('critical_count &gt;= 3'), TDC('NO_GO')],
    [TD('veto_nmck_below_70pct'), TD('НМЦК &lt; 70% рынка'), TDC('NO_GO')],
]
story.extend(make_table(veto_data, [0.30, 0.40, 0.30], 'Таблица 7. Veto-правила Hermes'))

# ══════════════════════════════════════════════════════════════
# SECTION 4: Test Fixtures
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('4. Тестовые фикстуры (3 тендера)'))

story.append(P(
    'Для верификации корректности работы Hermes Router и всех компонентов MAC ASD v11.3 разработаны '
    'три тестовых фикстуры, представляющих типичные сценарии: простой тендер с очевидным GO, '
    'средний тендер с пограничными показателями и тендер с множественными ловушками, требующий '
    'категорический NO_GO. Каждая фикстура содержит полный набор данных AgentState v2, включая '
    'результаты всех агентов, что позволяет протестировать все три ветви Hermes: прямое GO через '
    'весовой скоринг, grey zone с LLM Reasoning и veto-override для NO_GO.'
))

fixtures_data = [
    [TH('Параметр'), TH('Простой (GO)'), TH('Средний (CONDITIONAL_GO)'), TH('С ловушками (NO_GO)')],
    [TD('Лот'), TDC('T-2026-0001'), TDC('T-2026-0451'), TDC('T-2026-0789')],
    [TD('Объект'), TD('Ремонт офисов'), TD('Складской комплекс'), TD('Реконструкция ЦОД')],
    [TD('НМЦК'), TDC('12.5 млн'), TDC('55 млн'), TDC('85 млн')],
    [TD('Маржа'), TDC('34.4%'), TDC('32.0%'), TDC('8.2%')],
    [TD('Критических'), TDC('0'), TDC('0'), TDC('3')],
    [TD('Высоких'), TDC('1'), TDC('3'), TDC('7')],
    [TD('НМЦК vs рынок'), TDC('-5%'), TDC('-12%'), TDC('-35%')],
    [TD('Уверенность ПТО'), TDC('0.92'), TDC('0.78'), TDC('0.55')],
    [TD('Вердикт'), TDC('GO'), TDC('CONDITIONAL_GO'), TDC('NO_GO')],
]
story.extend(make_table(fixtures_data, [0.20, 0.25, 0.28, 0.27], 'Таблица 8. Сравнение тестовых фикстур'))

story.append(Paragraph('<b>4.1 Фикстура T-2026-0001: Простой тендер (GO)</b>', style_h2))

story.append(P(
    'Тендер на ремонт офисных помещений с НМЦК 12.5 млн рублей, маржинальностью 34.4% и рыночной '
    'стоимостью всего на 5% выше НМЦК. Юридических ловушек не обнаружено, один риск высокого уровня '
    '(стандартные условия ответственности). ПТО извлёк ВОР с уверенностью 0.92, все объёмы подтверждаются '
    'документацией. Ожидаемый результат: Score = 0.82, veto-правила не срабатывают, вердикт GO без '
    'перехода к LLM Reasoning. Этот фикстура верифицирует базовый сценарий, в котором все агенты '
    'дают положительные сигналы и система быстро принимает решение.'
))

story.append(Paragraph('<b>4.2 Фикстура T-2026-0451: Средний тендер (CONDITIONAL_GO)</b>', style_h2))

story.append(P(
    'Тендер на строительство складского комплекса с НМЦК 55 млн рублей, маржинальностью 32.0% и '
    'НМЦК на 12% ниже рынка. Обнаружены три риска высокого уровня: нестандартные условия приёмки, '
    'короткие сроки выполнения и ограниченный перечень субподрядчиков. Уверенность ПТО снижена до 0.78 '
    'из-за расхождений в спецификации материалов. Ожидаемый результат: Score = 0.58, попадание в grey zone, '
    'переход к LLM Reasoning, который с учётом контекста выдаёт CONDITIONAL_GO с рекомендациями '
    'по дополнительной проработке. Этот фикстура верифицирует работу grey zone и LLM Reasoning.'
))

story.append(Paragraph('<b>4.3 Фикстура T-2026-0789: Тендер с ловушками (NO_GO)</b>', style_h2))

story.append(P(
    'Тендер на реконструкцию ЦОД с НМЦК 85 млн рублей, критически низкой маржинальностью 8.2% и '
    'НМЦК на 35% ниже рынка. Обнаружены три критических риска (штрафы за простой оборудования, '
    'ответственность за сохранность данных, отсутствие эскроу-счёта) и семь высоких. Юридический вердикт: '
    'dangerous. Уверенность ПТО — 0.55 из-за отсутствия рабочей документации. Ожидаемый результат: '
    'срабатывают veto_dangerous_verdict, veto_margin_below_10 и veto_nmck_below_70pct, вердикт NO_GO '
    'без перехода к LLM Reasoning. Этот фикстура верифицирует корректность veto-механизма.'
))

story.append(Paragraph('<b>4.4 Пример использования фикстур</b>', style_h2))

story.append(P(
    'Фикстуры загружаются из директории tests/fixtures/ в формате JSON, соответствующем схеме AgentState v2. '
    'Каждая фикстура проходит через полный пайплайн Hermes Router, после чего результат сравнивается '
    'с ожидаемым вердиктом. Это обеспечивает регрессионное тестирование при любых изменениях в логике '
    'скоринга, veto-правилах или промптах LLM. Ниже приведён пример загрузки и запуска фикстуры.'
))

story.append(Paragraph(
    '<b>Пример запуска:</b><br/>'
    'from tests.fixtures import load_fixture<br/>'
    'from hermes.router import HermesRouter<br/>'
    '<br/>'
    'fixture = load_fixture("T-2026-0789")<br/>'
    'router = HermesRouter()<br/>'
    'report = router.decide(fixture)<br/>'
    'assert report.verdict == "NO_GO"<br/>'
    'assert "veto_margin_below_10" in report.veto_triggered<br/>'
    'assert "veto_dangerous_verdict" in report.veto_triggered',
    style_code
))

# ══════════════════════════════════════════════════════════════
# SECTION 5: Hermes Router
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('5. Hermes Router — реализация'))

story.append(P(
    'HermesRouter является центральным компонентом принятия решений в MAC ASD v11.3. Он реализует '
    'трёхэтапную модель Hermes, координируя работу пяти агентов и принимая итоговое решение об участии '
    'в тендере. Класс спроектирован как stateless-компонент: все данные о текущем тендере передаются '
    'через AgentState v2, что обеспечивает возможность параллельной обработки нескольких тендеров '
    'и лёгкое горизонтальное масштабирование. Архитектура класса следует принципам единой ответственности: '
    'каждый внутренний компонент отвечает за один этап пайплайна.'
))

story.append(Paragraph('<b>5.1 Signal Extractor</b>', style_h2))

story.append(P(
    'Signal Extractor отвечает за извлечение структурированных AgentSignal из результатов работы '
    'пяти агентов. Для каждого агента компонент считывает соответствующую sub-структуру из AgentState v2 '
    '(например, legal_result для Юриста или smeta_result для Сметчика), нормализует внутренний '
    'вердикт агента в числовой score от 0.0 до 1.0 и извлекает confidence из confidence_scores. '
    'Если агент ещё не завершил работу (результат отсутствует), Signal Extractor генерирует сигнал '
    'с score = 0.0, confidence = 0.0 и verdict = "no_data". Это гарантирует, что WeightedScoringEngine '
    'всегда получает полный набор из пяти сигналов, даже если часть агентов не работала.'
))

extractor_data = [
    [TH('Агент'), TH('Источник в AgentState'), TH('Маппинг вердикта')],
    [TD('Юрист'), TD('legal_result'), TD('go=1.0, caution=0.5, dangerous=0.0')],
    [TD('Сметчик'), TD('smeta_result'), TD('go=1.0, caution=0.5, no_data=0.0')],
    [TD('ПТО'), TD('vor_result'), TD('go=1.0, caution=0.5, no_data=0.0')],
    [TD('Закупщик'), TD('procurement_result'), TD('go=1.0, caution=0.5, no_data=0.0')],
    [TD('Логист'), TD('logistics_result'), TD('go=1.0, caution=0.5, no_data=0.0')],
]
story.extend(make_table(extractor_data, [0.18, 0.32, 0.50], 'Таблица 9. Signal Extractor: маппинг вердиктов'))

story.append(Paragraph('<b>5.2 WeightedScoringEngine</b>', style_h2))

story.append(P(
    'WeightedScoringEngine реализует формальный расчёт взвешенного балла по формуле, описанной в '
    'разделе 1. Движок принимает список AgentSignal, умножает score каждого сигнала на вес агента '
    'и суммирует результаты. Полученный итоговый score сравнивается с пороговыми значениями: '
    'Score >= 0.70 даёт предварительный GO, 0.40 <= Score < 0.70 — CONDITIONAL_GO, '
    'Score < 0.40 — NO_GO. Движок также учитывает confidence агентов: если средний confidence '
    'ниже 0.6, порог GO повышается до 0.80, что требует большей определённости для положительного '
    'решения при сомнительных данных. Это предотвращает ложноположительные решения на основе '
    'ненадёжных заключений.'
))

story.append(Paragraph('<b>5.3 VetoEngine</b>', style_h2))

story.append(P(
    'VetoEngine проверяет четыре veto-правила после расчёта WeightedScoringEngine. Правила проверяются '
    'в порядке приоритета: сначала veto_dangerous_verdict (наивысший приоритет, так как правовой риск '
    'является наиболее критичным), затем veto_margin_below_10, veto_critical_traps_3plus и '
    'veto_nmck_below_70pct. Если хотя бы одно правило срабатывает, VetoEngine немедленно возвращает '
    'вердикт NO_GO и список сработавших правил. Проверка прекращается после первого срабатывания '
    'с наивысшим приоритетом, однако все правила логируются для аудита. Это позволяет обнаружить '
    'комбинированные риски, даже если решение уже определено первым сработавшим veto-правилом.'
))

story.append(Paragraph('<b>5.4 LLM Reasoning (grey zone)</b>', style_h2))

story.append(P(
    'Если предварительный вердикт попадает в grey zone (CONDITIONAL_GO) и veto-правила не сработали, '
    'HermesRouter передаёт управление LLM Reasoning. Этот компонент формирует промпт, содержащий '
    'полный контекст: описание тендера, сигналы всех агентов с confidence, список обнаруженных рисков '
    'и предварительный score. Языковая модель анализирует семантику рисков, выявляет скрытые зависимости '
    'между ними и формирует итоговое обоснование. Результат LLM может подтвердить CONDITIONAL_GO '
    '(с рекомендациями по митигации рисков) или повысить вердикт до GO (если риски оказались '
    'несущественными при более глубоком анализе). Понижение вердикта до NO_GO через LLM не допускается: '
    'для этого существуют veto-правила.'
))

story.append(Paragraph(
    '<b>Структура промпта LLM:</b><br/>'
    'system: Ты — аналитик тендерных рисков. На основе данных агентов<br/>'
    '&nbsp;&nbsp;определи: подтвердить CONDITIONAL_GO или повысить до GO.<br/>'
    '&nbsp;&nbsp;Понижение до NO_GO запрещено — для этого есть veto-правила.<br/>'
    'user: Тендер: {task_description}<br/>'
    '&nbsp;&nbsp;НМЦК: {nmck}, Маржа: {margin}%, Риск-факторы: {risks}<br/>'
    '&nbsp;&nbsp;Score: {score}, Агенты: {agent_summary}<br/>'
    '&nbsp;&nbsp;Дай обоснованное решение в формате VerdictReport.',
    style_code
))

story.append(Paragraph('<b>5.5 Risk Level Calculator</b>', style_h2))

story.append(P(
    'Risk Level Calculator определяет общий уровень риска тендера на основе количества и критичности '
    'обнаруженных рисков, а также значений confidence агентов. Калькулятор использует матрицу рисков: '
    'LOW (0-1 высоких, 0 критических), MEDIUM (2-3 высоких или 1 критический), HIGH (4-6 высоких '
    'или 2 критических), CRITICAL (7+ высоких или 3+ критических). Уровень риска включается в '
    'VerdictReport и отображается пользователю как индикатор приоритетности проработки. '
    'Дополнительно калькулятор учитывает средний confidence агентов: если он ниже 0.5, уровень риска '
    'повышается на одну ступень, так как низкая уверенность означает недостаток информации для '
    'надёжного решения.'
))

risk_matrix_data = [
    [TH('Уровень'), TH('Высоких рисков'), TH('Критических рисков'), TH('Доп. условие')],
    [TDC('LOW'), TDC('0-1'), TDC('0'), TD('Средний confidence >= 0.7')],
    [TDC('MEDIUM'), TDC('2-3'), TDC('1'), TD('Средний confidence >= 0.5')],
    [TDC('HIGH'), TDC('4-6'), TDC('2'), TD('Средний confidence >= 0.4')],
    [TDC('CRITICAL'), TDC('7+'), TDC('3+'), TD('Или средний confidence &lt; 0.4')],
]
story.extend(make_table(risk_matrix_data, [0.18, 0.22, 0.25, 0.35], 'Таблица 10. Матрица уровней риска'))

# ══════════════════════════════════════════════════════════════
# SECTION 6: Implementation Roadmap
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('6. Дорожная карта внедрения (обновлённая)'))

story.append(P(
    'Дорожная карта внедрения MAC ASD v11.3 разделена на четыре фазы: P0 (недели 1-2), P1 (недели 3-4), '
    'P2 (недели 5-6) и P3 (долгосрочная перспектива). Каждая фаза определяет конкретные задачи, '
    'их статус и зависимости. Фаза P0 является текущей и включает все критические компоненты, '
    'необходимые для первого рабочего прототипа. Последующие фазы наращивают функциональность '
    'и повышают надёжность системы. Реализация ведётся итеративно: каждая фаза завершается '
    'демонстрацией работающего функционала и набором регрессионных тестов.'
))

story.append(Paragraph('<b>6.1 P0 (неделя 1-2): Критический минимум</b>', style_h2))

story.append(P(
    'Фаза P0 включает реализацию всех компонентов, описанных в настоящем документе: AgentState v2, '
    'Hermes Router с WeightedScoringEngine, VetoEngine и LLM Reasoning, JSON-схемы и тестовые '
    'фикстуры. На текущий момент реализованы: структура AgentState v2, миграция migrate_v1_to_v2(), '
    'WeightedScoringEngine, VetoEngine с четырьмя правилами, Signal Extractor и Risk Level Calculator. '
    'Остаётся доработать: интеграцию LLM Reasoning с production-моделью, валидацию JSON-схем через '
    'jsonschema и покрытие тестовыми фикстурами edge cases (пустые результаты агентов, пограничные '
    'значения score). Все реализованные компоненты проходят регрессионные тесты на трёх фикстурах.'
))

p0_data = [
    [TH('Компонент'), TH('Статус'), TH('Примечание')],
    [TD('AgentState v2'), TDC('Реализовано'), TD('Поля, типы, валидация')],
    [TD('migrate_v1_to_v2()'), TDC('Реализовано'), TD('Обратная совместимость')],
    [TD('WeightedScoringEngine'), TDC('Реализовано'), TD('Формула, пороги, confidence')],
    [TD('VetoEngine (4 правила)'), TDC('Реализовано'), TD('Приоритеты, логирование')],
    [TD('Signal Extractor'), TDC('Реализовано'), TD('5 агентов, маппинг вердиктов')],
    [TD('Risk Level Calculator'), TDC('Реализовано'), TD('Матрица, confidence-корректировка')],
    [TD('LLM Reasoning'), TDC('В процессе'), TD('Промпт написан, интеграция с API')],
    [TD('JSON-схемы (валидация)'), TDC('В процессе'), TD('Схемы написаны, jsonschema pending')],
    [TD('Тестовые фикстуры (edge)'), TDC('Не начато'), TD('Пустые результаты, пограничные score')],
]
story.extend(make_table(p0_data, [0.30, 0.18, 0.52], 'Таблица 11. Статус P0'))

story.append(Paragraph('<b>6.2 P1 (неделя 3-4): Усиление аналитики</b>', style_h2))

story.append(P(
    'Фаза P1 фокусируется на усилении аналитических возможностей системы. Три ключевых направления: '
    '(1) RAG hybrid + reranker — внедрение гибридной retrieval-augmented generation с двустадийным '
    'ранжированием документов для повышения релевантности контекста, поставляемого агентам; '
    '(2) SK_FER_CALC caching — кэширование результатов расчёта ФЕР для типовых конструктивных '
    'элементов, сокращающее время работы Сметчика на 40-60% для повторяющихся позиций ВОР; '
    '(3) SK_DRAWING_ANALYZE verification — верификация результатов анализа чертежей через '
    'перекрёстную проверку с данными ВОР и спецификаций. Каждый компонент P1 проходит '
    'интеграционное тестирование с полным пайплайном Hermes.'
))

story.append(Paragraph('<b>6.3 P2 (неделя 5-6): Расширение и оптимизация</b>', style_h2))

story.append(P(
    'Фаза P2 расширяет охват системы и оптимизирует производительность. Ключевые задачи: '
    '(1) расширение БЛС (базы локальных смет) для поддержки ГрК (гражданских конструкций) и '
    'ГК (гидротехнических конструкций), что увеличивает покрытие ФЕР с 65% до 85%; '
    '(2) pre-warm моделей — предзагрузка LLM-моделей в память при старте системы, сокращающая '
    'время первого ответа с 8-12 секунд до менее 2 секунд; (3) Prometheus метрики — экспорт '
    'операционных метрик (время ответа агентов, частота veto, распределение вердиктов) в формат '
    'Prometheus для мониторинга в реальном времени. P2 также включает нагрузочное тестирование '
    'с имитацией 100+ параллельных тендеров.'
))

story.append(Paragraph('<b>6.4 P3 (долгосрочно): Стратегические инициативы</b>', style_h2))

story.append(P(
    'Фаза P3 охватывает стратегические инициативы, не имеющие критических сроков, но необходимые '
    'для долгосрочного развития платформы. Ключевые направления: (1) MCP-серверы — реализация '
    'Model Context Protocol для унифицированного доступа к внешним данным (реестр недобросовестных '
    'поставщиков, ФГИС ЦС, ЕИС); (2) интерактивная коррекция — возможность пользователя '
    'вмешиваться в процесс принятия решения, корректируя веса агентов или отменяя veto-правила '
    'с обязательным обоснованием; (3) мульти-бэкенд LLM — поддержка нескольких LLM-провайдеров '
    '(OpenAI, Anthropic, локальные модели) с автоматическим переключением при недоступности '
    'основного провайдера. P3 планируется к началу реализации после стабилизации P0-P2.'
))

# ══════════════════════════════════════════════════════════════
# SECTION 7: New Roadmap Items
# ══════════════════════════════════════════════════════════════
story.extend(add_major_section('7. Новые roadmap-пункты'))

story.append(P(
    'В дополнение к основному roadmap (P0-P3) в MAC ASD v11.3 добавлены три новых пункта, '
    'выделенных в отдельный раздел ввиду их кросс-фазной природы. Эти инициативы затрагивают '
    'несколько фаз одновременно и требуют координации между различными потоками разработки. '
    'Каждый пункт имеет собственный приоритет и сроки реализации, привязанные к основным фазам.'
))

story.append(Paragraph('<b>7.1 P11: Телеметрия (Prometheus + Grafana)</b>', style_h2))

story.append(P(
    'Пункт P11 предусматривает создание полноценной системы телеметрии на базе стека Prometheus + Grafana. '
    'Система будет собирать метрики из всех компонентов MAC ASD: время выполнения каждого агента, '
    'частоту срабатывания veto-правил, распределение вердиктов (GO/CONDITIONAL_GO/NO_GO), '
    'confidence-профили по агентам, использование LLM Reasoning и токен-расход. Grafana дашборды '
    'будут визуализировать эти метрики в реальном времени, позволяя оперативно выявлять деградацию '
    'качества решений и аномалии в поведении агентов. Реализация P11 частично пересекается с P2 '
    '(Prometheus метрики) и расширяет её до полного мониторингового стека. Сроки: начало в неделю 5, '
    'завершение — неделя 8.'
))

p11_data = [
    [TH('Метрика'), TH('Тип'), TH('Описание')],
    [TD('agent_execution_seconds'), TD('Histogram'), TD('Время выполнения каждого агента')],
    [TD('veto_triggered_total'), TD('Counter'), TD('Счётчик срабатываний veto-правил по типам')],
    [TD('verdict_distribution'), TD('Gauge'), TD('Распределение GO/CONDITIONAL_GO/NO_GO')],
    [TD('agent_confidence_avg'), TD('Gauge'), TD('Средний confidence по агентам')],
    [TD('llm_tokens_used'), TD('Counter'), TD('Расход токенов LLM Reasoning')],
    [TD('llm_reasoning_invocations'), TD('Counter'), TD('Количество вызовов grey zone анализа')],
]
story.extend(make_table(p11_data, [0.32, 0.15, 0.53], 'Таблица 12. Метрики P11'))

story.append(Paragraph('<b>7.2 P12: Human-in-the-loop (подтверждение решений)</b>', style_h2))

story.append(P(
    'Пункт P12 реализует механизм подтверждения решений оператором (human-in-the-loop) для случаев, '
    'когда автоматическое решение недостаточно надёжно или затрагивает критические бизнес-процессы. '
    'Механизм активируется в трёх сценариях: (1) вердикт CONDITIONAL_GO с risk_level HIGH или CRITICAL; '
    '(2) override veto-правила оператором (требует обязательного текстового обоснования, сохраняемого '
    'в audit_trail); (3) низкий средний confidence агентов (ниже 0.5). В каждом сценарии система '
    'приостанавливает выполнение и отправляет уведомление оператору через интерфейс чата. Оператор '
    'может подтвердить, отклонить или запросить дополнительный анализ. Все действия логируются в '
    'revision_history для последующего аудита. Реализация P12 запланирована на недели 6-8.'
))

story.append(Paragraph('<b>7.3 P13: Regression testing (фикстуры в CI/CD)</b>', style_h2))

story.append(P(
    'Пункт P13 интегрирует тестовые фикстуры (описанные в разделе 4) в CI/CD пайплайн для '
    'автоматической регрессионной проверки каждого коммита. Пайплайн запускает все три фикстуры '
    'через HermesRouter и проверяет соответствие результатов ожидаемым вердиктам. Дополнительно '
    'проверяются: корректность score (отклонение не более 0.05 от эталона), полнота veto_triggered '
    '(все ожидаемые veto сработали), и отсутствие ложных veto (неожиданные срабатывания). При '
    'любом несоответствии коммит блокируется до исправления. P13 также включает генерацию отчёта '
    'о регрессионном тестировании в формате JUnit XML для интеграции с GitLab CI. Реализация '
    'запланирована на недели 3-4, параллельно с P1, так как регрессионное тестирование критически '
    'важно для безопасного развития системы.'
))

p13_data = [
    [TH('Шаг CI/CD'), TH('Действие'), TH('Условие прохода')],
    [TD('1. Load fixtures'), TD('Загрузка 3 JSON из tests/fixtures/'), TD('Все файлы валидны по JSON-схеме')],
    [TD('2. Run Hermes'), TD('HermesRouter.decide() для каждой фикстуры'), TD('Вердикт совпадает с ожидаемым')],
    [TD('3. Validate score'), TD('Сравнение score с эталоном'), TD('Отклонение &lt;= 0.05')],
    [TD('4. Validate veto'), TD('Проверка veto_triggered'), TD('Все ожидаемые veto сработали, ложных нет')],
    [TD('5. Generate report'), TD('JUnit XML + HTML summary'), TD('Отчёт сформирован без ошибок')],
]
story.extend(make_table(p13_data, [0.22, 0.40, 0.38], 'Таблица 13. Шаги CI/CD для P13'))

# ━━ Build Body PDF ━━
doc = TocDocTemplate(
    BODY_PDF,
    pagesize=A4,
    leftMargin=LEFT_MARGIN,
    rightMargin=RIGHT_MARGIN,
    topMargin=TOP_MARGIN,
    bottomMargin=BOTTOM_MARGIN,
    title="MAC ASD v11.3",
    author="Z.ai",
    subject="Architectural Response and P0 Implementation",
)

doc.multiBuild(story)
print(f"Body PDF generated: {BODY_PDF}")

# ━━ Generate Cover HTML ━━
cover_html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
@page { size: 794px 1123px; margin: 0; }
html, body {
    margin: 0; padding: 0;
    width: 794px; height: 1123px;
    background: #ffffff;
    font-family: 'Calibri', sans-serif;
    overflow: hidden;
}
.cover {
    width: 794px; height: 1123px;
    position: relative;
    background: #ffffff;
}
/* Layer 1: decorative accent lines */
.accent-line-top {
    position: absolute;
    top: 80px; left: 60px;
    width: 680px; height: 3px;
    background: #5835c1;
}
.accent-line-bottom {
    position: absolute;
    bottom: 180px; left: 60px;
    width: 300px; height: 2px;
    background: #5835c1;
    opacity: 0.4;
}
.accent-rect {
    position: absolute;
    top: 0; right: 0;
    width: 180px; height: 1123px;
    background: #5835c1;
    opacity: 0.06;
}
/* Layer 3: text content */
.kicker {
    position: absolute;
    top: 110px; left: 60px;
    width: 540px;
    font-size: 14px;
    font-weight: 400;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #7e858a;
    line-height: 1.4;
}
.hero {
    position: absolute;
    top: 180px; left: 60px;
    width: 560px;
    font-size: 38px;
    font-weight: 700;
    color: #1a1b1c;
    line-height: 1.25;
}
.subtitle {
    position: absolute;
    top: 370px; left: 60px;
    width: 560px;
    font-size: 16px;
    font-weight: 400;
    color: #7e858a;
    line-height: 1.6;
}
.meta {
    position: absolute;
    bottom: 120px; left: 60px;
    width: 500px;
    font-size: 16px;
    font-weight: 400;
    color: #1a1b1c;
    line-height: 1.6;
}
.version {
    position: absolute;
    bottom: 80px; left: 60px;
    font-size: 12px;
    color: #7e858a;
    letter-spacing: 1px;
}
</style>
</head>
<body>
<div class="cover">
    <div class="accent-rect"></div>
    <div class="accent-line-top"></div>
    <div class="accent-line-bottom"></div>
    <div class="kicker">ARCHITECTURAL REVIEW RESPONSE</div>
    <div class="hero">MAC ASD v11.3<br/>Архитектурный ответ<br/>и реализация P0</div>
    <div class="subtitle">Гибридная модель принятия решений Hermes, AgentState v2,<br/>JSON-схемы, тестовые фикстуры</div>
    <div class="meta">20 апреля 2026</div>
    <div class="version">VERSION 11.3 &nbsp; | &nbsp; P0 IMPLEMENTATION</div>
</div>
</body>
</html>"""

with open(COVER_HTML, 'w', encoding='utf-8') as f:
    f.write(cover_html)
print(f"Cover HTML generated: {COVER_HTML}")

# ━━ Render Cover PDF via html2poster.js ━━
scripts_dir = "/home/z/my-project/skills/pdf/scripts"
subprocess.run([
    'node', os.path.join(scripts_dir, 'html2poster.js'),
    COVER_HTML, '--output', COVER_PDF,
    '--width', '794px',
], check=True)
print(f"Cover PDF generated: {COVER_PDF}")

# ━━ Merge Cover + Body ━━
from pypdf import PdfReader, PdfWriter, Transformation

A4_W, A4_H = 595.28, 841.89

def normalize_page_to_a4(page):
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    # Always normalize to exact A4 for consistency
    if abs(w - A4_W) > 0.5 or abs(h - A4_H) > 0.5:
        sx, sy = A4_W / w, A4_H / h
        page.add_transformation(Transformation().scale(sx=sx, sy=sy))
    page.mediabox.lower_left = (0, 0)
    page.mediabox.upper_right = (A4_W, A4_H)
    return page

writer = PdfWriter()
cover_page = PdfReader(COVER_PDF).pages[0]
writer.add_page(normalize_page_to_a4(cover_page))

for page in PdfReader(BODY_PDF).pages:
    writer.add_page(normalize_page_to_a4(page))

writer.add_metadata({
    '/Title': 'MAC ASD v11.3 - Architectural Response and P0 Implementation',
    '/Author': 'Z.ai',
    '/Creator': 'Z.ai',
    '/Subject': 'Hermes hybrid decision model, AgentState v2, JSON schemas, test fixtures',
})

with open(FINAL_PDF, 'wb') as f:
    writer.write(f)

print(f"\nFinal PDF generated: {FINAL_PDF}")

# Report file size
size_bytes = os.path.getsize(FINAL_PDF)
if size_bytes > 1024 * 1024:
    size_str = f"{size_bytes / (1024*1024):.1f} MB"
else:
    size_str = f"{size_bytes / 1024:.0f} KB"
print(f"File size: {size_str}")

# Count pages
reader = PdfReader(FINAL_PDF)
print(f"Page count: {len(reader.pages)}")
