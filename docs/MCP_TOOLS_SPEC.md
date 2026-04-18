# АСД v11.0 — СПЕЦИФИКАЦИЯ MCP ИНСТРУМЕНТОВ

**Дата:** 17 апреля 2026
**Статус:** Активная разработка (Package 1 завершен)

---

## 1. ОБЗОР

*   Общее количество инструментов: **23** (основные модули ASD).
*   Агенты: Hermes (PM), ПТО, Сметчик, Юрист, Закупщик, Логист, Делопроизводитель (Архив).

---

## 2. ЮРИСТ (6 инструментов)

### 2.1. asd_upload_document

**Описание:** Загрузка и парсинг документа. Сохранение в LightRAG.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `file_path` | string | ✅ | Путь к файлу (PDF, XLSX, JSON) |
| `doc_type` | string | ✅ | Тип: "contract" \| "pd" \| "rd" \| "vor" \| "estimate" \| "correspondence" \| "act" |
| `project_id` | string | ❌ | ID проекта (если не указан — создаётся новый) |
| `description` | string | ❌ | Описание документа |

**Возвращает:**
```json
{
  "success": true,
  "document_id": 42,
  "project_id": "prichaly",
  "file_name": "contract_РТМ-066.pdf",
  "file_size": 15728640,
  "page_count": 150,
  "is_scan": false,
  "chunks_count": 38,
  "parsed_text_length": 185000,
  "parse_time_seconds": 12.5,
  "message": "Документ загружен и обработан"
}
```

**Ошибки:**
| Код | Когда |
|-----|-------|
| `FILE_NOT_FOUND` | Файл не существует |
| `UNSUPPORTED_FORMAT` | Не PDF/XLSX/JSON |
| `PARSER_ERROR` | Ошибка парсинга |
| `DB_ERROR` | Ошибка записи в БД |

---

### 2.2. asd_analyze_contract

**Описание:** Полная юридическая экспертиза договора. Map-Reduce + БЛС + LightRAG + CrossChecker.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `document_id` | int | ❌ | ID документа (если уже загружен) |
| `file_path` | string | ❌ | Путь к файлу (если ещё не загружен) |
| `enable_thinking` | bool | ❌ | Включить thinking mode (по умолч. true) |
| `check_bls` | bool | ❌ | Проверка по БЛС (по умолч. true) |
| `normative_search` | bool | ❌ | Нормативный поиск (по умолч. true) |

**Возвращает:**
```json
{
  "success": true,
  "document_id": 42,
  "analysis": {
    "total_pages": 150,
    "total_chunks": 38,
    "analysis_time_seconds": 245,
    "traps_found": [
      {
        "trap_id": 7,
        "severity": "high",
        "category": "payment",
        "description": "Заказчик вправе изменить объём работ без согласования цены",
        "location": "Раздел 4, п. 4.3, страница 23",
        "original_text": "Заказчик имеет право в одностороннем порядке...",
        "law_reference": "ст. 743 ГК РФ",
        "recommendation": "Требуется письменное согласование изменения объёма и цены"
      }
    ],
    "normative_references": [
      {
        "norm": "ст. 743 ГК РФ",
        "title": "Общие правила выполнения работ",
        "relevance": 0.92,
        "snippet": "Подрядчик обязан выполнять работы..."
      }
    ],
    "contradictions": [
      {
        "section_a": "Раздел 3 (Сроки)",
        "section_b": "Раздел 7 (Ответственность)",
        "description": "Противоречие в сроках приёмки работ"
      }
    ],
    "summary": {
      "total_traps": 12,
      "high_severity": 4,
      "medium_severity": 5,
      "low_severity": 3,
      "total_normative_refs": 23,
      "total_contradictions": 2
    }
  }
}
```

**Ошибки:**
| Код | Когда |
|-----|-------|
| `DOCUMENT_NOT_FOUND` | document_id не найден |
| `LLM_ERROR` | Ошибка вызова LLM |
| `PARSER_ERROR` | Ошибка парсинга |
| `DB_ERROR` | Ошибка БД |

