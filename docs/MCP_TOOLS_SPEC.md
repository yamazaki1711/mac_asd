# АСД v12.0 — СПЕЦИФИКАЦИЯ MCP ИНСТРУМЕНТОВ

**Дата:** 3 мая 2026
**Статус:** Package 5 ✅ (Evidence Graph, Inference Engine, ProjectLoader), Package 11 ✅ (Chain Builder, HITL, Journal Reconstructor), Artifact Store ✅, Legal Service ✅ (FZ-44/223 lookup, RAG, NormativeGuard), Vision Cascade ✅ (Stage 1/2, Gemma 4 31B Cloud VLM fallback), Auditor ✅, IDRequirementsRegistry ✅, WorkEntry ✅

---

## 1. ОБЗОР

Архитектура АСД v12.0 использует модель **Gemma 4 31B 4-bit** (MLX-VLM, 128K контекст) для пяти рабочих агентов (Юрист, ПТО, Сметчик, Закупщик, Логист), работающих через разделяемую память (shared memory) LLMEngine. Агент **Делопроизводитель** использует **Gemma 4 E4B 4-bit** (8K контекст). Агент **Руководитель проекта** (PM/руководитель) использует **Llama 3.3 70B 4-bit** для стратегического планирования и оркестрации. Gemma 4 31B (MLX-VLM) обеспечивает встроенную vision-поддержку для OCR сложных документов без отдельной vision-модели.

*   Общее количество инструментов: **82** (74 в mcp_servers/asd_core/, включая Evidence Graph, Chain Builder, HITL, Journal Reconstructor, Artifact Store, Legal Service, Vision Cascade, WorkEntry; +8 служебных MCP server-тулов).
*   Агенты: Руководитель проекта (PM, Llama 3.3 70B), ПТО, Сметчик, Юрист, Закупщик, Логист (все — Gemma 4 31B), Делопроизводитель (Gemma 4 E4B), Аудитор (rule-based).
*   Embeddings: **bge-m3-mlx-4bit** (1024-мерные векторы).
*   Vision: встроена в **Gemma 4 31B MLX-VLM**.

---

## 2. ЮРИСТ (6 инструментов)

### 2.1. asd_upload_document

**Описание:** Загрузка и парсинг документа. Сохранение в LightRAG. Поддерживаемые форматы: PDF (включая сканы через OCR-конвейер), XLSX, JSON, DOCX. PDF v3 генерируется через чистый ReportLab + TrueType-шрифты.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `file_path` | string | ✅ | Путь к файлу (PDF, XLSX, JSON, DOCX) |
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
  "ocr_tier_used": "tier1_pytesseract",
  "message": "Документ загружен и обработан"
}
```

**Ошибки:**
| Код | Когда |
|-----|-------|
| `FILE_NOT_FOUND` | Файл не существует |
| `UNSUPPORTED_FORMAT` | Не PDF/XLSX/JSON/DOCX |
| `PARSER_ERROR` | Ошибка парсинга |
| `DB_ERROR` | Ошибка записи в БД |

---

### 2.2. asd_analyze_contract

**Описание:** Полная юридическая экспертиза договора. Поддерживает два режима: **Quick Review** (быстрый просмотр, одиночный вызов Gemma 4 31B, подходит для коротких документов <6K символов) и **Map-Reduce** (полный анализ длинных договоров ≥6K символов с разбиением на чанки, параллельной обработкой и синтезом). БЛС-проверка охватывает 61 ловушка в 10 категориях (payment, penalty, acceptance, scope, warranty, subcontractor, liability, corporate_policy, termination, insurance). Результаты обогащаются нормативным поиском через LightRAG Graph+Vector и кросс-проверкой (CrossChecker).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `document_id` | int | ❌ | ID документа (если уже загружен) |
| `file_path` | string | ❌ | Путь к файлу (если ещё не загружен) |
| `review_mode` | string | ❌ | "quick" \| "full" (по умолч. "full"; "quick" для <6K символов) |
| `enable_thinking` | bool | ❌ | Включить thinking mode (по умолч. true) |
| `check_bls` | bool | ❌ | Проверка по БЛС 61 ловушка (по умолч. true) |
| `normative_search` | bool | ❌ | Нормативный поиск (по умолч. true) |

**Возвращает:**
```json
{
  "success": true,
  "document_id": 42,
  "analysis": {
    "findings": [
      {
        "category": "trap",
        "severity": "high",
        "clause_ref": "Раздел 4, п. 4.3",
        "legal_basis": "ст. 743 ГК РФ",
        "issue": "Заказчик вправе изменить объём работ без согласования цены",
        "recommendation": "Требуется письменное согласование изменения объёма и цены",
        "auto_fixable": true,
        "blc_match": {
          "blc_id": 7,
          "blc_name": "Одностороннее изменение объёма",
          "blc_severity": "high"
        }
      },
      {
        "category": "compliance",
        "severity": "critical",
        "clause_ref": "Раздел 6, п. 6.1",
        "legal_basis": "ст. 708 ГК РФ, ФЗ-44 ст. 34",
        "issue": "Отсутствует условие о порядке и сроках оплаты",
        "recommendation": "Добавить условие о сроках оплаты в соответствии с ФЗ-44",
        "auto_fixable": false,
        "blc_match": null
      },
      {
        "category": "risk",
        "severity": "medium",
        "clause_ref": "Раздел 9, п. 9.2",
        "legal_basis": "ст. 395 ГК РФ",
        "issue": "Неустойка подрядчика выше законной в 3 раза",
        "recommendation": "Снизить размер неустойки до двукратной ставки ЦБ",
        "auto_fixable": true,
        "blc_match": {
          "blc_id": 12,
          "blc_name": "Завышенная неустойка подрядчика",
          "blc_severity": "medium"
        }
      },
      {
        "category": "ambiguity",
        "severity": "low",
        "clause_ref": "Раздел 3, п. 3.1",
        "legal_basis": null,
        "issue": "Неопределённый срок начала работ — «в разумный срок»",
        "recommendation": "Указать конкретную дату или привязку к событию",
        "auto_fixable": false,
        "blc_match": null
      },
      {
        "category": "omission",
        "severity": "high",
        "clause_ref": null,
        "legal_basis": "ФЗ-44 ст. 34 ч. 1",
        "issue": "Отсутствует условие об ответственности заказчика за неисполнение",
        "recommendation": "Добавить условие об ответственности заказчика",
        "auto_fixable": true,
        "blc_match": {
          "blc_id": 3,
          "blc_name": "Отсутствие ответственности заказчика",
          "blc_severity": "high"
        }
      }
    ],
    "verdict": "approved_with_comments",
    "contradictions": [
      {
        "section_a": "Раздел 3 (Сроки)",
        "section_b": "Раздел 7 (Ответственность)",
        "description": "Противоречие в сроках приёмки работ"
      }
    ],
    "normative_refs": [
      {
        "norm": "ст. 743 ГК РФ",
        "title": "Общие правила выполнения работ",
        "relevance": 0.92,
        "snippet": "Подрядчик обязан выполнять работы..."
      },
      {
        "norm": "ст. 708 ГК РФ",
        "title": "Сроки выполнения работ",
        "relevance": 0.88,
        "snippet": "Указываются начальный и конечный сроки..."
      }
    ],
    "summary": "Договор содержит 12 замечаний (4 критических/высоких, 5 средних, 3 низких). Выявлены 2 противоречия и 58 совпадений с БЛС. Рекомендуется согласование перед подписанием.",
    "analysis_metadata": {
      "duration_seconds": 245,
      "model": "gemma4-31b",
      "engine": "map_reduce_v2",
      "document_chars": 185000,
      "review_type": "full",
      "map_chunks": 12,
      "reduce_iterations": 1,
      "timestamp": "2026-04-20T14:35:12Z"
    }
  }
}
```

**Режимы работы:**

| Режим | Условие | LLM-вызовы | Время |
|-------|---------|-------------|-------|
| Quick Review | Документ <6K символов | 1 вызов Gemma 4 31B | ~30 сек |
| Map-Reduce | Документ ≥6K символов | N чанков + Reduce | ~4-10 мин |

**Ошибки:**
| Код | Когда |
|-----|-------|
| `DOCUMENT_NOT_FOUND` | document_id не найден |
| `LLM_ERROR` | Ошибка вызова LLM (Gemma 4 31B не отвечает) |
| `PARSER_ERROR` | Ошибка парсинга |
| `DB_ERROR` | Ошибка БД |

---

### 2.3. asd_normative_search

**Описание:** Поиск по нормативной базе (LightRAG Graph+Vector + RRF). Использует embeddings bge-m3 для векторного поиска и графовые связи LightRAG для контекстного расширения. Результаты ранжируются через Reciprocal Rank Fusion (RRF), объединяющий векторные и графовые оценки.

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

**Описание:** Генерация протокола разногласий (DOCX) с полными реквизитами сторон. Включает структуру **ProtocolPartyInfo** — извлечённые из договора наименования, ИНН, ОГРН, юридические адреса, расчётные счета, БИК, подписанты и должности как для Заказчика, так и для Подрядчика. Протокол формируется на базе результатов `asd_analyze_contract` с автозаполнением формулировок из БЛС. Поддерживает пользовательские редакции пунктов через параметр `custom_edits`.

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/protocols/protocol_contract_42_20260420.docx",
  "sections_count": 12,
  "disagreements_count": 8,
  "parties": {
    "customer": {
      "name": "ФКУ «Ространсмодернизация»",
      "inn": "7701234567",
      "ogrn": "1037701234567",
      "legal_address": "г. Москва, ул. Рождественка, д. 5/7, стр. 1",
      "checking_account": "40501810000001234567",
      "bank": "Отделение 1 Московского ГТУ Банка России",
      "bik": "044583001",
      "signatory": "Петров А.В.",
      "position": "Руководитель филиала"
    },
    "contractor": {
      "name": "ООО «КСК №1»",
      "inn": "7701987654",
      "ogrn": "1027701987654",
      "legal_address": "г. Москва, ул. Строителей, д. 15, оф. 3",
      "checking_account": "40702810900001234567",
      "bank": "ПАО «Сбербанк»",
      "bik": "044525225",
      "signatory": "Сидоров И.П.",
      "position": "Генеральный директор"
    }
  },
  "protocol_party_info_extracted": true,
  "message": "Протокол разногласий сгенерирован с реквизитами сторон"
}
```

