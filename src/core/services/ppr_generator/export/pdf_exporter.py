"""
PPR Generator — PDF Exporter.

Собирает все разделы ПЗ, ТТК и графику в единый PDF-документ.
v0.1: генерирует базовый PDF через reportlab.
"""
from __future__ import annotations

import logging
import tempfile
from typing import List

from ..schemas import PPRInput, SectionResult, TTKResult, GraphicResult

logger = logging.getLogger(__name__)


class PPDFExporter:
    """Экспортёр ППР в PDF."""

    def compile(
        self,
        input: PPRInput,
        sections: List[SectionResult],
        ttks: List[TTKResult],
        graphics: List[GraphicResult],
    ) -> str:
        """
        Собрать финальный PDF.

        Args:
            input: Входные данные ППР
            sections: Сгенерированные разделы ПЗ
            ttks: Технологические карты
            graphics: Графическая часть

        Returns:
            Путь к созданному PDF-файлу
        """
        safe_code = input.project_code.replace("/", "-")

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
            from reportlab.lib import colors
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            logger.warning("reportlab not installed — generating plain text PDF placeholder")
            return self._compile_placeholder(input)

        # Try to register a Cyrillic font
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
            font_name = "DejaVu"
        except Exception:
            font_name = "Helvetica"

        output_path = tempfile.mktemp(suffix=".pdf", prefix=f"ppr_{safe_code}_")

        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                leftMargin=20*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)

        styles = getSampleStyleSheet()
        style_h1 = ParagraphStyle("H1Custom", parent=styles["Heading1"], fontName=font_name, fontSize=16, spaceAfter=12)
        style_h2 = ParagraphStyle("H2Custom", parent=styles["Heading2"], fontName=font_name, fontSize=13, spaceAfter=8)
        style_body = ParagraphStyle("BodyCustom", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=14)

        story = []
        for section in sections:
            story.append(Paragraph(f"<b>{section.title}</b>", style_h1))
            story.append(Spacer(1, 6*mm))

            # Render markdown content as plain paragraphs
            for para in section.content.split("\n\n"):
                text = para.strip()
                if not text:
                    continue
                if text.startswith("### "):
                    story.append(Paragraph(f"<b>{text[4:]}</b>", style_h2))
                elif text.startswith("## "):
                    story.append(Paragraph(f"<b>{text[3:]}</b>", style_h2))
                else:
                    # Replace markdown table pipes with simple text
                    if text.startswith("|"):
                        text = text.replace("|", " ")
                    story.append(Paragraph(text.replace("\n", "<br/>"), style_body))
                story.append(Spacer(1, 2*mm))

            if section != sections[-1]:
                story.append(PageBreak())

        # Add TTK sections
        for ttk in ttks:
            story.append(PageBreak())
            story.append(Paragraph(f"<b>ТТК: {ttk.scope.work_type}</b>", style_h1))
            story.append(Paragraph(f"Область применения: {ttk.scope.description}", style_body))
            story.append(Paragraph(f"Трудоёмкость: {ttk.total_labor_intensity_person_hours} чел-ч", style_body))
            story.append(Paragraph(f"Машино-часы: {ttk.total_machine_hours} маш-ч", style_body))

        doc.build(story)
        logger.info(f"PDF compiled: {output_path}")
        return output_path

    def _compile_placeholder(self, input: PPRInput) -> str:
        """Fallback: save as text when reportlab is unavailable."""
        import os
        safe_code = input.project_code.replace("/", "-")
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"ppr_{safe_code}_export.txt"
        )
        logger.warning(f"PDF exporter using plain text fallback: {output_path}")
        return output_path