---

### 2.3. asd_normative_search

**Описание:** Поиск по нормативной базе (LightRAG Graph+Vector + RRF).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `query` | string | ✅ | Поисковый запрос |
| `k` | int | ❌ | Количество результатов (по умолч. 10) |
| `project_id` | string | ❌ | Фильтр по проекту |
| `norm_type` | string | ❌ | Тип нормы: "gk" \| "grk" \| "fz44" \| "fz223" \| "sp" \| "gost" \| "all" |

**Возвращает:**
```json
{
  "success": true,
  "query": "штраф за просрочку работ",
  "results": [
    {
      "source": "ст. 333 ГК РФ",
      "title": "Уменьшение неустойки",
      "text": "Если подлежащая уплате неустойка явно несоразмерна последствиям нарушения обязательства...",
      "relevance": 0.94,
      "vector_score": 0.91,
      "graph_score": 0.97,
      "document_id": null,
      "chunk_position": null
    },
    {
      "source": "ст. 28.4 ФЗ-44",
      "title": "Ответственность заказчика",
      "text": "...",
      "relevance": 0.87,
      "document_id": null
    }
  ],
  "total_found": 2,
  "search_time_seconds": 1.2
}
```

---

### 2.4. asd_generate_protocol

**Описание:** Генерация протокола разногласий (DOCX).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `document_id` | int | ✅ | ID анализируемого договора |
| `mode` | string | ❌ | "protocol" \| "full" (по умолч. "protocol") |
| `custom_edits` | list[dict] | ❌ | Пользовательские редакции пунктов |

**custom_edits формат:**
```json
[
  {
    "section": "Раздел 4, п. 4.3",
    "original": "Заказчик имеет право в одностороннем порядке...",
    "proposed": "Изменение объёма работ допускается только по письменному согласованию..."
  }
]
```

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/protocols/protocol_contract_42_20260413.docx",
  "sections_count": 12,
  "disagreements_count": 8,
  "message": "Протокол разногласий сгенерирован"
}
```

---

### 2.5. asd_generate_claim

**Описание:** Генерация претензии при неоплате выполненных работ (СМР).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `contract_id` | int | ✅ | ID контракта |
| `debt_amount` | float | ✅ | Сумма задолженности |
| `works_description` | string | ✅ | Описание выполненных работ |
| `works_completed_date` | string | ❌ | Дата завершения работ (ISO формат) |
| `payment_deadline` | string | ❌ | Срок оплаты по договору |
| `penalty` | float | ❌ | Неустойка (если рассчитана) |

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/claims/claim_contract_42_20260413.docx",
  "debt_amount": 1500000.00,
  "penalty_amount": 125000.00,
  "total_amount": 1625000.00,
  "claim_deadline": "2026-05-13",
  "message": "Претензия сгенерирована. Срок ответа: 30 дней"
}
```

---

### 2.6. asd_generate_lawsuit