**Ошибки:**
| Код | Когда |
|-----|-------|
| `DOCUMENT_NOT_FOUND` | document_id не найден |
| `LLM_ERROR` | Ошибка извлечения ProtocolPartyInfo |
| `DOCX_ERROR` | Ошибка генерации DOCX |

---

### 2.5. asd_generate_claim

**Описание:** Генерация претензии при неоплате выполненных работ (СМР). Автоматически извлекает реквизиты сторон (ProtocolPartyInfo) из договора, рассчитывает неустойку по ставке ЦБ РФ и формирует DOCX-документ. Претензия содержит ссылки на конкретные статьи ГК РФ (ст. 708, ст. 746, ст. 395) и нормы ФЗ-44.

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/claims/claim_contract_42_20260420.docx",
  "debt_amount": 1500000.00,
  "penalty_amount": 125000.00,
  "total_amount": 1625000.00,
  "claim_deadline": "2026-05-20",
  "parties": {
    "customer": {
      "name": "ФКУ «Ространсмодернизация»",
      "inn": "7701234567"
    },
    "contractor": {
      "name": "ООО «КСК №1»",
      "inn": "7701987654"
    }
  },
  "message": "Претензия сгенерирована. Срок ответа: 30 дней"
}
```

---

### 2.6. asd_generate_lawsuit

**Описание:** Генерация искового заявления в арбитражный суд. Формируется на базе неудовлетворённой претензии с автоматическим извлечением всех юридически значимых данных из контракта и претензии. Включает ProtocolPartyInfo для истца и ответчика, расчёт штрафных санкций, судебных расходов и ссылок на процессуальные нормы (АПК РФ).

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/lawsuits/lawsuit_contract_42_20260420.docx",
  "court": "Арбитражный суд г. Москвы",
  "plaintiff": "ООО «КСК №1»",
  "defendant": "ФКУ «Ространсмодернизация»",
  "claim_amount": 1625000.00,
  "attachments": [
    "Копия договора РТМ-066/22",
    "Акты выполненных работ (КС-2)",
    "Справка о стоимости (КС-3)",
    "Претензия от 20.04.2026",
    "Доказательства отправки претензии"
  ],
  "message": "Исковое заявление сгенерировано. Проверьте перед подачей."
}
```

---

## 3. ПТО-ИНЖЕНЕР (4 инструмента)

Все инструменты ПТО-инженера работают через LLMEngine с моделью **Gemma 4 31B** (MLX-VLM, 128K контекст). Vision-поддержка встроена в основную модель для OCR сложных сканов (таблицы, печати, рукописные пометки).

### 3.1. asd_vor_check

**Описание:** Сверка ВОР с проектной документацией. Построчное сравнение позиций с fuzzy matching. Выявляет расхождения в объёмах, неучтённые работы и позиции, отсутствующие в ВОР. Результаты обогащаются контекстным анализом через Gemma 4 31B для определения критичности расхождений.

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

**Описание:** Комплексный анализ проектной документации. Выявление коллизий между разделами (АР/КР/ИОС), неучтённых объёмов и проверка комплектности разделов по ГОСТ Р 21.1101-2013. OCR сканов выполняется через vision-возможности Gemma 4 31B (MLX-VLM) при обнаружении сложных графических элементов.

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

**Описание:** Генерация акта (АОСР, входной контроль, скрытые работы, освидетельствование). Формирует DOCX по шаблону с автозаполнением реквизитов из контракта и ProtocolPartyInfo. Данные о представителях и материалах обогащаются через Gemma 4 31B.

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/acts/aosr_20260420_001.docx",
  "act_type": "aosr",
  "act_number": 1,
  "act_date": "2026-04-20",
  "message": "Акт освидетельствования скрытых работ сгенерирован"
}
```

---

### 3.4. asd_id_completeness

**Описание:** Проверка комплектности исполнительной документации. Сопоставляет выполненные работы с перечнем требуемых документов (АОСР, акты входного контроля, исполнительные схемы, паспорта материалов, лабораторные испытания) по ГОСТ Р и РД-11-02-2006. Руководитель проекта использует результаты этого инструмента для отслеживания delta (разрыва) между имеющейся и требуемой ИД.

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
  "delta": 12,
  "message": "Комплектность ИД: 78.5%. Не хватает 12 документов."
}
```

