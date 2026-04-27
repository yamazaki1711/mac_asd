"""
ASD v11.3 — Profit Model Schema.

Модель рентабельности тендера.
Генерируется Сметчиком на основе ВОР, ФЕР/ТЕР расценок и логистических данных.

Содержит:
- Калькуляция себестоимости по позициям ВОР
- Сравнение с НМЦК
- Анализ маржинальности
- Оценка рисков занижения
- Условный ветвинг: НМЦК < 70% рынка → NO GO
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class MarginZone(str, Enum):
    """Зона маржинальности."""
    EXCELLENT = "excellent"    # > 40%
    GOOD = "good"             # 25-40%
    ACCEPTABLE = "acceptable"  # 15-25%
    MARGINAL = "marginal"      # 10-15%
    BELOW_MINIMUM = "below_minimum"  # < 10% (NO GO)
    NEGATIVE = "negative"      # < 0% (убыток)


class CostCategory(str, Enum):
    """Категория затрат."""
    MATERIALS = "materials"          # Материалы
    LABOR = "labor"                  # Заработная плата
    MACHINERY = "machinery"          # Машины и механизмы
    OVERHEAD = "overhead"            # Накладные расходы
    PROFIT_PLAN = "profit_plan"      # Сметная прибыль
    SUBCONTRACTOR = "subcontractor"  # Субподрядные работы
    TRANSPORT = "transport"          # Транспортные расходы
    OTHER = "other"                  # Прочие затраты


class NMCkStatus(str, Enum):
    """Статус НМЦК относительно рынка."""
    ADEQUATE = "adequate"          # НМЦК в пределах рынка (отклонение < 15%)
    BELOW_MARKET = "below_market"  # НМЦК ниже рынка (отклонение 15-30%)
    DANGEROUSLY_LOW = "dangerously_low"  # НМЦК критически ниже (< 70% рынка)
    ABOVE_MARKET = "above_market"  # НМЦК выше рынка (редко, но возможно)


# =============================================================================
# Position Cost
# =============================================================================

class PositionCost(BaseModel):
    """Стоимость одной позиции ВОР."""
    position_code: str = Field(
        description="Код позиции (ФЕР/ТЕР или внутренний)"
    )
    position_name: str = Field(
        description="Наименование работы/материала"
    )
    unit: str = Field(
        description="Единица измерения (м3, м2, шт, т)"
    )
    quantity: float = Field(
        gt=0,
        description="Количество по ВОР"
    )
    unit_cost: float = Field(
        gt=0,
        description="Единичная расценка (руб.)"
    )
    total_cost: float = Field(
        gt=0,
        description="Итого по позиции (руб.)"
    )
    cost_category: CostCategory = Field(
        default=CostCategory.LABOR,
        description="Категория затрат"
    )
    region_coeff: float = Field(
        default=1.0,
        description="Региональный коэффициент"
    )
    year_index: float = Field(
        default=1.0,
        description="Индекс пересчёта в текущие цены"
    )
    fer_code: Optional[str] = Field(
        default=None,
        description="Код ФЕР/ТЕР расценки"
    )
    margin_pct: float = Field(
        description="Маржа по позиции (%)"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        default=0.8,
        description="Уверенность в расчёте позиции"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "position_code": "01-01-001-01",
                "position_name": "Разработка грунта I группы в отвал экскаваторами",
                "unit": "1000 м3",
                "quantity": 1.5,
                "unit_cost": 12500.0,
                "total_cost": 18750.0,
                "cost_category": "labor",
                "region_coeff": 1.12,
                "year_index": 8.45,
                "fer_code": "ФЕР01-01-001-01",
                "margin_pct": 28.5,
                "confidence": 0.9,
            }
        }


# =============================================================================
# Cost Breakdown
# =============================================================================

class CostBreakdown(BaseModel):
    """Разбивка затрат по категориям."""
    materials: float = Field(default=0.0, description="Материалы (руб.)")
    labor: float = Field(default=0.0, description="Зарплата (руб.)")
    machinery: float = Field(default=0.0, description="Механизмы (руб.)")
    overhead: float = Field(default=0.0, description="Накладные расходы (руб.)")
    profit_plan: float = Field(default=0.0, description="Сметная прибыль (руб.)")
    subcontractor: float = Field(default=0.0, description="Субподряд (руб.)")
    transport: float = Field(default=0.0, description="Транспорт (руб.)")
    other: float = Field(default=0.0, description="Прочие (руб.)")

    @property
    def total(self) -> float:
        """Итого себестоимость."""
        return (
            self.materials + self.labor + self.machinery +
            self.overhead + self.profit_plan + self.subcontractor +
            self.transport + self.other
        )

    def to_pct(self) -> Dict[str, float]:
        """Структура затрат в процентах."""
        t = self.total
        if t == 0:
            return {}
        return {
            "materials": round(self.materials / t * 100, 1),
            "labor": round(self.labor / t * 100, 1),
            "machinery": round(self.machinery / t * 100, 1),
            "overhead": round(self.overhead / t * 100, 1),
            "profit_plan": round(self.profit_plan / t * 100, 1),
            "subcontractor": round(self.subcontractor / t * 100, 1),
            "transport": round(self.transport / t * 100, 1),
            "other": round(self.other / t * 100, 1),
        }


# =============================================================================
# Profit Model (Main)
# =============================================================================

class ProfitModel(BaseModel):
    """
    Модель рентабельности тендера.

    Генерируется Сметчиком как результат расчёта стоимости.
    Включает полную калькуляцию, анализ маржинальности и оценку рисков.
    """
    # ── Идентификация ──
    lot_id: str = Field(
        description="ID тендерного лота"
    )
    project_id: Optional[int] = Field(
        default=None,
        description="ID проекта в БД"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Дата/время расчёта (ISO 8601)"
    )

    # ── НМЦК ──
    nmck: float = Field(
        gt=0,
        description="Начальная максимальная цена контракта (руб.)"
    )
    nmck_vs_market_pct: float = Field(
        description="Отклонение НМЦК от рынка (%). Отрицательное = ниже рынка."
    )
    nmck_status: NMCkStatus = Field(
        description="Статус НМЦК относительно рынка"
    )
    market_price_estimate: Optional[float] = Field(
        default=None,
        description="Оценка рыночной стоимости работ (руб.)"
    )

    # ── Себестоимость ──
    total_cost: float = Field(
        gt=0,
        description="Полная себестоимость (руб.)"
    )
    cost_breakdown: CostBreakdown = Field(
        default_factory=CostBreakdown,
        description="Разбивка затрат по категориям"
    )

    # ── Маржинальность ──
    profit_amount: float = Field(
        description="Прибыль (руб.) = НМЦК - себестоимость"
    )
    profit_margin_pct: float = Field(
        description="Маржа (%) = прибыль / НМЦК × 100"
    )
    margin_zone: MarginZone = Field(
        description="Зона маржинальности"
    )

    # ── Позиции ВОР ──
    positions: List[PositionCost] = Field(
        default_factory=list,
        description="Калькуляция по позициям ВОР"
    )
    total_positions: int = Field(
        default=0,
        description="Общее количество позиций"
    )
    low_margin_positions: List[str] = Field(
        default_factory=list,
        description="Позиции с маржой < 10%"
    )
    negative_margin_positions: List[str] = Field(
        default_factory=list,
        description="Позиции с отрицательной маржой"
    )

    # ── Условный ветвинг: НМЦК < 70% ──
    nmck_70pct_threshold: Optional[float] = Field(
        default=None,
        description="70% от рыночной стоимости (руб.). Если НМЦК < этого значения → NO GO."
    )
    nmck_below_70pct: bool = Field(
        default=False,
        description="НМЦК ниже 70% рынка (критический порог)"
    )

    # ── Риски ──
    volume_risk: Optional[str] = Field(
        default=None,
        description="Риск по объёмам (если ВОР неполная или нечёткая)"
    )
    price_risk: Optional[str] = Field(
        default=None,
        description="Риск по ценам (если прайсы устарели или ненадёжны)"
    )
    scope_change_risk: Optional[str] = Field(
        default=None,
        description="Риск изменения объёмов (доп. работы, корректировки)"
    )

    # ── Уверенность ──
    overall_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Общая уверенность Сметчика в расчёте"
    )
    fer_coverage_pct: float = Field(
        ge=0.0, le=100.0,
        default=0.0,
        description="Покрытие позиций ФЕР/ТЕР расценками (%)"
    )

    # ── Рекомендации ──
    recommended_bid_price: Optional[float] = Field(
        default=None,
        description="Рекомендуемая цена подачи (руб.) — может быть ниже НМЦК"
    )
    recommended_discount_pct: Optional[float] = Field(
        default=None,
        description="Рекомендуемый дисконт от НМЦК (%)"
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Примечания и оговорки"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "lot_id": "T-2026-0451",
                "nmck": 55000000.0,
                "nmck_vs_market_pct": -12.5,
                "nmck_status": "below_market",
                "total_cost": 37400000.0,
                "profit_amount": 17600000.0,
                "profit_margin_pct": 32.0,
                "margin_zone": "good",
                "total_positions": 145,
                "low_margin_positions": ["ФЕР06-01-001-02"],
                "nmck_below_70pct": False,
                "overall_confidence": 0.78,
                "fer_coverage_pct": 92.0,
                "recommended_bid_price": 52000000.0,
                "recommended_discount_pct": 5.5,
            }
        }


# =============================================================================
# Profit Model Builder
# =============================================================================

class ProfitModelBuilder:
    """Строитель ProfitModel — пошаговое формирование модели."""

    def __init__(self, lot_id: str, nmck: float):
        self._lot_id = lot_id
        self._nmck = nmck
        self._positions: List[PositionCost] = []
        self._cost_breakdown = CostBreakdown()
        self._market_estimate: Optional[float] = None
        self._confidence: float = 0.8

    def add_position(self, position: PositionCost) -> "ProfitModelBuilder":
        self._positions.append(position)
        return self

    def set_cost_breakdown(self, breakdown: CostBreakdown) -> "ProfitModelBuilder":
        self._cost_breakdown = breakdown
        return self

    def set_market_estimate(self, estimate: float) -> "ProfitModelBuilder":
        self._market_estimate = estimate
        return self

    def set_confidence(self, confidence: float) -> "ProfitModelBuilder":
        self._confidence = confidence
        return self

    def build(self) -> ProfitModel:
        """Рассчитывает и собирает ProfitModel."""
        # Себестоимость
        total_cost = sum(p.total_cost for p in self._positions)
        if total_cost == 0:
            total_cost = self._cost_breakdown.total

        # Прибыль и маржа
        profit = self._nmck - total_cost
        margin_pct = (profit / self._nmck * 100) if self._nmck > 0 else 0.0

        # Зона маржинальности
        if margin_pct > 40:
            margin_zone = MarginZone.EXCELLENT
        elif margin_pct > 25:
            margin_zone = MarginZone.GOOD
        elif margin_pct > 15:
            margin_zone = MarginZone.ACCEPTABLE
        elif margin_pct > 10:
            margin_zone = MarginZone.MARGINAL
        elif margin_pct > 0:
            margin_zone = MarginZone.BELOW_MINIMUM
        else:
            margin_zone = MarginZone.NEGATIVE

        # НМЦК vs рынок
        nmck_vs_market_pct = 0.0
        nmck_status = NMCkStatus.ADEQUATE
        nmck_70pct = None
        nmck_below_70 = False

        if self._market_estimate and self._market_estimate > 0:
            nmck_vs_market_pct = round(
                (self._nmck - self._market_estimate) / self._market_estimate * 100, 1
            )
            nmck_70pct = round(self._market_estimate * 0.70, 2)
            nmck_below_70 = self._nmck < nmck_70pct

            if nmck_below_70:
                nmck_status = NMCkStatus.DANGEROUSLY_LOW
            elif nmck_vs_market_pct < -15:
                nmck_status = NMCkStatus.BELOW_MARKET
            elif nmck_vs_market_pct > 15:
                nmck_status = NMCkStatus.ABOVE_MARKET
            else:
                nmck_status = NMCkStatus.ADEQUATE

        # Позиции с низкой маржой
        low_margin = [p.position_code for p in self._positions if 0 < p.margin_pct < 10]
        negative_margin = [p.position_code for p in self._positions if p.margin_pct < 0]

        # Покрытие ФЕР
        fer_covered = sum(1 for p in self._positions if p.fer_code)
        fer_pct = (fer_covered / len(self._positions) * 100) if self._positions else 0

        return ProfitModel(
            lot_id=self._lot_id,
            nmck=self._nmck,
            nmck_vs_market_pct=nmck_vs_market_pct,
            nmck_status=nmck_status,
            market_price_estimate=self._market_estimate,
            total_cost=total_cost,
            cost_breakdown=self._cost_breakdown,
            profit_amount=profit,
            profit_margin_pct=round(margin_pct, 1),
            margin_zone=margin_zone,
            positions=self._positions,
            total_positions=len(self._positions),
            low_margin_positions=low_margin,
            negative_margin_positions=negative_margin,
            nmck_70pct_threshold=nmck_70pct,
            nmck_below_70pct=nmck_below_70,
            overall_confidence=self._confidence,
            fer_coverage_pct=round(fer_pct, 1),
        )
