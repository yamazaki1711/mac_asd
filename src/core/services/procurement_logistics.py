"""
ASD v12.0 — Procurement Agent (Закупщик) и Logistics Agent (Логист).

Закупщик: анализ тендеров, НМЦК, поиск поставщиков, оценка рентабельности.
Логист: расчёт доставки, сроки, vendors, транспортные расходы.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Shared Enums
# =============================================================================

class TenderDecision(str, Enum):
    BID = "bid"           # Подавать
    WATCH = "watch"        # Наблюдать
    SKIP = "skip"          # Пропустить
    CONDITIONAL = "conditional"  # Подавать с условиями


class TransportType(str, Enum):
    ROAD = "road"
    RAIL = "rail"
    SEA = "sea"
    AIR = "air"
    MULTIMODAL = "multimodal"


# =============================================================================
# Procurement Data Classes
# =============================================================================

@dataclass
class TenderInfo:
    """Информация о тендере."""
    lot_id: str
    title: str
    nmck: float
    customer: str = ""
    region: str = ""
    deadline: str = ""
    url: str = ""


@dataclass
class SupplierQuote:
    """Коммерческое предложение поставщика."""
    supplier_name: str
    material_name: str
    unit: str
    quantity: float
    unit_price: float
    total: float
    delivery_days: int = 14
    region: str = ""
    inn: str = ""
    rating: int = 5  # 1-5
    notes: str = ""


@dataclass
class TenderAnalysis:
    """Результат анализа тендера."""
    tender: TenderInfo
    total_cost: float            # Расчётная себестоимость
    margin_pct: float            # Маржа
    margin_absolute: float       # Прибыль в рублях
    nmck_vs_market_pct: float    # Отклонение НМЦК от рынка
    competitor_count: int = 0
    decision: TenderDecision = TenderDecision.WATCH
    risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lot_id": self.tender.lot_id,
            "nmck": self.tender.nmck,
            "total_cost": round(self.total_cost, 2),
            "margin_pct": round(self.margin_pct, 2),
            "margin_absolute": round(self.margin_absolute, 2),
            "nmck_vs_market_pct": round(self.nmck_vs_market_pct, 2),
            "decision": self.decision.value,
            "risks": self.risks,
        }


# =============================================================================
# Logistics Data Classes
# =============================================================================

@dataclass
class DeliveryRoute:
    """Маршрут доставки."""
    origin: str
    destination: str
    distance_km: float
    transport: TransportType = TransportType.ROAD
    cost_per_km: float = 55.0   # ₽/км (среднее по РФ, 2026)
    total_cost: float = 0.0
    duration_days: int = 3

    def __post_init__(self):
        if not self.total_cost:
            self.total_cost = self.distance_km * self.cost_per_km


@dataclass
class VendorInfo:
    """Информация о поставщике."""
    name: str
    inn: str = ""
    region: str = ""
    categories: List[str] = field(default_factory=list)  # металл, бетон...
    rating: int = 5
    min_order: float = 0.0
    delivery_available: bool = True
    contact: str = ""


@dataclass
class LogisticsPlan:
    """План логистики по проекту."""
    project_id: int
    routes: List[DeliveryRoute] = field(default_factory=list)
    vendors: List[VendorInfo] = field(default_factory=list)
    total_transport_cost: float = 0.0
    max_lead_time_days: int = 0

    @property
    def vendor_count(self) -> int:
        return len(self.vendors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "routes": len(self.routes),
            "vendors": self.vendor_count,
            "total_transport_cost": round(self.total_transport_cost, 2),
            "max_lead_time_days": self.max_lead_time_days,
        }


# =============================================================================
# Procurement Agent
# =============================================================================

class ProcurementAgent:
    """Агент-Закупщик ASD v12.0."""

    # Среднерыночные коэффициенты по видам работ
    MARKET_RATIOS: Dict[str, float] = {
        "земляные": 0.75,
        "фундаменты": 0.82,
        "бетонные": 0.78,
        "металлоконструкции": 0.85,
        "кровля": 0.80,
        "отделка": 0.72,
        "электромонтаж": 0.88,
        "овк": 0.83,
        "водоснабжение": 0.80,
    }

    def analyze_tender(
        self,
        tender: TenderInfo,
        estimated_cost: float,
        market_work_type: str = "",
    ) -> TenderAnalysis:
        """
        Анализ тендера: стоит ли подавать заявку.

        Args:
            tender: информация о тендере
            estimated_cost: расчётная себестоимость (из Сметчика)
            market_work_type: вид работ для рыночного коэффициента
        """
        margin = (tender.nmck - estimated_cost) / tender.nmck * 100 if tender.nmck > 0 else 0
        margin_abs = tender.nmck - estimated_cost

        # Оценка НМЦК относительно рынка
        ratio = self.MARKET_RATIOS.get(market_work_type, 0.80)
        market_price = estimated_cost / ratio if ratio > 0 else estimated_cost
        nmck_vs_market = (tender.nmck - market_price) / market_price * 100 if market_price > 0 else 0

        # Решение
        risks = []
        if margin < 10:
            decision = TenderDecision.SKIP
            risks.append("Маржа < 10% — высокий риск убытка")
        elif margin < 15:
            decision = TenderDecision.CONDITIONAL
            risks.append("Маржа 10-15% — подавать только при низких рисках")
        elif nmck_vs_market < -20:
            decision = TenderDecision.SKIP
            risks.append(f"НМЦК на {abs(nmck_vs_market):.0f}% ниже рынка — вероятный демпинг")
        elif nmck_vs_market < -10:
            decision = TenderDecision.CONDITIONAL
            risks.append(f"НМЦК ниже рынка на {abs(nmck_vs_market):.0f}%")
        else:
            decision = TenderDecision.BID

        recommendations = []
        if margin >= 25:
            recommendations.append("Рекомендуется агрессивная стратегия — снижение цены до 5% для гарантии победы")
        elif margin >= 15:
            recommendations.append("Рекомендуется умеренная стратегия — снижение до 3%")

        return TenderAnalysis(
            tender=tender,
            total_cost=estimated_cost,
            margin_pct=round(margin, 2),
            margin_absolute=round(margin_abs, 2),
            nmck_vs_market_pct=round(nmck_vs_market, 2),
            decision=decision,
            risks=risks,
            recommendations=recommendations,
        )

    def search_suppliers(
        self, materials: List[str], region: str = ""
    ) -> List[SupplierQuote]:
        """
        Поиск поставщиков материалов (упрощённый — без внешних API).

        В production — интеграция с базой поставщиков (pgvector поиск).
        """
        # Демо-поставщики
        demo_suppliers = [
            SupplierQuote("МеталлИнвест", "", "т", 1, 85000, 85000, 7, "Москва", "7700000001", 5),
            SupplierQuote("СеверСталь", "", "т", 1, 92000, 92000, 14, "Череповец", "7700000002", 4),
            SupplierQuote("БетонСтрой", "", "м³", 1, 5500, 5500, 1, "Москва", "7700000003", 5),
            SupplierQuote("ЖБИ-Комплект", "", "шт", 1, 35000, 35000, 10, "Москва", "7700000004", 4),
            SupplierQuote("ЭлектроСнаб", "", "компл", 1, 45000, 45000, 5, "СПб", "7800000001", 4),
            SupplierQuote("СантехКомплект", "", "компл", 1, 28000, 28000, 3, "Москва", "7700000005", 5),
        ]

        # Фильтр по региону (упрощённо)
        if region:
            demo_suppliers = [s for s in demo_suppliers if region.lower() in s.region.lower()] or demo_suppliers

        # Заполняем названия материалов
        for s, mat in zip(demo_suppliers, materials * (len(demo_suppliers) // max(len(materials), 1) + 1)):
            s.material_name = mat

        return demo_suppliers[: max(len(materials), 3)]

    def compare_quotes(self, quotes: List[SupplierQuote]) -> Dict[str, Any]:
        """Сравнить коммерческие предложения."""
        if not quotes:
            return {}

        best = min(quotes, key=lambda q: q.total)
        avg = sum(q.total for q in quotes) / len(quotes)

        return {
            "quotes_count": len(quotes),
            "best_supplier": best.supplier_name,
            "best_price": best.total,
            "average_price": round(avg, 2),
            "potential_savings": round(avg - best.total, 2),
            "suppliers": [
                {
                    "name": q.supplier_name,
                    "price": q.total,
                    "delivery_days": q.delivery_days,
                    "rating": q.rating,
                }
                for q in sorted(quotes, key=lambda q: q.total)
            ],
        }

    # =========================================================================
    # Knowledge Base RAG
    # =========================================================================

    def ask_kb(
        self, query: str, top_k: int = 5, min_weight: int = 20
    ) -> List[Dict[str, Any]]:
        """Search knowledge base for procurement-relevant traps, suppliers, prices."""
        from src.core.knowledge.knowledge_base import knowledge_base
        results = knowledge_base.search(
            query=query, domain="procurement", top_k=top_k, min_weight=min_weight,
        )
        logger.info("Procurement ask_kb: '%s' → %d results", query[:60], len(results))
        return results


# =============================================================================
# Logistics Agent
# =============================================================================

class LogisticsAgent:
    """Агент-Логист ASD v12.0."""

    # Средние скорости и стоимости по видам транспорта
    TRANSPORT_PARAMS = {
        TransportType.ROAD: {"speed_km_day": 500, "cost_per_km": 55.0},
        TransportType.RAIL: {"speed_km_day": 400, "cost_per_km": 30.0},
        TransportType.SEA: {"speed_km_day": 600, "cost_per_km": 20.0},
        TransportType.AIR: {"speed_km_day": 5000, "cost_per_km": 200.0},
    }

    # Расстояния между основными городами (км)
    CITY_DISTANCES: Dict[str, Dict[str, float]] = {
        "Москва": {"СПб": 700, "Казань": 820, "Сочи": 1600, "Владивосток": 9000, "Череповец": 500},
        "СПб": {"Москва": 700, "Мурманск": 1400, "Петрозаводск": 430},
        "Казань": {"Москва": 820, "Екатеринбург": 1000, "Уфа": 530},
    }

    def plan_delivery(
        self,
        origin: str,
        destination: str,
        transport: TransportType = TransportType.ROAD,
        custom_distance_km: float = 0.0,
    ) -> DeliveryRoute:
        """Рассчитать маршрут доставки."""
        # Расстояние
        if custom_distance_km > 0:
            distance = custom_distance_km
        else:
            distance = self._estimate_distance(origin, destination)

        params = self.TRANSPORT_PARAMS.get(transport, self.TRANSPORT_PARAMS[TransportType.ROAD])
        duration = max(1, int(distance / params["speed_km_day"]))
        cost = distance * params["cost_per_km"]

        return DeliveryRoute(
            origin=origin,
            destination=destination,
            distance_km=distance,
            transport=transport,
            cost_per_km=params["cost_per_km"],
            total_cost=cost,
            duration_days=duration,
        )

    def build_logistics_plan(
        self,
        project_id: int,
        suppliers: List[SupplierQuote],
        destination: str,
        transport: TransportType = TransportType.ROAD,
    ) -> LogisticsPlan:
        """Построить план логистики: доставка от каждого поставщика."""
        routes = []
        vendors = []
        total_cost = 0.0
        max_lead = 0

        for s in suppliers:
            origin = s.region or "Москва"
            route = self.plan_delivery(origin, destination, transport)
            routes.append(route)
            total_cost += route.total_cost

            total_lead = route.duration_days + s.delivery_days
            if total_lead > max_lead:
                max_lead = total_lead

            vendors.append(VendorInfo(
                name=s.supplier_name,
                inn=s.inn,
                region=s.region,
                rating=s.rating,
                delivery_available=True,
            ))

        return LogisticsPlan(
            project_id=project_id,
            routes=routes,
            vendors=vendors,
            total_transport_cost=total_cost,
            max_lead_time_days=max_lead,
        )

    def _estimate_distance(self, origin: str, destination: str) -> float:
        """Оценка расстояния между городами."""
        # Прямой поиск
        if origin in self.CITY_DISTANCES:
            if destination in self.CITY_DISTANCES[origin]:
                return self.CITY_DISTANCES[origin][destination]
        if destination in self.CITY_DISTANCES:
            if origin in self.CITY_DISTANCES[destination]:
                return self.CITY_DISTANCES[destination][origin]

        # По умолчанию — среднее по РФ
        return 2500.0


procurement_agent = ProcurementAgent()
logistics_agent = LogisticsAgent()