**Описание:** Генерация искового заявления в арбитражный суд.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `contract_id` | int | ✅ | ID контракта |
| `claim_id` | int | ✅ | ID претензии (должна быть неудовлетворена) |
| `court` | string | ❌ | Подсудность (если не указана — берётся из договора) |
| `additional_amounts` | list[dict] | ❌ | Дополнительные суммы (судебные расходы, экспертизы) |

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/lawsuits/lawsuit_contract_42_20260413.docx",
  "court": "Арбитражный суд г. Москвы",
  "plaintiff": "ООО «КСК №1»",
  "defendant": "ФКУ «Ространсмодернизация»",
  "claim_amount": 1625000.00,
  "attachments": [
    "Копия договора РТМ-066/22",
    "Акты выполненных работ (КС-2)",
    "Справка о стоимости (КС-3)",
    "Претензия от 13.04.2026",
    "Доказательства отправки претензии"
  ],
  "message": "Исковое заявление сгенерировано. Проверьте перед подачей."
}
```

---

## 3. ПТО-ИНЖЕНЕР (4 инструмента)

### 3.1. asd_vor_check

**Описание:** Сверка ВОР с проектной документацией. Построчное сравнение.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `vor_file` | string | ✅ | Путь к файлу ВОР (полученного) |
| `pd_file` | string | ✅ | Путь к файлу ПД/РД (из проекта) |
| `fuzzy_threshold` | float | ❌ | Порог fuzzy matching (по умолч. 0.85) |

**Возвращает:**
```json
{
  "success": true,
  "vor_items": 12270,
  "pd_items": 11850,
  "matches": 11200,
  "discrepancies": [
    {
      "vor_item": {
        "name": "Устройство щебёночной подготовки",
        "volume": 1500.0,
        "unit": "м³"
      },
      "pd_item": {
        "name": "Устройство щебёночной подготовки",
        "volume": 1200.0,
        "unit": "м³"
      },
      "diff_volume": 300.0,
      "diff_percent": 25.0,
      "diff_type": "volume_mismatch"
    }
  ],
  "unaccounted_in_vor": [
    {"name": "Монтаж ограждения", "volume": 200, "unit": "м²"}
  ],
  "unaccounted_in_pd": [
    {"name": "Демонтаж временных сооружений", "volume": 1, "unit": "компл."}
  ],
  "summary": {
    "total_discrepancies": 23,
    "volume_increase_percent": 15.3,
    "unaccounted_in_vor_count": 5,
    "unaccounted_in_pd_count": 3
  }
}
```

---

### 3.2. asd_pd_analysis

**Описание:** Комплексный анализ проектной документации. Выявление коллизий и неучтённых объёмов.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `pd_files` | list[string] | ✅ | Список файлов ПД (АР, КР, ИОС, и т.д.) |
| `check_completeness` | bool | ❌ | Проверка комплектности разделов (по умолч. true) |
| `check_collisions` | bool | ❌ | Поиск коллизий (по умолч. true) |
| `check_unaccounted` | bool | ❌ | Поиск неучтённых объёмов (по умолч. true) |

**Возвращает:**
```json
{
  "success": true,
  "files_analyzed": 12,
  "total_pages": 2450,
  "analysis_time_seconds": 420,
  "completeness": {
    "required_sections": ["АР", "КР", "ИОС1", "ИОС2", "ИОС3", "ПОС", "ПМ"],
    "present": ["АР", "КР", "ИОС1", "ИОС2", "ПОС"],
    "missing": ["ИОС3", "ПМ"],
    "completeness_percent": 71.4
  },
  "collisions": [
    {
      "type": "spatial",
      "section_a": "КР (лист 45)",
      "section_b": "ИОС1 (лист 12)",
      "description": "Труба ventilation пересекает несущую балку на отм. +3.600",
      "severity": "high"
    }
  ],
  "unaccounted_volumes": [
    {
      "work": "Гидроизоляция фундамента",
      "in_vor": false,
      "in_pd": true,
      "volume": 450.0,
      "unit": "м²"
    }
  ],
  "summary": {
    "missing_sections": 2,
    "collisions_found": 3,
    "unaccounted_volumes": 5,
    "risk_level": "medium"
  }
}
```

---

### 3.3. asd_generate_act

**Описание:** Генерация акта (АОСР, входной контроль, скрытые работы).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `act_type` | string | ✅ | "aosr" \| "incoming_control" \| "hidden_works" \| "inspection" |
| `work_description` | string | ✅ | Описание работ |
| `contract_id` | int | ❌ | ID контракта |
| `project_id` | string | ❌ | ID проекта |
| `representatives` | list[dict] | ❌ | Представители (подписанты) |
| `materials` | list[dict] | ❌ | Использованные материалы |
| `drawings` | list[string] | ❌ | Чертежи/схемы (приложения) |
| `custom_data` | dict | ❌ | Произвольные данные для акта |

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/acts/aosr_20260413_001.docx",
  "act_type": "aosr",
  "act_number": 1,
  "act_date": "2026-04-13",
  "message": "Акт освидетельствования скрытых работ сгенерирован"
}
```

