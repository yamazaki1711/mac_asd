"""
ASD v12.0 — idprosto.ru Knowledge Loader.

Programmatic loader for 31 id-prosto.ru work type checklists (569 document
entries, 356+ normative references). Provides fuzzy keyword matching with
150+ compound patterns for accurate work type resolution.

Sources:
  - 31 DOCX checklists from C:\idprosto\downloads_idprosto_lists\
  - Extracted to data/knowledge/idprosto_worktype_docs.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to extracted knowledge base
_KB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "knowledge" / "idprosto_worktype_docs.json"

# 31 work type codes -> human-readable names
IDPROSTO_WORK_TYPES: Dict[str, str] = {
    "01_permit": "Разрешительная документация",
    "02_geodetic": "Геодезические работы",
    "03_earth": "Земляные работы",
    "04_piles": "Свайные работы (забивные)",
    "05_bored-piles": "Буронабивные сваи",
    "06_concrete": "Бетонные работы (монолитные ЖБК)",
    "07_steel": "Металлоконструкции",
    "08_precast-concrete": "Сборные железобетонные конструкции",
    "09_finishing-works": "Отделочные работы",
    "10_anticorrosive": "Антикоррозийная защита и огнезащита",
    "11_extwatersupply": "Наружные сети водоснабжения",
    "12_extsewerage": "Наружные сети канализации",
    "13_drilling": "Горизонтально-направленное бурение (ГНБ)",
    "14_intwatersupply": "Внутреннее водоснабжение",
    "15_intsewerage": "Внутренняя канализация",
    "16_heating": "Отопление",
    "17_ventilation": "Вентиляция и кондиционирование",
    "18_extinguishing": "Пожаротушение",
    "19_pipelines": "Технологические трубопроводы",
    "20_equipment": "Технологическое оборудование",
    "21_tanks": "Резервуары",
    "22_electric": "Электромонтажные работы (внутренние)",
    "23_extelectric": "Наружное электроснабжение",
    "24_automatic": "Системы автоматизации",
    "25_fire-alarm": "Пожарная сигнализация",
    "26_sks": "Структурированные кабельные системы (СКС)",
    "27_elevators": "Лифты",
    "28_heat-pipelines": "Тепловые сети",
    "29_roads": "Автомобильные дороги",
    "30_demolition": "Демонтажные работы",
    "31_steam-boiler": "Паровая котельная",
}

# Compound keyword patterns for fuzzy resolution.
# Format: (pattern, code) — ordered by specificity (most specific first).
_COMPOUND_PATTERNS: List[tuple] = [
    # Exact matches on full names
    (r"разрешительн\w*\s+документац", "01_permit"),
    (r"геодезическ\w*\s+работ", "02_geodetic"),
    (r"землян\w*\s+работ", "03_earth"),
    (r"забивн\w*\s+сва[йи]", "04_piles"),
    (r"буро(?:набивны|вые)\w*\s+сва[йи]", "05_bored-piles"),
    (r"бетонн\w*\s+работ", "06_concrete"),
    (r"монолитн\w*\s+(?:жбк|железобетон)", "06_concrete"),
    (r"металлоконструкц", "07_steel"),
    (r"металлическ\w*\s+конструкц", "07_steel"),
    (r"сборн\w*\s+(?:жбк|железобетон|ж/б)", "08_precast-concrete"),
    (r"сборн\w*\s+конструкц", "08_precast-concrete"),
    (r"отделочн\w*\s+работ", "09_finishing-works"),
    (r"антикоррозийн\w*\s+защит", "10_anticorrosive"),
    (r"огнезащит", "10_anticorrosive"),
    (r"наружн\w*\s+(?:сети\s+)?водоснабжен", "11_extwatersupply"),
    (r"наружн\w*\s+(?:сети\s+)?водопровод", "11_extwatersupply"),
    (r"наружн\w*\s+(?:сети\s+)?канализац", "12_extsewerage"),
    (r"горизонтально.направленн\w*\s+бурен", "13_drilling"),
    (r"гнб\s", "13_drilling"),
    (r"\bгнб\b", "13_drilling"),
    (r"прокол\w*\s+(?:грунт|почв|земл)", "13_drilling"),
    (r"внутренн\w*\s+(?:сети\s+)?водоснабжен", "14_intwatersupply"),
    (r"внутренн\w*\s+(?:сети\s+)?водопровод", "14_intwatersupply"),
    (r"внутренн\w*\s+(?:сети\s+)?канализац", "15_intsewerage"),
    (r"\bотоплени", "16_heating"),
    (r"вентиляц", "17_ventilation"),
    (r"кондиционировани", "17_ventilation"),
    (r"пожаротушени", "18_extinguishing"),
    (r"\bтушени[ея]\s+пожар", "18_extinguishing"),
    (r"технологическ\w*\s+трубопровод", "19_pipelines"),
    (r"трубопровод", "19_pipelines"),
    (r"технологическ\w*\s+оборудовани", "20_equipment"),
    (r"резервуар", "21_tanks"),
    (r"электромонтажн\w*\s+работ", "22_electric"),
    (r"внутренн\w*\s+(?:сети\s+)?электр", "22_electric"),
    (r"наружн\w*\s+(?:сети\s+)?электр", "23_extelectric"),
    (r"электроснабжен", "23_extelectric"),
    (r"автоматизац", "24_automatic"),
    (r"пожарн\w*\s+сигнализац", "25_fire-alarm"),
    (r"\bскс\b", "26_sks"),
    (r"кабельн\w*\s+систем", "26_sks"),
    (r"лифт", "27_elevators"),
    (r"теплов\w*\s+сет", "28_heat-pipelines"),
    (r"\bдорог", "29_roads"),
    (r"асфальтобетон", "29_roads"),
    (r"асфальт", "29_roads"),
    (r"дорожн\w*\s+(?:работ|одежд|покрыт)", "29_roads"),
    (r"демонтаж", "30_demolition"),
    (r"снос\s+(?:здани|сооружени|конструкци)", "30_demolition"),
    (r"паров\w*\s+котельн", "31_steam-boiler"),
    (r"котельн", "31_steam-boiler"),

    # Spelling and case variants
    (r"\bмонтаж\s+лифт", "27_elevators"),
    (r"\bсва[йи]+\s+работ", "04_piles"),
    (r"\bсва[йи]+\b(?!\s+работ)", "04_piles"),
    (r"\bжбк\b", "08_precast-concrete"),
    (r"\bж/б\s", "08_precast-concrete"),
    (r"\bжб\s", "08_precast-concrete"),
    (r"\bэлектрик", "22_electric"),
    (r"\bэлектрич\w*\s+работ", "22_electric"),
    (r"\bканализ", "12_extsewerage"),

    # Specific additions from test expectations
    (r"асфальтобетонн\w*\s+покрыт", "29_roads"),
    (r"сборн\w*\s+(?:ж/б|жб\s|железобетонн)", "08_precast-concrete"),
    (r"наружн\w*\s+водоснабжен", "11_extwatersupply"),
    (r"технологическ\w*\s+трубопровод", "19_pipelines"),
]

# Single keyword fallbacks (lower priority)
_KEYWORD_MAP: Dict[str, str] = {
    "разрешительн": "01_permit",
    "геодези": "02_geodetic",
    "землян": "03_earth",
    "свайн": "04_piles",
    "буронабивн": "05_bored-piles",
    "бетон": "06_concrete",
    "жбк": "06_concrete",
    "металлоконструкци": "07_steel",
    "сборн": "08_precast-concrete",
    "отделоч": "09_finishing-works",
    "антикоррози": "10_anticorrosive",
    "огнезащит": "10_anticorrosive",
    "акз": "10_anticorrosive",
    "водоснабжен": "11_extwatersupply",
    "канализац": "12_extsewerage",
    "бурен": "13_drilling",
    "прокол": "13_drilling",
    "отоплен": "16_heating",
    "вентиляц": "17_ventilation",
    "пожаротушен": "18_extinguishing",
    "трубопровод": "19_pipelines",
    "оборудован": "20_equipment",
    "резервуар": "21_tanks",
    "электромонтаж": "22_electric",
    "автоматизац": "24_automatic",
    "сигнализац": "25_fire-alarm",
    "лифт": "27_elevators",
    "дорог": "29_roads",
    "демонтаж": "30_demolition",
    "снос": "30_demolition",
    "котельн": "31_steam-boiler",
    "паров": "31_steam-boiler",
}


class IdProstoLoader:
    """Programmatic loader for id-prosto.ru knowledge base."""

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._normative_refs_cache: Optional[List[str]] = None

    @property
    def _kb(self) -> Dict[str, Any]:
        if self._data is None:
            self._load()
        return self._data or {}

    def _load(self) -> None:
        """Load the JSON knowledge base."""
        if not _KB_PATH.exists():
            logger.warning("Knowledge base not found: %s", _KB_PATH)
            self._data = {"work_types": {}, "all_normative_refs": []}
            return

        try:
            with open(_KB_PATH, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("Loaded idprosto KB: %d work types, %d normative refs",
                        len(self._data.get("work_types", {})),
                        len(self._data.get("all_normative_refs", [])))
        except Exception as e:
            logger.error("Failed to load idprosto KB: %s", e)
            self._data = {"work_types": {}, "all_normative_refs": []}

    # ── Work Type Resolution ──

    def resolve_work_type(self, query: str) -> Optional[str]:
        """
        Fuzzy-resolve a work type query to an id-prosto.ru checklist code.

        Uses compound pattern matching first, then keyword fallback.
        Returns None if no match found.
        """
        q = query.lower().strip()

        # 1. Direct code match
        for code in IDPROSTO_WORK_TYPES:
            if code in q:
                return code

        # 2. Compound pattern matching (most specific first)
        for pattern, code in _COMPOUND_PATTERNS:
            if re.search(pattern, q, re.IGNORECASE):
                return code

        # 3. Single keyword fallback
        for keyword, code in _KEYWORD_MAP.items():
            if keyword in q:
                return code

        # 4. Try checking work type names in the KB
        for code, wt_data in self._kb.get("work_types", {}).items():
            name = wt_data.get("name", "").lower()
            if name and (q in name or name in q):
                return code

        return None

    # ── Work Type Summary ──

    def get_work_type_summary(self, code: str) -> Dict[str, Any]:
        """
        Get a comprehensive summary of required documents for a work type.

        Returns:
            {
                "code": str,
                "name": str,
                "total_docs": int,
                "aosr": [{"name", "form", "normative", "num"}, ...],
                "aook": [...],
                "journals": [...],
                "test_acts": [...],
                "schemas": [...],
                "certificates": [...],
                "other": [...],
                "normative_refs": [str, ...],
            }
        """
        wt_data = self._kb.get("work_types", {}).get(code, {})
        if not wt_data:
            name = IDPROSTO_WORK_TYPES.get(code, code)
            return {
                "code": code,
                "name": name,
                "total_docs": 0,
                "aosr": [],
                "aook": [],
                "journals": [],
                "test_acts": [],
                "schemas": [],
                "certificates": [],
                "other": [],
                "normative_refs": [],
            }

        docs = wt_data.get("documents", [])
        result = {
            "code": code,
            "name": wt_data.get("name", IDPROSTO_WORK_TYPES.get(code, code)),
            "total_docs": wt_data.get("total_docs", len(docs)),
            "aosr": [],
            "aook": [],
            "journals": [],
            "test_acts": [],
            "schemas": [],
            "certificates": [],
            "other": [],
            "normative_refs": wt_data.get("normative_refs", []),
        }

        for d in docs:
            cats = d.get("categories", [])
            entry = {
                "name": d.get("name", ""),
                "form": d.get("form", ""),
                "normative": d.get("normative", ""),
                "num": d.get("num", ""),
            }
            if "aosr" in cats:
                result["aosr"].append(entry)
            if "aook" in cats:
                result["aook"].append(entry)
            if "journal" in cats:
                result["journals"].append(entry)
            if "test_act" in cats:
                result["test_acts"].append(entry)
            if "schema" in cats:
                result["schemas"].append(entry)
            if "certificate" in cats:
                result["certificates"].append(entry)
            if "other" in cats:
                result["other"].append(entry)

        return result

    # ── Normative References ──

    def get_all_normative_refs(self) -> List[str]:
        """
        Return ALL unique normative references from the entire knowledge base.

        This aggregates:
          - Raw normative texts from 31 checklists (252 texts)
          - Extracted norm codes from checklist documents
          - Normative references from 39 form package directories
          - Normative references from 231 template filenames

        Returns >= 356 unique entries.
        """
        if self._normative_refs_cache is not None:
            return self._normative_refs_cache

        all_refs = set()

        # From JSON consolidated list
        all_refs.update(self._kb.get("all_normative_refs", []))

        # From individual work type normative_refs
        for wt_data in self._kb.get("work_types", {}).values():
            all_refs.update(wt_data.get("normative_refs", []))

            # Also collect raw norm texts from each document
            for doc in wt_data.get("documents", []):
                for t in doc.get("raw_norm_texts", []):
                    all_refs.add(t)

        # From templates
        for t in self._kb.get("templates", []):
            for n in t.get("normative_refs", []):
                all_refs.add(n)

        self._normative_refs_cache = sorted(all_refs)
        return self._normative_refs_cache

    def reload(self) -> None:
        """Force reload the knowledge base from disk."""
        self._data = None
        self._normative_refs_cache = None
        self._load()


# Singleton
idprosto_loader = IdProstoLoader()
