"""PPR Generator — Раздел 9: Лист ознакомления."""
from typing import List
from ..schemas import PPRInput, SectionResult, TTKResult


def generate_attestation(input: PPRInput, ttks: List[TTKResult]) -> SectionResult:
    # Collect unique workers
    workers = {}
    idx = 1
    for ttk in ttks:
        for w in ttk.resources.workers:
            if w.name not in workers:
                workers[w.name] = {"№": idx, "name": w.name, "profession": w.name}
                idx += 1

    rows = []
    for w in sorted(workers.values(), key=lambda x: x["№"]):
        rows.append(f"| {w['№']} | {w['name']} | _______________ | _______________ | _______________ |")

    table = "| № | ФИО | Должность | Дата инструктажа | Подпись |\n"
    table += "|---|-----|-----------|------------------|--------|\n"
    table += "\n".join(rows) if rows else "| — | — | — | — | — |"

    content = f"""## 9. Лист ознакомления с ППР

Настоящий ППР доведён до сведения нижеперечисленных работников.
Работники ознакомлены с технологией, организацией работ и требованиями охраны труда.

{table}

---
**Разработчик ППР:** {input.developer.developer} / _______________ /  
**Главный инженер:** {input.developer.chief_engineer} / _______________ /  
**Утверждаю:** Руководитель организации / _______________ /  
"""

    return SectionResult(
        section_id="attestation",
        title="9. Лист ознакомления",
        content=content,
        page_count=max(1, len(workers) // 15 + 1),
        tables=[{"headers": ["№", "ФИО", "Должность", "Дата инструктажа", "Подпись"], "rows": len(workers)}],
        metadata={"workers_count": len(workers)},
    )
