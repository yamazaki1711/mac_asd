# АСД v11.0 — ДЕТАЛЬНАЯ АРХИТЕКТУРА КОМПОНЕНТОВ

**Дата:** 17 апреля 2026
**Статус:** Активная разработка (Package 1 завершен)

---

## 1. ОБЗОР

Этот документ описывает внутреннюю архитектуру каждого компонента АСД:
классы, методы, потоки данных, зависимости между модулями.

Не содержит рабочего кода — только проектирование.

---

## 2. MCP SERVER — ГЛАВНЫЙ КОМПОНЕНТ

### 2.1. Роль

Единая точка входа для Hermes Agent. Регистрирует 23 инструмента,
маршрутизирует вызовы к соответствующим модулям. Управляет жизненным циклом через EventManager и LangGraph.

### 2.2. Структура

```
mcp_servers/asd_core/server.py
│
├── Инициализация FastMCP
│   ├── Имя: "АСД v11.0 Core"
│   └── Описание: "Единый сервер инструментов АСД"
│
├── Регистрация инструментов (23 штуки)
│   ├── Юрист: tools/jurist_tools.py (6)
│   ├── ПТО: tools/pto_tools.py (4)
│   ├── Сметчик: tools/smeta_tools.py (3)
│   ├── Делопроизводитель: tools/delo_tools.py (4)
│   ├── Закупщик: tools/procurement_tools.py (2)
│   ├── Логист: tools/logistics_tools.py (3)
│   └── Общий: tools/general_tools.py (1)
│
├── Интеграция с LangGraph
│   └── src/agents/workflow.py (Оркестрация 7 агентов)
│
├── Инициализация сервисов
│   ├── LLMEngine()
│   ├── PostgreSQL подключ
│   ├── ParserEngine()
│   ├── LightRAG()
│   ├── RAMManager()
│   ├── ModelRouter()
│   ├── EventManager()
│   └── GoogleWorkspaceService()
│
└── Entry point
    └── mcp.run(transport="stdio")  # или "http" для тестов
```

### 2.3. Lifecycle

```
Запуск:
  1. Загрузка конфигурации (config/settings.py)
  2. Подключение к PostgreSQL
  3. Инициализация LLMEngine (определение профиля, подключение Ollama/MLX backend)
  4. Инициализация ParserEngine, LightRAG, RAMManager
  5. Регистрация 23 инструментов в FastMCP
  6. Запуск stdio транспорта

Остановка:
  1. Закрытие соединений с БД
  2. Ожидание завершения активных задач
  3. Освобождение ресурсов
```

### 2.4. Обработка ошибок

Каждый инструмент возвращает единый формат:

```json
{
  "success": true/false,
  "error_code": "PARSER_ERROR" | "LLM_ERROR" | "DB_ERROR" | "NOT_FOUND" | "VALIDATION_ERROR",
  "message": "Человеко-понятное описание ошибки",
  "details": {}
}
```

---

## 3. LLM ENGINE

### 3.1. Роль

Заменяет OllamaClient из ранних версий. Единый интерфейс с поддержкой Ollama и MLX бэкендов.
Агент указывается по имени, модель определяется автоматически через профиль.

### 3.2. Методы

```
LLMEngine(profile="auto")
│
├── chat(agent, messages, temperature=0.7, max_tokens=4096)
│   → str (ответ модели)
│   │
│   ├── agent: "pm" | "pto" | "smeta" | "legal" | "procurement" | "logistics" | "archive"
│   ├── messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
│   ├── Модель определяется автоматически через профиль: settings.get_model_config(agent)
│   └── Делегирует вызов соответствующему бэкенду (Ollama / MLX)
│
├── safe_chat(agent, messages, fallback="archive")
│   → str (ответ модели с автоматическим fallback)
│   │
│   ├── Основной вызов: chat(agent, messages)
│   ├── При ошибке: повторная попытка через fallback-агент
│   └── Гарантирует возврат результата даже при недоступности основной модели
│
├── vision(agent, image_base64, prompt)
│   → str (ответ vision модели)
│   │
│   ├── agent: "vision" (по умолчанию)
│   ├── image_base64: base64-кодированное изображение
│   └── Использует Gemma 4 31B в vision режиме (MLX)
│
├── embed(text)
│   → list[float] (embedding вектор, 1024 dim для bge-m3)
│   │
│   ├── Всегда через Ollama bge-m3
│   └── POST /api/embeddings (Ollama backend)
│
└── Автоопределение профиля
    → settings.get_model_config(agent)
    │
    ├── Профиль "mac_studio": MLX-бэкенд, локальные модели
    ├── Профиль "dev_linux": Ollama-бэкенд, удалённый сервер
    └── Выбор бэкенда: MlxBackend | OllamaBackend
```

