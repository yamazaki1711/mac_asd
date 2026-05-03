"""
MAC_ASD v12.0 — IDRequirementsRegistry.

Загрузчик эталона состава ИД по 344/пр для каждого вида работ.
Отвечает на вопрос: «Что должно быть в ИД для вида работ X?»
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "id_requirements.yaml"


class IDRequirementsRegistry:
    """
    SSOT эталона состава исполнительной документации.

    Используется:
    - asd_id_completeness (расчёт delta ИД)
    - ПТО (определение шлейфа документов для вида работ)
    - Auditor (проверка комплектности)
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def _load(self) -> Dict[str, Any]:
        if self._loaded:
            return self._data

        if not self._path.exists():
            logger.warning("IDRequirementsRegistry: %s not found", self._path)
            self._data = {"work_types": {}}
            self._loaded = True
            return self._data

        with open(self._path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

        self._loaded = True
        wt_count = len(self._data.get("work_types", {}))
        logger.info("IDRequirementsRegistry: loaded %d work types from %s", wt_count, self._path)
        return self._data

    def get_base_trail(self) -> Dict[str, Any]:
        """Базовый шлейф документов, общий для всех видов работ."""
        return self._load().get("base_trail", {}).get("id_requirements", {})

    def get_work_type_trail(self, work_type: str) -> Dict[str, Any]:
        """
        Получить специфичный шлейф для вида работ.

        Args:
            work_type: Значение WorkType enum или строковый идентификатор

        Returns:
            {
                "aosr_count": "≥1 на захватку",
                "aook": True/False,
                "special_journals": [...],
                "typical_tests": [...],
                "input_control_materials": [...],
                "executive_schemes_detail": str or None,
            }
        """
        data = self._load()
        wt_data = data.get("work_types", {}).get(work_type)

        if wt_data is None:
            # Try fuzzy match
            for key in data.get("work_types", {}):
                if work_type in key or key in work_type:
                    wt_data = data["work_types"][key]
                    break

        if wt_data is None:
            logger.warning("IDRequirementsRegistry: work type '%s' not found, using defaults", work_type)
            return {
                "aosr_count": "≥1 на этап",
                "aook": False,
                "special_journals": ["ОЖР"],
                "typical_tests": ["по проекту"],
                "input_control_materials": ["согласно спецификации"],
            }

        return wt_data

    def get_required_documents(self, work_type: str) -> List[Dict[str, Any]]:
        """
        Полный список обязательных документов для вида работ.

        Объединяет базовый шлейф (344/пр) + специфику вида работ.

        Returns:
            Список словарей: {"name": "...", "type": "...", "required": bool, "quantity": "..."}
        """
        base = self.get_base_trail()
        spec = self.get_work_type_trail(work_type)

        docs = []

        # Базовые — из 344/пр (п. 13)
        for doc_id, doc_info in base.items():
            docs.append({
                "id": doc_id,
                "name": doc_info.get("name", doc_id),
                "type": "base",
                "required": doc_info.get("required", True),
                "quantity": doc_info.get("quantity", 1),
                "form": doc_info.get("form", ""),
                "signers": doc_info.get("signers", []),
            })

        # АОСР
        docs.append({
            "id": "aosr",
            "name": "Акты освидетельствования скрытых работ (АОСР)",
            "type": "aosr",
            "required": True,
            "quantity": spec.get("aosr_count", "≥1"),
            "form": "344/пр прил. 3",
            "signers": ["застройщик", "ЛОС", "проектировщик", "стройконтроль"],
        })

        # АООК — если требуется
        if spec.get("aook"):
            docs.append({
                "id": "aook",
                "name": "Акты освидетельствования ответственных конструкций (АООК)",
                "type": "aook",
                "required": True,
                "quantity": "≥1",
                "form": "344/пр прил. 4",
                "signers": ["застройщик", "ЛОС", "проектировщик", "стройконтроль"],
            })

        # Спецжурналы
        for journal in spec.get("special_journals", []):
            docs.append({
                "id": f"journal_{journal.replace(' ', '_')}",
                "name": journal,
                "type": "journal",
                "required": True,
                "quantity": 1,
                "form": "по форме СП/ГОСТ",
            })

        # Испытания
        for test in spec.get("typical_tests", []):
            docs.append({
                "id": f"test_{test.replace(' ', '_')}",
                "name": f"Протокол испытаний: {test}",
                "type": "test_report",
                "required": True,
                "quantity": "≥1",
                "form": "ГОСТ/СП",
                "signers": ["лаборатория", "стройконтроль"],
            })

        return docs

    def list_work_types(self) -> List[str]:
        """Список всех зарегистрированных видов работ."""
        return sorted(self._load().get("work_types", {}).keys())

    def calculate_delta(
        self,
        work_type: str,
        present_docs: List[str],
    ) -> Dict[str, Any]:
        """
        Рассчитать delta между требуемым составом ИД и фактическим наличием.

        Args:
            work_type: Вид работ
            present_docs: Список ID имеющихся документов

        Returns:
            {
                "total_required": int,
                "present": int,
                "missing": [str],
                "delta": int,
                "completeness_pct": float,
            }
        """
        required = self.get_required_documents(work_type)
        required_ids = {doc["id"] for doc in required if doc["required"]}

        present_set = set(present_docs)
        missing = sorted(required_ids - present_set)

        return {
            "total_required": len(required_ids),
            "present": len(required_ids & present_set),
            "missing": missing,
            "delta": len(missing),
            "completeness_pct": round(
                (len(required_ids & present_set) / max(len(required_ids), 1)) * 100, 1
            ),
        }


# Singleton
id_requirements = IDRequirementsRegistry()