---

## 4. ИНЖЕНЕР-СМЕТЧИК (3 инструмента)

Все инструменты Сметчика работают через LLMEngine с моделью **Gemma 4 31B**. Сметные расчёты выполняются на базе ФЕР/ГЭСН/ТЕР с корректировкой на текущие индексы.

### 4.1. asd_estimate_compare

**Описание:** Сверка ВОР со сметным расчётом. Выявляет расхождения в объёмах и ценах между ведомостью объёмов работ и локальным сметным расчётом. Каждое расхождение классифицируется по степени риска (low/medium/high) с помощью Gemma 4 31B.

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

**Описание:** Создание локального сметного расчёта (ЛСР) по ВОРу. Автоматически подбирает расценки из базы ФЕР/ГЭСН/ТЕР, рассчитывает прямые затраты, накладные расходы, сметную прибыль и итоговую стоимость. Результат сохраняется в XLSX.

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/estimates/lsr_7_20260420.xlsx",
  "message": "ЛСР готова. 156 позиций, итого: 4.83 млн руб."
}
```

---

### 4.3. asd_supplement_estimate

**Описание:** Осмечивание допсоглашения (дополнительные объёмы). Сравнивает новый ВОР допсоглашения с базовым контрактом, определяет дополнительные работы, увеличенные объёмы и изменившиеся цены. Автоматически формирует сравнительную таблицу и расчёт стоимости допсоглашения.

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

Все инструменты Делопроизводителя работают через LLMEngine с моделью **Gemma 4 E4B 4-bit** (8K контекст).

### 5.1. asd_register_document

**Описание:** Регистрация входящего документа с автоматическим определением типа, срока ответа и привязкой к проекту. Система отслеживает дедлайны и уведомляет Руководитель проекта о приближающихся просрочках.

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
  "registration_date": "2026-04-20",
  "source": "ФКУ «Ространсмодернизация»",
  "doc_type": "letter",
  "deadline": "2026-05-04",
  "days_remaining": 10,
  "message": "Документ зарегистрирован. Срок ответа: 10 рабочих дней"
}
```

---

### 5.2. asd_generate_letter

