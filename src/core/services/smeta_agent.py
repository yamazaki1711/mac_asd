"""
ASD v12.0 — Smeta Agent (Сметчик).

Расчёт стоимости, анализ рентабельности, сравнение ВОР ↔ КС-2.

Нормативная база:
  - МДС 81-35.2004 (методика определения стоимости)
  - МДС 81-33.2004 (накладные расходы)
  - МДС 81-25.2001 (сметная прибыль)
  - ФЕР/ТЕР (федеральные/территориальные единичные расценки)
  - НК РФ ст. 164 (НДС 20%)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

class MarginZone(str, Enum):
    EXCELLENT = "excellent"       # > 40%
    GOOD = "good"                 # 25-40%
    ACCEPTABLE = "acceptable"     # 15-25%
    MARGINAL = "marginal"         # 10-15%
    BELOW_MINIMUM = "below_minimum"  # < 10%
    NEGATIVE = "negative"         # < 0%


@dataclass
class CostLine:
    """Одна строка затрат."""
    code: str                    # Код позиции (ФЕР или свободный)
    name: str
    unit: str
    quantity: float
    unit_price: float            # Цена за единицу
    total: float                 # Количество × цена
    category: str = "materials"  # materials, labor, machinery, subcontractor, other
    overhead_pct: float = 0.0    # % накладных
    profit_pct: float = 0.0      # % сметной прибыли
    index_coeff: float = 1.0     # Индекс пересчёта Минстроя
    region_coeff: float = 1.0    # Региональный коэффициент


@dataclass
class SmetaEstimate:
    """Полная смета."""
    project_id: int
    title: str
    lines: List[CostLine] = field(default_factory=list)
    vat_pct: float = 20.0
    overhead_global_pct: float = 0.0  # Глобальный % НР (если не постатейно)
    profit_global_pct: float = 0.0

    @property
    def direct_costs(self) -> float:
        return sum(l.total for l in self.lines)

    @property
    def overhead_total(self) -> float:
        if self.overhead_global_pct > 0:
            return self.direct_costs * self.overhead_global_pct / 100
        return sum(l.total * l.overhead_pct / 100 for l in self.lines)

    @property
    def profit_total(self) -> float:
        base = self.direct_costs + self.overhead_total
        if self.profit_global_pct > 0:
            return base * self.profit_global_pct / 100
        return sum(l.total * l.profit_pct / 100 for l in self.lines)

    @property
    def subtotal(self) -> float:
        return self.direct_costs + self.overhead_total + self.profit_total

    @property
    def vat(self) -> float:
        return self.subtotal * self.vat_pct / 100

    @property
    def grand_total(self) -> float:
        return self.subtotal + self.vat

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "lines": [
                {"code": l.code, "name": l.name, "unit": l.unit,
                 "quantity": l.quantity, "unit_price": l.unit_price,
                 "total": l.total, "category": l.category}
                for l in self.lines
            ],
            "direct_costs": round(self.direct_costs, 2),
            "overhead": round(self.overhead_total, 2),
            "profit": round(self.profit_total, 2),
            "subtotal": round(self.subtotal, 2),
            "vat": round(self.vat, 2),
            "grand_total": round(self.grand_total, 2),
            "line_count": len(self.lines),
        }


@dataclass
class MarginReport:
    """Отчёт о рентабельности."""
    estimate: SmetaEstimate
    nmck: float = 0.0            # НМЦК тендера
    margin_pct: float = 0.0
    margin_zone: MarginZone = MarginZone.ACCEPTABLE
    low_margin_lines: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_profitable(self) -> bool:
        return self.margin_pct >= 10.0

    @property
    def profit_absolute(self) -> float:
        return self.nmck - self.estimate.grand_total if self.nmck > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "margin_pct": round(self.margin_pct, 2),
            "margin_zone": self.margin_zone.value,
            "nmck": self.nmck,
            "cost_total": self.estimate.grand_total,
            "profit_absolute": round(self.profit_absolute, 2),
            "is_profitable": self.is_profitable,
            "warnings": self.warnings,
        }


# =============================================================================
# Smeta Agent
# =============================================================================

class SmetaAgent:
    """Агент-Сметчик ASD v12.0."""

    def __init__(self, llm_engine=None):
        from src.core.llm_engine import llm_engine as _llm
        self._llm = llm_engine or _llm

    # -------------------------------------------------------------------------
    # Cost Estimation
    # -------------------------------------------------------------------------

    def build_estimate(
        self,
        project_id: int,
        title: str,
        vor_positions: List[Dict[str, Any]],
        rates: Optional[Dict[str, float]] = None,
        region_coeff: float = 1.0,
        index_coeff: float = 1.0,
    ) -> SmetaEstimate:
        """
        Построить смету из ВОР с привязкой к ФЕР.

        Args:
            vor_positions: список позиций ВОР [{code, name, unit, quantity}, ...]
            rates: словарь {code: unit_price} — если не передан, используются дефолтные
            region_coeff: региональный коэффициент
            index_coeff: индекс пересчёта Минстроя
        """
        rates = rates or {}

        # Дефолтные расценки ФЕР (упрощённые, для демонстрации)
        default_rates = {
            "ФЕР01-01-013": 850.0,   # Разработка грунта
            "ФЕР06-01-001": 12500.0, # Бетонная подготовка
            "ФЕР06-01-015": 18500.0, # Армирование
            "ФЕР06-01-020": 22000.0, # Бетонирование
            "ФЕР07-01-001": 9500.0,  # Кирпичная кладка
            "ФЕР08-01-001": 7500.0,  # Гидроизоляция
            "ФЕР09-03-012": 18500.0, # Монтаж МК
            "ФЕР15-01-001": 12000.0, # Отделка стен
            "ФЕР15-02-001": 8500.0,  # Устройство полов
            "ФЕР16-01-001": 10500.0, # Водопровод
            "ФЕР17-01-001": 9500.0,  # Канализация
            "ФЕР18-01-001": 13500.0, # Отопление
            "ФЕР20-01-001": 15000.0, # Вентиляция
            "ФЕР21-01-001": 11500.0, # Электромонтаж
        }

        lines = []
        for pos in vor_positions:
            code = pos.get("code", "")
            rate = rates.get(code) or default_rates.get(code, 5000.0)
            quantity = float(pos.get("quantity", 0))
            coeff = region_coeff * index_coeff
            unit_price = rate * coeff

            lines.append(CostLine(
                code=code,
                name=pos.get("name", "Без названия"),
                unit=pos.get("unit", "ед."),
                quantity=quantity,
                unit_price=round(unit_price, 2),
                total=round(unit_price * quantity, 2),
                category=pos.get("category", "materials"),
                overhead_pct=pos.get("overhead_pct", 12.0),
                profit_pct=pos.get("profit_pct", 8.0),
                index_coeff=index_coeff,
                region_coeff=region_coeff,
            ))

        return SmetaEstimate(
            project_id=project_id,
            title=title,
            lines=lines,
            vat_pct=20.0,
        )

    # -------------------------------------------------------------------------
    # Margin Analysis
    # -------------------------------------------------------------------------

    def analyze_margin(self, estimate: SmetaEstimate, nmck: float) -> MarginReport:
        """Анализ рентабельности относительно НМЦК."""
        if nmck <= 0:
            margin = 0.0
        else:
            margin = (nmck - estimate.grand_total) / nmck * 100

        # Зона маржинальности
        if margin > 40:
            zone = MarginZone.EXCELLENT
        elif margin > 25:
            zone = MarginZone.GOOD
        elif margin > 15:
            zone = MarginZone.ACCEPTABLE
        elif margin > 10:
            zone = MarginZone.MARGINAL
        elif margin >= 0:
            zone = MarginZone.BELOW_MINIMUM
        else:
            zone = MarginZone.NEGATIVE

        # Низкомаржинальные позиции (маржа < 10%)
        low = []
        for line in estimate.lines:
            line_margin = (nmck / len(estimate.lines) - line.total) / max(nmck / len(estimate.lines), 1) * 100 if nmck > 0 else 0
            if line_margin < 10:
                low.append(f"{line.code}: {line.name} (маржа {line_margin:.1f}%)")

        # Предупреждения
        warnings = []
        if zone in (MarginZone.BELOW_MINIMUM, MarginZone.NEGATIVE):
            warnings.append("Маржа ниже допустимого минимума 10% — РЕКОМЕНДУЕТСЯ НЕ ПОДАВАТЬ")
        if margin < 15:
            warnings.append("Риск убытка при любых отклонениях по объёмам или ценам")
        if low:
            warnings.append(f"{len(low)} позиций с маржой < 10%")

        return MarginReport(
            estimate=estimate,
            nmck=nmck,
            margin_pct=round(margin, 2),
            margin_zone=zone,
            low_margin_lines=low,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    # VOR ↔ KS-2 Comparison
    # -------------------------------------------------------------------------

    def compare_vor_ks2(
        self, vor_positions: List[Dict], ks2_positions: List[Dict]
    ) -> Dict[str, Any]:
        """Сравнение ВОР с КС-2: расхождения по объёмам и позициям."""
        vor_map = {p.get("code", p.get("name", "")): p for p in vor_positions}
        ks2_map = {p.get("code", p.get("name", "")): p for p in ks2_positions}

        only_in_vor = set(vor_map) - set(ks2_map)
        only_in_ks2 = set(ks2_map) - set(vor_map)
        common = set(vor_map) & set(ks2_map)

        discrepancies = []
        for code in common:
            v = float(vor_map[code].get("quantity", 0))
            k = float(ks2_map[code].get("quantity", 0))
            if v > 0:
                diff = abs(v - k) / v * 100
                if diff > 1.0:
                    discrepancies.append({
                        "code": code,
                        "name": vor_map[code].get("name", code),
                        "vor_quantity": v,
                        "ks2_quantity": k,
                        "diff_pct": round(diff, 1),
                    })

        return {
            "total_vor_positions": len(vor_positions),
            "total_ks2_positions": len(ks2_positions),
            "matching": len(common),
            "only_in_vor": list(only_in_vor),
            "only_in_ks2": list(only_in_ks2),
            "discrepancies": discrepancies,
            "has_discrepancies": len(discrepancies) > 0,
        }

    # -------------------------------------------------------------------------
    # KS-2/KS-3 Generation
    # -------------------------------------------------------------------------

    def generate_ks2_data(
        self, estimate: SmetaEstimate, act_number: str, period: str
    ) -> Dict[str, Any]:
        """Сформировать данные для КС-2 (акт о приёмке выполненных работ)."""
        lines = []
        for i, line in enumerate(estimate.lines, 1):
            lines.append({
                "row": i,
                "code": line.code,
                "name": line.name,
                "unit": line.unit,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "total": line.total,
            })

        return {
            "act_number": act_number,
            "period": period,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "lines": lines,
            "total": round(estimate.grand_total, 2),
            "vat": round(estimate.vat, 2),
            "line_count": len(lines),
        }

    def generate_ks3_data(
        self, estimate: SmetaEstimate, ks2_acts: List[Dict], period: str
    ) -> Dict[str, Any]:
        """Сформировать данные для КС-3 (справка о стоимости)."""
        total_since_start = estimate.grand_total if not ks2_acts else sum(
            a.get("total", 0) for a in ks2_acts
        )

        return {
            "period": period,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "total_since_start": round(total_since_start, 2),
            "this_period": round(estimate.grand_total, 2),
            "acts_included": [a.get("act_number", "") for a in ks2_acts],
        }


    # -------------------------------------------------------------------------
    # Normative Validity Check (Knowledge Invalidation)
    # -------------------------------------------------------------------------

    def check_norms_validity(self, norm_refs: List[str]) -> List[Dict[str, Any]]:
        """
        Проверить актуальность нормативных ссылок (ФЕР/ТЕР/МДС) через InvalidationEngine.

        Возвращает список предупреждений для устаревших норм.
        """
        try:
            from src.core.knowledge.invalidation_engine import invalidation_engine
            results = invalidation_engine.check_validity_batch(norm_refs)
        except Exception:
            return []

        warnings = []
        for ref, status in results.items():
            if not status.get("valid", True) or status.get("warning"):
                warnings.append({
                    "norm_ref": ref,
                    "status": status.get("status", "unknown"),
                    "replaced_by": status.get("replaced_by"),
                    "warning": status.get("warning", ""),
                })
        return warnings

    def build_estimate_with_validity(
        self,
        project_id: int,
        title: str,
        vor_positions: List[Dict[str, Any]],
        norm_refs: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[SmetaEstimate, List[Dict[str, Any]]]:
        """
        Построить смету с проверкой актуальности нормативной базы.

        Returns:
            (SmetaEstimate, stale_warnings_list)
        """
        estimate = self.build_estimate(project_id, title, vor_positions, **kwargs)

        # Collect norm refs from estimate codes
        all_refs = set(norm_refs or [])
        for line in estimate.lines:
            if line.code:
                all_refs.add(line.code)
        # Add common smeta norms
        all_refs.update(["МДС 81-35.2004", "МДС 81-33.2004", "МДС 81-25.2001"])

        validity_warnings = self.check_norms_validity(list(all_refs))

        return estimate, validity_warnings

    # =========================================================================
    # Knowledge Base RAG
    # =========================================================================

    def ask_kb(
        self, query: str, top_k: int = 5, min_weight: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base for smeta-relevant traps, prices, norms.

        Args:
            query: Search query (e.g. "ФЕР на бетонирование", "индексы Минстроя")
        Returns:
            List of KB entries
        """
        from src.core.knowledge.knowledge_base import knowledge_base

        results = knowledge_base.search(
            query=query, domain="smeta", top_k=top_k, min_weight=min_weight,
        )
        logger.info("Smeta ask_kb: '%s' → %d results", query[:60], len(results))
        return results


smeta_agent = SmetaAgent()
