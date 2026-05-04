"""
MAC_ASD v13.0 — PTO VorCheck Skill.

Сверка ведомости объёмов работ (ВОР) с проектной документацией (ПД).
Выявляет расхождения по объёмам, единицам измерения, отсутствующие позиции.

Покрывает Этап 4 восьмиэтапной экспертизы ПСД (проверка спецификаций).
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus

logger = logging.getLogger(__name__)


class DiscrepancyType(str, Enum):
    VOLUME_MISMATCH = "volume_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    MISSING_IN_PD = "missing_in_pd"
    EXTRA_IN_VOR = "extra_in_vor"
    NAME_MISMATCH = "name_mismatch"


class Severity(str, Enum):
    CRITICAL = "critical"   # >10% volume diff
    HIGH = "high"           # unit mismatch or missing item
    MEDIUM = "medium"       # 5-10% volume diff
    LOW = "low"             # <5% volume diff


VOLUME_TOLERANCE_PCT = 5.0
CRITICAL_THRESHOLD_PCT = 10.0
FUZZY_MATCH_THRESHOLD = 55


class PTO_VorCheck(SkillBase):
    """
    Навык ПТО: сверка ведомости объёмов работ с проектной документацией.

    Сравнивает позиции ВОР с позициями ПД, выявляет:
      - Расхождения по объёмам
      - Несовпадение единиц измерения
      - Позиции ВОР, отсутствующие в ПД
      - Позиции ПД, неучтённые в ВОР
    """

    skill_id = "PTO_VorCheck"
    description = "Сверка ведомости объёмов работ (ВОР) с проектной документацией (ПД)"
    agent = "pto"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        vor_items = params.get("vor_items")
        pd_items = params.get("pd_items")

        if not vor_items and not pd_items:
            return {"valid": False, "errors": ["vor_items и pd_items не могут быть оба пустыми"]}

        if not isinstance(vor_items, list):
            return {"valid": False, "errors": ["vor_items должен быть списком"]}

        if not isinstance(pd_items, list):
            return {"valid": False, "errors": ["pd_items должен быть списком"]}

        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        vor_items = self._normalize_items(params.get("vor_items", []))
        pd_items = self._normalize_items(params.get("pd_items", []))
        tolerance = float(params.get("volume_tolerance_pct", VOLUME_TOLERANCE_PCT))

        if not vor_items:
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={
                    "total_vor_items": 0,
                    "total_pd_items": len(pd_items),
                    "matches": [],
                    "missing_in_pd": [],
                    "extra_in_vor": pd_items,
                    "discrepancies": [],
                    "summary": self._build_summary(0, 0, len(pd_items), [], []),
                },
                warnings=["ВОР не содержит позиций — проверьте входные данные"],
            )

        if not pd_items:
            return SkillResult(
                status=SkillStatus.SUCCESS,
                skill_id=self.skill_id,
                data={
                    "total_vor_items": len(vor_items),
                    "total_pd_items": 0,
                    "matches": [],
                    "missing_in_pd": vor_items,
                    "extra_in_vor": [],
                    "discrepancies": [],
                    "summary": self._build_summary(len(vor_items), 0, 0, [], []),
                },
                warnings=["ПД не содержит позиций — проверьте входные данные"],
            )

        # Fuzzy-match VOR items against PD items
        matches, unmatched_vor, unmatched_pd = self._match_items(
            vor_items, pd_items,
        )

        # Detect discrepancies within matched pairs
        discrepancies = []
        for m in matches:
            disc = self._check_match(m, tolerance)
            discrepancies.extend(disc)

        # Add missing/extra items as discrepancies
        for item in unmatched_vor:
            discrepancies.append({
                "type": DiscrepancyType.MISSING_IN_PD.value,
                "severity": Severity.HIGH.value,
                "vor_name": item["name"],
                "vor_quantity": item.get("quantity", 0),
                "vor_unit": item.get("unit", ""),
                "detail": f"Позиция ВОР «{item['name']}» не найдена в проектной документации",
            })

        for item in unmatched_pd:
            discrepancies.append({
                "type": DiscrepancyType.EXTRA_IN_VOR.value,
                "severity": Severity.MEDIUM.value,
                "pd_name": item["name"],
                "pd_quantity": item.get("quantity", 0),
                "pd_unit": item.get("unit", ""),
                "detail": f"Позиция ПД «{item['name']}» не учтена в ВОР",
            })

        critical = [d for d in discrepancies if d["severity"] == Severity.CRITICAL.value]
        high = [d for d in discrepancies if d["severity"] == Severity.HIGH.value]
        medium = [d for d in discrepancies if d["severity"] == Severity.MEDIUM.value]
        low = [d for d in discrepancies if d["severity"] == Severity.LOW.value]

        return SkillResult(
            status=SkillStatus.SUCCESS if not critical else SkillStatus.PARTIAL,
            skill_id=self.skill_id,
            data={
                "total_vor_items": len(vor_items),
                "total_pd_items": len(pd_items),
                "matches": matches,
                "missing_in_pd": unmatched_vor,
                "extra_in_vor": unmatched_pd,
                "discrepancies": discrepancies,
                "summary": self._build_summary(
                    len(matches), len(unmatched_vor), len(unmatched_pd),
                    critical, high, medium, low,
                ),
            },
        )

    # ── Item normalisation ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_items(items: List[Any]) -> List[Dict[str, Any]]:
        """Convert raw items to uniform {name, quantity, unit} dicts."""
        out = []
        for item in items:
            if isinstance(item, str):
                out.append({"name": item, "quantity": 0, "unit": ""})
            elif isinstance(item, dict):
                out.append({
                    "name": str(item.get("name", item.get("description", item.get("item", "")))),
                    "quantity": float(item.get("quantity", item.get("volume", item.get("amount", 0))) or 0),
                    "unit": str(item.get("unit", item.get("uom", ""))),
                })
        return out

    # ── Fuzzy matching ─────────────────────────────────────────────────────

    @staticmethod
    def _match_items(
        vor_items: List[Dict[str, Any]],
        pd_items: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Greedy fuzzy match: each VOR item against the best unmatched PD item.

        Returns (matches, unmatched_vor, unmatched_pd).
        """
        matches = []
        matched_pd_indices: set = set()

        def _scorer(a: str, b: str) -> float:
            """Token-sort fuzzy scorer with character n-gram fallback."""
            try:
                from rapidfuzz import fuzz
                return fuzz.token_sort_ratio(a, b)
            except ImportError:
                pass
            # Fallback: character trigram Jaccard (language-agnostic, handles morphology)
            def trigrams(s):
                s = s.lower()
                return {s[i:i+3] for i in range(len(s) - 2)}
            a_tri = trigrams(a)
            b_tri = trigrams(b)
            if not a_tri or not b_tri:
                return 0.0
            overlap = a_tri & b_tri
            return len(overlap) / max(len(a_tri), len(b_tri)) * 100

        for vor_idx, vor_item in enumerate(vor_items):
            vor_name = vor_item["name"]
            best_score = 0.0
            best_pd_idx = -1

            for pd_idx, pd_item in enumerate(pd_items):
                if pd_idx in matched_pd_indices:
                    continue
                score = _scorer(vor_name, pd_item["name"])
                if score > best_score:
                    best_score = score
                    best_pd_idx = pd_idx

            if best_score >= FUZZY_MATCH_THRESHOLD and best_pd_idx >= 0:
                matched_pd_indices.add(best_pd_idx)
                pd_item = pd_items[best_pd_idx]
                matches.append({
                    "vor_index": vor_idx,
                    "pd_index": best_pd_idx,
                    "vor_name": vor_name,
                    "pd_name": pd_item["name"],
                    "match_score": round(best_score, 1),
                    "vor_quantity": vor_item["quantity"],
                    "pd_quantity": pd_item["quantity"],
                    "vor_unit": vor_item["unit"],
                    "pd_unit": pd_item["unit"],
                })

        unmatched_vor = [
            item for i, item in enumerate(vor_items)
            if not any(m["vor_index"] == i for m in matches)
        ]
        unmatched_pd = [
            item for i, item in enumerate(pd_items)
            if i not in matched_pd_indices
        ]

        return matches, unmatched_vor, unmatched_pd

    # ── Discrepancy detection ──────────────────────────────────────────────

    @staticmethod
    def _check_match(match: Dict[str, Any], tolerance: float) -> List[Dict[str, Any]]:
        """Check one matched pair for volume/unit discrepancies."""
        discrepancies = []

        vor_qty = match.get("vor_quantity", 0) or 0
        pd_qty = match.get("pd_quantity", 0) or 0
        vor_unit = match.get("vor_unit", "")
        pd_unit = match.get("pd_unit", "")

        # Unit check
        if vor_unit and pd_unit and vor_unit.lower() != pd_unit.lower():
            discrepancies.append({
                "type": DiscrepancyType.UNIT_MISMATCH.value,
                "severity": Severity.HIGH.value,
                "vor_name": match["vor_name"],
                "pd_name": match["pd_name"],
                "vor_unit": vor_unit,
                "pd_unit": pd_unit,
                "detail": (
                    f"Несовпадение единиц измерения: "
                    f"ВОР → {vor_unit}, ПД → {pd_unit}"
                ),
            })
            return discrepancies  # Don't compare volumes if units differ

        # Volume check (only if both have non-zero quantities)
        if vor_qty > 0 and pd_qty > 0:
            diff_pct = abs(vor_qty - pd_qty) / pd_qty * 100

            if diff_pct > CRITICAL_THRESHOLD_PCT:
                severity = Severity.CRITICAL.value
            elif diff_pct > tolerance:
                severity = Severity.HIGH.value
            else:
                severity = Severity.LOW.value

            if diff_pct > 0.01:  # Only report measurable differences
                discrepancies.append({
                    "type": DiscrepancyType.VOLUME_MISMATCH.value,
                    "severity": severity,
                    "vor_name": match["vor_name"],
                    "pd_name": match["pd_name"],
                    "vor_quantity": vor_qty,
                    "pd_quantity": pd_qty,
                    "diff_abs": round(abs(vor_qty - pd_qty), 2),
                    "diff_pct": round(diff_pct, 1),
                    "detail": (
                        f"Расхождение объёмов {diff_pct:.1f}%: "
                        f"ВОР → {vor_qty} {vor_unit}, ПД → {pd_qty} {pd_unit}"
                    ),
                })

        return discrepancies

    # ── Summary ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(
        matched: int, missing: int, extra: int,
        critical=None, high=None, medium=None, low=None,
    ) -> Dict[str, Any]:
        critical = critical or []
        high = high or []
        medium = medium or []
        low = low or []
        return {
            "matched_items": matched,
            "missing_in_pd": missing,
            "extra_in_vor": extra,
            "total_discrepancies": len(critical) + len(high) + len(medium) + len(low),
            "critical": len(critical),
            "high": len(high),
            "medium": len(medium),
            "low": len(low),
        }
