"""
MAC_ASD v12.0 — SmetaCalc Skill.

Расчёт локальной сметы. Выполняет полный расчёт стоимости:
  - Прямые затраты (ОТ + Материалы + ЭМ) с индексацией Минстроя
  - Накладные расходы (по МДС 81-33.2004)
  - Сметная прибыль (по МДС 81-25.2001)
  - НДС 20%
  - Поправочные коэффициенты

Формулы:
  ПЗ = ОТ * I_от + М * I_м + ЭМ * I_эм
  НР = ПЗ * НР%  (или от ФОТ по видам работ)
  СП = ПЗ * СП%  (или от ФОТ по видам работ)
  Итого = ПЗ + НР + СП
  НДС = Итого * 20%
  Всего = Итого + НДС

Нормативная база:
  - МДС 81-35.2004 (методика)
  - МДС 81-33.2004 (накладные расходы)
  - МДС 81-25.2001 (сметная прибыль)
  - НК РФ ст. 164 (НДС 20% с 01.01.2019)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Default parameters
# =============================================================================

DEFAULT_VAT_PCT = 20.0  # НДС с 01.01.2019


class SmetaCalc(SkillBase):
    """
    Навык Сметчика: расчёт локальной сметы.

    Выполняет полный расчёт стоимости работ по позициям:
      1. Расчёт прямых затрат с индексацией
      2. Начисление накладных расходов
      3. Начисление сметной прибыли
      4. Расчёт НДС
      5. Формирование итогов по разделам
    """

    skill_id = "SmetaCalc"
    description = "Расчёт локальной сметы (ПЗ + НР + СП + НДС)"
    agent = "smeta"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: action обязателен."""
        action = params.get("action")
        if not action:
            return {"valid": False, "errors": ["Параметр 'action' обязателен"]}
        valid_actions = {"calculate", "calculate_item", "apply_coefficient", "totals"}
        if action not in valid_actions:
            return {"valid": False, "errors": [f"Неизвестное действие: {action}. Допустимые: {valid_actions}"]}
        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Выполнить расчёт.

        Actions:
            calculate: Полный расчёт сметы по списку позиций
            calculate_item: Расчёт одной позиции
            apply_coefficient: Применить поправочный коэффициент
            totals: Подвести итоги по разделам
        """
        action = params["action"]

        if action == "calculate":
            return self._calculate(params)
        elif action == "calculate_item":
            return self._calculate_item(params)
        elif action == "apply_coefficient":
            return self._apply_coefficient(params)
        elif action == "totals":
            return self._totals(params)

    def _calculate_item(self, params: Dict[str, Any]) -> SkillResult:
        """
        Расчёт одной позиции сметы.

        Args:
            rate_code: Код расценки
            description: Описание работы
            unit: Единица измерения
            quantity: Количество (объём)
            unit_costs: {"labor": X, "materials": Y, "machinery": Z} — базисные затраты
            index: Индекс Минстроя (default 1.0)
            overhead_pct: % накладных расходов (default 12.0)
            profit_pct: % сметной прибыли (default 8.0)
            coefficient: Поправочный коэффициент (default 1.0)
        """
        required = ["rate_code", "description", "unit", "quantity", "unit_costs"]
        missing = [r for r in required if r not in params]
        if missing:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[f"Обязательные параметры отсутствуют: {missing}"],
            )

        unit_costs = params["unit_costs"]
        quantity = float(params["quantity"])
        index = float(params.get("index", 1.0))
        overhead_pct = float(params.get("overhead_pct", 12.0))
        profit_pct = float(params.get("profit_pct", 8.0))
        coefficient = float(params.get("coefficient", 1.0))
        vat_pct = float(params.get("vat_pct", DEFAULT_VAT_PCT))

        # Прямые затраты с индексацией
        labor_total = unit_costs.get("labor", 0.0) * quantity * index
        materials_total = unit_costs.get("materials", 0.0) * quantity * index
        machinery_total = unit_costs.get("machinery", 0.0) * quantity * index

        direct_costs = (labor_total + materials_total + machinery_total) * coefficient

        # Накладные расходы
        overhead = direct_costs * (overhead_pct / 100.0)

        # Сметная прибыль
        profit = direct_costs * (profit_pct / 100.0)

        # Итого без НДС
        subtotal = direct_costs + overhead + profit

        # НДС
        vat = subtotal * (vat_pct / 100.0)

        # Всего с НДС
        total_with_vat = subtotal + vat

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "item": {
                    "rate_code": params["rate_code"],
                    "description": params["description"],
                    "unit": params["unit"],
                    "quantity": quantity,
                },
                "base_costs_per_unit": unit_costs,
                "index_applied": index,
                "coefficient_applied": coefficient,
                "calculated": {
                    "labor": round(labor_total * coefficient, 2),
                    "materials": round(materials_total * coefficient, 2),
                    "machinery": round(machinery_total * coefficient, 2),
                    "direct_costs": round(direct_costs, 2),
                    "overhead": round(overhead, 2),
                    "overhead_pct": overhead_pct,
                    "profit": round(profit, 2),
                    "profit_pct": profit_pct,
                    "subtotal": round(subtotal, 2),
                    "vat": round(vat, 2),
                    "vat_pct": vat_pct,
                    "total_with_vat": round(total_with_vat, 2),
                },
            },
        )

    def _calculate(self, params: Dict[str, Any]) -> SkillResult:
        """
        Полный расчёт сметы по списку позиций.

        Args:
            project_id: Идентификатор проекта
            sections: Список разделов с позициями
                [
                    {
                        "section_name": "Раздел 1. Бетонные работы",
                        "items": [
                            {
                                "rate_code": "ФЕР...",
                                "description": "...",
                                "unit": "м3",
                                "quantity": 150.0,
                                "unit_costs": {"labor": X, "materials": Y, "machinery": Z},
                                "index": 1.0915,
                                "overhead_pct": 12.0,
                                "profit_pct": 8.0,
                            }
                        ]
                    }
                ]
            vat_pct: НДС % (default 20)
        """
        sections = params.get("sections", [])
        if not sections:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Список 'sections' пуст или отсутствует"],
            )

        vat_pct = float(params.get("vat_pct", DEFAULT_VAT_PCT))
        project_id = params.get("project_id", "unknown")

        calculated_sections = []
        grand_totals = {
            "direct_costs": 0.0,
            "overhead": 0.0,
            "profit": 0.0,
            "subtotal": 0.0,
            "vat": 0.0,
            "total_with_vat": 0.0,
        }
        warnings = []

        for section in sections:
            section_name = section.get("section_name", "Без названия")
            items = section.get("items", [])
            calculated_items = []
            section_totals = {
                "direct_costs": 0.0,
                "overhead": 0.0,
                "profit": 0.0,
                "subtotal": 0.0,
                "vat": 0.0,
                "total_with_vat": 0.0,
            }

            for item in items:
                # Расчёт каждой позиции
                item_result = self._calculate_item({
                    "rate_code": item.get("rate_code", "UNKNOWN"),
                    "description": item.get("description", ""),
                    "unit": item.get("unit", "шт"),
                    "quantity": item.get("quantity", 0),
                    "unit_costs": item.get("unit_costs", {}),
                    "index": item.get("index", 1.0),
                    "overhead_pct": item.get("overhead_pct", 12.0),
                    "profit_pct": item.get("profit_pct", 8.0),
                    "coefficient": item.get("coefficient", 1.0),
                    "vat_pct": vat_pct,
                })

                if item_result.is_success:
                    calc = item_result.data["calculated"]
                    calculated_items.append({
                        "rate_code": item.get("rate_code", "UNKNOWN"),
                        "description": item.get("description", ""),
                        "unit": item.get("unit", "шт"),
                        "quantity": item.get("quantity", 0),
                        "index_applied": item.get("index", 1.0),
                        "direct_costs": calc["direct_costs"],
                        "overhead": calc["overhead"],
                        "profit": calc["profit"],
                        "subtotal": calc["subtotal"],
                        "total_with_vat": calc["total_with_vat"],
                    })
                    for key in section_totals:
                        section_totals[key] += calc.get(key, 0.0)
                else:
                    warnings.append(
                        f"Ошибка расчёта позиции {item.get('rate_code', '???')}: "
                        f"{'; '.join(item_result.errors)}"
                    )

            # Округление итогов раздела
            for key in section_totals:
                section_totals[key] = round(section_totals[key], 2)

            calculated_sections.append({
                "section_name": section_name,
                "total_items": len(calculated_items),
                "items": calculated_items,
                "totals": section_totals,
            })

            # Суммирование в общие итоги
            for key in grand_totals:
                grand_totals[key] += section_totals[key]

        # Округление общих итогов
        for key in grand_totals:
            grand_totals[key] = round(grand_totals[key], 2)

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "project_id": project_id,
                "calculation_date": datetime.now().isoformat(),
                "base_level": "01.01.2024",
                "sections": calculated_sections,
                "total_sections": len(calculated_sections),
                "total_items": sum(s["total_items"] for s in calculated_sections),
                "grand_totals": grand_totals,
                "vat_pct": vat_pct,
            },
            warnings=warnings,
        )

    def _apply_coefficient(self, params: Dict[str, Any]) -> SkillResult:
        """
        Применить поправочный коэффициент к рассчитанной сумме.

        Args:
            amount: Исходная сумма
            coefficient: Коэффициент (например, 1.15 для зимнего удорожания)
            coefficient_name: Название коэффициента
            applies_to: К чему применяется ("direct_costs" | "labor" | "total")
        """
        amount = params.get("amount")
        coefficient = params.get("coefficient")

        if amount is None or coefficient is None:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметры 'amount' и 'coefficient' обязательны"],
            )

        amount = float(amount)
        coefficient = float(coefficient)
        applies_to = params.get("applies_to", "direct_costs")
        coefficient_name = params.get("coefficient_name", "Поправочный коэффициент")

        adjusted = round(amount * coefficient, 2)
        adjustment = round(adjusted - amount, 2)

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "original_amount": amount,
                "coefficient": coefficient,
                "coefficient_name": coefficient_name,
                "applies_to": applies_to,
                "adjusted_amount": adjusted,
                "adjustment": adjustment,
                "adjustment_pct": round((coefficient - 1.0) * 100, 2),
            },
        )

    def _totals(self, params: Dict[str, Any]) -> SkillResult:
        """
        Подвести итоги по предварительно рассчитанным разделам.

        Args:
            section_totals: Список итогов по разделам
                [{"direct_costs": X, "overhead": Y, "profit": Z, ...}]
            vat_pct: НДС % (default 20)
            additional_costs: Дополнительные затраты (временные здания, зимнее удорожание и т.п.)
                [{"name": "...", "amount": X, "applies_to": "subtotal"}]
        """
        section_totals = params.get("section_totals", [])
        if not section_totals:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Список 'section_totals' пуст"],
            )

        vat_pct = float(params.get("vat_pct", DEFAULT_VAT_PCT))
        additional_costs = params.get("additional_costs", [])

        # Суммирование итогов
        totals = {
            "direct_costs": 0.0,
            "overhead": 0.0,
            "profit": 0.0,
            "subtotal": 0.0,
        }

        for st in section_totals:
            for key in totals:
                totals[key] += float(st.get(key, 0.0))

        # Дополнительные затраты
        additional_total = 0.0
        additional_details = []

        for ac in additional_costs:
            ac_amount = float(ac.get("amount", 0.0))
            additional_total += ac_amount
            additional_details.append({
                "name": ac.get("name", "Неизвестно"),
                "amount": ac_amount,
                "applies_to": ac.get("applies_to", "subtotal"),
            })

        totals["subtotal"] = totals["direct_costs"] + totals["overhead"] + totals["profit"] + additional_total
        totals["vat"] = round(totals["subtotal"] * (vat_pct / 100.0), 2)
        totals["total_with_vat"] = round(totals["subtotal"] + totals["vat"], 2)
        totals["additional_costs"] = round(additional_total, 2)

        # Округление
        for key in totals:
            totals[key] = round(totals[key], 2)

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "totals": totals,
                "vat_pct": vat_pct,
                "additional_costs_detail": additional_details,
                "total_sections": len(section_totals),
            },
        )