---

### 3.4. asd_id_completeness

**Описание:** Проверка комплектности исполнительной документации.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `work_items` | list[dict] | ✅ | Список выполненных работ |
| `project_id` | string | ❌ | ID проекта |
| `contract_type` | string | ❌ | Тип контракта (для определения требований) |

**Возвращает:**
```json
{
  "success": true,
  "work_items_count": 15,
  "required_documents": {
    "aosr": {"required": 15, "present": 12, "missing": 3},
    "incoming_control_acts": {"required": 8, "present": 8, "missing": 0},
    "executive_schemes": {"required": 15, "present": 10, "missing": 5},
    "material_passports": {"required": 20, "present": 18, "missing": 2},
    "lab_tests": {"required": 5, "present": 3, "missing": 2}
  },
  "missing_items": [
    {"type": "aosr", "work": "Бетонирование ростверка №3", "required_by": "РД-11-02-2006"},
    {"type": "executive_scheme", "work": "Монтаж колонн К-1..К-6", "required_by": "СП 48.13330"}
  ],
  "completeness_percent": 78.5,
  "message": "Комплектность ИД: 78.5%. Не хватает 12 документов."
}
```

---

## 4. ИНЖЕНЕР-СМЕТЧИК (3 инструмента)

### 4.1. asd_estimate_compare

**Описание:** Сверка ВОР со сметным расчётом.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `vor_file` | string | ✅ | Путь к файлу ВОР |
| `estimate_file` | string | ✅ | Путь к файлу сметы (PDF/Excel) |
| `price_base` | string | ❌ | База расценок: "ФЕР" \| "ГЭСН" \| "ТЕР" |

**Возвращает:**
```json
{
  "success": true,
  "vor_items": 156,
  "estimate_items": 148,
  "matches": 140,
  "discrepancies": [
    {
      "vor_item": {"name": "Бетонирование", "volume": 500, "unit": "м³"},
      "estimate_item": {"name": "Бетонирование", "volume": 450, "unit": "м³"},
      "diff_volume": 50,
      "diff_percent": 11.1
    }
  ],
  "vor_total": 4200000.00,
  "estimate_total": 3850000.00,
  "diff_total": 350000.00,
  "diff_percent": 9.1,
  "summary": {
    "total_discrepancies": 8,
    "overestimate": true,
    "risk_level": "medium"
  }
}
```

---

### 4.2. asd_create_lsr

**Описание:** Создание локального сметтного расчёта (ЛСР) по ВОРу.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `vor_file` | string | ✅ | Путь к файлу ВОР (проверенного) |
| `price_base` | string | ✅ | "ФЕР-2024" \| "ГЭСН-2024" \| "ТЕР-2024" \| "рынок" |
| `project_id` | string | ❌ | ID проекта |
| `include_materials` | bool | ❌ | Включить материалы (по умолч. true) |
| `include_machines` | bool | ❌ | Включить машины (по умолч. true) |

**Возвращает:**
```json
{
  "success": true,
  "lsr_id": 7,
  "items_count": 156,
  "total_direct_costs": 3200000.00,
  "materials_cost": 800000.00,
  "machines_cost": 200000.00,
  "overhead_percent": 15.0,
  "profit_percent": 8.0,
  "grand_total": 4830000.00,
  "price_base": "ФЕР-2024",
  "file_path": "/Users/oleg/MAC_ASD/data/exports/estimates/lsr_7_20260413.xlsx",
  "message": "ЛСР готова. 156 позиций, итого: 4.83 млн руб."
}
```

---

### 4.3. asd_supplement_estimate