### 3.3. Thinking Mode

Для Gemma 4 thinking mode включается через системный промпт:

```python
def _build_thinking_prompt(system_prompt):
    return f"""{system_prompt}

Think step by step. Analyze the input carefully before responding.
Show your reasoning process."""
```

Thinking mode используется для:

- Юридическая экспертиза договоров
- Генерация протоколов, претензий, исков
- Сверка ВОР/ПД
- Комплексный анализ ПД

Thinking mode **отключается** для:

- Классификация документов
- Простые ответы в чате
- Извлечение метаданных
- Статус системы

### 3.4. Retry и таймауты

| Операция | Таймаут | Retries | Backoff |
|----------|---------|---------|---------|
| chat | 300 сек (5 мин) | 2 | 2x |
| chat_stream | 600 сек (10 мин) | 1 | — |
| embeddings | 30 сек | 3 | 1.5x |
| batch_embeddings | 120 сек | 2 | 2x |
| vision | 60 сек | 2 | 2x |
| is_available | 5 сек | 3 | 1x |

---

## 4. MODEL ROUTER

> **Примечание:** Model routing теперь интегрирован в LLMEngine. Агент указывается по имени, модель определяется автоматически через профиль.

### 4.1. Роль

Автоматический выбор модели на основе агента (имя роли).
Пользователь не указывает модель — LLMEngine решает сам через профиль.

### 4.2. Правила маршрутизации

```
Агент (имя роли)
  │
  ├── pm (Руководитель проекта)
  │     → Llama 3.3 70B (MLX)
  │
  ├── pto (ПТО)
  │     → Gemma 4 31B (MLX)
  │
  ├── smeta (Сметчик)
  │     → Qwen3 32B (MLX)
  │
  ├── legal (Юрист)
  │     → Qwen3 32B (MLX)
  │
  ├── procurement (Закупщик)
  │     → Qwen3 32B (MLX)
  │
  ├── logistics (Логист)
  │     → Qwen3 32B (MLX)
  │
  ├── archive (Архивариус)
  │     → Gemma 4 9B (MLX)
  │
  ├── vision (Vision)
  │     → Gemma 4 31B (MLX vision mode)
  │
  └── embed (Embeddings)
        → bge-m3 (Ollama)
```

### 4.3. Fallback стратегия

```
Модель агента недоступна (через LLMEngine.safe_chat)
  → fallback на archive-агент (Gemma 4 9B, сниженное качество, но работает)
    → Ошибка "LLM недоступна"

Llama 3.3 70B недоступна (pm)
  → Qwen3 32B (альтернатива для руководителя)
    → Gemma 4 9B (archive fallback)

Qwen3 32B недоступна (smeta, legal, procurement, logistics)
  → Gemma 4 31B (альтернатива)
    → Gemma 4 9B (archive fallback)

bge-m3 недоступна (embed)
  → Ошибка "Поиск временно недоступен"

Gemma 4 31B vision недоступна
  → pytesseract (fallback OCR)
```

---

## 5. RAM MANAGER

### 5.1. Роль

Контроль использования 128GB Unified Memory.
Предотвращение OOM (Out Of Memory) при загрузке больших PDF
и одновременной работе нескольких моделей.

### 5.2. Мониторинг