**Описание:** Генерация письма, уведомления или заявки. Формирует DOCX с реквизитами из ProtocolPartyInfo и ссылками на нормы ГК РФ / ФЗ-44. Gemma 4 31B генерирует юридически корректный текст на основе контекста и типа письма.

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
  "file_path": "/Users/oleg/MAC_ASD/data/exports/letters/letter_20260420_001.docx",
  "letter_type": "notification",
  "recipient": "ФКУ «Ространсмодернизация»",
  "subject": "Уведомление о начале работ по допсоглашению №3",
  "message": "Письмо сгенерировано. Проверьте и отправьте."
}
```

---

### 5.3. asd_prepare_shipment

**Описание:** Подготовка пакета документов для отправки Заказчику. Формирует сопроводительное письмо, реестр и полный комплект документов. Использует ProtocolPartyInfo для заполнения адресных и платёжных реквизитов. Фиксирует юридически значимый факт передачи документов.

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
  "cover_letter": "/Users/oleg/MAC_ASD/data/exports/letters/cover_20260420_015.docx",
  "registry": "/Users/oleg/MAC_ASD/data/exports/letters/registry_20260420_015.docx",
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

**Описание:** Отслеживание сроков ответа по зарегистрированным документам. Руководитель проекта использует этот инструмент для контроля дедлайнов и инициирования претензионных действий при просрочке. Поддерживает фильтрацию по проекту и статусу (активные/просроченные).

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
      "registered_date": "2026-04-20",
      "deadline": "2026-05-04",
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

| `asd_get_system_status` | Проверка статуса всех компонентов системы. Возвращает информацию о загруженных моделях, состоянии БД, потреблении памяти и готовности модулей. Отражает текущую архитектуру с Gemma 4 31B как основной рабочей моделью и Llama 3.3 70B как моделью Руководитель проекта (PM). |
| **asd_work_entry_parse** | Парсинг записи журнала работ (WorkEntry) — извлечение работ, материалов, дат и привязка к ConstructionElement. Триггерит создание АОСР. |
| **asd_work_entry_trigger_aosr** | Автоматический запуск генерации АОСР на основе WorkEntry (цепочка: WorkEntry → ConstructionElement → АОСР). |
| **asd_artifact_*** | Инструменты работы с артефактами (файловый менеджмент проектов) — ✅ заполнены |
| **asd_legal_normative_guard** | NormativeGuard — SSOT-валидация документов через library/normative/normative_index.json |
| **asd_legal_id_requirements** | IDRequirementsRegistry — проверка требований к ИД по 33 типам работ (id_requirements.yaml) |
| **asd_vision_*** | Инструменты vision/OCR для анализа чертежей и сканов — ✅ заполнены |

**Аргументы:** Нет

**Возвращает:**
```json
{
  "success": true,
  "system": "АСД v12.0",
  "components": {
    "llm_engine": {
      "status": "running",
      "primary_model": "gemma4-31b",
      "dele_model": "gemma4-e4b",
      "pm_model": "llama-3.3-70b",
      "vision_model": "gemma4-31b-vlm",
      "embedding_model": "bge-m3-mlx-4bit",
      "shared_memory": true,
      "active_agents": 7
    },
    "mlx": {
      "status": "running",
      "models_loaded": ["llama-3.3-70b", "gemma4-31b", "gemma4-e4b", "bge-m3-mlx-4bit"],
      "models_total": 4
    },
    "database": {
      "status": "connected",
      "host": "localhost",
      "name": "asd_v12",
      "documents": 156,
      "chunks": 5928,
      "traps": 58
    },
    "memory": {
      "total_gb": 128,
      "used_gb": 86,
      "available_gb": 42,
      "models_gb": 66,
      "system_gb": 20,
      "pressure": "low"
    },
    "modules": {
      "lawyer": "ready",
      "pto": "ready",
      "estimator": "ready",
      "clerk": "ready",
      "procurement": "ready",
      "logistics": "ready",
      "hermes": "ready"
    }
  },
  "statistics": {
    "total_documents": 156,
    "total_projects": 2,
    "total_contracts": 5,
    "total_acts_generated": 42,
    "total_letters": 18,
    "total_claims": 1,
    "total_lawsuits": 0,
    "bls_traps": 58
  }
}
```

---

## 7. ЗАКУПЩИК (2 инструмента)

Инструменты Закупщика работают через LLMEngine с моделью **Gemma 4 31B**.

### 7.1. asd_tender_search

**Описание:** Поиск тендеров по заданным критериям (ЕИС,zakupki.gov.ru, коммерческие площадки). Возвращает структурированный список лотов с метаданными: НМЦК, срок подачи, регион, заказчик, объект закупки. Gemma 4 31B выполняет фильтрацию и релевантность результатов.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `keywords` | list[string] | ✅ | Ключевые слова |
| `region` | string | ❌ | Регион |
| `max_nmck` | float | ❌ | Лимит цены лота |

**Возвращает:** Список найденных лотов с метаданными.

---

### 7.2. asd_analyze_lot_profitability

**Описание:** Анализ НМЦК и расчёт потенциальной прибыли по тендерному лоту. Сопоставляет НМЦК с предварительной оценкой стоимости работ на базе ФЕР/ГЭСН. Возвращает рентабельность и рекомендацию (участвовать/не участвовать).

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `lot_id` | string | ✅ | ID лота/тендера |
| `pd_summary` | dict | ❌ | Сводка по ПД (если есть) |

---

## 8. ЛОГИСТ (4 инструмента)

Инструменты Логиста работают через LLMEngine с моделью **Gemma 4 31B**.

### 8.1. asd_source_vendors

**Описание:** Поиск и квалификация поставщиков по категориям ТМЦ. Использует внутреннюю базу проверенных поставщиков (vendors) и веб-поиск для расширения списка. Gemma 4 31B оценивает релевантность поставщика и формирует краткий профиль.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `category` | string | ✅ | Категория (Металл, Бетон, Песок...) |
| `region` | string | ❌ | Регион доставки |

---

### 8.2. asd_add_price_list

**Описание:** Загрузка и парсинг прайс-листа поставщика. Поддерживает PDF, Excel, DOCX форматы. Для сканов автоматически вызывается OCR-конвейер (pytesseract → Gemma 4 31B VLM).

---

### 8.3. asd_compare_quotes

**Описание:** Сравнение коммерческих предложений от разных поставщиков. Формирует конкурентный лист с рейтингом по цене, срокам доставки и надёжности поставщика.

---

### 8.4. asd_parse_price_list

**Описание:** Парсинг и извлечение данных из входящих коммерческих предложений (PDF, Excel) от поставщиков. Gemma 4 31B извлекает структурированные данные (наименование, цена, единица измерения) и сопоставляет с каталогом ТМЦ. Для сканированных КП используется OCR-конвейер.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `file_path` | string | ✅ | Путь к прайс-листу или КП |
| `rfq_batch_id` | int | ❌ | Привязка к запросу |

**Возвращает:**
```json
{
  "success": true,
  "vendor_name": "ООО 'МеталлСнаб'",
  "parsed_items": 15,
  "best_matches": [
    {"requested": "Шпунт Л5-УМ", "offered": "Шпунт Л5-УМ новый", "price": 120000.00, "unit": "тн"}
  ],
  "message": "КП успешно спарсено и занесено в сравнение."
}
```

---

## 9. ARTIFACT STORE — 3 инструмента

Файловое версионированное хранилище артефактов. Артефакты сохраняются в `data/artifacts/{project_id}/{doc_type}/{filename}.v{version}.json`. Реестр артефактов ведётся в `data/artifacts/registry.json`. Поддерживает атомарные операции записи с авто-инкрементом версий и чтение любой версии. Используется **всеми агентами** для сохранения и извлечения результатов работы (акты, сметы, протоколы, письма, сертификаты, чертежи).

### 9.1. artifact_list

**Описание:** Список зарегистрированных артефактов с фильтрацией по проекту и типу документа. Возвращает метаданные каждой записи: ID артефакта, текущую версию, дату последнего изменения.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ❌ | Фильтр по проекту |
| `doc_type` | string | ❌ | Фильтр по типу (aosr, ks2, ks3, certificate, drawing, legal, protocol, letter, estimate) |

**Возвращает:**
```json
{
  "status": "ok",
  "count": 15,
  "items": [
    {
      "artifact_id": "prichaly/aosr/aosr_042_v2",
      "project_id": "prichaly",
      "doc_type": "aosr",
      "filename": "aosr_042_v2",
      "current_version": 3,
      "updated_at": "2026-05-03T10:15:00Z"
    }
  ]
}
```

---

### 9.2. artifact_write

**Описание:** Запись артефакта с автоматическим версионированием. При каждом вызове создаётся новая версия файла (авто-инкремент), предыдущие версии сохраняются. Путь: `data/artifacts/{project_id}/{doc_type}/{filename}.v{version}.json`.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `doc_type` | string | ✅ | Тип документа (aosr, ks2, ks3, certificate, invoice, protocol, letter, estimate, drawing, legal) |
| `filename` | string | ✅ | Имя файла (без расширения) |
| `content` | string | ✅ | Содержимое артефакта (JSON-строка) |
| `version` | int | ❌ | Номер версии (если не указан — авто-инкремент) |

**Возвращает:**
```json
{
  "status": "ok",
  "artifact_id": "prichaly/aosr/aosr_042",
  "project_id": "prichaly",
  "doc_type": "aosr",
  "filename": "aosr_042",
  "version": 3,
  "path": "data/artifacts/prichaly/aosr/aosr_042.v3.json",
  "updated_at": "2026-05-03T10:15:00Z"
}
```

---

### 9.3. artifact_read

**Описание:** Чтение содержимого конкретной версии артефакта. Если версия не указана — возвращает последнюю. Отображает все доступные версии и метаданные.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `doc_type` | string | ✅ | Тип документа |
| `filename` | string | ✅ | Имя файла |
| `version` | int | ❌ | Номер версии (по умолчанию — последняя) |

**Возвращает:**
```json
{
  "status": "ok",
  "artifact_id": "prichaly/aosr/aosr_042",
  "project_id": "prichaly",
  "doc_type": "aosr",
  "filename": "aosr_042",
  "version": 3,
  "content": "{...}",
  "versions_available": [1, 2, 3],
  "current_version": 3,
  "updated_at": "2026-05-03T10:15:00Z"
}
```

---

## 10. LEGAL SERVICE (FZ lookup + RAG) — 3 инструмента

Сервис юридического поиска: локальная база ключевых статей ФЗ-44 и ФЗ-223, текстовый поиск по нормам, RAG-поиск через LightRAG (Graph+Vector) с делегированием в `legal_service`. **NormativeGuard** — встроенный валидатор нормативных ссылок в `legal_service`, проверяющий корректность ссылок на статьи ФЗ-44/223, ГК РФ, ГОСТ, СП и другие нормативные документы по единому реестру (`normative_index.json`). Если индекс не загружен — все ссылки помечаются как UNVERIFIED.

### 10.1. legal_search

**Описание:** Поиск нормы закона по текстовому запросу или прямой ссылке на статью. Поддерживает локальную базу ключевых статей ФЗ-44 (ст. 34, 94, 95) и ФЗ-223 (ст. 3, 4) с keyword-поиском. При указании article — прямой lookup без семантического поиска.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `query` | string | ✅ | Текстовый запрос или ключевые слова |
| `law_code` | string | ❌ | Код закона: "fz44" \| "fz223" \| "gk" \| "grk" |
| `article` | string | ❌ | Номер статьи (для прямого lookup, например "34") |

**Возвращает:**
```json
{
  "status": "ok",
  "query": "ответственность заказчика",
  "law_code": "fz44",
  "results_count": 2,
  "results": [
    {
      "law": "ФЗ-44",
      "article": "34",
      "title": "Статья 34. Контракт",
      "summary": "Контракт заключается на условиях...",
      "key_points": [
        "Цена контракта — твёрдая (ч.2)",
        "В контракт включается условие об ответственности заказчика и поставщика (ч.4-8)"
      ]
    }
  ]
}
```

---

### 10.2. fz_lookup

**Описание:** Точный lookup статьи федерального закона (ФЗ-44 или ФЗ-223) по номеру статьи, части и пункту. Возвращает полный текст нормы из локальной базы.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `law` | string | ✅ | "fz44" \| "fz223" |
| `article` | string | ❌ | Номер статьи |
| `part` | string | ❌ | Часть статьи |
| `clause` | string | ❌ | Пункт |

**Возвращает:**
```json
{
  "status": "ok",
  "law": "ФЗ-44",
  "article": "95",
  "title": "Статья 95. Изменение, расторжение контракта",
  "summary": "Изменение существенных условий контракта при его исполнении не допускается...",
  "key_points": [
    "Снижение цены без изменения объёма — допускается (п.1)",
    "Увеличение/уменьшение объёма до 10% — допускается (пп.б п.1)"
  ]
}
```

---

### 10.3. rag_query

**Описание:** Семантический RAG-поиск по полной базе юридических документов через LightRAG (Graph+Vector). Делегирует запрос в `legal_service.normative_search()`, который комбинирует графовые и векторные результаты через RRF (Reciprocal Rank Fusion). **NormativeGuard** валидирует найденные нормативные ссылки.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `query` | string | ✅ | Текстовый запрос |
| `index` | string | ❌ | Имя индекса: "legal" \| "normative" (по умолч. "legal") |
| `top_k` | int | ❌ | Количество результатов (по умолч. 5) |

**Возвращает:**
```json
{
  "status": "ok",
  "query": "сроки приёмки работ по ФЗ-44",
  "index": "legal",
  "results": [
    {
      "source": "ФЗ-44 ст. 94 ч. 13",
      "text": "Срок приёмки — не более 20 рабочих дней...",
      "relevance": 0.94
    }
  ],
  "normative_guard": {
    "references_found": 3,
    "verified": 2,
    "unverified": 1
  }
}
```

---

## 11. VISION CASCADE — 2 инструмента

Двухстадийный конвейер анализа чертежей (**Vision Cascade**). Стадия 1 — общий анализ: определение типа чертежа, чтение штампа, выделение зон (tiles). Стадия 2 — детальный анализ: извлечение размеров, материалов, марок, спецификаций из заданной зоны. VLM-модель: **Gemma 4 31B Cloud VLM** (на dev_linux через Ollama API, порт 11434) или **MLX-VLM** (на Mac Studio). Поддерживает PNG, JPG и PDF (первая страница через pdftoppm).

### 11.1. vision_analyze

**Описание:** Стадия 1 Vision Cascade — общий анализ чертежа. Определяет тип документа (АР/КР/ОВ/ВК/ЭОМ/ПЗ/ГП), извлекает штамп (проект, номер чертежа, дата, масштаб), формирует карту tiles для детального анализа на Стадии 2, детектирует материалы.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `image_path` | string | ✅ | Путь к файлу изображения (PNG, JPG, PDF) |
| `drawing_type` | string | ❌ | Подсказка типа: "AR" \| "KR" \| "OV" \| "VK" \| "EOM" \| "PZ" \| "GP" |

**Возвращает:**
```json
{
  "status": "ok",
  "image_path": "/data/drawings/AR_Sheet_12.pdf",
  "drawing_type": "AR",
  "stamp": {
    "project": "Причалы порта Корсаков",
    "drawing_number": "АР-12",
    "date": "15.03.2025",
    "scale": "1:100"
  },
  "tiles": [
    {"x": 100, "y": 200, "width": 400, "height": 300, "description": "Фасад 1-10"},
    {"x": 550, "y": 200, "width": 300, "height": 300, "description": "Разрез А-А"}
  ],
  "materials_detected": ["Бетон B25", "Арматура А500С"],
  "notes": "Чертёж читаемый, штамп заполнен",
  "metadata": {"model": "gemma4:31b-cloud", "stage": "overview"}
}
```

---

### 11.2. vision_tile

**Описание:** Стадия 2 Vision Cascade — детальный анализ одной зоны (tile) чертежа. Извлекает размеры (значение, единица измерения, описание), материалы (наименование, марка, ГОСТ), количества (позиция, значение, единица). Использует контекст из Стадии 1 для уточнения анализа.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `image_path` | string | ✅ | Путь к исходному изображению |
| `tile_coords` | tuple[4] | ✅ | (x, y, width, height) — координаты зоны в пикселях |
| `context` | string | ❌ | Контекст из Стадии 1 для данного tile |

**Возвращает:**
```json
{
  "status": "ok",
  "image_path": "/data/drawings/AR_Sheet_12.pdf",
  "tile_coords": [100, 200, 400, 300],
  "dimensions": [
    {"value": 12000, "unit": "мм", "description": "Длина фасада"},
    {"value": 3600, "unit": "мм", "description": "Высота этажа"}
  ],
  "materials": [
    {"name": "Бетон", "mark": "B25 F200 W6", "gost": "ГОСТ 26633-2015"},
    {"name": "Арматура", "mark": "А500С Ø12", "gost": "ГОСТ 34028-2016"}
  ],
  "quantities": [
    {"item": "Колонны", "value": 10, "unit": "шт"},
    {"item": "Бетон", "value": 24.5, "unit": "м³"}
  ],
  "notes": "Все размеры в осях 1-10",
  "metadata": {"model": "gemma4:31b-cloud", "stage": "tile_detail"}
}
```

---

## 12. EVIDENCE GRAPH v2 (Package 5) — 6 инструментов

Все инструменты Evidence Graph работают через LLMEngine с моделью **Gemma 4 31B**. Граф строится на базе NetworkX с файловой сериализацией в `data/graphs/`. Inference Engine выполняет логический вывод над графом для обнаружения скрытых связей.

### 12.1. asd_evidence_query

**Описание:** Запрос к графу доказательств (evidence graph) с фильтрацией по типу узла, диапазону дат и уровню confidence. Возвращает узлы и рёбра, удовлетворяющие критериям. Используется агентами для поиска документов, событий и связей в проекте.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `node_type` | string | ❌ | Тип узла: "document" \| "event" \| "work_unit" \| "fact" \| "all" |
| `date_from` | string | ❌ | Начальная дата (ISO) |
| `date_to` | string | ❌ | Конечная дата (ISO) |
| `confidence_min` | float | ❌ | Минимальный confidence (0.0–1.0) |
| `project_id` | string | ❌ | Фильтр по проекту |

**Возвращает:**
```json
{
  "success": true,
  "nodes": [
    {
      "id": "node_42",
      "type": "document",
      "label": "АОСР №15",
      "date": "2026-04-15",
      "confidence": 0.98,
      "metadata": {"project_id": "prichaly", "doc_type": "act"}
    }
  ],
  "edges": [
    {"source": "node_42", "target": "node_18", "relation": "references", "weight": 0.95}
  ],
  "total_nodes": 156,
  "total_edges": 423,
  "query_time_ms": 12
}
```

---

### 12.2. asd_evidence_get_chain

**Описание:** Получение цепочки документов (document chain) для конкретного WorkUnit. Показывает полную прослеживаемость: от спецификации/чертежа до акта приёмки.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `work_unit_id` | string | ✅ | ID WorkUnit |
| `direction` | string | ❌ | "forward" \| "backward" \| "both" (по умолч. "both") |

**Возвращает:**
```json
{
  "success": true,
  "work_unit_id": "WU-042",
  "chain": [
    {"step": 1, "node_id": "spec_12", "type": "specification", "label": "Спецификация арматуры"},
    {"step": 2, "node_id": "cert_07", "type": "certificate", "label": "Сертификат качества"},
    {"step": 3, "node_id": "act_15", "type": "act", "label": "АОСР №15"},
    {"step": 4, "node_id": "journal_03", "type": "journal", "label": "Запись ОЖР №42"}
  ],
  "chain_length": 4,
  "completeness": "full"
}
```

---

### 12.3. asd_evidence_summary

**Описание:** Статистика графа доказательств: количество узлов по типам, рёбер по отношениям, средний confidence, топ-связные компоненты.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ❌ | Фильтр по проекту |

**Возвращает:**
```json
{
  "success": true,
  "nodes_by_type": {"document": 120, "event": 45, "work_unit": 30, "fact": 18},
  "edges_by_relation": {"references": 350, "derives": 80, "contradicts": 5},
  "avg_confidence": 0.91,
  "connected_components": 3,
  "largest_component_size": 195,
  "graph_density": 0.012
}
```

---

### 12.4. asd_inference_run

**Описание:** Запуск правил логического вывода (inference rules) на графе доказательств. Правила обнаруживают скрытые связи, противоречия и несоответствия между документами. Inference Engine использует forward-chaining над правилами, описанными в `src/evidence/inference_rules.py`.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `rule_set` | string | ❌ | Набор правил: "all" \| "contradictions" \| "derivations" \| "completeness" (по умолч. "all") |
| `project_id` | string | ❌ | Фильтр по проекту |
| `max_iterations` | int | ❌ | Максимальное число итераций (по умолч. 10) |

**Возвращает:**
```json
{
  "success": true,
  "rules_evaluated": 24,
  "new_inferences": 7,
  "inferences": [
    {
      "rule": "missing_certificate",
      "description": "Материал «Бетон B25» использован в АОСР №15 без сертификата качества",
      "confidence": 0.93,
      "involved_nodes": ["act_15", "mat_07"],
      "action": "alert"
    }
  ],
  "runtime_ms": 340
}
```

---

### 12.5. asd_inference_results

**Описание:** Получение результатов последнего запуска inference engine. Кэширует результаты для быстрого доступа без повторного вычисления.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ❌ | Фильтр по проекту |
| `status` | string | ❌ | "all" \| "alert" \| "info" \| "resolved" (по умолч. "all") |

**Возвращает:**
```json
{
  "success": true,
  "last_run": "2026-05-02T10:15:00Z",
  "total_inferences": 7,
  "alerts": 3,
  "results": [
    {
      "id": "inf_001",
      "rule": "missing_certificate",
      "description": "Материал «Бетон B25» использован в АОСР №15 без сертификата",
      "status": "alert",
      "confidence": 0.93
    }
  ]
}
```

---

### 12.6. asd_project_load

**Описание:** Загрузка проектной и рабочей документации (ПД/РД) в граф доказательств через ProjectLoader. Автоматически создаёт узлы и связи на основе структуры проектной документации. Поддерживает пакетную загрузку директорий с рекурсивным обходом.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `path` | string | ✅ | Путь к файлу или директории ПД/РД |
| `project_id` | string | ✅ | ID проекта для привязки |
| `recursive` | bool | ❌ | Рекурсивный обход (по умолч. true) |
| `file_pattern` | string | ❌ | Glob-паттерн фильтрации файлов (по умолч. "*.pdf") |

**Возвращает:**
```json
{
  "success": true,
  "project_id": "prichaly",
  "files_processed": 42,
  "nodes_created": 156,
  "edges_created": 89,
  "sections_detected": ["АР", "КР", "ИОС1", "ИОС2", "ПОС"],
  "missing_sections": ["ИОС3", "ПМ"],
  "load_time_seconds": 45.2
}
```

---

## 13. CHAIN BUILDER (Package 11) — 3 инструмента

Chain Builder автоматически строит цепочки документов для всех WorkUnit в проекте, обеспечивая полную прослеживаемость от спецификации до акта приёмки.

### 13.1. asd_chain_build

**Описание:** Построение цепочек документов (document chains) для всех WorkUnit в проекте. Анализирует граф доказательств и строит направленные цепочки: спецификация → сертификат → входной контроль → акт скрытых работ → запись ОЖР → КС-2.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `rebuild` | bool | ❌ | Перестроить все цепочки заново (по умолч. false) |

**Возвращает:**
```json
{
  "success": true,
  "project_id": "prichaly",
  "work_units_total": 30,
  "chains_built": 28,
  "chains_incomplete": 2,
  "avg_chain_length": 4.2,
  "missing_links": [
    {"work_unit_id": "WU-007", "missing": "certificate", "description": "Нет сертификата на арматуру А500С"},
    {"work_unit_id": "WU-019", "missing": "hidden_works_act", "description": "Нет АОСР на бетонирование"}
  ],
  "build_time_seconds": 12.3
}
```

---

### 13.2. asd_chain_report

**Описание:** Отчёт о состоянии цепочек документов. Показывает процент готовности, разрывы и критический путь по всем WorkUnit.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `format` | string | ❌ | "summary" \| "detailed" (по умолч. "summary") |

**Возвращает:**
```json
{
  "success": true,
  "project_id": "prichaly",
  "chains_total": 30,
  "chains_complete": 22,
  "chains_partial": 6,
  "chains_missing": 2,
  "completeness_percent": 73.3,
  "critical_path": ["WU-007", "WU-019"],
  "delta_to_sign_ks11": 8
}
```

---

### 13.3. asd_chain_validate

**Описание:** Валидация конкретной цепочки документов. Проверяет корректность связей, временную последовательность и полноту цепочки для заданного WorkUnit.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `work_unit_id` | string | ✅ | ID WorkUnit для валидации |

**Возвращает:**
```json
{
  "success": true,
  "work_unit_id": "WU-042",
  "valid": true,
  "chain_length": 4,
  "issues": [],
  "temporal_sequence_ok": true,
  "all_links_present": true
}
```

---

## 14. HITL (Package 11) — 3 инструмента

Human-in-the-Loop модуль для эскалации неразрешимых системой вопросов. Генерирует вопросы, принимает ответы человека и применяет их к графу.

### 14.1. asd_hitl_generate

**Описание:** Генерация вопросов для HITL-сессии на основе неразрешённых противоречий, inference-алертов и разрывов в цепочках доказательств.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `max_questions` | int | ❌ | Максимальное число вопросов (по умолч. 10) |
| `categories` | list[string] | ❌ | Категории: "contradiction" \| "missing_link" \| "low_confidence" \| "all" |

**Возвращает:**
```json
{
  "success": true,
  "session_id": "hitl_20260502_001",
  "questions": [
    {
      "id": "q_001",
      "category": "missing_link",
      "question": "Подтвердите наличие сертификата качества на арматуру А500С для WU-007",
      "context": "Сертификат не найден в БД. Возможно, не загружен.",
      "options": ["Да, загрузить вручную", "Нет, отсутствует", "Пропустить"]
    },
    {
      "id": "q_002",
      "category": "contradiction",
      "question": "Объём бетона в АОСР №15 (45 м³) расходится с ЛСР (50 м³). Какой объём верный?",
      "context": "Расхождение 5 м³. АОСР подписан, ЛСР утверждён.",
      "options": ["Подтвердить 45 м³ (по АОСР)", "Подтвердить 50 м³ (по ЛСР)", "Уточнить"]
    }
  ],
  "total_questions": 2,
  "generated_at": "2026-05-02T10:30:00Z"
}
```

---

### 14.2. asd_hitl_answer

**Описание:** Применение ответа человека на HITL-вопрос. Ответ записывается в граф и разрешает соответствующее противоречие/разрыв.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `session_id` | string | ✅ | ID HITL-сессии |
| `question_id` | string | ✅ | ID вопроса |
| `answer` | string | ✅ | Ответ (текст или выбранная опция) |
| `comment` | string | ❌ | Комментарий человека |

**Возвращает:**
```json
{
  "success": true,
  "session_id": "hitl_20260502_001",
  "question_id": "q_001",
  "answer": "Да, загрузить вручную",
  "applied_to_graph": true,
  "nodes_updated": 1,
  "edges_created": 1,
  "message": "Ответ применён. Сертификат ожидает загрузки."
}
```

---

### 14.3. asd_hitl_status

**Описание:** Статус HITL-сессии: сколько вопросов задано, отвечено, ожидает ответа.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `session_id` | string | ❌ | ID конкретной сессии (если не указан — все активные) |
| `project_id` | string | ❌ | Фильтр по проекту |

**Возвращает:**
```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "hitl_20260502_001",
      "project_id": "prichaly",
      "status": "active",
      "total_questions": 2,
      "answered": 1,
      "pending": 1,
      "created_at": "2026-05-02T10:30:00Z"
    }
  ]
}
```

---

## 15. JOURNAL RECONSTRUCTOR (Package 11) — 3 инструмента

Модуль реконструкции Общего Журнала Работ (ОЖР) из графа доказательств. Восстанавливает хронологию работ по цепочкам документов и записям в графе.

### 15.1. asd_journal_reconstruct

**Описание:** Реконструкция Общего Журнала Работ (ОЖР) из графа доказательств. Восстанавливает хронологическую последовательность выполнения работ на основе цепочек документов, актов и записей в графе.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `date_from` | string | ❌ | Начальная дата периода |
| `date_to` | string | ❌ | Конечная дата периода |
| `section` | string | ❌ | Раздел ОЖР (по умолч. "all") |

**Возвращает:**
```json
{
  "success": true,
  "project_id": "prichaly",
  "period": {"from": "2026-03-01", "to": "2026-04-30"},
  "total_entries": 87,
  "entries_by_type": {"work_execution": 45, "material_receipt": 18, "inspection": 12, "other": 12},
  "first_entry_date": "2026-03-02",
  "last_entry_date": "2026-04-29",
  "missing_dates": 3,
  "reconstruction_confidence": 0.94
}
```

---

### 15.2. asd_journal_export

**Описание:** Экспорт реконструированного ОЖР в формат JSON или таблицу (XLSX/CSV). Поддерживает формат, совместимый с РД-11-05-2007.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `format` | string | ✅ | "json" \| "xlsx" \| "table" |
| `date_from` | string | ❌ | Начальная дата |
| `date_to` | string | ❌ | Конечная дата |
| `output_path` | string | ❌ | Путь для сохранения (если не указан — в `data/exports/`) |

**Возвращает:**
```json
{
  "success": true,
  "file_path": "/Users/oleg/MAC_ASD/data/exports/journal_prichaly_20260502.xlsx",
  "format": "xlsx",
  "entries_exported": 87,
  "file_size_bytes": 24576,
  "message": "ОЖР экспортирован в XLSX. 87 записей."
}
```

---

### 15.3. asd_journal_verify

**Описание:** Верификация реконструированного ОЖР по известным фактам. Сверяет записи журнала с подтверждёнными документами в графе и выявляет расхождения.

**Аргументы:**
| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `project_id` | string | ✅ | ID проекта |
| `strict_mode` | bool | ❌ | Строгий режим (по умолч. false) |

**Возвращает:**
```json
{
  "success": true,
  "project_id": "prichaly",
  "total_entries": 87,
  "verified_entries": 84,
  "discrepancies": [
    {
      "entry_date": "2026-04-03",
      "work_description": "Бетонирование ростверка №5",
      "issue": "Запись ОЖР есть, но АОСР не найден",
      "severity": "medium"
    }
  ],
  "verification_percent": 96.6
}
```

---

## 16. СВОДНАЯ ТАБЛИЦА ИНСТРУМЕНТОВ

| # | Группа | Инструментов | Агенты | Статус |
|---|--------|-------------|--------|--------|
| 1 | **Юрист** (core) | 7 | Юрист | ✅ |
| 2 | **ПТО-инженер** (core) | 4 | ПТО | ✅ |
| 3 | **ПТО WorkSpec** | 7 | ПТО | ✅ |
| 4 | **Инженер-сметчик** | 5 | Сметчик | ✅ |
| 5 | **Делопроизводитель** | 7 | Делопроизводитель | ✅ |
| 6 | **Общий** | 1 | Все | ✅ |
| 7 | **Закупщик** | 2 | Закупщик | ✅ |
| 8 | **Логист** | 4 | Логист | ✅ |
| 9 | **Artifact Store** | 3 | Все агенты | ✅ |
| 10 | **Legal Service** (FZ lookup + RAG) | 3 | Юрист, Закупщик | ✅ |
| 11 | **Vision Cascade** | 2 | ПТО | ✅ |
| 12 | **Evidence Graph v2** | 6 | Все | ✅ |
| 13 | **Chain Builder** | 3 | ПТО, PM | ✅ |
| 14 | **HITL** | 3 | PM, Все | ✅ |
| 15 | **Journal Reconstructor** | 3 | ПТО, Делопроизводитель | ✅ |
| 16 | **Лабораторный контроль** | 13 | ПТО, Закупщик, Логист, Дело | ✅ |
| 17 | **Google Workspace** | 16 | Все | ✅ |
| 18 | **Lessons Learned** | 7 | Все | ✅ |
| 19 | **Pipeline (E2E Tender)** | 1 | PM | 🧪 Тест |
| — | **MCP Server (служебные)** | 8 | Система | ✅ |
| | **ВСЕГО** | **82** | 7 агентов + PM | |

> **Примечание:** Таблица отражает полный реестр инструментов, зарегистрированных в `mcp_servers/asd_core/server.py` + служебные MCP server-тулы (health, status, ping и др.). Не все инструменты документированы в разделах 2-15 — полные спецификации для WorkSpec, Lab, Google Workspace, Lessons Learned ведутся в отдельных файлах.

---

## 17. ОБЩИЕ ПРАВИЛА

### 17.1. Маршрутизация LLM-вызовов

Все LLM-вызовы в инструментах осуществляются через **LLMEngine** (не напрямую к Ollama). LLMEngine реализует маршрутизацию:

| Агент | Модель | Профиль |
|-------|--------|---------|
| Руководитель проекта (PM) | Llama 3.3 70B 4-bit | `pm_profile` |
| Юрист | Gemma 4 31B 4-bit | `default_profile` |
| ПТО | Gemma 4 31B 4-bit | `default_profile` |
| Сметчик | Gemma 4 31B 4-bit | `default_profile` |
| Закупщик | Gemma 4 31B 4-bit | `default_profile` |
| Логист | Gemma 4 31B 4-bit | `default_profile` |
| Делопроизводитель | Gemma 4 E4B 4-bit | `default_profile` |
| Vision (on-demand) | Gemma 4 31B VLM | `vision_profile` |
| Embeddings | bge-m3 | `embed_profile` |

LLMEngine обеспечивает поддержку профилей (dev_linux/mac_studio), разделяемую память для Gemma 4 31B и автоматический fallback при недоступности модели.

### 17.2. Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "success": false,
  "error_code": "LLM_ERROR",
  "message": "Ошибка вызова LLM: модель gemma4-31b не отвечает",
  "details": {
    "model": "gemma4-31b",
    "timeout_seconds": 300,
    "retries": 2
  }
}
```