**Описание:** Осмечивание допсоглашения (дополнительные объёмы).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `supplement_vor` | string | ✅ | Путь к новому ВОР допсоглашения |
| `base_contract_id` | int | ✅ | ID базового контракта |
| `price_base` | string | ❌ | База расценок (по умолч. как в базовом контракте) |

**Возвращает:**
```json
{
  "success": true,
  "supplement_id": 3,
  "additional_items": 42,
  "additional_cost": 850000.00,
  "base_contract_cost": 5650000.00,
  "increase_percent": 15.0,
  "lsr_file": "/Users/oleg/MAC_ASD/data/exports/estimates/supplement_3_lsr.xlsx",
  "comparison": {
    "new_works": 12,
    "increased_volumes": 18,
    "changed_prices": 12
  },
  "message": "Допсоглашение осмечено: +850 тыс. руб., +15% от контракта"
}
```

---

## 5. ДЕЛОПРОИЗВОДИТЕЛЬ (4 инструмента)

### 5.1. asd_register_document

**Описание:** Регистрация входящего документа.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `file_path` | string | ✅ | Путь к документу |
| `source` | string | ✅ | Отправитель (название организации) |
| `doc_type` | string | ✅ | "letter" \| "request" \| "claim" \| "notice" \| "contract" \| "other" |
| `project_id` | string | ❌ | ID проекта |
| `deadline` | string | ❌ | Срок ответа (ISO дата, если известен) |

**Возвращает:**
```json
{
  "success": true,
  "registration_id": 127,
  "registration_number": "ВХ-2026-127",
  "registration_date": "2026-04-13",
  "source": "ФКУ «Ространсмодернизация»",
  "doc_type": "letter",
  "deadline": "2026-04-27",
  "days_remaining": 10,
  "message": "Документ зарегистрирован. Срок ответа: 10 рабочих дней"
}
```

---

### 5.2. asd_generate_letter