```
RAMManager
│
├── get_used_memory()
│   → float (GB использовано)
│   │
│   └── psutil.virtual_memory() + macOS sysctl
│
├── get_available_memory()
│   → float (GB свободно)
│
├── get_memory_pressure()
│   → "low" | "medium" | "high" | "critical"
│   │
│   └── На основе % использованной памяти
│
├── can_load_model(required_gb)
│   → bool (можно ли загрузить модель без OOM)
│
├── should_unload_model()
│   → bool (пора ли выгрузить модель)
│   │
│   └── Когда давление памяти > "high"
│
└── get_model_budget(model_name)
    → float (сколько RAM требует модель)
    │
    └── Словарь: gemma-4-31b(fp16): 62, gemma-4-31b(q8_0): 33, bge-m3: 2.2, minicpm-v: 5
```

### 5.3. Политики

| Давление памяти | Действие |
|----------------|----------|
| **low** (< 70%) | FP16 31B + bge-m3 загружены, последовательная обработка |
| **medium** (70-80%) | Нормально, пик контекста укладывается, лог-предупреждение |
| **high** (80-90%) | E4B/minicpm-v выгружаются, задачи завершаются последовательно |
| **critical** (> 90%) | Переключение на Q8_0, отклонение новых задач |

### 5.4. Бюджет контекста

При Map-Reduce анализе большого документа:

```
FP16 31B базово:       62 GB
Система:               18 GB
Остаток на контекст:   48 GB (128 - 62 - 18)
Безопасный лимит:      10-15 GB на чанк
Параллелизм:           1 задача (последовательно)
Максимальный пик RAM:  ~99 GB
```

---

## 6. PARSER ENGINE

### 6.1. Роль

Универсальный парсер документов: PDF (текстовый/скан), Excel, JSON.
Автоматически определяет тип и выбирает метод.

### 6.2. Архитектура

```
ParserEngine
│
├── detect_type(file_path)
│   → "pdf_text" | "pdf_scan" | "xlsx" | "tg_json"
│
├── parse(file_path)
│   → ParsedDocument(text, metadata, pages[])
│   │
│   ├── pdf_text → PyMuPDFParser
│   ├── pdf_scan → DeepSeekOCRParser (pytesseract → Ollama vision)
│   ├── xlsx → ExcelParser (openpyxl)
│   └── tg_json → TelegramParser (json)
│
└── chunk(parsed_document, chunk_size=4000, overlap=200)
    → list[Chunk(text, position, metadata)]
```

### 6.3. Автомаршрутизация PDF

```
PDF файл
  │
  ▼
PyMuPDF: extract text
  │
  ├── > 50% страниц имеют текст
  │     → Текстовый PDF
  │     → PyMuPDFParser (быстро, точно)
  │
  └── < 50% страниц имеют текст
        → Скан PDF
        │
        ▼
        pytesseract (300 DPI → PNG)
          │
          ├── pytesseract справился (> 90% распознавания)
          │     → Готово
          │
          └── pytesseract не справился
                → Ollama vision (minicpm-v)
                → base64 изображений → LLM → текст
```

### 6.4. ParsedDocument

```
ParsedDocument
├── text: str (полный текст)
├── pages: list[Page]
│   ├── page_number: int
│   ├── text: str
│   ├── images: list[Image]
│   └── tables: list[Table]
├── metadata: Metadata
│   ├── file_name: str
│   ├── file_size: int
│   ├── page_count: int
│   ├── is_scan: bool
│   ├── detected_language: str
│   └── parsed_at: datetime
└── chunks: list[Chunk] (после чанкинга)
    ├── text: str
    ├── position: int (порядковый номер)
    ├── page_range: (start, end)
    └── token_count: int
```

### 6.5. Чанкинг

```
chunk(document, chunk_size=4000, overlap=200)
  │
  ├── Разбивает по token_count (не по символам!)
  ├── Сохраняет границы абзацев (не рвёт посередине)
  ├── overlap = 200 tokens (контекст между чанками)
  └── Для юридических документов: не рвёт посередине статьи/пункта
```

---

## 7. LIGHT RAG

### 7.1. Роль

Единый поиск по нормативной базе и проектной документации.
Комбинирует векторный + графовый поиск с RRF Fusion.

### 7.2. Архитектура

