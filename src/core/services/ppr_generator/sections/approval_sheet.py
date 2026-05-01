"""PPR Generator — Лист согласования."""
from ..schemas import PPRInput, SectionResult


def generate_approval_sheet(input: PPRInput) -> SectionResult:
    content = f"""## Лист согласования

Проект производства работ по объекту: **{input.object_name}**
Шифр: **{input.project_code}-ППР**

| Должность | ФИО | Подпись | Дата |
|-----------|-----|---------|------|
| Главный инженер проекта | {input.developer.chief_engineer} | ________ | __.__.20__ |
| Разработчик ППР | {input.developer.developer} | ________ | __.__.20__ |
| Руководитель организации | _______________ | ________ | __.__.20__ |
| Представитель заказчика | _______________ | ________ | __.__.20__ |
| Ответственный за ОТ | _______________ | ________ | __.__.20__ |

---
**ППР утверждён и согласован в установленном порядке.**
"""
    return SectionResult(
        section_id="approval_sheet",
        title="Лист согласования",
        content=content,
        page_count=1,
    )
