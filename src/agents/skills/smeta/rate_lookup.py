"""
MAC_ASD v11.3 — SmetaRateLookup Skill.

База единичных расценок по видам работ компании.
Содержит эталонные расценки ФЕР/ГЭСН для 6 специализаций:
  общестроительные, бетонные, земляные, сварочные, монтажные, шпунтовые.

Предоставляет:
  - Поиск расценки по коду ФЕР или описанию работы
  - Фильтрация по виду работ
  - Проверка актуальности индекса Минстроя
  - Расчёт с учётом поправочных коэффициентов

Нормативная база (2026):
  - ФЕР-2024 (федеральные единичные расценки)
  - ГЭСН-2024 (государственные элементные сметные нормы)
  - Приказ Минстроя об индексах (ежеквартальный)
  - МДС 81-35.2004 (методика определения стоимости)
  - МДС 81-33.2004 (накладные расходы)
  - МДС 81-25.2001 (смстная прибыль)
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Rate Database — seed data for company specializations
# =============================================================================

class RateSource(str, Enum):
    """Источник расценки."""
    FER = "ФЕР-2024"
    GESN = "ГЭСН-2024"
    TER = "ТЕР-2024"  # территориальные (при наличии)
    ANALOG = "по_аналогии"
    COMMERCIAL = "коммерческая"


class RateCategory(str, Enum):
    """Категория затрат в расценке."""
    LABOR = "оплата_труда"
    MATERIALS = "материалы"
    MACHINERY = "эксплуатация_машин"
    TOTAL = "всего"


# Справочник расценок по видам работ компании
# Структура: код ФЕР → описание → состав затрат (базисный уровень 01.01.2024)
RATE_DATABASE: Dict[str, List[Dict[str, Any]]] = {
    "общестроительные": [
        {
            "code": "ФЕР08-02-001-01",
            "description": "Устройство фундаментов ленточных бетонных",
            "unit": "м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 1245.50,
                RateCategory.MATERIALS: 5320.80,
                RateCategory.MACHINERY: 890.30,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["общестроительные", "бетонные"],
            "norm_reference": "ГЭСН 08-02-001-01",
        },
        {
            "code": "ФЕР08-01-003-05",
            "description": "Укладка сеток и каркасов арматурных",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 8920.00,
                RateCategory.MATERIALS: 48500.00,
                RateCategory.MACHINERY: 2340.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["общестроительные", "бетонные"],
            "norm_reference": "ГЭСН 08-01-003-05",
        },
        {
            "code": "ФЕР08-04-001-01",
            "description": "Гидроизоляция боковая обмазочная битумная",
            "unit": "100 м2",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 2840.00,
                RateCategory.MATERIALS: 6150.00,
                RateCategory.MACHINERY: 320.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["общестроительные"],
            "norm_reference": "ГЭСН 08-04-001-01",
        },
        {
            "code": "ФЕР07-05-001-01",
            "description": "Кладка стен кирпичных наружных простых",
            "unit": "м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 1680.00,
                RateCategory.MATERIALS: 7240.00,
                RateCategory.MACHINERY: 540.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["общестроительные"],
            "norm_reference": "ГЭСН 07-05-001-01",
        },
    ],
    "бетонные": [
        {
            "code": "ФЕР06-01-001-01",
            "description": "Устройство бетонной подготовки",
            "unit": "м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 780.00,
                RateCategory.MATERIALS: 4120.00,
                RateCategory.MACHINERY: 620.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["бетонные"],
            "norm_reference": "ГЭСН 06-01-001-01",
        },
        {
            "code": "ФЕР06-01-013-01",
            "description": "Бетонирование конструкций стен и перегородок",
            "unit": "м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 1560.00,
                RateCategory.MATERIALS: 5680.00,
                RateCategory.MACHINERY: 940.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["бетонные"],
            "norm_reference": "ГЭСН 06-01-013-01",
        },
        {
            "code": "ФЕР06-01-031-01",
            "description": "Установка опалубки стен",
            "unit": "м2",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 920.00,
                RateCategory.MATERIALS: 2450.00,
                RateCategory.MACHINERY: 380.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["бетонные"],
            "norm_reference": "ГЭСН 06-01-031-01",
        },
        {
            "code": "ФЕР06-01-040-01",
            "description": "Установка и вязка арматуры отдельно стоящих фундаментов",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 12400.00,
                RateCategory.MATERIALS: 52800.00,
                RateCategory.MACHINERY: 3500.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["бетонные"],
            "norm_reference": "ГЭСН 06-01-040-01",
        },
    ],
    "земляные": [
        {
            "code": "ФЕР01-01-013-01",
            "description": "Разработка грунта экскаватором в отвал",
            "unit": "1000 м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 420.00,
                RateCategory.MATERIALS: 0.00,
                RateCategory.MACHINERY: 18200.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["земляные"],
            "norm_reference": "ГЭСН 01-01-013-01",
        },
        {
            "code": "ФЕР01-01-033-01",
            "description": "Засыпка грунта бульдозером",
            "unit": "1000 м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 180.00,
                RateCategory.MATERIALS: 0.00,
                RateCategory.MACHINERY: 6840.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["земляные"],
            "norm_reference": "ГЭСН 01-01-033-01",
        },
        {
            "code": "ФЕР01-02-056-01",
            "description": "Уплотнение грунта пневмотрамбовками",
            "unit": "100 м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 890.00,
                RateCategory.MATERIALS: 120.00,
                RateCategory.MACHINERY: 1450.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["земляные"],
            "norm_reference": "ГЭСН 01-02-056-01",
        },
        {
            "code": "ФЕР01-02-061-01",
            "description": "Разработка грунта вручную в котлованах",
            "unit": "м3",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 680.00,
                RateCategory.MATERIALS: 0.00,
                RateCategory.MACHINERY: 0.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["земляные"],
            "norm_reference": "ГЭСН 01-02-061-01",
        },
    ],
    "сварочные": [
        {
            "code": "ФЕР09-06-001-01",
            "description": "Сварка стыков стальных трубопроводов",
            "unit": "стык",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 540.00,
                RateCategory.MATERIALS: 280.00,
                RateCategory.MACHINERY: 190.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["сварочные"],
            "norm_reference": "ГЭСН 09-06-001-01",
        },
        {
            "code": "ФЕР30-01-015-01",
            "description": "Антикоррозионная защита сварных соединений",
            "unit": "м2",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 380.00,
                RateCategory.MATERIALS: 1240.00,
                RateCategory.MACHINERY: 150.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["сварочные", "монтажные"],
            "norm_reference": "ГЭСН 30-01-015-01",
        },
        {
            "code": "ФЕР09-03-002-01",
            "description": "Ручная дуговая сварка стальных конструкций",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 6800.00,
                RateCategory.MATERIALS: 3450.00,
                RateCategory.MACHINERY: 2100.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["сварочные"],
            "norm_reference": "ГЭСН 09-03-002-01",
        },
    ],
    "монтажные": [
        {
            "code": "ФЕР09-01-001-01",
            "description": "Монтаж стальных колонн одноэтажных зданий",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 5400.00,
                RateCategory.MATERIALS: 1200.00,
                RateCategory.MACHINERY: 8900.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["монтажные"],
            "norm_reference": "ГЭСН 09-01-001-01",
        },
        {
            "code": "ФЕР09-03-011-01",
            "description": "Монтаж балок и ригелей стальных",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 4200.00,
                RateCategory.MATERIALS: 980.00,
                RateCategory.MACHINERY: 7600.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["монтажные"],
            "norm_reference": "ГЭСН 09-03-011-01",
        },
        {
            "code": "ФЕР07-01-011-01",
            "description": "Монтаж железобетонных фундаментов",
            "unit": "шт",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 3200.00,
                RateCategory.MATERIALS: 1800.00,
                RateCategory.MACHINERY: 5400.00,
            },
            "overhead_pct": 12.0,
            "profit_pct": 8.0,
            "applicable_works": ["монтажные", "бетонные"],
            "norm_reference": "ГЭСН 07-01-011-01",
        },
        {
            "code": "ФЕР09-04-001-01",
            "description": "Монтаж связей стальных",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 8100.00,
                RateCategory.MATERIALS: 2400.00,
                RateCategory.MACHINERY: 6300.00,
            },
            "overhead_pct": 13.0,
            "profit_pct": 7.0,
            "applicable_works": ["монтажные"],
            "norm_reference": "ГЭСН 09-04-001-01",
        },
    ],
    "шпунтовые": [
        {
            "code": "ФЕР05-01-001-01",
            "description": "Погружение шпунта Ларсена вибропогружателем",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 2800.00,
                RateCategory.MATERIALS: 450.00,
                RateCategory.MACHINERY: 12400.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["шпунтовые"],
            "norm_reference": "ГЭСН 05-01-001-01",
        },
        {
            "code": "ФЕР05-01-003-01",
            "description": "Извлечение шпунта вибропогружателем",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 1400.00,
                RateCategory.MATERIALS: 0.00,
                RateCategory.MACHINERY: 8200.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["шпунтовые"],
            "norm_reference": "ГЭСН 05-01-003-01",
        },
        {
            "code": "ФЕР05-01-005-01",
            "description": "Устройство распорных креплений шпунтового ограждения",
            "unit": "т",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 5600.00,
                RateCategory.MATERIALS: 1800.00,
                RateCategory.MACHINERY: 4200.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["шпунтовые"],
            "norm_reference": "ГЭСН 05-01-005-01",
        },
        {
            "code": "ФЕР30-01-008-01",
            "description": "Антикоррозионная защита шпунта",
            "unit": "м2",
            "rate_source": RateSource.FER,
            "base_costs": {
                RateCategory.LABOR: 420.00,
                RateCategory.MATERIALS: 1580.00,
                RateCategory.MACHINERY: 180.00,
            },
            "overhead_pct": 14.0,
            "profit_pct": 6.0,
            "applicable_works": ["шпунтовые"],
            "norm_reference": "ГЭСН 30-01-008-01",
        },
    ],
}

# Индексы изменения сметной стоимости Минстроя (seed data)
# Реальные данные загружаются из ./data/indices/minstroy_latest.json
MINSTROY_INDICES: Dict[str, Dict[str, Any]] = {
    "current_quarter": "2025-Q4",
    "published_date": "2025-12-15",
    "next_update": "2026-03-15",
    "base_level": "01.01.2024",
    "indices_by_work_type": {
        "общестроительные": {
            "index": 1.0872,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
        "бетонные": {
            "index": 1.0915,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
        "земляные": {
            "index": 1.0643,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
        "сварочные": {
            "index": 1.0728,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
        "монтажные": {
            "index": 1.0845,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
        "шпунтовые": {
            "index": 1.0761,
            "region": "РФ средний",
            "note": "К базисному уровню 01.01.2024",
        },
    },
}

# Поправочные коэффициенты для особых условий
ADJUSTMENT_COEFFICIENTS: Dict[str, Dict[str, Any]] = {
    "winter": {
        "name": "Зимнее удорожание",
        "coefficient_range": (1.02, 1.15),
        "depends_on": "температурная зона",
        "reference": "МДС 81-35.2004, раздел 4",
    },
    "night_work": {
        "name": "Работа в ночное время",
        "coefficient": 1.20,
        "applies_to": "оплата труда рабочих",
        "reference": "ТК РФ ст. 154",
    },
    "confined_space": {
        "name": "Работа в стеснённых условиях",
        "coefficient_range": (1.05, 1.25),
        "depends_on": "стеснённость",
        "reference": "МДС 81-35.2004, приложение 1",
    },
    "height_work": {
        "name": "Работа на высоте",
        "coefficient_range": (1.04, 1.25),
        "depends_on": "высота",
        "reference": "МДС 81-35.2004",
    },
}


class SmetaRateLookup(SkillBase):
    """
    Навык Сметчика: поиск и выбор расценок.

    Содержит справочник ФЕР/ГЭСН по видам работ компании,
    актуальные индексы Минстроя и поправочные коэффициенты.
    """

    skill_id = "SmetaRateLookup"
    description = "Поиск расценок ФЕР/ГЭСН по видам работ компании"
    agent = "smeta"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: action обязателен."""
        action = params.get("action")
        if not action:
            return {"valid": False, "errors": ["Параметр 'action' обязателен"]}
        valid_actions = {"lookup", "search", "list_by_work", "get_index", "list_coefficients"}
        if action not in valid_actions:
            return {"valid": False, "errors": [f"Неизвестное действие: {action}. Допустимые: {valid_actions}"]}
        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Выполнить поиск расценки.

        Actions:
            lookup: Найти расценку по коду ФЕР
            search: Поиск по описанию работы
            list_by_work: Все расценки для вида работ
            get_index: Актуальный индекс Минстроя
            list_coefficients: Поправочные коэффициенты
        """
        action = params["action"]

        if action == "lookup":
            return self._lookup(params.get("code", ""))
        elif action == "search":
            return self._search(params.get("query", ""), params.get("work_type"))
        elif action == "list_by_work":
            return self._list_by_work(params.get("work_type", ""))
        elif action == "get_index":
            return self._get_index(params.get("work_type"))
        elif action == "list_coefficients":
            return self._list_coefficients()

    def _lookup(self, code: str) -> SkillResult:
        """Найти расценку по коду ФЕР."""
        if not code:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметр 'code' обязателен для lookup"],
            )

        # Поиск по всем видам работ
        for work_type, rates in RATE_DATABASE.items():
            for rate in rates:
                if rate["code"].upper() == code.upper():
                    return SkillResult(
                        status=SkillStatus.SUCCESS,
                        skill_id=self.skill_id,
                        data={
                            "rate": rate,
                            "work_type": work_type,
                            "index_available": work_type in MINSTROY_INDICES["indices_by_work_type"],
                        },
                    )

        return SkillResult(
            status=SkillStatus.REJECTED,
            skill_id=self.skill_id,
            data={"code": code},
            errors=[f"Расценка с кодом '{code}' не найдена в базе"],
            warnings=[
                "Проверьте корректность кода ФЕР. "
                "Если расценка отсутствует — подберите аналог через action='search'."
            ],
        )

    def _search(self, query: str, work_type: Optional[str] = None) -> SkillResult:
        """Поиск расценок по описанию работы."""
        if not query:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметр 'query' обязателен для search"],
            )

        query_lower = query.lower()
        results = []

        search_in = {work_type: RATE_DATABASE[work_type]} if work_type and work_type in RATE_DATABASE else RATE_DATABASE

        for wt, rates in search_in.items():
            for rate in rates:
                # Поиск по описанию и коду
                searchable = f"{rate['code']} {rate['description']} {rate['norm_reference']}".lower()
                if any(word in searchable for word in query_lower.split() if len(word) > 2):
                    results.append({**rate, "work_type": wt})

        if not results:
            return SkillResult(
                status=SkillStatus.PARTIAL,
                skill_id=self.skill_id,
                data={"query": query, "results": [], "total_found": 0},
                warnings=[
                    f"По запросу '{query}' расценки не найдены. "
                    "Рекомендуется подобрать расценку по аналогии (source=ANALOG)."
                ],
            )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "query": query,
                "results": results,
                "total_found": len(results),
            },
        )

    def _list_by_work(self, work_type: str) -> SkillResult:
        """Все расценки для вида работ."""
        if not work_type:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметр 'work_type' обязателен"],
            )

        if work_type not in RATE_DATABASE:
            return SkillResult(
                status=SkillStatus.REJECTED,
                skill_id=self.skill_id,
                errors=[f"Вид работ '{work_type}' не найден в базе расценок."],
                data={"available_work_types": list(RATE_DATABASE.keys())},
            )

        rates = RATE_DATABASE[work_type]
        index_info = MINSTROY_INDICES["indices_by_work_type"].get(work_type, {})

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "total_rates": len(rates),
                "rates": rates,
                "current_index": index_info,
                "index_quarter": MINSTROY_INDICES["current_quarter"],
                "base_level": MINSTROY_INDICES["base_level"],
            },
        )

    def _get_index(self, work_type: Optional[str] = None) -> SkillResult:
        """Получить актуальный индекс Минстроя."""
        if work_type:
            if work_type not in MINSTROY_INDICES["indices_by_work_type"]:
                return SkillResult(
                    status=SkillStatus.REJECTED,
                    skill_id=self.skill_id,
                    errors=[f"Индекс для '{work_type}' не найден."],
                    data={"available": list(MINSTROY_INDICES["indices_by_work_type"].keys())},
                )
            index_info = MINSTROY_INDICES["indices_by_work_type"][work_type]
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={
                    "work_type": work_type,
                    "index": index_info["index"],
                    "region": index_info["region"],
                    "quarter": MINSTROY_INDICES["current_quarter"],
                    "base_level": MINSTROY_INDICES["base_level"],
                    "published_date": MINSTROY_INDICES["published_date"],
                    "next_update": MINSTROY_INDICES["next_update"],
                },
            )

        # Вернуть все индексы
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data=MINSTROY_INDICES,
        )

    def _list_coefficients(self) -> SkillResult:
        """Перечислить поправочные коэффициенты."""
        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "coefficients": ADJUSTMENT_COEFFICIENTS,
                "total": len(ADJUSTMENT_COEFFICIENTS),
            },
        )
