"""PPR Generator — Титульный лист."""
from ..schemas import PPRInput, SectionResult


def generate_title_page(input: PPRInput) -> SectionResult:
    content = f"""# {input.object_name}

## ПРОЕКТ ПРОИЗВОДСТВА РАБОТ

**Шифр:** {input.project_code}-ППР

| | |
|---|---|
| **Заказчик** | {input.customer.name} |
| **Подрядчик** | {input.contractor.name} |
| **Разработчик ППР** | {input.developer.organization} |
| **Главный инженер проекта** | {input.developer.chief_engineer} |
| **Разработчик** | {input.developer.developer} |
| **Должность** | {input.developer.position} |

---
**{input.developer.organization}**
**20__ г.**
"""
    return SectionResult(
        section_id="title_page",
        title="Титульный лист",
        content=content,
        page_count=1,
    )
