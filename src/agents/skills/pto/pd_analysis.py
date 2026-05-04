"""
MAC_ASD v13.0 — PTO PD Analysis Skill.

Комплексный анализ проектной документации:
  1. Пространственные коллизии (rule-based) — пересечения осей/отметок
  2. Проверка комплектности разделов по ГОСТ Р 21.1101-2013
  3. Семантический анализ через LLM — поиск противоречий в тексте

Покрывает Этапы 5 (XRef) и частично 6 (визуальный анализ) восьмиэтапной
экспертизы ПСД.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus

logger = logging.getLogger(__name__)


# ГОСТ Р 21.1101-2013: обязательные разделы проектной документации
REQUIRED_PD_SECTIONS = {
    "АР": "Архитектурные решения",
    "КР": "Конструктивные и объёмно-планировочные решения",
    "ИОС1": "Система электроснабжения",
    "ИОС2": "Система водоснабжения",
    "ИОС3": "Система водоотведения",
    "ИОС4": "Отопление, вентиляция и кондиционирование",
    "ИОС5": "Сети связи",
    "ПОС": "Проект организации строительства",
    "ПМ": "Проект мероприятий по обеспечению доступа инвалидов",
}

# Patterns for spatial collision detection
AXIS_PATTERN = re.compile(r"(?:ос[ьи]|в\s+осях)\s+([А-Я0-9/\-\s]+)", re.IGNORECASE)
ELEVATION_PATTERN = re.compile(r"(?:отм[\.\s]*)\s*([+\-]?\d+[.,]\d{3})", re.IGNORECASE)
PAIRED_DIM_PATTERN = re.compile(r"(\d+)\s*(?:х|x|×)\s*(\d+)\s*(мм|см|м|m)", re.IGNORECASE)
SINGLE_DIM_PATTERN = re.compile(
    r"(?:толщин[аой]|диаметр|ширин[аой]|высот[аой]|глубин[аой]|сечение|размер|габарит)\D*(\d+)\s*(мм|см|м)",
    re.IGNORECASE,
)
GENERIC_DIM_PATTERN = re.compile(r"(\d{2,4})\s*(мм)\b", re.IGNORECASE)
XREF_PATTERN = re.compile(
    r"(?:см\.|смотри|ссылка|по)\s*(?:лист|раздел|чертёж|л\.)?\s*([А-Я]+[\s\-.]*\d+)",
    re.IGNORECASE,
)


class PTO_PDAnalysis(SkillBase):
    """
    Навык ПТО: комплексный анализ проектной документации.

    Выполняет три стадии анализа:
      1. Rule-based: пространственные коллизии между разделами
      2. Комплектность: проверка наличия обязательных разделов ПД
      3. LLM: семантический поиск противоречий в тексте разделов
    """

    skill_id = "PTO_PDAnalysis"
    description = "Комплексный анализ проектной документации на коллизии и комплектность"
    agent = "pto"

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sections = params.get("sections")
        if not sections:
            return {"valid": False, "errors": ["Параметр 'sections' обязателен"]}
        if not isinstance(sections, list):
            return {"valid": False, "errors": ["'sections' должен быть списком"]}
        for i, sec in enumerate(sections):
            if not isinstance(sec, dict):
                return {"valid": False, "errors": [f"sections[{i}] должен быть словарём"]}
            if "code" not in sec and "name" not in sec:
                return {"valid": False, "errors": [f"sections[{i}]: требуется 'code' или 'name'"]}
        return {"valid": True}

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        sections = params["sections"]
        check_spatial = params.get("check_collisions", True)
        check_completeness_flag = params.get("check_completeness", True)
        check_semantic = params.get("check_semantic", False)
        enable_llm = params.get("enable_llm", self._llm is not None)

        # Normalize sections
        normalized = self._normalize_sections(sections)

        collisions: List[Dict[str, Any]] = []
        completeness: Dict[str, Any] = {}
        llm_used = False

        # Stage 1: Spatial collision detection
        if check_spatial:
            spatial = self._check_spatial_collisions(normalized)
            collisions.extend(spatial)

        # Stage 2: Completeness check
        if check_completeness_flag:
            completeness = self._check_completeness(normalized)
            for missing_code in completeness.get("missing", []):
                collisions.append({
                    "type": "completeness",
                    "severity": "high",
                    "section_a": missing_code,
                    "section_b": "",
                    "description": f"Отсутствует обязательный раздел ПД: {missing_code}",
                    "gost_ref": "ГОСТ Р 21.1101-2013",
                })

        # Stage 3: Semantic analysis (LLM)
        if check_semantic and enable_llm:
            try:
                semantic = await self._analyze_semantic_collisions(normalized)
                collisions.extend(semantic)
                llm_used = True
            except Exception as e:
                logger.warning("LLM semantic analysis failed: %s", e)

        # Compute severity counts
        critical = [c for c in collisions if c.get("severity") == "critical"]
        high = [c for c in collisions if c.get("severity") == "high"]
        medium = [c for c in collisions if c.get("severity") == "medium"]
        low = [c for c in collisions if c.get("severity") == "low"]

        return SkillResult(
            status=SkillStatus.SUCCESS if not critical else SkillStatus.PARTIAL,
            skill_id=self.skill_id,
            data={
                "sections_analyzed": len(normalized),
                "collisions": collisions,
                "completeness": completeness,
                "llm_used": llm_used,
                "summary": {
                    "total_collisions": len(collisions),
                    "critical": len(critical),
                    "high": len(high),
                    "medium": len(medium),
                    "low": len(low),
                },
            },
        )

    # ── Normalization ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize section dicts to uniform shape."""
        out = []
        for sec in sections:
            out.append({
                "code": str(sec.get("code", sec.get("section_code", ""))).upper(),
                "name": str(sec.get("name", sec.get("section_name", sec.get("code", "")))),
                "content": str(sec.get("content", sec.get("text", ""))),
                "key_positions": sec.get("key_positions", []) or [],
            })
        return out

    # ── Stage 1: Spatial Collisions ───────────────────────────────────────

    def _check_spatial_collisions(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect spatial collisions: incompatible dimensions, axis overlaps,
        conflicting elevation marks across sections.
        """
        collisions = []

        # Extract structured data per section
        sec_data: Dict[str, Dict[str, Any]] = {}
        for sec in sections:
            code = sec["code"]
            content = sec["content"]
            key_pos = sec["key_positions"]

            # Parse from text content
            axes = set()
            elevations = set()
            dimensions = set()  # (value, unit) single measurements

            for match in AXIS_PATTERN.finditer(content):
                axes.add(match.group(1).strip())
            for match in ELEVATION_PATTERN.finditer(content):
                elevations.add(match.group(1).strip().replace(",", "."))
            for match in PAIRED_DIM_PATTERN.finditer(content):
                unit = match.group(3) or "мм"
                dimensions.add((int(match.group(1)), unit))
                dimensions.add((int(match.group(2)), unit))
            for match in SINGLE_DIM_PATTERN.finditer(content):
                dimensions.add((int(match.group(1)), match.group(2)))
            for match in GENERIC_DIM_PATTERN.finditer(content):
                dimensions.add((int(match.group(1)), match.group(2)))
            # Merge with key_positions
            for kp in key_pos:
                kp_str = str(kp)
                for m in AXIS_PATTERN.finditer(kp_str):
                    axes.add(m.group(1).strip())
                for m in ELEVATION_PATTERN.finditer(kp_str):
                    elevations.add(m.group(1).strip().replace(",", "."))
                for m in PAIRED_DIM_PATTERN.finditer(kp_str):
                    unit = m.group(3) or "мм"
                    dimensions.add((int(m.group(1)), unit))
                    dimensions.add((int(m.group(2)), unit))
                for m in SINGLE_DIM_PATTERN.finditer(kp_str):
                    dimensions.add((int(m.group(1)), m.group(2)))
                for m in GENERIC_DIM_PATTERN.finditer(kp_str):
                    dimensions.add((int(m.group(1)), m.group(2)))

            sec_data[code] = {"axes": axes, "elevations": elevations, "dimensions": dimensions}

        # Cross-compare sections
        codes = list(sec_data.keys())
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                ci, cj = codes[i], codes[j]
                di, dj = sec_data[ci], sec_data[cj]

                # Compare dimensions with same axis context
                common_axes = di["axes"] & dj["axes"]
                if common_axes and di["dimensions"] and dj["dimensions"]:
                    for val_i, unit_i in di["dimensions"]:
                        for val_j, unit_j in dj["dimensions"]:
                            # Only compare same units
                            if unit_i != unit_j:
                                continue
                            # Flag if dimensions diverge > 30% at same axis
                            if val_i > 0 and val_j > 0:
                                diff_pct = abs(val_i - val_j) / max(val_i, val_j) * 100
                                if diff_pct > 30:
                                    collisions.append({
                                        "type": "spatial",
                                        "severity": "high",
                                        "section_a": ci,
                                        "section_b": cj,
                                        "description": (
                                            f"Возможная коллизия размеров: {ci} → {val_i}{unit_i}, "
                                            f"{cj} → {val_j}{unit_i} в осях {common_axes}"
                                        ),
                                        "gost_ref": "ГОСТ Р 21.1101-2013 п. 4.2",
                                    })

                # Compare elevation marks
                common_elev = di["elevations"] & dj["elevations"]
                # Just flag that two sections reference the same elevation
                # — worth manual review for consistency
                if len(common_elev) >= 3:
                    collisions.append({
                        "type": "spatial",
                        "severity": "low",
                        "section_a": ci,
                        "section_b": cj,
                        "description": (
                            f"{len(common_elev)} общих высотных отметок между "
                            f"{ci} и {cj} — проверьте согласованность"
                        ),
                        "gost_ref": "ГОСТ Р 21.1101-2013",
                    })

        # Cross-reference check: references to non-existent sections
        for sec in sections:
            for match in XREF_PATTERN.finditer(sec["content"]):
                ref_code = match.group(1).upper().strip()
                # Check if referenced section code exists
                if ref_code and len(ref_code) >= 2:
                    found = any(
                        ref_code.startswith(s["code"]) or s["code"].startswith(ref_code)
                        for s in sections
                    )
                    if not found:
                        collisions.append({
                            "type": "xref",
                            "severity": "medium",
                            "section_a": sec["code"],
                            "section_b": ref_code,
                            "description": (
                                f"Ссылка на отсутствующий раздел: {sec['code']} "
                                f"ссылается на {ref_code}"
                            ),
                            "gost_ref": "ГОСТ Р 21.1101-2013 п. 4.1",
                        })

        return collisions

    # ── Stage 2: Completeness Check ───────────────────────────────────────

    @staticmethod
    def _check_completeness(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check section completeness per GOST R 21.1101-2013.
        """
        present_codes = {sec["code"] for sec in sections}

        # Try to match present codes against required sections
        matched = set()
        for req_code in REQUIRED_PD_SECTIONS:
            for pc in present_codes:
                if req_code in pc or pc in req_code:
                    matched.add(req_code)

        missing = set(REQUIRED_PD_SECTIONS.keys()) - matched
        extra = present_codes - {
            req for req in REQUIRED_PD_SECTIONS
            for pc in present_codes
            if req in pc or pc in req
        }

        return {
            "required_sections": {
                code: REQUIRED_PD_SECTIONS[code]
                for code in REQUIRED_PD_SECTIONS
            },
            "present": sorted(matched),
            "missing": sorted(missing),
            "extra": sorted(extra),
            "completeness_pct": round(
                len(matched) / max(len(REQUIRED_PD_SECTIONS), 1) * 100, 1
            ),
            "required_by": "ГОСТ Р 21.1101-2013",
        }

    # ── Stage 3: LLM Semantic Analysis ────────────────────────────────────

    async def _analyze_semantic_collisions(
        self, sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to find semantic contradictions between PD sections.
        Falls back to keyword-based check if LLM unavailable.
        """
        if not self._llm:
            return self._keyword_semantic_check(sections)

        # Build prompt
        section_summaries = []
        for sec in sections:
            content = sec["content"][:2000]
            section_summaries.append(
                f"### {sec['code']} — {sec['name']}\n"
                f"Текст: {content}\n"
            )

        prompt = (
            "Проанализируй разделы проектной документации на наличие "
            "противоречий и коллизий.\n\n"
            + "\n---\n".join(section_summaries)
            + "\n\nНайди противоречия между разделами. Примеры:\n"
            "- АР говорит «стены 200 мм», а КР показывает «стены 250 мм»\n"
            "- В ИОС2 указан расход 10 л/с, а в ИОС3 — 15 л/с для того же узла\n"
            "- ПОС предполагает кран Q=25т, а КР требует монтаж элементов по 30т\n\n"
            "Верни СТРОГО JSON без markdown:\n"
            '{"collisions": [{"section_a": "АР", "section_b": "КР", '
            '"description": "...", "severity": "high|medium|low"}]}'
        )

        response = await self._llm.safe_chat(
            self.agent,
            [{"role": "user", "content": prompt}],
            fallback_response='{"collisions": []}',
            temperature=0.1,
        )

        try:
            data = self._parse_json_response(response)
            return data.get("collisions", [])
        except Exception:
            return self._keyword_semantic_check(sections)

    def _keyword_semantic_check(
        self, sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Keyword-based fallback: detect sections mentioning same material/equipment
        with potentially conflicting specifications.
        """
        collisions = []

        # Look for numeric specs (NNN mm/cm/m) and compare across sections
        spec_pattern = re.compile(
            r"(?:толщин[аой]|диаметр|ширин[аой]|высот[аой]|глубин[аой]|сечение)\s*(\d+)\s*(мм|см|м)",
            re.IGNORECASE,
        )

        for i in range(len(sections)):
            for j in range(i + 1, len(sections)):
                si = sections[i]
                sj = sections[j]
                specs_i = [(int(m.group(1)), m.group(2)) for m in spec_pattern.finditer(si["content"])]
                specs_j = [(int(m.group(1)), m.group(2)) for m in spec_pattern.finditer(sj["content"])]

                # If same unit and value differs > 30%, flag
                for val_i, unit_i in specs_i:
                    for val_j, unit_j in specs_j:
                        if unit_i == unit_j and val_i > 0 and val_j > 0:
                            diff = abs(val_i - val_j) / max(val_i, val_j) * 100
                            if diff > 30:
                                collisions.append({
                                    "type": "semantic",
                                    "severity": "medium",
                                    "section_a": si["code"],
                                    "section_b": sj["code"],
                                    "description": (
                                        f"Возможное расхождение размеров: "
                                        f"{val_i}{unit_i} ({si['code']}) vs "
                                        f"{val_j}{unit_j} ({sj['code']})"
                                    ),
                                    "gost_ref": "",
                                })

        return collisions[:10]  # Limit fallback results

    @staticmethod
    def _parse_json_response(text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, tolerant of markdown wrappers."""
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
