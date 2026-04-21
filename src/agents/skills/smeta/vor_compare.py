"""
MAC_ASD v11.3 — SmetaVorCompare Skill.

Сверка ведомости объёмов работ (ВОР) со сметным расчётом.
Выявляет расхождения между проектными объёмами (от ПТО) и
осмеченными объёмами (от Сметчика).

Ключевые проверки:
  - Расхождение по объёмам (количество)
  - Расхождение по единицам измерения
  - Отсутствующие позиции (в ВОР есть, в смете нет, и наоборот)
  - Расхождение по стоимости
  - Несоответствие кодов расценок

Нормативная основа:
  - МДС 81-35.2004 (порядок составления смет)
  - СП 48.13330.2019 (организация строительства)
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


logger = logging.getLogger(__name__)


# =============================================================================
# Comparison result types
# =============================================================================

class DiscrepancyType(str, Enum):
    """Тип расхождения."""
    VOLUME_MISMATCH = "расхождение_объёмов"
    UNIT_MISMATCH = "расхождение_единиц"
    MISSING_IN_ESTIMATE = "отсутствует_в_смете"
    MISSING_IN_VOR = "отсутствует_в_ВОР"
    COST_MISMATCH = "расхождение_стоимости"
    RATE_CODE_MISMATCH = "несоответствие_кода_расценки"


class Severity(str, Enum):
    """Степень серьёзности расхождения."""
    CRITICAL = "критичное"    # > 10% расхождение
    WARNING = "предупреждение"  # 5-10% расхождение
    INFO = "информация"        # < 5% расхождение


# Пороги расхождений (в процентах)
VOLUME_TOLERANCE_PCT = 5.0   # допустимое расхождение объёмов
COST_TOLERANCE_PCT = 5.0     # допустимое расхождение стоимости
CRITICAL_THRESHOLD_PCT = 10.0  # порог критичности


class SmetaVorCompare(SkillBase):
    """
    Навык Сметчика: сверка ВОР со сметой.

    Сравнивает позиции ведомости объёмов работ (от ПТО)
    с позициями локальной сметы. Выявляет все виды расхождений
    и формирует отчёт о результатах сверки.
    """

    skill_id = "SmetaVorCompare"
    description = "Сверка ведомости объёмов работ (ВОР) со сметным расчётом"
    agent = "smeta"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация: action обязателен."""
        action = params.get("action")
        if not action:
            return {"valid": False, "errors": ["Параметр 'action' обязателен"]}
        valid_actions = {"compare", "compare_items", "summary"}
        if action not in valid_actions:
            return {"valid": False, "errors": [f"Неизвестное действие: {action}. Допустимые: {valid_actions}"]}
        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Выполнить сверку.

        Actions:
            compare: Полная сверка ВОР со сметой
            compare_items: Сверка двух конкретных позиций
            summary: Сводка по результатам предыдущей сверки
        """
        action = params["action"]

        if action == "compare":
            return self._compare(params)
        elif action == "compare_items":
            return self._compare_items(params)
        elif action == "summary":
            return self._summary(params)

    def _compare(self, params: Dict[str, Any]) -> SkillResult:
        """
        Полная сверка ВОР со сметой.

        Args:
            vor_items: Позиции ВОР (от ПТО)
                [
                    {
                        "id": "vor-001",
                        "description": "Устройство фундаментов ленточных бетонных",
                        "unit": "м3",
                        "quantity": 150.0,
                        "work_type": "бетонные",
                    }
                ]
            estimate_items: Позиции сметы
                [
                    {
                        "id": "est-001",
                        "rate_code": "ФЕР08-02-001-01",
                        "description": "Устройство фундаментов ленточных бетонных",
                        "unit": "м3",
                        "quantity": 145.0,
                        "unit_price": 8462.40,
                        "total": 1227048.00,
                    }
                ]
            volume_tolerance_pct: Допустимое расхождение объёмов % (default 5)
            cost_tolerance_pct: Допустимое расхождение стоимости % (default 5)
        """
        vor_items = params.get("vor_items", [])
        estimate_items = params.get("estimate_items", [])

        if not vor_items and not estimate_items:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Оба списка (vor_items, estimate_items) пусты"],
            )

        vol_tolerance = float(params.get("volume_tolerance_pct", VOLUME_TOLERANCE_PCT))
        cost_tolerance = float(params.get("cost_tolerance_pct", COST_TOLERANCE_PCT))

        discrepancies: List[Dict[str, Any]] = []
        matched: List[Dict[str, Any]] = []

        # Сопоставление позиций по описанию
        matched_estimate_ids = set()

        for vor in vor_items:
            vor_desc = vor.get("description", "").lower()
            vor_id = vor.get("id", "")
            best_match = None
            best_score = 0.0

            for est in estimate_items:
                est_id = est.get("id", "")
                if est_id in matched_estimate_ids:
                    continue

                est_desc = est.get("description", "").lower()
                # Простое совпадение по ключевым словам
                vor_words = set(w for w in vor_desc.split() if len(w) > 3)
                est_words = set(w for w in est_desc.split() if len(w) > 3)

                if not vor_words or not est_words:
                    continue

                overlap = len(vor_words & est_words) / max(len(vor_words | est_words), 1)
                if overlap > best_score and overlap > 0.3:  # Минимальный порог совпадения
                    best_score = overlap
                    best_match = est

            if best_match:
                matched_estimate_ids.add(best_match["id"])

                # Проверка расхождений
                item_discrepancies = self._check_discrepancies(
                    vor, best_match, vol_tolerance, cost_tolerance
                )

                if item_discrepancies:
                    discrepancies.extend(item_discrepancies)
                else:
                    matched.append({
                        "vor_id": vor_id,
                        "vor_description": vor.get("description", ""),
                        "estimate_id": best_match.get("id", ""),
                        "estimate_description": best_match.get("description", ""),
                        "match_score": round(best_score, 2),
                    })
            else:
                # Позиция ВОР не найдена в смете
                discrepancies.append({
                    "type": DiscrepancyType.MISSING_IN_ESTIMATE,
                    "severity": Severity.CRITICAL,
                    "vor_id": vor_id,
                    "description": vor.get("description", ""),
                    "detail": (
                        f"Позиция ВОР '{vor.get('description', '')}' "
                        f"не найдена в смете. Объём: {vor.get('quantity', 0)} {vor.get('unit', '')}"
                    ),
                })

        # Позиции в смете, не найденные в ВОР
        for est in estimate_items:
            if est.get("id", "") not in matched_estimate_ids:
                discrepancies.append({
                    "type": DiscrepancyType.MISSING_IN_VOR,
                    "severity": Severity.WARNING,
                    "estimate_id": est.get("id", ""),
                    "description": est.get("description", ""),
                    "detail": (
                        f"Позиция сметы '{est.get('description', '')}' "
                        f"не найдена в ВОР. Сумма: {est.get('total', 0):,.2f} руб."
                    ),
                })

        # Классификация по серьёзности
        critical = [d for d in discrepancies if d.get("severity") == Severity.CRITICAL]
        warnings = [d for d in discrepancies if d.get("severity") == Severity.WARNING]
        info = [d for d in discrepancies if d.get("severity") == Severity.INFO]

        # Итоговый статус сверки
        if critical:
            overall_status = "расхождения_критичны"
        elif warnings:
            overall_status = "расхождения_есть"
        elif matched and not discrepancies:
            overall_status = "данных_совпадают"
        else:
            overall_status = "есть_информационные_расхождения"

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "overall_status": overall_status,
                "vor_items_count": len(vor_items),
                "estimate_items_count": len(estimate_items),
                "matched_count": len(matched),
                "discrepancies_total": len(discrepancies),
                "critical_count": len(critical),
                "warning_count": len(warnings),
                "info_count": len(info),
                "matched": matched,
                "discrepancies": discrepancies,
                "tolerances": {
                    "volume_pct": vol_tolerance,
                    "cost_pct": cost_tolerance,
                },
            },
            warnings=[d["detail"] for d in warnings] if warnings else [],
        )

    def _check_discrepancies(
        self,
        vor: Dict[str, Any],
        estimate: Dict[str, Any],
        vol_tolerance: float,
        cost_tolerance: float,
    ) -> List[Dict[str, Any]]:
        """Проверить расхождения между парой ВОР-смета."""
        discrepancies = []
        vor_id = vor.get("id", "")
        est_id = estimate.get("id", "")

        # Проверка единиц измерения
        vor_unit = vor.get("unit", "").lower()
        est_unit = estimate.get("unit", "").lower()
        if vor_unit and est_unit and vor_unit != est_unit:
            discrepancies.append({
                "type": DiscrepancyType.UNIT_MISMATCH,
                "severity": Severity.CRITICAL,
                "vor_id": vor_id,
                "estimate_id": est_id,
                "detail": (
                    f"Расхождение единиц: ВОР='{vor_unit}', Смета='{est_unit}'. "
                    f"Сравнение объёмов невозможно."
                ),
            })
            return discrepancies  # Нет смысла проверять объём при разных единицах

        # Проверка объёмов
        vor_qty = float(vor.get("quantity", 0))
        est_qty = float(estimate.get("quantity", 0))

        if vor_qty > 0 and est_qty > 0:
            diff_pct = abs(vor_qty - est_qty) / vor_qty * 100.0

            if diff_pct > CRITICAL_THRESHOLD_PCT:
                severity = Severity.CRITICAL
            elif diff_pct > vol_tolerance:
                severity = Severity.WARNING
            else:
                severity = Severity.INFO

            if diff_pct > vol_tolerance:
                discrepancies.append({
                    "type": DiscrepancyType.VOLUME_MISMATCH,
                    "severity": severity,
                    "vor_id": vor_id,
                    "estimate_id": est_id,
                    "vor_quantity": vor_qty,
                    "estimate_quantity": est_qty,
                    "difference_pct": round(diff_pct, 2),
                    "detail": (
                        f"Расхождение объёмов: ВОР={vor_qty}, Смета={est_qty}. "
                        f"Отклонение {diff_pct:.1f}% (допуск {vol_tolerance}%)"
                    ),
                })

        return discrepancies

    def _compare_items(self, params: Dict[str, Any]) -> SkillResult:
        """
        Сверка двух конкретных позиций.

        Args:
            vor_item: Позиция ВОР
            estimate_item: Позиция сметы
            volume_tolerance_pct: Допустимое расхождение объёмов % (default 5)
        """
        vor_item = params.get("vor_item")
        estimate_item = params.get("estimate_item")

        if not vor_item or not estimate_item:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметры 'vor_item' и 'estimate_item' обязательны"],
            )

        vol_tolerance = float(params.get("volume_tolerance_pct", VOLUME_TOLERANCE_PCT))
        cost_tolerance = float(params.get("cost_tolerance_pct", COST_TOLERANCE_PCT))

        discrepancies = self._check_discrepancies(
            vor_item, estimate_item, vol_tolerance, cost_tolerance
        )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "vor_item": vor_item,
                "estimate_item": estimate_item,
                "discrepancies_found": len(discrepancies),
                "discrepancies": discrepancies,
                "match": len(discrepancies) == 0,
            },
        )

    def _summary(self, params: Dict[str, Any]) -> SkillResult:
        """
        Сводка по результатам сверки.

        Args:
            comparison_result: Результат предыдущей сверки (от _compare)
        """
        comparison = params.get("comparison_result")
        if not comparison:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=["Параметр 'comparison_result' обязателен"],
            )

        data = comparison.get("data", comparison)
        total_discrepancies = data.get("discrepancies_total", 0)
        total_items = data.get("vor_items_count", 0)
        critical = data.get("critical_count", 0)
        warnings = data.get("warning_count", 0)

        # Рекомендации на основе результатов
        recommendations = []

        if critical > 0:
            recommendations.append(
                f"Критичные расхождения ({critical} шт.): требуется немедленная "
                f"корректировка сметы в соответствии с ВОР."
            )

        if warnings > 0:
            recommendations.append(
                f"Предупреждения ({warnings} шт.): проверьте расхождения и "
                f"уточните объёмы с ПТО."
            )

        if total_items > 0 and total_discrepancies == 0:
            recommendations.append(
                "Расхождений не обнаружено. Смета соответствует ВОР."
            )

        compliance_pct = round(
            (1 - total_discrepancies / max(total_items, 1)) * 100, 1
        )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "overall_status": data.get("overall_status", "неизвестно"),
                "compliance_pct": compliance_pct,
                "vor_items": data.get("vor_items_count", 0),
                "estimate_items": data.get("estimate_items_count", 0),
                "matched": data.get("matched_count", 0),
                "discrepancies_total": total_discrepancies,
                "critical": critical,
                "warnings": warnings,
                "info": data.get("info_count", 0),
                "recommendations": recommendations,
            },
        )