**Описание:** Генерация письма, уведомления или заявки.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `letter_type` | string | ✅ | "notification" \| "request" \| "application" \| "claim" \| "inquiry" |
| `context` | string | ✅ | Содержание/тема письма |
| `recipient` | string | ✅ | Получатель |
| `contract_id` | int | ❌ | ID контракта (для реквизитов) |
| `project_id` | string | ❌ | ID проекта |
| `urgency` | string | ❌ | "normal" \| "urgent" (по умолч. "normal") |
| `attachments` | list[string] | ❌ | Вложения |

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/letters/letter_20260413_001.docx",
  "letter_type": "notification",
  "recipient": "ФКУ «Ространсмодернизация»",
  "subject": "Уведомление о начале работ по допсоглашению №3",
  "message": "Письмо сгенерировано. Проверьте и отправьте."
}
```

---

### 5.3. asd_prepare_shipment

**Описание:** Подготовка пакета документов для отправки Заказчику.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `documents` | list[int] | ✅ | Список ID документов для отправки |
| `contract_id` | int | ✅ | ID контракта (для адреса и реквизитов) |
| `shipment_type` | string | ❌ | "id" \| "ks" \| "protocol" \| "claim" \| "other" |
| `cover_letter_text` | string | ❌ | Текст сопроводительного письма (если не генерировать) |

**Возвращает:**
```json
{
  "success": true,
  "shipment_id": 15,
  "cover_letter": "/Users/oleg/MAC_ASD/data/exports/letters/cover_20260413_015.docx",
  "registry": "/Users/oleg/MAC_ASD/data/exports/letters/registry_20260413_015.docx",
  "documents": [
    {"id": 42, "name": "АОСР №15", "type": "act"},
    {"id": 43, "name": "АОСР №16", "type": "act"},
    {"id": 44, "name": "Акт входного контроля №8", "type": "act"}
  ],
  "recipient": {
    "name": "ФКУ «Ространсмодернизация»",
    "address": "г. Москва, ул. Рождественка, д. 5/7, стр. 1",
    "inn": "7701234567",
    "contact": "Иванов И.И."
  },
  "message": "Пакет готов: 3 документа, сопроводительное, реестр"
}
```

---

### 5.4. asd_track_deadlines

**Описание:** Отслеживание сроков ответа по зарегистрированным документам.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `registration_id` | int | ❌ | ID конкретного документа |
| `project_id` | string | ❌ | Фильтр по проекту |
| `status` | string | ❌ | "active" \| "overdue" \| "all" (по умолч. "active") |

**Возвращает:**
```json
{
  "success": true,
  "documents": [
    {
      "registration_id": 127,
      "registration_number": "ВХ-2026-127",
      "source": "ФКУ «Ространсмодернизация»",
      "doc_type": "letter",
      "registered_date": "2026-04-13",
      "deadline": "2026-04-27",
      "days_remaining": 10,
      "status": "active"
    },
    {
      "registration_id": 120,
      "registration_number": "ВХ-2026-120",
      "source": "ООО «СубПодряд»",
      "doc_type": "claim",
      "registered_date": "2026-04-01",
      "deadline": "2026-04-11",
      "days_remaining": -2,
      "status": "overdue"
    }
  ],
  "summary": {
    "total_active": 8,
    "total_overdue": 1,
    "urgent_within_3_days": 2
  }
}
```

---

## 6. ОБЩИЙ (1 инструмент)

### 6.1. asd_get_system_status

**Описание:** Проверка статуса всех компонентов системы.

**Аргументы:** Нет

**Возвращает:**
```json
{
  "success": true,
  "system": "АСД v11.0",
  "components": {
    "ollama": {
      "status": "running",
      "url": "http://localhost:11434",
      "models_loaded": ["gemma-4-31b:q8_0", "bge-m3", "minicpm-v:q4_k_m"],
      "models_total": 3
    },
    "database": {
      "status": "connected",
      "host": "localhost",
      "name": "asd_v11",
      "documents": 156,
      "chunks": 5928,
      "traps": 27
    },
    "memory": {
      "total_gb": 128,
      "used_gb": 82.5,
      "available_gb": 45.5,
      "pressure": "low"
    },
    "modules": {
      "lawyer": "ready",
      "pto": "ready",
      "estimator": "ready",
      "clerk": "ready"
    }
  },
  "statistics": {
    "total_documents": 156,
    "total_projects": 2,
    "total_contracts": 5,
    "total_acts_generated": 42,
    "total_letters": 18,
    "total_claims": 1,
    "total_lawsuits": 0
  }
}
```

---

## 7. ЗАКУПЩИК (2 инструмента)

### 7.1. asd_tender_search

**Описание:** Поиск тендеров по заданным критериям (Telegram/Web).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `keywords` | list[string] | ✅ | Ключевые слова |
| `region` | string | ❌ | Регион |
| `max_nmck` | float | ❌ | Лимит цены лота |

**Возвращает:** Список найденных лотов с метаданными.

---

### 7.2. asd_analyze_lot_profitability

**Описание:** Анализ НМЦК и расчет потенциальной прибыли.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `lot_id` | string | ✅ | ID лота/тендера |
| `pd_summary` | dict | ❌ | Сводка по ПД (если есть) |

---

## 8. ЛОГИСТ (3 инструмента)

### 8.1. asd_source_vendors

**Описание:** Поиск и квалификация поставщиков по категориям.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `category` | string | ✅ | Категория (Металл, Бетон, Песок...) |
| `region` | string | ❌ | Регион доставки |

---

### 8.2. asd_add_price_list

**Описание:** Загрузка и парсинг прайс-листа поставщика.

---

### 8.3. asd_compare_quotes

**Описание:** Сравнение коммерческих предложений.

---

### 7.3. asd_parse_price_list

**Описание:** Парсинг и извлечение данных из входящих коммерческих предложений (PDF, Excel) от поставщиков.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `file_path` | string | ✅ | Путь к прайс-листу или КП |
| `rfq_batch_id` | int | ❌ | Привязка к запросу |

**Возвращает:**
```json
{
  \"success\": true,
  \"vendor_name\": \"ООО 'МеталлСнаб'\",
  \"parsed_items\": 15,
  \"best_matches\": [
    {\"requested\": \"Шпунт Л5-УМ\", \"offered\": \"Шпунт Л5-УМ новый\", \"price\": 120000.00, \"unit\": \"тн\"}
  ],
  \"message\": \"КП успешно спарсено и занесено в сравнение.\"
}
```

---

## 8. ОБЩИЕ ПРАВИЛА

### 7.1. Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "success": false,
  "error_code": "LLM_ERROR",
  "message": "Ошибка вызова LLM: модель gemma-4-31b не отвечает",
  "details": {
    "model": "gemma-4-31b",
    "timeout_seconds": 300,
    "retries": 2
  }
}
```

