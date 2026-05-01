"""
ASD v12.0 — Batch ID Generator.

Принимает календарный график работ и генерирует полный комплект
исполнительной документации: АОСР, КС-2, КС-3, реестр, опись.

Сценарий: ПТО-шник загружает график (CSV/Excel), АСД определяет:
  - Какие АОСР нужны для каждого вида работ
  - Какие журналы обязательны
  - Какие сертификаты и паспорта требуются
  - Даты начала/окончания по графику

Результат: готовый ZIP-комплект для стройконтроля.

Pipeline:
  WorkSchedule → PTOAgent.classify → DeloAgent.register → OutputPipeline.generate → ZIP
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from src.core.output_pipeline import output_pipeline
from src.core.services.pto_agent import pto_agent
from src.core.services.delo_agent import delo_agent, DocStatus


class BatchIDGenerator:
    """
    Пакетный генератор ИД из календарного графика работ.

    Args:
        project_id: ID проекта
        project_name: наименование объекта
        project_meta: метаданные проекта (заказчик, подрядчик, адрес, договор)
    """

    def __init__(
        self,
        project_id: int,
        project_name: str,
        project_meta: Optional[Dict[str, Any]] = None,
    ):
        self.project_id = project_id
        self.project_name = project_name
        self.meta = project_meta or {}

        # Инициализируем реестр
        delo_agent.create_registry(project_id, project_name)

    # -------------------------------------------------------------------------
    # Schedule Loading
    # -------------------------------------------------------------------------

    def load_schedule_csv(self, csv_path: str) -> List[Dict[str, str]]:
        """
        Загружает календарный график из CSV.

        Ожидаемые колонки:
          work_type, work_name, start_date, end_date, quantity, unit, executor
        """
        rows = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "work_type": row.get("work_type", "").strip(),
                    "work_name": row.get("work_name", "").strip(),
                    "start_date": row.get("start_date", "").strip(),
                    "end_date": row.get("end_date", "").strip(),
                    "quantity": row.get("quantity", "1"),
                    "unit": row.get("unit", "шт"),
                    "executor": row.get("executor", "ООО «КСК №1»"),
                })
        logger.info("Loaded %d work items from %s", len(rows), csv_path)
        return rows

    def load_schedule_dict(self, items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Загружает график из списка словарей."""
        return items

    # -------------------------------------------------------------------------
    # ID Package Generation
    # -------------------------------------------------------------------------

    def generate(
        self,
        schedule: List[Dict[str, str]],
        output_dir: str = "",
        skip_optional: bool = True,
    ) -> Dict[str, Any]:
        """
        Генерирует полный комплект ИД по графику работ.

        Args:
            schedule: список работ [{work_type, work_name, start_date, end_date, ...}]
            output_dir: куда сохранять (по умолчанию /tmp/asd_output/{project_code})
            skip_optional: пропускать необязательные АОСР

        Returns:
            {
                "project_id": int,
                "total_aosr": int,
                "total_ks2_lines": int,
                "total_journals": int,
                "zip_path": str,
                "registry_summary": str,
                "warnings": [str],
            }
        """
        output_dir = output_dir or f"/tmp/asd_output/PRJ-{self.project_id}"
        warnings: List[str] = []
        all_aosr_data: List[Dict[str, Any]] = []
        all_ks2_lines: List[Dict[str, Any]] = []
        journal_set: Dict[str, List[Dict[str, Any]]] = {}

        # ── Шаг 1: Проходим по каждой работе в графике ──
        for item in schedule:
            work_type = item["work_type"]
            work_name = item["work_name"]

            # 1a. Какие АОСР нужны?
            aosr_list = pto_agent.get_required_aosr_list(work_type)
            for aosr in aosr_list:
                if skip_optional and not aosr.get("mandatory", True):
                    continue
                if aosr.get("conditional"):
                    warnings.append(
                        f"АОСР '{aosr['name']}' для '{work_name}' — условный "
                        f"({aosr['conditional']}). Требуется ручная проверка."
                    )

                aosr_number = self._next_aosr_number()
                all_aosr_data.append({
                    "aosr_number": aosr_number,
                    "project_name": self.project_name,
                    "object_address": self.meta.get("object_address", ""),
                    "work_type": aosr["name"],
                    "work_start": item["start_date"],
                    "work_end": item["end_date"],
                    "materials": [],
                    "certificates": [],
                    "design_docs": [],
                    "executor_company": self.meta.get("contractor", "ООО «КСК №1»"),
                    "customer_company": self.meta.get("customer", "Заказчик"),
                    "developer_company": self.meta.get("developer", ""),
                    "commission_members": [
                        {"name": "", "role": "Представитель заказчика",
                         "company": self.meta.get("customer", "")},
                        {"name": "", "role": "Представитель подрядчика",
                         "company": self.meta.get("contractor", "")},
                        {"name": "", "role": "Представитель стройконтроля", "company": ""},
                    ],
                    "decision": "разрешается",
                    "date": item["end_date"],
                    "output_dir": output_dir,
                })

                # Регистрируем в DeloAgent
                delo_agent.register_document(
                    project_id=self.project_id,
                    doc_type="АОСР",
                    doc_name=aosr["name"],
                    category_344="act_aosr",
                    work_type=work_type,
                    pages=2,
                )

            # 1b. Строки для КС-2
            all_ks2_lines.append({
                "row": len(all_ks2_lines) + 1,
                "code": item.get("rate_code", ""),
                "name": work_name,
                "unit": item["unit"],
                "quantity": float(item.get("quantity", "1")),
                "unit_price": float(item.get("unit_price", "0")),
                "total": float(item.get("quantity", "1")) * float(item.get("unit_price", "0")),
            })

            # 1c. Журналы
            journals = pto_agent.get_required_journals(work_type)
            for j in journals:
                if skip_optional and not j.get("mandatory", True):
                    continue
                jname = j["name"]
                if jname not in journal_set:
                    journal_set[jname] = []
                journal_set[jname].append({
                    "work_type": work_type,
                    "work_name": work_name,
                    "start_date": item["start_date"],
                    "end_date": item["end_date"],
                    "form": j.get("form", ""),
                })

                delo_agent.register_document(
                    project_id=self.project_id,
                    doc_type="Журнал",
                    doc_name=jname,
                    category_344="journals",
                    work_type=work_type,
                    pages=0,
                )

        # ── Шаг 2: Генерируем DOCX ──
        paths: List[Path] = []

        # АОСР
        for aosr_data in all_aosr_data:
            path = output_pipeline.generate_aosr_package(
                f"PRJ-{self.project_id}", aosr_data
            )
            paths.append(path)

        # КС-2 + КС-3
        if all_ks2_lines:
            subtotal = sum(l["total"] for l in all_ks2_lines)
            ks2_data = {
                "project_name": self.project_name,
                "customer": self.meta.get("customer", "Заказчик"),
                "contractor": self.meta.get("contractor", "ООО «КСК №1»"),
                "contract_number": self.meta.get("contract_number", ""),
                "contract_date": self.meta.get("contract_date", ""),
                "period": f"{schedule[0]['start_date']} – {schedule[-1]['end_date']}" if schedule else "",
                "date": datetime.now().strftime("%d.%m.%Y"),
                "lines": all_ks2_lines,
                "subtotal": subtotal,
                "overhead_pct": self.meta.get("overhead_pct", 15),
                "overhead": subtotal * self.meta.get("overhead_pct", 15) / 100,
                "profit_pct": self.meta.get("profit_pct", 8),
                "profit": subtotal * self.meta.get("profit_pct", 8) / 100,
                "vat_pct": 20,
                "vat": (subtotal + subtotal * 0.15 + subtotal * 0.08) * 0.20,
                "grand_total": (subtotal + subtotal * 0.15 + subtotal * 0.08) * 1.20,
            }
            ks2_path, ks3_path = output_pipeline.generate_ks_package(
                f"PRJ-{self.project_id}", ks2_data
            )
            paths.extend([ks2_path, ks3_path])

            delo_agent.register_document(
                project_id=self.project_id,
                doc_type="КС-2",
                doc_name=f"Акт приёмки выполненных работ ({schedule[0]['start_date']} – {schedule[-1]['end_date']})",
                category_344="act_aosr",
                pages=1,
            )

        # Реестр ИД
        registry_data = delo_agent.export_registry_for_output(self.project_id)
        registry_data["output_dir"] = output_dir
        register_path = output_pipeline.generate_id_register(registry_data)
        paths.append(register_path)

        # ── Шаг 3: Упаковка ──
        zip_path = output_pipeline.bundle_package(f"PRJ-{self.project_id}", paths, output_dir)

        # ── Шаг 4: Статистика ──
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "total_aosr": len(all_aosr_data),
            "total_ks2_lines": len(all_ks2_lines),
            "total_journals": len(journal_set),
            "journals": list(journal_set.keys()),
            "zip_path": str(zip_path),
            "registry_summary": (
                f"Сгенерировано: {len(all_aosr_data)} АОСР, "
                f"{len(all_ks2_lines)} строк КС-2, "
                f"{len(journal_set)} журналов, "
                f"{len(paths)} файлов"
            ),
            "warnings": warnings,
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    _aosr_counter: int = 0

    def _next_aosr_number(self) -> str:
        self._aosr_counter += 1
        return f"АОСР-PRJ{self.project_id}-{self._aosr_counter:04d}"

    # -------------------------------------------------------------------------
    # LLM-powered work schedule analysis
    # -------------------------------------------------------------------------

    async def analyze_schedule(self, schedule: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Анализирует график через LLM: находит пропущенные работы,
        конфликты дат, нереалистичные сроки.

        Returns:
            {"issues": [...], "suggestions": [...], "completeness_pct": float}
        """
        from src.core.llm_engine import llm_engine

        lines = ["Проанализируй календарный график строительных работ:\n"]
        for i, item in enumerate(schedule, 1):
            lines.append(
                f"{i}. {item['work_name']} ({item['work_type']}) "
                f"— {item['start_date']} / {item['end_date']}"
            )

        prompt = "\n".join(lines) + """

Проверь:
1. Логическая последовательность работ (не идёт ли отделка до бетонирования?)
2. Нереалистичные сроки (например, 1 день на монолитные работы)
3. Пропущенные обязательные этапы (гидроизоляция, геодезия, испытания)
4. Конфликты дат (две работы в одном помещении одновременно)

Верни JSON:
{
  "issues": [{"work": "название", "problem": "описание", "severity": "critical|high|medium"}],
  "suggestions": ["предложение 1", ...],
  "completeness_pct": 0-100,
  "overall": "краткая оценка графика (1-2 предложения)"
}"""

        try:
            response = await llm_engine.chat("pto", [
                {"role": "system", "content": "Ты — начальник ПТО. Анализируй графики строительных работ. JSON-only."},
                {"role": "user", "content": prompt},
            ], temperature=0.1)
            import json as _json
            return _json.loads(response)
        except Exception as e:
            logger.warning("Schedule analysis failed: %s", e)
            return {"issues": [], "suggestions": [], "completeness_pct": 0,
                    "overall": f"Не удалось проанализировать: {e}"}


# Синглтон
batch_id_generator = BatchIDGenerator(
    project_id=0, project_name="default"
)
