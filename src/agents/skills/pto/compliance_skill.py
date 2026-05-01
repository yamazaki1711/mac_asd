"""
ASD v12.0 — PTO Compliance Skill.

Объединяет все источники знаний о составе ИД:
  1. work_spec.py — 33 WorkType с детальными журналами/АОСР/АООК
  2. idprosto_loader — 569 документов из 31 перечня id-prosto.ru
  3. regulation_templates — шаблоны актов из Регламента ТЗ-П
  4. PDF-пособие (Щербаков, 2026) — нормативная база

Предоставляет единый интерфейс для:
  - resolve(work_type) → полный перечень документов
  - compliance_report(project_id, work_types) → матрица полноты
  - generate_spec(schedule) → спецификация пакета ИД для BatchIDGenerator
  - normative_lookup(query) → поиск по нормативной базе
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.agents.skills.pto.work_spec import (
    WorkType,
    WORK_TYPE_CATEGORIES,
    WORK_JOURNALS,
    WORK_HIDDEN_ACTS,
    WORK_RESPONSIBLE_ACTS,
    WORK_ACCEPTANCE_ACTS,
    COMMON_REGULATIONS,
    COMMON_JOURNAL_OJR,
    COMMON_JOURNAL_JVK,
)
from src.core.knowledge.idprosto_loader import idprosto_loader, IDPROSTO_WORK_TYPES
from src.core.knowledge.template_registry import template_registry

logger = logging.getLogger(__name__)


@dataclass
class WorkTypeSpec:
    """Полная спецификация документов для одного вида работ."""
    work_type_code: str
    work_type_name: str
    aosr_hidden: List[Dict[str, Any]] = field(default_factory=list)
    aosr_responsible: List[Dict[str, Any]] = field(default_factory=list)
    journals: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_acts: List[Dict[str, Any]] = field(default_factory=list)
    test_protocols: List[Dict[str, Any]] = field(default_factory=list)
    executive_schemas: List[Dict[str, Any]] = field(default_factory=list)
    certificates: List[Dict[str, Any]] = field(default_factory=list)
    normative_refs: List[str] = field(default_factory=list)
    regulation_notes: List[str] = field(default_factory=list)
    from_idprosto: bool = False

    @property
    def total_required(self) -> int:
        mandatory = 0
        for lst in [self.aosr_hidden, self.aosr_responsible]:
            mandatory += sum(1 for d in lst if d.get("mandatory", True))
        mandatory += len([j for j in self.journals if j.get("mandatory", True)])
        return mandatory

    @property
    def mandatory_names(self) -> List[str]:
        names = []
        for field in ["aosr_hidden", "aosr_responsible"]:
            for d in getattr(self, field, []):
                if d.get("mandatory", True):
                    names.append(d["name"])
        for j in self.journals:
            if j.get("mandatory", True):
                names.append(j["name"])
        return names


class PTOComplianceSkill:
    """
    Единый навык комплаенса ПТО.

    Объединяет work_spec.py (18→33 WorkType) и idprosto_loader (31 перечень)
    для полного покрытия любых видов строительных работ.
    """

    # ── Resolution ──

    def resolve(self, work_type_query: str) -> WorkTypeSpec:
        """
        Определить полный перечень документов для вида работ.

        Алгоритм:
          1. Точное совпадение с WorkType enum (work_spec.py)
          2. Fuzzy-match через idprosto_loader (31 перечень)
          3. Fallback: общий набор (ОЖР + ЖВК + АОСР)
        """
        # Step 1: WorkType enum
        try:
            wt = WorkType(work_type_query)
            return self._spec_from_worktype(wt)
        except ValueError:
            pass

        # Step 2: idprosto fuzzy match
        code = idprosto_loader.resolve_work_type(work_type_query)
        if code:
            return self._spec_from_idprosto(code)

        # Step 3: general fallback
        return self._spec_fallback(work_type_query)

    def _spec_from_worktype(self, wt: WorkType) -> WorkTypeSpec:
        """Build spec from work_spec.py data."""
        aosr = WORK_HIDDEN_ACTS.get(wt, [])
        aook = WORK_RESPONSIBLE_ACTS.get(wt, [])
        journals = WORK_JOURNALS.get(wt, [])
        acceptance = WORK_ACCEPTANCE_ACTS.get(wt, [])

        return WorkTypeSpec(
            work_type_code=wt.value,
            work_type_name=wt.value,
            aosr_hidden=[
                {"name": a["name"], "mandatory": a.get("mandatory", True),
                 "conditional": a.get("conditional", ""), "note": a.get("note", "")}
                for a in aosr
            ],
            aosr_responsible=[
                {"name": a["name"], "mandatory": a.get("mandatory", True),
                 "note": a.get("note", "")}
                for a in aook
            ],
            journals=[
                {"name": j["name"], "form": j.get("form", ""),
                 "mandatory": j.get("mandatory", True),
                 "conditional": j.get("conditional", "")}
                for j in journals
            ],
            acceptance_acts=[
                {"name": a["name"], "mandatory": a.get("mandatory", True),
                 "note": a.get("note", "")}
                for a in acceptance
            ],
            regulation_notes=[f"Раздел Пособия: {wt.value}"],
        )

    def _spec_from_idprosto(self, code: str) -> WorkTypeSpec:
        """Build spec from idprosto.ru checklist data."""
        summary = idprosto_loader.get_work_type_summary(code)
        return WorkTypeSpec(
            work_type_code=code,
            work_type_name=summary["name"],
            aosr_hidden=summary.get("aosr", []),
            aosr_responsible=summary.get("aook", []),
            journals=summary.get("journals", []),
            test_protocols=summary.get("test_acts", []),
            executive_schemas=summary.get("schemas", []),
            certificates=summary.get("certificates", []),
            normative_refs=summary.get("normative_refs", []),
            regulation_notes=[f"Из перечня id-prosto.ru: {summary['name']}"],
            from_idprosto=True,
        )

    def _spec_fallback(self, query: str) -> WorkTypeSpec:
        """General fallback when no specific mapping found."""
        return WorkTypeSpec(
            work_type_code="unknown",
            work_type_name=query,
            journals=[
                {"name": COMMON_JOURNAL_OJR["name"], "form": COMMON_JOURNAL_OJR["form"],
                 "mandatory": True},
                {"name": COMMON_JOURNAL_JVK["name"], "form": COMMON_JOURNAL_JVK["form"],
                 "mandatory": True},
            ],
            aosr_hidden=[
                {"name": "АОСР на выполняемые работы", "mandatory": True,
                 "note": "Точный перечень уточните по виду работ"},
            ],
            regulation_notes=["ВНИМАНИЕ: вид работ не найден в базе. Использован общий минимальный набор."],
        )

    # ── Completeness Report ──

    def completeness_report(
        self, project_id: int, work_type_queries: List[str],
        available_docs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Построить отчёт о комплектности ИД для проекта.

        Args:
            project_id: ID проекта
            work_type_queries: список видов работ (любые строки)
            available_docs: имеющиеся документы

        Returns:
            {
                "project_id": int,
                "work_types": [{"query": str, "resolved": str, "spec": WorkTypeSpec.to_dict()}],
                "required_total": int,
                "present_total": int,
                "gaps": [{"doc": str, "required": bool, "found": bool}],
                "completeness_pct": float,
                "recommendations": [str],
            }
        """
        specs = []
        required_total = 0
        gaps = []

        for q in work_type_queries:
            spec = self.resolve(q)
            specs.append(spec)
            required_total += spec.total_required

        # Check against available docs
        present_total = 0
        if available_docs:
            av_names = {d.get("name", "").lower() for d in available_docs}
            for spec in specs:
                for name in spec.mandatory_names:
                    if any(n.lower() in av_names for n in [name, name.lower()]):
                        present_total += 1
                    else:
                        gaps.append({
                            "doc": name,
                            "work_type": spec.work_type_name,
                            "required": True,
                            "found": False,
                        })

        completeness = round(present_total / max(required_total, 1) * 100, 1)

        # Recommendations
        recs = []
        if completeness < 50:
            recs.append("КРИТИЧЕСКИЙ: отсутствует более 50% обязательных документов.")
        if gaps:
            critical = len([g for g in gaps if g["required"]])
            if critical > 0:
                recs.append(f"Отсутствует {critical} обязательных документов. Приоритет: АОСР → журналы → акты испытаний.")

        return {
            "project_id": project_id,
            "work_types": [
                {"query": q, "resolved": s.work_type_name, "code": s.work_type_code}
                for q, s in zip(work_type_queries, specs)
            ],
            "required_total": required_total,
            "present_total": present_total,
            "gaps": gaps,
            "completeness_pct": completeness,
            "recommendations": recs,
        }

    # ── Batch ID Spec Generator ──

    def generate_batch_spec(
        self, schedule: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Сгенерировать спецификацию пакета ИД для BatchIDGenerator.

        Args:
            schedule: [{"work_type": "...", "work_name": "...", "start_date": "...", "end_date": "..."}]

        Returns:
            {
                "total_aosr_expected": int,
                "total_journals_expected": int,
                "by_work_type": {work_type: WorkTypeSpec},
                "warnings": [str],
            }
        """
        by_work_type = {}
        total_aosr = 0
        total_journals = 0
        warnings = []

        for item in schedule:
            wt = item.get("work_type", "")
            spec = self.resolve(wt)
            by_work_type[wt] = spec

            mandatory_aosr = [a for a in spec.aosr_hidden if a.get("mandatory", True)]
            total_aosr += len(mandatory_aosr)

            mandatory_journals = [j for j in spec.journals if j.get("mandatory", True)]
            total_journals += len(mandatory_journals)

            if spec.from_idprosto:
                warnings.append(
                    f"'{wt}' — данные из id-prosto.ru. "
                    f"Подробные АОСР и журналы могут отличаться от work_spec.py."
                )

        return {
            "total_aosr_expected": total_aosr,
            "total_journals_expected": total_journals,
            "by_work_type": {
                wt: {
                    "name": spec.work_type_name,
                    "aosr_count": len([a for a in spec.aosr_hidden if a.get("mandatory", True)]),
                    "journal_count": len([j for j in spec.journals if j.get("mandatory", True)]),
                    "mandatory_docs": spec.mandatory_names,
                }
                for wt, spec in by_work_type.items()
            },
            "warnings": warnings,
        }

    # ── Normative Lookup ──

    def normative_lookup(self, query: str) -> List[Dict[str, str]]:
        """
        Поиск по нормативной базе.

        Ищет по всем известным НТД: 344/пр, 1026/пр, СП, ГОСТ, ВСН, РД.
        """
        results = []
        q = query.lower()

        # Search COMMON_REGULATIONS
        for reg in COMMON_REGULATIONS:
            if q in reg["code"].lower() or q in reg.get("note", "").lower():
                results.append({"code": reg["code"], "note": reg.get("note", ""), "status": reg.get("status", "")})

        # Search all idprosto normative refs
        all_norms = idprosto_loader.get_all_normative_refs()
        for norm in all_norms:
            if q in norm.lower():
                results.append({"code": norm, "note": "", "status": ""})

        return results[:20]

    def list_all_work_types(self) -> List[Dict[str, Any]]:
        """Полный каталог всех известных видов работ с обоих источников."""
        result = []

        # From work_spec.py
        for wt in WorkType:
            aosr_count = len([
                a for a in WORK_HIDDEN_ACTS.get(wt, [])
                if a.get("mandatory", True)
            ])
            journal_count = len([
                j for j in WORK_JOURNALS.get(wt, [])
                if j.get("mandatory", True)
            ])
            result.append({
                "code": wt.value,
                "source": "work_spec.py",
                "aosr_count": aosr_count,
                "journal_count": journal_count,
            })

        # From idprosto
        for code, name in IDPROSTO_WORK_TYPES.items():
            summary = idprosto_loader.get_work_type_summary(code)
            result.append({
                "code": code,
                "name": name,
                "source": "idprosto.ru",
                "aosr_count": len(summary.get("aosr", [])),
                "journal_count": len(summary.get("journals", [])),
                "total_docs": summary["total_docs"],
            })

        return result

    # ── Template Resolution ──

    def get_templates_for_work_type(self, work_type_query: str) -> Dict[str, Any]:
        """
        Get available DOCX form templates for a work type.

        Returns:
            {
                "work_type": str,
                "forms_with_templates": int,
                "forms_without_templates": int,
                "total_forms": int,
                "templates": [{"doc_name", "form_ref", "file_name", "full_path"}],
                "missing": [{"doc_name", "form_ref"}],
            }
        """
        spec = self.resolve(work_type_query)
        code = spec.work_type_code

        if spec.from_idprosto:
            forms = template_registry.get_forms_for_work_type(code)
        else:
            # For work_spec types, try fuzzy resolve to idprosto code
            idp_code = idprosto_loader.resolve_work_type(work_type_query)
            if idp_code:
                forms = template_registry.get_forms_for_work_type(idp_code)
            else:
                forms = []

        with_templates = []
        without_templates = []
        forms_covered = 0
        forms_missing = 0
        for f in forms:
            if f["has_template"]:
                forms_covered += 1
                for t in f["templates"]:
                    with_templates.append({
                        "doc_name": f["doc_name"],
                        "form_ref": f["form_ref"],
                        "file_name": t["file_name"],
                        "full_path": t["full_path"],
                        "regulation": t["regulation"],
                    })
            else:
                forms_missing += 1
                without_templates.append({
                    "doc_name": f["doc_name"],
                    "form_ref": f["form_ref"],
                })

        return {
            "work_type": spec.work_type_name,
            "code": code,
            "forms_with_templates": forms_covered,
            "forms_without_templates": forms_missing,
            "total_forms": len(forms),
            "templates": with_templates,
            "missing": without_templates,
        }

    def resolve_template(self, normative_ref: str) -> List[Dict[str, Any]]:
        """Find DOCX templates matching a normative reference."""
        return template_registry.resolve_form(normative_ref)


# Singleton
compliance_skill = PTOComplianceSkill()