### 7.2. Коды ошибок

| Код | Описание | Действие |
|-----|----------|----------|
| `FILE_NOT_FOUND` | Файл не найден | Проверить путь |
| `UNSUPPORTED_FORMAT` | Неподдерживаемый формат | Проверить тип файла |
| `DOCUMENT_NOT_FOUND` | Документ не найден в БД | Проверить document_id |
| `PARSER_ERROR` | Ошибка парсинга | Проверить целостность файла |
| `LLM_ERROR` | Ошибка LLM | Проверить Ollama |
| `DB_ERROR` | Ошибка базы данных | Проверить PostgreSQL |
| `VALIDATION_ERROR` | Ошибка валидации аргументов | Проверить аргументы |
| `NOT_FOUND` | Ресурс не найден | Проверить ID |
| `MEMORY_CRITICAL` | Критическое использование RAM | Подождать или закрыть задачи |
| `INTERNAL_ERROR` | Внутренняя ошибка | Смотреть логи |

### 7.3. Таймауты инструментов

| Инструмент | Таймаут | Примечание |
|-----------|---------|------------|
| `asd_upload_document` | 120 сек | Зависит от размера PDF |
| `asd_analyze_contract` | 600 сек | Map-Reduce 150 страниц |
| `asd_normative_search` | 30 сек | Быстрый поиск |
| `asd_generate_protocol` | 60 сек | Генерация DOCX |
| `asd_generate_claim` | 60 сек | Генерация DOCX |
| `asd_generate_lawsuit` | 120 сек | Генерация DOCX |
| `asd_vor_check` | 300 сек | Построчное сравнение |
| `asd_pd_analysis` | 600 сек | Комплексный анализ |
| `asd_generate_act` | 30 сек | Генерация DOCX |
| `asd_id_completeness` | 60 сек | Проверка комплектности |
| `asd_estimate_compare` | 300 сек | Сравнение |
| `asd_create_lsr` | 180 сек | Создание ЛСР |
| `asd_supplement_estimate` | 300 сек | Осмечивание |
| `asd_register_document` | 10 сек | Регистрация |
| `asd_generate_letter` | 30 сек | Генерация DOCX |
| `asd_prepare_shipment` | 30 сек | Подготовка пакета |
| `asd_track_deadlines` | 5 сек | SQL запрос |
| `asd_tender_search` | 60 сек | Запрос к API ЕИС/Площадок |
| `asd_send_rfq` | 30 сек | Отправка email |
| `asd_parse_price_list` | 60 сек | Анализ сметы/КП |
| `asd_get_system_status` | 5 сек | Проверка компонентов |

> **Примечание:** Все LLM-вызовы в инструментах осуществляются через LLMEngine (не напрямую к Ollama). Это обеспечивает поддержку профилей (dev_linux/mac_studio) и автоматический fallback.

---

Документ актуализирован. Спецификации инструментов используются при реализации MCP-тулов в Packages 2-10.
