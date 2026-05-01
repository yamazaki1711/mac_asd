"""
PPR Generator v0.1 — Orchestrator.

Управляет полным циклом генерации ППР: анализ входных данных →
генерация разделов ПЗ по уровням зависимостей → графика → сборка.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from .schemas import (
    PPRInput, PPRResult, PPRStats, SectionResult, GraphicResult,
    TTKResult, WorkTypeItem,
)
from .event_bus import PPRBus, PPRStage, PPREvent
from .sections.ttk_base import TTKRegistry

logger = logging.getLogger(__name__)


class PPRGenerator:
    """
    Оркестратор генерации ППР.

    Pipeline:
    1. Анализ входных данных → выбор ТТК-генераторов через TTKRegistry
    2. Генерация разделов ПЗ по уровням зависимостей:
       L0: general_data, work_organization (без зависимостей)
       L1: ТТК (по видам работ)
       L2: ps_works, quality_control (зависят от ТТК)
       L3: manpower, machinery (агрегируют ТТК)
       L4: safety, attestation (зависят от всех)
    3. Генерация графической части (СГП, техсхемы, строповка, календарный график)
    4. Сборка PDF/DOCX
    """

    def __init__(self, bus: Optional[PPRBus] = None):
        self._bus = bus or PPRBus()

    # ── Public API ──

    def generate(self, input: PPRInput) -> PPRResult:
        """
        Запустить полный цикл генерации ППР.

        Args:
            input: Входные данные (реквизиты, ПОС, ПД/РД)

        Returns:
            PPRResult с разделами, ТТК, графикой и путями к файлам
        """
        t0 = time.time()
        stats = PPRStats()
        warnings: List[str] = []

        # ── Stage 1: Input Analysis ──
        self._emit(PPRStage.INPUT_ANALYSIS, 0, "Анализ входных данных...")
        work_type_codes = [wt.code for wt in input.work_types]
        ttks = self._generate_ttks(input, work_type_codes, stats, warnings)
        self._emit(PPRStage.INPUT_ANALYSIS, 10, f"Выбрано ТТК: {len(ttks)}")

        # ── Stage 2: Sections ──
        sections = self._generate_sections(input, ttks, stats, warnings)

        # ── Stage 3: Graphics ──
        graphics: List[GraphicResult] = []
        if input.include_graphics:
            graphics = self._generate_graphics(input, ttks, sections, stats, warnings)

        # ── Stage 4: Compile ──
        self._emit(PPRStage.COMPILING, 90, "Сборка документа...")
        from .export.pdf_exporter import PPRPDFExporter
        pdf_exporter = PPRPDFExporter()
        pdf_path = pdf_exporter.compile(input, sections, ttks, graphics)

        docx_path = None
        if input.output_format in ("docx", "both"):
            from .export.docx_exporter import PPRDocxExporter
            docx_exporter = PPRDocxExporter()
            docx_path = docx_exporter.compile(input, sections, ttks)

        # ── Done ──
        elapsed = time.time() - t0
        stats.generation_time_seconds = round(elapsed, 1)
        stats.sections_generated = len(sections)
        stats.ttks_generated = len(ttks)
        stats.graphics_generated = len(graphics)
        stats.total_pages = sum(s.page_count for s in sections) + sum(g.page_count for g in graphics)
        stats.warnings = warnings

        self._emit(PPRStage.DONE, 100, f"Генерация завершена за {elapsed:.1f}с")

        return PPRResult(
            project_code=input.project_code,
            sections=sections,
            ttks=ttks,
            graphics=graphics,
            pdf_path=pdf_path,
            docx_path=docx_path,
            stats=stats,
        )

    # ── Stage 1: TTK Generation ──

    def _generate_ttks(
        self, input: PPRInput, work_type_codes: List[str],
        stats: PPRStats, warnings: List[str],
    ) -> List[TTKResult]:
        self._emit(PPRStage.TTK_GENERATING, 15, "Генерация технологических карт...")
        generators = TTKRegistry.select_for_project(work_type_codes)
        ttks: List[TTKResult] = []

        for i, gen in enumerate(generators):
            try:
                ttk = gen.generate(input)
                ttks.append(ttk)
                pct = 15 + (i + 1) / max(len(generators), 1) * 25
                self._emit(PPRStage.TTK_GENERATING, pct, f"ТТК: {gen.title}")
            except Exception as e:
                warnings.append(f"TTK {gen.work_type} failed: {e}")
                logger.error(f"TTK generation failed for {gen.work_type}: {e}")

        # Check for missing work types
        for wt_code in work_type_codes:
            if not TTKRegistry.has(wt_code):
                warnings.append(f"Нет генератора ТТК для вида работ: {wt_code}")

        return ttks

    # ── Stage 2: Sections ──

    def _generate_sections(
        self, input: PPRInput, ttks: List[TTKResult],
        stats: PPRStats, warnings: List[str],
    ) -> List[SectionResult]:
        from .sections import (
            generate_general_data, generate_work_organization,
            generate_ps_works, generate_quality_control,
            generate_manpower, generate_machinery,
            generate_safety, generate_attestation,
            generate_title_page, generate_approval_sheet,
        )

        self._emit(PPRStage.SECTIONS_GENERATING, 40, "Генерация разделов ПЗ...")
        sections: List[SectionResult] = []

        # L0: title + approval + general + work_org
        sections.append(generate_title_page(input))
        sections.append(generate_approval_sheet(input))
        sections.append(generate_general_data(input, ttks))
        sections.append(generate_work_organization(input, ttks))
        self._emit(PPRStage.SECTIONS_GENERATING, 50, "L0 разделы готовы")

        # L2: ps_works + quality
        sections.append(generate_ps_works(input, ttks))
        sections.append(generate_quality_control(input, ttks))
        self._emit(PPRStage.SECTIONS_GENERATING, 60, "L2 разделы готовы")

        # L3: manpower + machinery
        sections.append(generate_manpower(input, ttks))
        sections.append(generate_machinery(input, ttks))
        self._emit(PPRStage.SECTIONS_GENERATING, 70, "L3 разделы готовы")

        # L4: safety + attestation
        sections.append(generate_safety(input, ttks))
        sections.append(generate_attestation(input, ttks))
        self._emit(PPRStage.SECTIONS_GENERATING, 80, "L4 разделы готовы")

        return sections

    # ── Stage 3: Graphics ──

    def _generate_graphics(
        self, input: PPRInput, ttks: List[TTKResult],
        sections: List[SectionResult], stats: PPRStats, warnings: List[str],
    ) -> List[GraphicResult]:
        from .graphics import (
            generate_site_plan, generate_tech_schemes,
            generate_slinging_schemes, generate_equipment_table,
            generate_schedule,
        )

        self._emit(PPRStage.GRAPHICS_GENERATING, 82, "Генерация графической части...")
        graphics: List[GraphicResult] = []

        for gen_func, title in [
            (generate_site_plan, "Стройгенплан"),
            (generate_tech_schemes, "Технологические схемы"),
            (generate_slinging_schemes, "Схемы строповки"),
            (generate_equipment_table, "Таблица техники"),
            (generate_schedule, "Календарный график"),
        ]:
            try:
                g = gen_func(input, ttks, sections)
                graphics.append(g)
            except Exception as e:
                warnings.append(f"Графика {title}: {e}")

        self._emit(PPRStage.GRAPHICS_GENERATING, 88, "Графика готова")
        return graphics

    # ── Helpers ──

    def _emit(self, stage: PPRStage, pct: float, msg: str, **details):
        self._bus.emit(PPREvent(stage=stage, progress_pct=pct, message=msg, details=details))
