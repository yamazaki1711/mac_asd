"""
Парсер проектных осей и конструктивных элементов из DXF-файлов.

Использует ezdxf для извлечения геометрии LINE, LWPOLYLINE и ARC
с привязкой к слоям (ОСИ, КМ, ШПУНТ и т.д.).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

logger = logging.getLogger(__name__)

# Импорт схем
from src.core.services.is_generator.schemas import DesignAxis

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    logger.warning("ezdxf не установлен. Установите: pip install ezdxf")

# Type hints — импортируем только для статического анализа, не в рантайме
if TYPE_CHECKING:
    from ezdxf.document import Drawing
    from ezdxf.entities import DXFGraphic


# ─── Слои по умолчанию ────────────────────────────────────────────────────────

DEFAULT_AXIS_LAYERS: tuple[str, ...] = (
    "ОСИ", "ОСКИ", "AXIS", "AXES",
    "КМ", "КМ_ОСИ", "СТРУКТУРА",
    "ШПУНТ", "СВАЯ", "РОСТВЕРК",
    "GRID", "GRIDS",
)

DEFAULT_LABEL_LAYERS: tuple[str, ...] = (
    "МЕТКИ", "LABELS", "TEXT", "TEXTY",
    "ПОДПИСИ", "МТЕКСТ", "АННОТАЦИИ",
)


# ─── Основной парсер ──────────────────────────────────────────────────────────

class DXFParser:
    """
    Извлекает проектные оси (DesignAxis) из DXF-файла.

    Args:
        axis_layers: Слои, содержащие оси/конструктивные элементы.
                     None → использовать DEFAULT_AXIS_LAYERS.
        label_layers: Слои с текстовыми метками для привязки к осям.
        extract_arcs: Включать ли дуги (ARC) в результат.
        min_length_mm: Минимальная длина линии в единицах DXF.
    """

    def __init__(
        self,
        axis_layers: Sequence[str] | None = None,
        label_layers: Sequence[str] | None = None,
        extract_arcs: bool = False,
        min_length_mm: float = 100.0,
    ) -> None:
        self.axis_layers: frozenset[str] = frozenset(
            s.upper() for s in (axis_layers or DEFAULT_AXIS_LAYERS)
        )
        self.label_layers: frozenset[str] = frozenset(
            s.upper() for s in (label_layers or DEFAULT_LABEL_LAYERS)
        )
        self.extract_arcs = extract_arcs
        self.min_length_mm = min_length_mm

    # ──────────────────────────────────────────────────────────────────────────

    def parse(self, file_path: str | Path) -> list[DesignAxis]:
        """
        Парсит DXF-файл и возвращает список проектных осей.

        Args:
            file_path: Путь к DXF-файлу (или DWG, если ODA FC установлен).

        Returns:
            list[DesignAxis]
        """
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"DXF-файл не найден: {path}")

        # Поддержка DWG через ODA File Converter
        if path.suffix.lower() == ".dwg":
            path = self._convert_dwg_to_dxf(path)

        try:
            doc: Drawing = ezdxf.readfile(str(path))
        except Exception as e:
            raise ValueError(f"Не удалось прочитать DXF: {e}") from e

        msp = doc.modelspace()

        # Строим индекс меток из текстовых слоёв
        label_index = self._build_label_index(msp)
        logger.debug(f"Индекс меток: {len(label_index)} текстовых объектов")

        axes: list[DesignAxis] = []
        for entity in msp:
            layer_upper = entity.dxf.layer.upper() if entity.dxf.hasattr("layer") else ""
            if layer_upper not in self.axis_layers:
                continue

            extracted = self._extract_entity(entity, label_index)
            if extracted:
                axes.append(extracted)

        logger.info(f"Извлечено {len(axes)} проектных осей из {path.name}")
        return axes

    # ─── Внутренние методы ────────────────────────────────────────────────────

    def _extract_entity(
        self,
        entity: "DXFGraphic",
        label_index: dict[tuple[float, float], str],
    ) -> DesignAxis | None:
        """Диспетчеризует по типу сущности."""
        etype = entity.dxftype()

        if etype == "LINE":
            return self._from_line(entity, label_index)
        elif etype == "LWPOLYLINE":
            return self._from_lwpolyline(entity, label_index)
        elif etype == "ARC" and self.extract_arcs:
            return self._from_arc(entity, label_index)
        return None

    def _from_line(self, entity, label_index: dict) -> DesignAxis | None:
        try:
            start = entity.dxf.start
            end   = entity.dxf.end
            sx, sy = float(start.x), float(start.y)
            ex, ey = float(end.x),   float(end.y)

            length = math.hypot(ex - sx, ey - sy)
            if length < self.min_length_mm:
                return None

            cx, cy = (sx + ex) / 2, (sy + ey) / 2
            label  = self._nearest_label(cx, cy, label_index)

            return DesignAxis(
                handle=entity.dxf.handle or "",
                layer=entity.dxf.layer,
                label=label,
                start_x=sx, start_y=sy,
                end_x=ex,   end_y=ey,
                design_x=cx, design_y=cy,
                entity_type="LINE",
            )
        except Exception as e:
            logger.debug(f"LINE entity пропущена: {e}")
            return None

    def _from_lwpolyline(self, entity, label_index: dict) -> DesignAxis | None:
        try:
            points = list(entity.get_points(format="xy"))
            if len(points) < 2:
                return None

            sx, sy = float(points[0][0]),  float(points[0][1])
            ex, ey = float(points[-1][0]), float(points[-1][1])

            length = math.hypot(ex - sx, ey - sy)
            if length < self.min_length_mm:
                return None

            # Центроид
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            label = self._nearest_label(cx, cy, label_index)

            return DesignAxis(
                handle=entity.dxf.handle or "",
                layer=entity.dxf.layer,
                label=label,
                start_x=sx, start_y=sy,
                end_x=ex,   end_y=ey,
                design_x=cx, design_y=cy,
                entity_type="LWPOLYLINE",
            )
        except Exception as e:
            logger.debug(f"LWPOLYLINE entity пропущена: {e}")
            return None

    def _from_arc(self, entity, label_index: dict) -> DesignAxis | None:
        try:
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            start_angle = math.radians(entity.dxf.start_angle)
            end_angle   = math.radians(entity.dxf.end_angle)

            cx = float(center.x)
            cy = float(center.y)

            # Начало и конец дуги
            sx = cx + radius * math.cos(start_angle)
            sy = cy + radius * math.sin(start_angle)
            ex = cx + radius * math.cos(end_angle)
            ey = cy + radius * math.sin(end_angle)

            label = self._nearest_label(cx, cy, label_index)

            return DesignAxis(
                handle=entity.dxf.handle or "",
                layer=entity.dxf.layer,
                label=label,
                start_x=sx, start_y=sy,
                end_x=ex,   end_y=ey,
                design_x=cx, design_y=cy,
                entity_type="ARC",
            )
        except Exception as e:
            logger.debug(f"ARC entity пропущена: {e}")
            return None

    def _build_label_index(self, msp) -> dict[tuple[float, float], str]:
        """Строит пространственный индекс: (x, y) → текст метки."""
        index: dict[tuple[float, float], str] = {}
        for entity in msp:
            layer_upper = entity.dxf.layer.upper() if entity.dxf.hasattr("layer") else ""
            etype = entity.dxftype()

            if etype in ("TEXT", "ATTDEF") and layer_upper in self.label_layers:
                try:
                    pos   = entity.dxf.insert
                    text  = str(entity.dxf.text).strip()
                    if text:
                        index[(float(pos.x), float(pos.y))] = text
                except Exception:
                    pass

            elif etype == "MTEXT" and layer_upper in self.label_layers:
                try:
                    pos  = entity.dxf.insert
                    text = entity.plain_mtext().strip()
                    if text:
                        index[(float(pos.x), float(pos.y))] = text
                except Exception:
                    pass

        return index

    def _nearest_label(
        self,
        cx: float,
        cy: float,
        label_index: dict[tuple[float, float], str],
        max_dist: float = 5000.0,
    ) -> str:
        """Возвращает ближайшую текстовую метку в радиусе max_dist."""
        best_dist = max_dist
        best_text = ""
        for (lx, ly), text in label_index.items():
            d = math.hypot(cx - lx, cy - ly)
            if d < best_dist:
                best_dist = d
                best_text = text
        return best_text

    @staticmethod
    def _convert_dwg_to_dxf(dwg_path: Path) -> Path:
        """
        Конвертирует DWG → DXF через ODA File Converter (если установлен).
        https://www.opendesign.com/guestfiles/oda_file_converter
        """
        try:
            from ezdxf.addons import odafc
        except ImportError:
            raise ImportError(
                "Для работы с DWG нужен ODA File Converter и ezdxf.addons.odafc"
            )

        dxf_path = dwg_path.with_suffix(".dxf")
        logger.info(f"Конвертация DWG→DXF: {dwg_path} → {dxf_path}")
        odafc.convert(str(dwg_path), str(dxf_path), version="R2013", audit=False)
        return dxf_path