### 17.3. Коды ошибок

| Код | Описание | Действие |
|-----|----------|----------|
| `FILE_NOT_FOUND` | Файл не найден | Проверить путь |
| `UNSUPPORTED_FORMAT` | Неподдерживаемый формат | Проверить тип файла |
| `DOCUMENT_NOT_FOUND` | Документ не найден в БД | Проверить document_id |
| `PARSER_ERROR` | Ошибка парсинга | Проверить целостность файла |
| `LLM_ERROR` | Ошибка LLM (Gemma 4 31B / Llama 3.3 70B) | Проверить Ollama |
| `DB_ERROR` | Ошибка базы данных | Проверить PostgreSQL |
| `VALIDATION_ERROR` | Ошибка валидации аргументов | Проверить аргументы |
| `NOT_FOUND` | Ресурс не найден | Проверить ID |
| `MEMORY_CRITICAL` | Критическое использование RAM (>90%) | Подождать или закрыть задачи |
| `INTERNAL_ERROR` | Внутренняя ошибка | Смотреть логи |
| `PROTOCOL_PARTY_INFO_ERROR` | Не удалось извлечь реквизиты сторон | Проверить документ |

### 17.4. Таймауты инструментов

| Инструмент | Таймаут | Примечание |
|-----------|---------|------------|
| `asd_upload_document` | 120 сек | Зависит от размера PDF |
| `asd_analyze_contract` (quick) | 120 сек | Quick Review <6K символов |
| `asd_analyze_contract` (full) | 600 сек | Map-Reduce ≥6K символов |
| `asd_normative_search` | 30 сек | Быстрый поиск |
| `asd_generate_protocol` | 60 сек | Генерация DOCX + ProtocolPartyInfo |
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
| `asd_source_vendors` | 60 сек | Поиск поставщиков |
| `asd_parse_price_list` | 60 сек | Анализ сметы/КП |
| `asd_compare_quotes` | 120 сек | Сравнение КП |
| `asd_get_system_status` | 5 сек | Проверка компонентов |
| `asd_evidence_query` | 30 сек | Запрос к графу |
| `asd_evidence_get_chain` | 15 сек | Получение цепочки |
| `asd_evidence_summary` | 10 сек | Статистика графа |
| `asd_inference_run` | 300 сек | Forward-chaining вывод |
| `asd_inference_results` | 5 сек | Кэшированные результаты |
| `asd_project_load` | 120 сек | Загрузка ПД/РД в граф |
| `asd_chain_build` | 120 сек | Построение цепочек |
| `asd_chain_report` | 10 сек | Отчёт по цепочкам |
| `asd_chain_validate` | 15 сек | Валидация цепочки |
| `asd_hitl_generate` | 60 сек | Генерация вопросов |
| `asd_hitl_answer` | 10 сек | Применение ответа |
| `asd_hitl_status` | 5 сек | Статус сессии |
| `asd_journal_reconstruct` | 120 сек | Реконструкция ОЖР |
| `asd_journal_export` | 30 сек | Экспорт ОЖР |
| `asd_journal_verify` | 60 сек | Верификация ОЖР |
| `artifact_list` | 5 сек | Чтение реестра |
| `artifact_write` | 10 сек | Запись артефакта |
| `artifact_read` | 5 сек | Чтение артефакта |
| `legal_search` | 5 сек | Локальный поиск |
| `fz_lookup` | 5 сек | Прямой lookup |
| `rag_query` | 30 сек | RAG-поиск через LightRAG |
| `vision_analyze` | 120 сек | VLM общий анализ |
| `vision_tile` | 120 сек | VLM детальный анализ |

