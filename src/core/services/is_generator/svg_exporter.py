"""
SVGExporter — векторный экспорт DXF → SVG → PDF.

Заменяет matplotlib-рендер (растровый, 200 dpi) на векторный пайплайн:
  1. ezdxf → SVG (встроенный SVG-писатель ezdxf)
  2. SVG → PDF через cairosvg (векторный, без потери качества)

Преимущества перед matplotlib:
  - Векторный PDF: линии, текст, штампы — чёткие при любом зуме
  - Корректная обработка штриховых линий (по ГОСТ)
  - Нет растровых артефактов
  - Меньший размер файла

v12.0
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

try:
    import cairosvg
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False


class SVGExporter:
    """
    Векторный экспорт DXF → SVG → PDF.

    Пайплайн:
      1. ezdxf.readfile() → SVG-строка через ezdxf.addons.drawing
      2. SVG → PDF через cairosvg.convert()

    Fallback (если cairosvg не установлен):
      SVG → PDF через Inkscape CLI (если установлен)
      SVG → PDF через rsvg-convert CLI (если установлен)

    Args:
        page_size: Размер страницы: "A3", "A2", "A1" (landscape).
        dpi: Разрешение для растровых элементов (подложки).
        margin_mm: Отступ от краёв страницы в мм.
    """

    # Размеры страниц (ширина × высота в мм, landscape)
    PAGE_SIZES: dict[str, tuple[float, float]] = {
        "A4": (297.0, 210.0),
        "A3": (420.0, 297.0),
        "A2": (594.0, 420.0),
        "A1": (841.0, 594.0),
        "A0": (1189.0, 841.0),
    }

    def __init__(
        self,
        page_size: str = "A3",
        dpi: int = 300,
        margin_mm: float = 10.0,
    ) -> None:
        self.page_size = page_size
        self.dpi = dpi
        self.margin_mm = margin_mm

    # ─── Публичный метод ──────────────────────────────────────────────────────

    def export_pdf(
        self,
        dxf_path: str | Path,
        output_pdf: str | Path,
    ) -> Path:
        """
        Конвертирует DXF → SVG → PDF (векторный).

        Args:
            dxf_path: Путь к DXF-файлу.
            output_pdf: Путь к выходному PDF.

        Returns:
            Путь к созданному PDF.
        """
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        dxf_path = Path(dxf_path)
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        # Шаг 1: DXF → SVG
        svg_content = self._dxf_to_svg(dxf_path)

        # Шаг 2: SVG → PDF
        self._svg_to_pdf(svg_content, output_pdf)

        logger.info(f"SVGExporter: {dxf_path.name} → {output_pdf.name} (векторный PDF)")
        return output_pdf

    def export_svg(
        self,
        dxf_path: str | Path,
        output_svg: str | Path,
    ) -> Path:
        """
        Конвертирует DXF → SVG.

        Полезно для промежуточной проверки или встраивания в HTML.
        """
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        dxf_path = Path(dxf_path)
        output_svg = Path(output_svg)
        output_svg.parent.mkdir(parents=True, exist_ok=True)

        svg_content = self._dxf_to_svg(dxf_path)
        output_svg.write_text(svg_content, encoding="utf-8")

        logger.info(f"SVGExporter: {dxf_path.name} → {output_svg.name}")
        return output_svg

    # ─── DXF → SVG ────────────────────────────────────────────────────────────

    def _dxf_to_svg(self, dxf_path: Path) -> str:
        """Конвертирует DXF в SVG-строку через ezdxf SVG writer."""
        doc = ezdxf.readfile(str(dxf_path))

        try:
            # ezdxf >= 1.x: новый SVG backend
            from ezdxf.addons.drawing import RenderContext, Frontend
            from ezdxf.addons.drawing.svg import SVGBackend

            page_w, page_h = self.PAGE_SIZES.get(self.page_size, self.PAGE_SIZES["A3"])

            ctx = RenderContext(doc)
            backend = SVGBackend()
            Frontend(ctx, backend).draw_layout(doc.modelspace())

            # Получаем SVG-строку
            svg_content = backend.get_string(
                page_size=(page_w, page_h),
                margin=self.margin_mm,
                dpi=self.dpi,
            )
            return svg_content

        except ImportError:
            # ezdxf < 1.x: fallback на matplotlib SVG
            logger.warning(
                "ezdxf.addons.drawing.svg недоступен — fallback на matplotlib SVG. "
                "Установите ezdxf >= 1.0 для нативного SVG-экспорта."
            )
            return self._dxf_to_svg_matplotlib(doc)

    def _dxf_to_svg_matplotlib(self, doc) -> str:
        """Fallback: DXF → SVG через matplotlib (качество хуже, но работает)."""
        import io
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        try:
            import matplotlib.pyplot as plt
            import matplotlib.backends.backend_svg as svg_backend
        except ImportError:
            raise ImportError(
                "matplotlib is required for DXF→SVG fallback rendering. "
                "Install it with: pip install matplotlib"
            )

        fig = plt.figure()
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(doc.modelspace(), finalize=True)

        # Сохраняем как SVG в строку
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", dpi=self.dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read().decode("utf-8")

    # ─── SVG → PDF ────────────────────────────────────────────────────────────

    def _svg_to_pdf(self, svg_content: str, output_pdf: Path) -> None:
        """Конвертирует SVG в PDF (пытается несколькими способами).

        v12.0: matplotlib raster fallback удалён — только векторные методы.
        Если ни один векторный конвертер не доступен, сохраняем SVG
        и логируем предупреждение.
        """

        # Способ 1: cairosvg (Python, лучший вариант)
        if CAIROSVG_AVAILABLE:
            cairosvg.svg2pdf(
                bytestring=svg_content.encode("utf-8"),
                write_to=str(output_pdf),
            )
            return

        # Способ 2: Inkscape CLI
        if self._try_inkscape(svg_content, output_pdf):
            return

        # Способ 3: rsvg-convert CLI
        if self._try_rsvg_convert(svg_content, output_pdf):
            return

        # Способ 4: Сохраняем SVG как есть — векторный формат сохранён
        svg_path = output_pdf.with_suffix(".svg")
        svg_path.write_text(svg_content, encoding="utf-8")
        logger.warning(
            f"cairosvg/Inkscape/rsvg-convert не найдены. "
            f"Сохранён SVG: {svg_path}. "
            f"Установите cairosvg для векторного PDF: pip install cairosvg"
        )

    @staticmethod
    def _try_inkscape(svg_content: str, output_pdf: Path) -> bool:
        """Попытка конвертации через Inkscape CLI."""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".svg", mode="w", encoding="utf-8", delete=False
            ) as tmp:
                tmp.write(svg_content)
                tmp_svg = tmp.name

            result = subprocess.run(
                ["inkscape", tmp_svg, "--export-filename", str(output_pdf)],
                capture_output=True, timeout=30,
            )
            Path(tmp_svg).unlink(missing_ok=True)

            if result.returncode == 0 and output_pdf.exists():
                logger.info("SVG→PDF через Inkscape CLI")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return False

    @staticmethod
    def _try_rsvg_convert(svg_content: str, output_pdf: Path) -> bool:
        """Попытка конвертации через rsvg-convert CLI."""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".svg", mode="w", encoding="utf-8", delete=False
            ) as tmp:
                tmp.write(svg_content)
                tmp_svg = tmp.name

            result = subprocess.run(
                ["rsvg-convert", "-f", "pdf", "-o", str(output_pdf), tmp_svg],
                capture_output=True, timeout=30,
            )
            Path(tmp_svg).unlink(missing_ok=True)

            if result.returncode == 0 and output_pdf.exists():
                logger.info("SVG→PDF через rsvg-convert CLI")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return False


