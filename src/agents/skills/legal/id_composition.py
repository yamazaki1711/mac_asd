"""
ASD v12.0 — Legal ID Composition Skill.

Knowledge base for checking composition of Исполнительная Документация (ИД)
against current regulatory requirements.

Key regulations:
- Приказ Минстроя № 344/пр (replaced РД-11-02-2006)
- Приказ № 1026/пр (7 sections, replaced РД 11-05-2007)
- ГОСТ Р 70108-2025 (electronic ИД)

Covers all 10 work types of the company (v12.0: added отделочные,
инженерные_системы, электромонтаж, слаботочные).

Architecture: MLX-only (Mac Studio M4 Max 128GB).
"""

from typing import Dict, List, Any, Optional
from src.agents.skills.common.base import SkillBase, SkillResult, SkillStatus


class LegalIDComposition(SkillBase):
    """
    Навык Юриста: проверка состава исполнительной документации.

    Содержит справочник требуемых документов ИД по каждому виду работ
    в соответствии с Приказом № 344/пр и Приказом № 1026/пр.
    """

    skill_id = "legal_id_composition"
    description = "Проверка состава ИД по видам работ (Приказ № 344/пр, № 1026/пр)"
    agent = "legal"

    # =========================================================================
    # ИД Requirements per work type
    # =========================================================================

    ID_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
        "общестроительные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ",
                    "regulation": "Приказ № 344/пр",
                    "stages": [
                        "Подготовка основания",
                        "Устройство фундаментов",
                        "Гидроизоляция",
                        "Утепление",
                        "Устройство перекрытий",
                    ],
                },
            ],
            "journals": [
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "7 разделов вместо 5 (замена РД 11-05-2007)",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости выполненных работ"},
            ],
            "additional": [
                "Исполнительные схемы и чертежи",
                "Акты испытаний материалов и конструкций",
                "Паспорта и сертификаты на материалы",
                "Акты геодезической разбивки",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "бетонные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ",
                    "regulation": "Приказ № 344/пр, СП 70.13330.2025",
                    "stages": [
                        "Подготовка основания под бетонирование",
                        "Установка опалубки",
                        "Армирование (перед бетонированием)",
                        "Установка закладных деталей",
                        "Бетонирование (после распалубки — проверка поверхности)",
                    ],
                },
                {
                    "type": "АОСР (формы 1-6)",
                    "description": "Акты по формам ГОСТ/СП для бетонных работ",
                    "regulation": "СП 70.13330.2025",
                    "stages": [],
                },
            ],
            "journals": [
                {
                    "type": "Журнал бетонных работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Включает данные о бетонной смеси, температуре, уходе",
                },
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Общий журнал работ",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Акты испытания бетонных кубиков (ГОСТ 18105-2018)",
                "Паспорта на бетонную смесь",
                "Паспорта на арматуру и закладные детали",
                "Исполнительные схемы конструкций",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "земляные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ",
                    "regulation": "Приказ № 344/пр, СП 45.13330.2017",
                    "stages": [
                        "Основание земляного сооружения",
                        "Обратная засыпка",
                        "Уплотнение грунта",
                        "Устройство дренажа (при наличии)",
                    ],
                },
            ],
            "journals": [
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Общий журнал работ",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Акты геодезической разбивки",
                "Исполнительные схемы земляных сооружений",
                "Протоколы испытаний грунта (плотность, влажность)",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "сварочные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (сварные соединения)",
                    "regulation": "Приказ № 344/пр, ВСН 012-88",
                    "stages": [
                        "Подготовка кромок под сварку",
                        "Сварные стыковые соединения (после сварки)",
                        "Сварные нахлёсточные соединения",
                    ],
                },
            ],
            "journals": [
                {
                    "type": "Журнал сварочных работ",
                    "form": "ВСН 012-88",
                    "sections": None,
                    "note": "Специализированный журнал для сварки",
                },
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Общий журнал работ",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Удостоверения сварщиков (НАКС)",
                "Заключения по неразрушающему контролю (ВИК, РК, УЗК)",
                "Паспорта на сварочные материалы (электроды, проволока)",
                "Исполнительные схемы сварных соединений",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "монтажные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (монтаж)",
                    "regulation": "Приказ № 344/пр, СП 70.13330.2025",
                    "stages": [
                        "Подготовка оснований под монтаж",
                        "Анкеровка элементов",
                        "Сварные монтажные соединения",
                        "Антикоррозийная защита",
                    ],
                },
            ],
            "journals": [
                {
                    "type": "Журнал монтажных работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Специализированный журнал монтажа",
                },
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Общий журнал работ",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Акты испытаний конструкций",
                "Паспорта и сертификаты на конструкции",
                "Исполнительные схемы",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "шпунтовые": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (шпунт)",
                    "regulation": "Приказ № 344/пр, ГОСТ Р 57365-2016",
                    "stages": [
                        "Погружение шпунта",
                        "Устройство распорной системы",
                        "Устройство обвязки",
                    ],
                },
            ],
            "journals": [
                {
                    "type": "Журнал работ",
                    "form": "Приказ № 1026/пр",
                    "sections": 7,
                    "note": "Общий журнал работ",
                },
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Акты приёмки шпунтового ограждения",
                "Исполнительные схемы шпунтового ряда",
                "Паспорта на шпунт",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "отделочные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (отделка)",
                    "regulation": "Приказ № 344/пр",
                    "stages": [
                        "Подготовка основания под отделку",
                        "Устройство стяжки/выравнивающего слоя",
                        "Гидроизоляция (при наличии)",
                        "Теплоизоляция (при наличии)",
                        "Звукоизоляция (при наличии)",
                        "Монтаж каркаса (при облицовке)",
                        "Грунтование",
                    ],
                },
            ],
            "journals": [
                {"type": "Журнал работ", "form": "Приказ № 1026/пр", "sections": 7},
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Исполнительные схемы отделки",
                "Паспорта и сертификаты на отделочные материалы",
                "Акты приёмки полов (СП 29.13330.2021)",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "инженерные_системы": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (инженерные системы)",
                    "regulation": "Приказ № 344/пр, СП 543.1325800.2024",
                    "stages": [
                        "Прокладка трубопроводов/кабелей",
                        "Устройство проходок через стены и перекрытия",
                        "Антикоррозийная обработка",
                        "Теплоизоляция (при наличии)",
                        "Герметизация мест проходок",
                    ],
                },
            ],
            "journals": [
                {"type": "Журнал работ", "form": "Приказ № 1026/пр", "sections": 7},
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Исполнительные чертежи (комплект по СП 543)",
                "Акты испытаний (гидравлические, пневматические)",
                "Паспорта на оборудование и материалы",
                "Сертификаты соответствия",
                "Акты индивидуальных испытаний оборудования",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "электромонтаж": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (электромонтаж)",
                    "regulation": "Приказ № 344/пр, ПУЭ, ПТЭЭП",
                    "stages": [
                        "Монтаж кабеленесущих систем",
                        "Прокладка кабеля",
                        "Устройство проходов через стены и перекрытия",
                        "Монтаж заземления",
                    ],
                },
            ],
            "journals": [
                {"type": "Журнал работ", "form": "Приказ № 1026/пр", "sections": 7},
                {"type": "Кабельный журнал", "form": "И 1.13-07", "sections": None, "note": "Обязателен для электромонтажа"},
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Исполнительные чертежи (комплект по СП 543)",
                "Протоколы замеров сопротивления изоляции",
                "Протоколы замеров сопротивления заземления",
                "Паспорта на кабельную продукцию",
                "Сертификаты на электрооборудование",
                "Акты приёмки-передачи оборудования",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
        "слаботочные": {
            "primary_acts": [
                {
                    "type": "АОСР",
                    "description": "Акты освидетельствования скрытых работ (сети связи)",
                    "regulation": "Приказ № 344/пр",
                    "stages": [
                        "Прокладка кабеля связи",
                        "Устройство проходов через стены и перекрытия",
                        "Монтаж оборудования связи",
                    ],
                },
            ],
            "journals": [
                {"type": "Журнал работ", "form": "Приказ № 1026/пр", "sections": 7},
            ],
            "acts_forms": [
                {"type": "КС-2", "description": "Акт приёмки выполненных работ"},
                {"type": "КС-3", "description": "Справка о стоимости"},
            ],
            "additional": [
                "Исполнительные чертежи (комплект по СП 543)",
                "Паспорта на оборудование связи",
                "Акты входного контроля оборудования",
            ],
            "outdated_forms": [
                {"ref": "РД-11-02-2006", "replaced_by": "Приказ № 344/пр"},
                {"ref": "РД 11-05-2007", "replaced_by": "Приказ № 1026/пр"},
            ],
        },
    }

    # =========================================================================
    # Skill Interface (overrides SkillBase)
    # =========================================================================

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Выполнить проверку состава ИД.

        params:
            action: "requirements" | "check_outdated" | "compare"
            work_type: вид работ
            provided_docs: список предоставленных документов (для compare)
        """
        action = params.get("action", "requirements")
        work_type = params.get("work_type", "общестроительные")

        if action == "requirements":
            return self._get_requirements(work_type)
        elif action == "check_outdated":
            return self._check_outdated_refs(work_type)
        elif action == "compare":
            return self._compare_with_required(
                work_type, params.get("provided_docs", [])
            )
        else:
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[f"Unknown action: {action}"],
            )

    def _get_requirements(self, work_type: str) -> SkillResult:
        """Получить требования к составу ИД для вида работ."""
        if work_type not in self.ID_REQUIREMENTS:
            return SkillResult(
                status=SkillStatus.REJECTED,
                skill_id=self.skill_id,
                errors=[
                    f"Вид работ '{work_type}' не поддерживается. "
                    f"Допустимые: {', '.join(self.ID_REQUIREMENTS.keys())}"
                ],
            )

        req = self.ID_REQUIREMENTS[work_type]

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "primary_acts": req["primary_acts"],
                "journals": req["journals"],
                "acts_forms": req["acts_forms"],
                "additional": req["additional"],
                "outdated_forms": req["outdated_forms"],
            },
        )

    def _check_outdated_refs(self, work_type: str) -> SkillResult:
        """Получить список устаревших форм для вида работ."""
        if work_type not in self.ID_REQUIREMENTS:
            return SkillResult(
                status=SkillStatus.REJECTED,
                skill_id=self.skill_id,
                errors=[f"Вид работ '{work_type}' не поддерживается."],
            )

        req = self.ID_REQUIREMENTS[work_type]

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "outdated_forms": req["outdated_forms"],
                "warning": (
                    "Все ссылки на РД-11-02-2006 и РД 11-05-2007 устарели. "
                    "Используйте Приказ № 344/пр и Приказ № 1026/пр соответственно."
                ),
            },
        )

    def _compare_with_required(
        self, work_type: str, provided_docs: List[str]
    ) -> SkillResult:
        """Сравнить предоставленный список документов с требуемым составом ИД."""
        if work_type not in self.ID_REQUIREMENTS:
            return SkillResult(
                status=SkillStatus.REJECTED,
                skill_id=self.skill_id,
                errors=[f"Вид работ '{work_type}' не поддерживается."],
            )

        req = self.ID_REQUIREMENTS[work_type]

        # Collect all required document types
        all_required = []
        for act in req["primary_acts"]:
            all_required.append(act["type"])
        for journal in req["journals"]:
            all_required.append(journal["type"])
        for form in req["acts_forms"]:
            all_required.append(form["type"])
        for doc in req["additional"]:
            all_required.append(doc)

        # Simple matching (keyword-based)
        provided_lower = [d.lower() for d in provided_docs]

        missing = []
        matched = []

        for required_doc in all_required:
            found = any(
                any(keyword in p for p in provided_lower)
                for keyword in required_doc.lower().split()
                if len(keyword) > 3  # Skip short words
            )
            if found:
                matched.append(required_doc)
            else:
                missing.append(required_doc)

        # Check for outdated refs in provided docs
        outdated_found = []
        for outdated in req["outdated_forms"]:
            if any(outdated["ref"].lower() in p for p in provided_lower):
                outdated_found.append(outdated)

        compliance_pct = (
            round(len(matched) / len(all_required) * 100, 1)
            if all_required
            else 0
        )

        return SkillResult(
            status=SkillStatus.SUCCESS,
            skill_id=self.skill_id,
            data={
                "work_type": work_type,
                "total_required": len(all_required),
                "matched": len(matched),
                "missing": len(missing),
                "compliance_pct": compliance_pct,
                "missing_documents": missing,
                "matched_documents": matched,
                "outdated_refs_in_provided": outdated_found,
            },
        )