```
LightRAG
│
├── ingest(parsed_document, project_id)
│   → document_id
│   │
│   ├── bge-m3 embeddings для каждого chunk
│   ├── Сохранение в PostgreSQL (chunks + embeddings)
│   ├── Извлечение нормативных ссылок
│   ├── Построение графа связей (NetworkX)
│   └── Обновление wiki
│
├── search(query, k=10, project_id=None)
│   → list[SearchResult]
│   │
│   ├── Vector Search (pgvector, cosine, bge-m3)
│   ├── Graph Search (NetworkX, обход связей)
│   ├── RRF Fusion (k=60)
│   ├── Фильтр по project_id (если указан)
│   └── Ранжирование + возврат top-k
│
├── search_by_entity(entity, k=5)
│   → list[SearchResult]
│   │
│   └── Поиск по извлечённым сущностям (статьи, нормы, ГОСТ)
│
└── get_related(document_id, k=5)
    → list[SearchResult]
    │
    └── Графовый поиск: документы, связанные с данным
```

### 7.3. RRF Fusion

```
Vector Results:  [A, B, C, D, E]
Graph Results:   [C, A, F, G, B]

RRF(A) = 1/(60+1) + 1/(60+1) = 0.0328
RRF(B) = 1/(60+2) + 1/(60+5) = 0.0315
RRF(C) = 1/(60+3) + 1/(60+1) = 0.0324

Fused: [A, C, B, D, E, F, G]
```

### 7.4. Извлечение нормативных ссылок

При ingest документа:

```
Текст chunk → LLM извлечение:
  ├── Ссылки на ГК РФ (ст. 743, ст. 333, ...)
  ├── Ссылки на ГрК РФ
  ├── Ссылки на ФЗ (44-ФЗ, 223-ФЗ, ...)
  ├── Ссылки на СП, ГОСТ, СНиП
  └── Ссылки на РД-11-02-2006 и другие формы

Каждая ссылка → узел в графе (NetworkX)
Связи между ссылками → рёбра графа
```

---

## 8. БЛС — БАЗА ЛОВУШЕК СУБПОДРЯДЧИКА

### 8.1. Структура ловушки

```
Trap
├── id: int
├── pattern: str (regex или текстовый паттерн)
├── description: str (описание ловушки)
├── law_reference: str (ссылка на закон, "ст. 743 ГК РФ")
├── recommendation: str (как исправить)
├── severity: "high" | "medium" | "low"
├── category: "payment" | "penalty" | "acceptance" | "scope" | "warranty"
└── source: str (откуда добавлена, YAML filename)
```

### 8.2. Проверка

```
BLSChecker
│
├── load_from_yaml(directory="traps/")
│   → list[Trap]
│
├── check(text, traps)
│   → list[TrapMatch]
│   │
│   ├── Pattern matching (regex)
│   ├── Semantic similarity (embeddings + pgvector)
│   └── LLM verification (gemma-4-e4b)
│
└── format_results(matches)
    → str (читаемый отчёт о ловушках)
```

### 8.3. Расширение

При обнаружении новой ловушки в договоре:

1. Пользователь подтверждает: «Это ловушка»
2. АСД создаёт новую Trap из контекста
3. Сохраняет в PostgreSQL + экспортирует в YAML
4. Система умнеет — следующая проверка уже с новой ловушкой

---

## 9. DOCX GENERATOR

### 9.1. Роль

Генерация документов Microsoft Word (.docx) по шаблонам.

### 9.2. Типы документов

| Тип | Шаблон | Модуль |
|-----|--------|--------|
| Протокол разногласий | protocol.docx | Юрист |
| Претензия | claim.docx | Юрист |
| Исковое заявление | lawsuit.docx | Юрист |
| АОСР | aosr.docx | ПТО |
| Акт входного контроля | incoming_control.docx | ПТО |
| Акт скрытых работ | hidden_works.docx | ПТО |
| Письмо | letter.docx | Делопроизводитель |
| Сопроводительное | cover_letter.docx | Делопроизводитель |
| Реестр отправки | shipment_registry.docx | Делопроизводитель |

### 9.3. Архитектура

```
DocXGenerator
│
├── generate(template_name, data, output_path)
│   → file_path
│   │
│   ├── Загрузка шаблона (data/templates/{template_name}.docx)
│   ├── Замена плейсхолдеров {{key}} → value
│   ├── Заполнение таблиц (для ВОР, ЛСР, реестров)
│   ├── Вставка изображений (подписи, печати)
│   └── Сохранение в exports/{type}/
│
└── fill_table(template, rows, headers)
    → заполненная таблица в DOCX
```

