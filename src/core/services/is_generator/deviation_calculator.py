"""
Движок расчёта отклонений для модуля ISGenerator.

Алгоритм:
  1. Вычисление аффинного преобразования DXF→геодезия (по опорным точкам).
  2. Fuzzy-matching меток осей ↔ геодезических точек (rapidfuzz + spatial).
  3. Расчёт ΔX, ΔY, ΔZ и классификация по статусу (OK / WARNING / CRITICAL).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    AnchorPoint,
    CoordinateTransform,
    DesignAxis,
    Deviation,
    DeviationStatus,
    SurveyPoint,
)


# ─── Допуски по умолчанию (СП 126.13330.2017) ────────────────────────────────

DEFAULT_TOLERANCE_MM = {
    "ОСИ":     10.0,   # Разбивка главных осей
    "КМ":      5.0,    # Металлоконструкции
    "ШПУНТ":   30.0,   # Шпунтовое ограждение
    "СВАЯ":    50.0,   # Буронабивные сваи
    "РОСТВЕРК":10.0,
    "_DEFAULT": 20.0,
}

WARNING_THRESHOLD = 0.80   # WARNING если |δ| > 80% допуска


# ─── Вспомогательные типы ─────────────────────────────────────────────────────

@dataclass
class MatchPair:
    axis: DesignAxis
    point: SurveyPoint
    score: float   # 0.0 – 1.0 (1.0 — точное совпадение меток)


# ─── Основной движок ──────────────────────────────────────────────────────────

class DeviationCalculator:
    """
    Рассчитывает отклонения фактических замеров от проектных осей.

    Args:
        anchor_points: Опорные точки для вычисления CoordinateTransform.
                       Если не переданы — трансформация не применяется.
        tolerance_map: Словарь {слой → допуск_мм}. Дополняет DEFAULT_TOLERANCE_MM.
        label_match_threshold: Минимальный score fuzzy-matching (0..1).
        spatial_search_radius_m: Радиус поиска ближайшей точки (в метрах).
    """

    def __init__(
        self,
        anchor_points: list[AnchorPoint] | None = None,
        tolerance_map: dict[str, float] | None = None,
        label_match_threshold: float = 0.5,
        spatial_search_radius_m: float = 5.0,
    ) -> None:
        self.transform: CoordinateTransform | None = None
        if anchor_points and len(anchor_points) >= 2:
            self.transform = self._compute_transform(anchor_points)

        self.tolerance_map: dict[str, float] = {**DEFAULT_TOLERANCE_MM}
        if tolerance_map:
            self.tolerance_map.update(tolerance_map)

        self.label_match_threshold = label_match_threshold
        self.spatial_search_radius_m = spatial_search_radius_m

    # ──────────────────────────────────────────────────────────────────────────

    def calculate(
        self,
        axes: Sequence[DesignAxis],
        survey_points: Sequence[SurveyPoint],
    ) -> tuple[list[Deviation], list[str], list[str]]:
        """
        Полный расчёт отклонений.

        Returns:
            (deviations, unmatched_axis_handles, unmatched_point_ids)
        """
        # 1. Трансформируем координаты осей
        geo_axes = self._transform_axes(list(axes))

        # 2. Matching
        pairs, unmatched_axes, unmatched_points = self._match(geo_axes, list(survey_points))

        # 3. Расчёт отклонений
        deviations = [self._compute_deviation(p) for p in pairs]

        logger.info(
            f"Matched: {len(pairs)}, "
            f"Unmatched axes: {len(unmatched_axes)}, "
            f"Unmatched points: {len(unmatched_points)}"
        )
        return deviations, unmatched_axes, unmatched_points

    # ─── Преобразование координат ─────────────────────────────────────────────

    def _transform_axes(self, axes: list[DesignAxis]) -> list[DesignAxis]:
        """Применяет CoordinateTransform к design_x/design_y каждой оси."""
        if self.transform is None:
            return axes

        transformed = []
        for ax in axes:
            gx, gy = self.transform.apply(ax.design_x, ax.design_y)
            # Создаём копию с обновлёнными координатами
            transformed.append(ax.model_copy(update={"design_x": gx, "design_y": gy}))
        return transformed

    @staticmethod
    def _compute_transform(anchors: list[AnchorPoint]) -> CoordinateTransform:
        """
        Вычисляет аффинное преобразование (масштаб + поворот + трансляция)
        методом наименьших квадратов по >= 2 опорным точкам.

        Для 2 точек — точное решение.
        Для N>2 — МНК через центроиды (Helmert 2D).
        """
        n = len(anchors)

        if n == 1:
            # Только трансляция
            a = anchors[0]
            return CoordinateTransform(
                scale=1.0,
                rotation_rad=0.0,
                translate_x=a.geo_x - a.dxf_x,
                translate_y=a.geo_y - a.dxf_y,
                anchor_points=anchors,
            )

        # Центроиды
        cx_dxf = sum(a.dxf_x for a in anchors) / n
        cy_dxf = sum(a.dxf_y for a in anchors) / n
        cx_geo = sum(a.geo_x for a in anchors) / n
        cy_geo = sum(a.geo_y for a in anchors) / n

        # Helmert 2D (МНК)
        sum_d2 = sum((a.dxf_x - cx_dxf)**2 + (a.dxf_y - cy_dxf)**2 for a in anchors)
        sum_ab = sum(
            (a.dxf_x - cx_dxf) * (a.geo_x - cx_geo) + (a.dxf_y - cy_dxf) * (a.geo_y - cy_geo)
            for a in anchors
        )
        sum_cd = sum(
            (a.dxf_x - cx_dxf) * (a.geo_y - cy_geo) - (a.dxf_y - cy_dxf) * (a.geo_x - cx_geo)
            for a in anchors
        )

        if sum_d2 < 1e-12:
            scale, rot = 1.0, 0.0
        else:
            scale = math.sqrt(sum_ab**2 + sum_cd**2) / sum_d2
            rot   = math.atan2(sum_cd, sum_ab)

        tx = cx_geo - scale * (cx_dxf * math.cos(rot) - cy_dxf * math.sin(rot))
        ty = cy_geo - scale * (cx_dxf * math.sin(rot) + cy_dxf * math.cos(rot))

        ct = CoordinateTransform(
            scale=scale,
            rotation_rad=rot,
            translate_x=tx,
            translate_y=ty,
            anchor_points=anchors,
        )

        # Вычисляем остаточную ошибку
        residuals = []
        for a in anchors:
            gx, gy = ct.apply(a.dxf_x, a.dxf_y)
            residuals.append(math.hypot(gx - a.geo_x, gy - a.geo_y) * 1000)  # → мм
        ct.residual_mm = max(residuals) if residuals else 0.0

        logger.info(
            f"CoordinateTransform: scale={scale:.6f}, rot={math.degrees(rot):.4f}°, "
            f"residual={ct.residual_mm:.2f} мм"
        )
        return ct

    # ─── Matching ─────────────────────────────────────────────────────────────

    def _match(
        self,
        axes: list[DesignAxis],
        points: list[SurveyPoint],
    ) -> tuple[list[MatchPair], list[str], list[str]]:
        """
        Двухшаговый matching:
          1. Fuzzy-matching меток (rapidfuzz).
          2. Пространственный фоллбэк (ближайшая точка в радиусе).

        Returns:
            (pairs, unmatched_axis_handles, unmatched_point_ids)
        """
        # Пробуем импортировать rapidfuzz
        fuzzy_available = False
        try:
            from rapidfuzz.distance import JaroWinkler
            fuzzy_available = True
        except ImportError:
            logger.warning("rapidfuzz не установлен — используется только пространственный matching")

        matched_point_ids: set[str] = set()
        pairs: list[MatchPair] = []
        unmatched_axis_handles: list[str] = []

        for ax in axes:
            best_pair: MatchPair | None = None

            # Шаг 1: fuzzy по метке
            if fuzzy_available and ax.label:
                from rapidfuzz.distance import JaroWinkler  # type: ignore[import]
                for pt in points:
                    if pt.point_id in matched_point_ids:
                        continue
                    score = JaroWinkler.normalized_similarity(
                        ax.label.upper(),
                        pt.description.upper(),
                    )
                    if score >= self.label_match_threshold:
                        if best_pair is None or score > best_pair.score:
                            best_pair = MatchPair(ax, pt, score)

            # Шаг 2: пространственный фоллбэк
            if best_pair is None:
                radius_sq = (self.spatial_search_radius_m) ** 2
                best_dist_sq = radius_sq
                for pt in points:
                    if pt.point_id in matched_point_ids:
                        continue
                    d_sq = (ax.design_x - pt.x) ** 2 + (ax.design_y - pt.y) ** 2
                    if d_sq < best_dist_sq:
                        best_dist_sq = d_sq
                        best_pair = MatchPair(ax, pt, score=1.0 - math.sqrt(d_sq) / self.spatial_search_radius_m)

            if best_pair:
                matched_point_ids.add(best_pair.point.point_id)
                pairs.append(best_pair)
            else:
                unmatched_axis_handles.append(ax.handle)

        # Несопоставленные точки
        unmatched_point_ids = [pt.point_id for pt in points if pt.point_id not in matched_point_ids]

        return pairs, unmatched_axis_handles, unmatched_point_ids

    # ─── Расчёт одного отклонения ─────────────────────────────────────────────

    def _compute_deviation(self, pair: MatchPair) -> Deviation:
        ax = pair.axis
        pt = pair.point

        # ΔX, ΔY в метрах → в мм
        delta_x_mm = (pt.x - ax.design_x) * 1000.0
        delta_y_mm = (pt.y - ax.design_y) * 1000.0
        delta_z_mm = (pt.z - 0.0) * 1000.0   # проектная высота = 0 если не задана

        distance_mm = math.hypot(delta_x_mm, delta_y_mm)

        # Допуск по слою
        layer_upper = ax.layer.upper()
        tolerance = self.tolerance_map.get(layer_upper, self.tolerance_map["_DEFAULT"])

        # Статус
        ratio = distance_mm / tolerance if tolerance > 0 else float("inf")
        if ratio > 1.0:
            status = DeviationStatus.CRITICAL
        elif ratio >= WARNING_THRESHOLD:
            status = DeviationStatus.WARNING
        else:
            status = DeviationStatus.OK

        return Deviation(
            axis_id=ax.handle,
            axis_label=ax.label or ax.handle,
            survey_point_id=pt.point_id,
            match_score=round(pair.score, 3),
            delta_x_mm=round(delta_x_mm, 2),
            delta_y_mm=round(delta_y_mm, 2),
            delta_z_mm=round(delta_z_mm, 2),
            distance_mm=round(distance_mm, 2),
            status=status,
            tolerance_mm=tolerance,
        )