### 17.5. БЛС (Библиотека Ловушек Сторон)

АСД v12.0 содержит **61 ловушка** в 10 категориях:

| ID | Статья | Название | Критичность |
|----|--------|----------|-------------|
| 1 | ст. 708 ГК РФ | Отсутствие сроков выполнения работ | high |
| 2 | ст. 740 ГК РФ | Нечёткая формулировка предмета договора | high |
| 3 | ст. 395 ГК РФ | Отсутствие ответственности заказчика | high |
| 4 | ст. 743 ГК РФ | Одностороннее изменение объёма | high |
| 5 | ст. 746 ГК РФ | Отсутствие порядка оплаты | critical |
| 6 | ФЗ-44 ст. 34 | Завышенная неустойка подрядчика | medium |
| 7 | ст. 708 ГК РФ | Размытые сроки начала работ | medium |
| 8 | ст. 753 ГК РФ | Уклонение от приёмки работ | high |
| 9 | ФЗ-44 ст. 95 | Безусловная банковская гарантия | critical |
| 10 | ст. 717 ГК РФ | Отсутствие права на удержание | medium |
| 11 | ст. 716 ГК РФ | Невозможность приостановки работ | medium |
| 12 | ст. 395 ГК РФ | Завышенная неустойка подрядчика | medium |
| 13 | ст. 755 ГК РФ | Расширенная гарантия качества | high |
| 14 | ст. 723 ГК РФ | Право заказчика на устранение недостатков | medium |
| 15 | ФЗ-44 ст. 34 | Отсутствие обеспечения обязательств | high |
| 16 | ст. 744 ГК РФ | Право заказчика на внесение изменений | medium |
| 17 | ст. 749 ГК РФ | Право заказчика на контроль и надзор | low |
| 18 | ст. 761 ГК РФ | Ограничение ответственности проектировщика | medium |
| 19 | **ст. 706 ГК РФ** | **Ответственность генподрядчика за субподрядчика** | **high** |
| 20 | **ст. 15/393 ГК РФ** | **Взыскание убытков вместо неустойки** | **critical** |
| 21 | **ст. 421/424 ГК РФ** | **Свобода договора vs. императивные нормы ФЗ-44** | **high** |

---

Документ актуализирован для АСД v12.0 (3 мая 2026). Спецификации инструментов используются при реализации MCP-тулов в Packages 2-12. Добавлены: Package 5 (Evidence Graph, Inference Engine, ProjectLoader), Package 11 (Chain Builder, HITL, Journal Reconstructor), Artifact Store (версионированное файловое хранилище), Legal Service (FZ-44/223 lookup, RAG, NormativeGuard), Vision Cascade (Стадия 1/2, Gemma 4 31B Cloud VLM fallback). Все агенты используют Gemma 4 31B через разделяемую память LLMEngine; Руководитель проекта использует Llama 3.3 70B. Визионный анализ выполняется Gemma 4 31B VLM по требованию.