### 9.4. Плейсхолдеры

```
Шаблон protocol.docx:
  {{contract_number}}
  {{contract_date}}
  {{party_1}}
  {{party_2}}
  {{disagreements_table}}  ← динамическая таблица
  {{date}}
  {{signatory_1}}
  {{signatory_2}}
```

---

## 10. WIKI ENGINE

### 10.1. Роль

База знаний проекта. Хранит нормативные акты, проектную информацию,
извлечённые сущности. Компаундинг знаний.

### 10.2. Структура

```
WikiEngine
│
├── ingest(document_id, extracted_entities[], normative_refs[])
│   → list[WikiArticle]
│   │
│   ├── Создание/обновление статей
│   ├── Обновление связей между статьями
│   ├── Confidence scoring
│   └── Запись в log.md
│
├── search(query)
│   → list[WikiArticle]
│
├── get_article(title)
│   → WikiArticle
│
├── get_project_wiki(project_id)
│   → list[WikiArticle]
│
└── export_markdown(directory)
    → файлы .md на диск
```

### 10.3. WikiArticle

```
WikiArticle
├── id: int
├── project_id: int
├── title: str
├── content: str (Markdown)
├── source: str (откуда извлечено)
├── source_document_id: int
├── entities: list[str] (извлечённые сущности)
├── normative_refs: list[str] (нормативные ссылки)
├── confidence: float (0.0-1.0)
├── superseded_by: int (если статья устарела)
├── created_at: datetime
└── updated_at: datetime
```

---

## 11. EVENT MANAGER (STATE MACHINE)

### 11.1. Роль

