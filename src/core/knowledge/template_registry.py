"""
ASD v12.0 — Template Registry.

Catalogues 149 DOCX (+ 82 XLSX) templates from 39 form packages
downloaded from id-prosto.ru. Provides form resolution by normative
reference and work type coverage analysis.

Data source: C:\idprosto\downloads_idprosto_forms\ (39 directories)
             C:\idprosto\downloads_idprosto_lists\ (31 checklists)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_KB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "knowledge" / "idprosto_worktype_docs.json"

# Maps normative reference keywords → form directory indices
# Each normative doc can contain multiple templates for different forms
_NORM_TO_PACKAGE: Dict[str, str] = {
    "344": "01_Приказ_Минстроя_344_пр",
    "344/пр": "01_Приказ_Минстроя_344_пр",
    "1026": "03_Приказ_Минстроя_1026_пр",
    "1026/пр": "03_Приказ_Минстроя_1026_пр",
    "рд-11-02": "02_РД-11-02-2006",
    "рд 11-02": "02_РД-11-02-2006",
    "рд-11-05": "04_РД-11-05-2007",
    "рд 11-05": "04_РД-11-05-2007",
    "сп 40-102": "05_СП_40-102-2000",
    "сп 42-101": "06_СП_42-101-2003",
    "сп 45.13330": "07_СП_45.13330.2017",
    "сп 48.13330": "08_СП_48.13330.2019",
    "сп 68.13330": "09_СП_68.13330.2017",
    "сп 70.13330": "10_СП_70.13330.2012",
    "сп 71.13330": "11_СП_71.13330.2017",
    "сп 72.13330": "12_СП_72.13330.2016",
    "сп 73.13330": "13_СП_73.13330.2016",
    "сп 74.13330": "14_СП_74.13330.2023",
    "сп 76.13330": "15_СП_76.13330.2016",
    "сп 77.13330": "16_СП_77.13330.2016",
    "сп 126.13330": "17_СП_126.13330.2017",
    "сп 129.13330": "18_СП_129.13330.2019",
    "сп 336.1325800": "19_СП_336.1325800.2017",
    "сп 341.1325800": "20_СП_341.1325800.2017",
    "сп 347.1325800": "21_СП_347.1325800.2017",
    "сп 365.1325800": "22_СП_365.1325800.2017",
    "сп 392.1325800": "23_СП_392.1325800.2018",
    "сп 399.1325800": "24_СП_399.1325800.2018",
    "сп 412.1325800": "25_СП_412.1325800.2018",
    "сп 520.1325800": "26_СП_520.1325800.2023",
    "сп 543.1325800": "27_СП_543.1325800.2024",
    "снип 42-01": "28_СНиП_42-01-2002",
    "гост 22845": "29_ГОСТ_22845-2018",
    "гост 23118": "30_ГОСТ_23118-2019",
    "гост 32569": "31_ГОСТ_32569-2013",
    "гост 59638": "32_ГОСТ_59638-2021",
    "гост 59639": "33_ГОСТ_59639-2021",
    "гост р 59492": "34_ГОСТ_Р_59492-2021",
    "всн 012": "35_ВСН_012-88_часть_II",
    "всн 478": "36_ВСН_478-86",
    "и 1.13": "37_И_1.13-07",
    "ростехнадзор": "38_Приказ_Ростехнадзора_от_16.01.2024_8",
    "рд 45.156": "39_РД_45.156-2000",
}

# Work type code → form package indices that contain templates for that work type
_WORK_TYPE_TO_PACKAGES: Dict[str, List[str]] = {
    "01_permit": ["01_Приказ_Минстроя_344_пр", "08_СП_48.13330.2019", "27_СП_543.1325800.2024"],
    "02_geodetic": ["17_СП_126.13330.2017", "01_Приказ_Минстроя_344_пр"],
    "03_earth": ["07_СП_45.13330.2017", "01_Приказ_Минстроя_344_пр", "23_СП_392.1325800.2018"],
    "04_piles": ["07_СП_45.13330.2017", "20_СП_341.1325800.2017", "01_Приказ_Минстроя_344_пр"],
    "05_bored-piles": ["07_СП_45.13330.2017", "20_СП_341.1325800.2017", "01_Приказ_Минстроя_344_пр"],
    "06_concrete": ["10_СП_70.13330.2012", "01_Приказ_Минстроя_344_пр", "03_Приказ_Минстроя_1026_пр",
                     "27_СП_543.1325800.2024"],
    "07_steel": ["09_СП_68.13330.2017", "30_ГОСТ_23118-2019", "01_Приказ_Минстроя_344_пр",
                  "10_СП_70.13330.2012"],
    "08_precast-concrete": ["10_СП_70.13330.2012", "01_Приказ_Минстроя_344_пр",
                             "27_СП_543.1325800.2024"],
    "09_finishing-works": ["11_СП_71.13330.2017", "01_Приказ_Минстроя_344_пр"],
    "10_anticorrosive": ["12_СП_72.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "11_extwatersupply": ["18_СП_129.13330.2019", "05_СП_40-102-2000", "01_Приказ_Минстроя_344_пр",
                           "03_Приказ_Минстроя_1026_пр"],
    "12_extsewerage": ["18_СП_129.13330.2019", "01_Приказ_Минстроя_344_пр"],
    "13_drilling": ["07_СП_45.13330.2017", "01_Приказ_Минстроя_344_пр"],
    "14_intwatersupply": ["13_СП_73.13330.2016", "05_СП_40-102-2000", "01_Приказ_Минстроя_344_пр"],
    "15_intsewerage": ["13_СП_73.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "16_heating": ["13_СП_73.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "17_ventilation": ["19_СП_336.1325800.2017", "13_СП_73.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "18_extinguishing": ["13_СП_73.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "19_pipelines": ["31_ГОСТ_32569-2013", "35_ВСН_012-88_часть_II", "01_Приказ_Минстроя_344_пр",
                      "03_Приказ_Минстроя_1026_пр", "23_СП_392.1325800.2018"],
    "20_equipment": ["36_ВСН_478-86", "01_Приказ_Минстроя_344_пр"],
    "21_tanks": ["22_СП_365.1325800.2017", "01_Приказ_Минстроя_344_пр"],
    "22_electric": ["15_СП_76.13330.2016", "01_Приказ_Минстроя_344_пр", "37_И_1.13-07"],
    "23_extelectric": ["15_СП_76.13330.2016", "37_И_1.13-07", "01_Приказ_Минстроя_344_пр"],
    "24_automatic": ["16_СП_77.13330.2016", "01_Приказ_Минстроя_344_пр"],
    "25_fire-alarm": ["32_ГОСТ_59638-2021", "01_Приказ_Минстроя_344_пр", "16_СП_77.13330.2016"],
    "26_sks": ["26_СП_520.1325800.2023", "39_РД_45.156-2000", "01_Приказ_Минстроя_344_пр"],
    "27_elevators": ["29_ГОСТ_22845-2018", "01_Приказ_Минстроя_344_пр", "38_Приказ_Ростехнадзора_от_16.01.2024_8"],
    "28_heat-pipelines": ["14_СП_74.13330.2023", "01_Приказ_Минстроя_344_пр", "03_Приказ_Минстроя_1026_пр"],
    "29_roads": ["24_СП_399.1325800.2018", "01_Приказ_Минстроя_344_пр", "03_Приказ_Минстроя_1026_пр"],
    "30_demolition": ["25_СП_412.1325800.2018", "01_Приказ_Минстроя_344_пр"],
    "31_steam-boiler": ["06_СП_42-101-2003", "38_Приказ_Ростехнадзора_от_16.01.2024_8",
                         "01_Приказ_Минстроя_344_пр", "03_Приказ_Минстроя_1026_пр"],
}


def _match_norm_package(norm_ref: str) -> Optional[str]:
    """Find the form package directory name matching a normative reference."""
    q = norm_ref.lower().replace(" ", "").replace("_", "")

    for key, pkg in _NORM_TO_PACKAGE.items():
        if key.lower().replace(" ", "").replace("_", "") in q:
            return pkg
    return None


class TemplateRegistry:
    """Registry of DOCX/XLSX templates from id-prosto.ru form packages."""

    def __init__(self):
        self._data: Optional[Dict[str, Any]] = None
        self._forms_cache: Optional[Dict[str, List[Dict]]] = None

    @property
    def _kb(self) -> Dict[str, Any]:
        if self._data is None:
            self._load()
        return self._data or {}

    def _load(self) -> None:
        if _KB_PATH.exists():
            try:
                with open(_KB_PATH, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.error("Failed to load KB: %s", e)
                self._data = {}
        else:
            self._data = {}

    # ── Template Listing ──

    def list_templates(self) -> List[Dict[str, Any]]:
        """List ALL templates (149 DOCX + 82 XLSX)."""
        return self._kb.get("templates", [])

    # ── Form Resolution ──

    def resolve_form(self, normative_ref: str) -> List[Dict[str, Any]]:
        """
        Find DOCX/XLSX templates matching a normative reference.

        Args:
            normative_ref: e.g. "Приказ Минстроя №344/пр, приложение 3"

        Returns:
            List of matching template dicts with file_name, full_path, etc.
        """
        pkg = _match_norm_package(normative_ref)
        if not pkg:
            return []

        pkg_norm = pkg.lower().replace("_", " ")
        results = []

        for t in self._kb.get("templates", []):
            reg_dir = t.get("regulation_dir", "").lower().replace("_", " ")
            if pkg_norm in reg_dir:
                results.append({
                    "file_name": t.get("file_name", ""),
                    "full_path": t.get("full_path", ""),
                    "extension": t.get("extension", ""),
                    "regulation_package": t.get("regulation_package", ""),
                    "regulation_dir": t.get("regulation_dir", ""),
                    "normative_refs": t.get("normative_refs", []),
                })

        return results

    # ── Work Type Form Coverage ──

    def get_forms_for_work_type(self, code: str) -> List[Dict[str, Any]]:
        """
        Get all required forms for a work type and whether we have DOCX templates.

        Returns:
            [{
                "doc_name": str,
                "form_ref": str,
                "has_template": bool,
                "templates": [{"file_name", "full_path", ...}],
            }]
        """
        wt_data = self._kb.get("work_types", {}).get(code, {})
        if not wt_data:
            return []

        all_templates = self._kb.get("templates", [])
        packages = _WORK_TYPE_TO_PACKAGES.get(code, [])

        forms = []
        for doc in wt_data.get("documents", []):
            form_ref = doc.get("form", "")
            norm_text = doc.get("normative", "")
            doc_name = doc.get("name", "")

            # Find matching templates
            matching = []
            if form_ref or norm_text:
                # First try to find templates by matching form reference
                form_keywords = re.findall(r'[а-яА-Яa-zA-Z]+', (form_ref + " " + doc_name).lower())
                norm_keywords = re.findall(r'[а-яА-Яa-zA-Z0-9]+', norm_text.lower())

                for t in all_templates:
                    t_name = t.get("file_name", "").lower()
                    t_dir = t.get("regulation_dir", "").lower()

                    # Check if template dir matches any of our packages
                    in_package = any(
                        pkg.lower().replace("_", " ") in t_dir.replace("_", " ")
                        for pkg in packages
                    )

                    if in_package:
                        # Check if template matches the form content
                        fname_no_num = re.sub(r'^\d+[_.-]', '', t_name)
                        score = 0
                        for kw in form_keywords[:3]:
                            if len(kw) >= 3 and kw in fname_no_num:
                                score += 1
                        for kw in norm_keywords[:3]:
                            if len(kw) >= 3 and kw in t_dir + t_name:
                                score += 1

                        if score >= 1:
                            matching.append({
                                "file_name": t.get("file_name", ""),
                                "full_path": t.get("full_path", ""),
                                "regulation": t.get("regulation_package", ""),
                            })
                        elif any(kw in t_name for kw in form_keywords if len(kw) >= 4):
                            matching.append({
                                "file_name": t.get("file_name", ""),
                                "full_path": t.get("full_path", ""),
                                "regulation": t.get("regulation_package", ""),
                            })

            forms.append({
                "doc_name": doc_name,
                "form_ref": form_ref,
                "normative": norm_text,
                "has_template": len(matching) > 0,
                "templates": matching,
                "num_templates": len(matching),
            })

        return forms

    # ── Coverage Report ──

    def template_coverage_report(self) -> Dict[str, Any]:
        """
        Generate coverage report: how many required forms have templates.

        Returns:
            {
                "work_types_analyzed": 31,
                "total_forms_required": int,
                "forms_with_templates": int,
                "coverage_pct": float,
                "by_work_type": {code: {"required": int, "covered": int, "pct": float}},
            }
        """
        total_required = 0
        total_covered = 0
        by_work_type = {}

        for code in self._kb.get("work_types", {}):
            forms = self.get_forms_for_work_type(code)
            required = len(forms)
            covered = sum(1 for f in forms if f["has_template"])
            total_required += required
            total_covered += covered

            by_work_type[code] = {
                "required": required,
                "covered": covered,
                "pct": round(covered / max(required, 1) * 100, 1),
            }

        coverage_pct = round(total_covered / max(total_required, 1) * 100, 1)

        return {
            "work_types_analyzed": len(self._kb.get("work_types", {})),
            "total_forms_required": total_required,
            "forms_with_templates": total_covered,
            "coverage_pct": coverage_pct,
            "by_work_type": by_work_type,
        }


# Singleton
template_registry = TemplateRegistry()