Управляет Event-Driven Workflow и графом событий проекта. Гарантирует, что агенты выполняют задачи в правильном порядке. Когда один этап завершается (например, \"Тендер выигран\"), EventManager генерирует события для следующих этапов (\"Начать подготовку ИД\").

### 11.2. Структура
```
EventManager
│
├── register_event(project_id, event_type, payload)
│   → EventResult
│   │
│   ├── Сохранение события в графовую БД (NetworkX/Neo4j)
│   ├── Определение следующего узла (state transition)
│   └── Trigger(оповещение) нужного агента
│
├── get_project_state(project_id)
│   → ProjectState
│   │
│   └── Текущий этап: \"Tender\", \"Execution\", \"Completion\", \"Claim\"
│
└── pending_tasks(agent_role)
    → list[Task]
    │
    └── Задачи для конкретного агента (например, Логиста или ПТО)
```

---

## 12. ЗАВИСИМОСТИ МЕЖДУ КОМПОНЕНТАМИ

```
                    mcp_server.py
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   tools/           core/            db/
        │                │                │
        │         ┌──────┴──────┬────────────┐
        │         │             │            │
        │    OllamaClient   LightRAG   EventManager
        │         │             │            │
        │    ModelRouter   ParserEngine      │
        │         │             │            │
        │    RAMManager     BLSChecker       │
        │         │             │            │
        │    DocXGenerator  WikiEngine       │
        │                                    │
        └───────────────┬────────────────────┘
                        │
                  PostgreSQL 16
                  + pgvector
                  + NetworkX (in-memory)
```

### Зависимости инструментов

| Инструмент | Зависит от |
|-----------|------------|
| `asd_upload_document` | ParserEngine, LightRAG, OllamaClient (embeddings) |
| `asd_analyze_contract` | ParserEngine, OllamaClient (chat), BLSChecker, LightRAG |
| `asd_normative_search` | LightRAG, OllamaClient (embeddings) |
| `asd_generate_protocol` | DocXGenerator, PostgreSQL |
| `asd_generate_claim` | DocXGenerator, PostgreSQL, OllamaClient |
| `asd_generate_lawsuit` | DocXGenerator, PostgreSQL, OllamaClient |
| `asd_vor_check` | ParserEngine, OllamaClient |
| `asd_pd_analysis` | ParserEngine, OllamaClient |
| `asd_generate_act` | DocXGenerator, PostgreSQL |
| `asd_id_completeness` | PostgreSQL, OllamaClient |
| `asd_estimate_compare` | ParserEngine, OllamaClient |
| `asd_create_lsr` | ParserEngine, OllamaClient |
| `asd_supplement_estimate` | ParserEngine, OllamaClient |
| `asd_register_document` | PostgreSQL |
| `asd_generate_letter` | DocXGenerator, PostgreSQL, OllamaClient |
| `asd_prepare_shipment` | DocXGenerator, PostgreSQL |
| `asd_track_deadlines` | PostgreSQL |
| `asd_tender_search` | External API / Telegram |
| `asd_analyze_lot_profitability` | OllamaClient, PostgreSQL |
| `asd_source_vendors` | PostgreSQL (Vendors table) |
| `asd_add_price_list` | ParserEngine, PostgreSQL |
| `asd_compare_quotes` | OllamaClient, PostgreSQL |
| `asd_get_system_status` | OllamaClient, PostgreSQL, RAMManager |

---

## 13. СТРУКТУРА ПРОЕКТА

```
/home/z/my-project/mac_asd/
│
├── src/
│   ├── agents/
│   │   ├── workflow.py          # LangGraph (7 агентов)
│   │   ├── nodes.py             # Логика узлов
│   │   └── state.py             # Состояние графа
│   │
│   ├── core/
│   │   ├── llm_engine.py        # LLMEngine — единый интерфейс к LLM
│   │   ├── backends/            # Бэкенды LLMEngine
│   │   │   ├── mlx_backend.py   # MLX бэкенд (Mac Studio)
│   │   │   └── ollama_backend.py # OllamaBackend (используется через LLMEngine)
│   │   ├── ollama_client.py     # OllamaBackend (используется через LLMEngine)
│   │   ├── ram_manager.py       # Управление 128GB памяти
│   │   ├── event_manager.py     # Управление событиями и Workflow
│   │   └── ...
│   │
│   ├── config.py                # Профили (mac_studio / dev_linux), settings.get_model_config()
│   │
│   └── db/
│       ├── models.py            # SQLAlchemy модели
│       └── seed_logistics.py    # Сидинг данных (Логистика)
│
├── data/
│   ├── templates/               # Шаблоны DOCX
│   │   ├── protocol.docx
│   │   ├── claim.docx
│   │   ├── lawsuit.docx
│   │   ├── aosr.docx
│   │   ├── incoming_control.docx
│   │   ├── hidden_works.docx
│   │   ├── letter.docx
│   │   ├── cover_letter.docx
│   │   └── shipment_registry.docx
│   ├── raw/                     # Исходные файлы (raw/{project_id}/)
│   ├── processed/               # Распознанные тексты
│   ├── exports/                 # Сгенерированные DOCX
│   │   ├── protocols/
│   │   ├── claims/
│   │   ├── lawsuits/
│   │   ├── acts/
│   │   ├── estimates/
│   │   └── letters/
│   ├── wiki/                    # База знаний (Markdown)
│   └── graphs/                  # NetworkX графы (сериализация)
│
├── traps/                       # YAML файлы БЛС
│   └── default_traps.yaml       # 27 базовых ловушек
│
├── scripts/
│   ├── launch_asd.sh            # Запуск MCP сервера
│   ├── setup_db.sh              # Создание БД + миграции
│   └── test_mcp.py              # Тесты MCP инструментов
│
├── .env.example                 # Пример переменных окружения (профиль, URL бэкендов)
├── requirements.txt
├── alembic.ini
└── docs/
    └── CONCEPT_v11.md           # Этот документ
```

---

Этот документ описывает внутреннюю архитектуру всех компонентов АСД.
Документ актуализирован. LLMEngine и профили реализованы в Package 1.

---

## 14. ВНЕШНИЕ ИНТЕГРАЦИИ (GOOGLE WORKSPACE)

### 14.1. Роль
Позволяет всем агентам взаимодействовать с экосистемой Google (Gmail, Drive, Sheets).

### 14.2. Функции
- **Gmail:** Отправка RFQ Логистом, получение уведомлений.
- **Drive:** Хранение сканов ТТН и сертификатов Делопроизводителем.
- **Sheets:** Ведение сравнительных таблиц цен и реестров.
- **Docs:** Автоматическая генерация писем и претензий Юристом.
