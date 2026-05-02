# АСД v12.0 — ДЕТАЛЬНАЯ АРХИТЕКТУРА КОМПОНЕНТОВ

**Дата:** 20 апреля 2026
**Платформа:** Mac Studio M4 Max 128GB Unified Memory
**Статус:** Активная разработка (Package 1 ✅, Package 5 ✅ Evidence Graph/Inference/ProjectLoader, Package 11 ✅ Chain Builder/HITL/Journal Reconstructor v2)

---

## 1. ОБЗОР

Этот документ описывает внутреннюю архитектуру каждого компонента АСД v12.0:
классы, методы, потоки данных, зависимости между модулями. Документ не содержит
рабочего кода — только проектирование. Все описания соответствуют текущему состоянию
реализации в репозитории `/home/oleg/MAC_ASD/`.

Модельный ряд v12.0:

| Модель | Назначение | RAM | Бэкенд |
|--------|-----------|-----|--------|
| Llama 3.3 70B 4-bit (Руководитель проекта) | Оркестратор (pm) | ~40 GB | MLX |
| Gemma 4 31B 4-bit | 5 рабочих агентов (shared, 128K контекст) | ~23 GB | MLX-VLM |
| Gemma 4 E4B 4-bit | Делопроизводитель (archive) | ~3 GB | MLX-VLM |
| bge-m3-mlx-4bit | Embeddings | ~0.3 GB | MLX |
| Gemma 4 31B VLM | Vision/OCR (on-demand) | ~5 GB | MLX |

**Ключевое архитектурное решение v12.0:** Все 5 рабочих агентов (pto, smeta, legal,
procurement, logistics) используют единую копию Gemma 4 31B (128K контекст) через shared memory.
Переключение между агентами происходит через системный промпт, без перезагрузки модели.
Делопроизводитель (archive) использует отдельную модель Gemma 4 E4B (~3 GB).
Это позволяет удерживать Llama 3.3 70B как оркестратор и Gemma 4 E4B на постоянной основе.

---

## 2. MCP SERVER — ГЛАВНЫЙ КОМПОНЕНТ

### 2.1. Роль

Единая точка входа для Руководитель проекта Agent. Регистрирует 23 инструмента,
маршрутизирует вызовы к соответствующим модулям. Управляет жизненным циклом
через StateGraph и LangGraph. Сервер построен на фреймворке FastMCP и
поддерживает stdio-транспорт для интеграции с Claude Code и HTTP-транспорт
для тестирования и отладки.

MCP Server не содержит бизнес-логики — он является тонким слоем маршрутизации.
Каждый инструмент делегирует вызов соответствующему сервису: LegalService для
юридического анализа, ParserEngine для парсинга, DocXGenerator для генерации
документов и т.д. Это обеспечивает тестируемость и модульность системы.

### 2.2. Структура

```
mcp_servers/asd_core/server.py
│
├── Инициализация FastMCP
│   ├── Имя: "asd_core"
│   ├── Версия: "12.0.0"
│   └── Транспорт: stdio (продакшен) / http (тесты)
│
├── Регистрация инструментов (23 штуки)
│   ├── Юрист: tools/jurist_tools.py (7)
│   │   ├── asd_upload_document
│   │   ├── asd_analyze_contract
│   │   ├── asd_normative_search
│   │   ├── asd_generate_protocol
│   │   ├── asd_generate_claim
│   │   ├── asd_generate_lawsuit
│   │   └── asd_add_trap
│   │
│   ├── ПТО: tools/pto_tools.py (4)
│   │   ├── asd_vor_check
│   │   ├── asd_pd_analysis
│   │   ├── asd_generate_act
│   │   └── asd_id_completeness
│   │
│   ├── Сметчик: tools/smeta_tools.py (3)
│   │   ├── asd_estimate_compare
│   │   ├── asd_create_lsr
│   │   └── asd_supplement_estimate
│   │
│   ├── Делопроизводитель: tools/delo_tools.py (4)
│   │   ├── asd_register_document
│   │   ├── asd_generate_letter
│   │   ├── asd_prepare_shipment
│   │   └── asd_track_deadlines
│   │
│   ├── Закупщик: tools/procurement_tools.py (2)
│   │   ├── asd_tender_search
│   │   └── asd_analyze_lot_profitability
│   │
│   ├── Логист: tools/logistics_tools.py (3)
│   │   ├── asd_source_vendors
│   │   ├── asd_add_price_list
│   │   └── asd_compare_quotes
│   │
│   └── Общий: tools/general_tools.py (1)
│       └── asd_get_system_status
│
├── Интеграция с LangGraph
│   └── src/agents/workflow.py (Оркестрация 7 агентов через asd_app)
│       └── run_tender_pipeline() — E2E тест пайплайна
│
├── Инициализация сервисов (при старте)
│   ├── LLMEngine() → единый интерфейс к LLM
│   ├── PostgreSQL подключение (SQLAlchemy)
│   ├── ParserEngine() → парсинг документов
│   ├── RAGService() → векторный + графовый поиск
│   ├── GraphService() → NetworkX граф знаний
│   ├── RamManager() → управление 128GB Unified Memory
│   ├── StateGraph() → конечный автомат проекта
│   ├── LegalService() → юридический анализ (Package 4)
│   └── GoogleWorkspaceService() → Gmail, Drive, Sheets
│
└── Entry point
    └── mcp.run(transport="stdio")  # или "http" для тестов
```

### 2.3. Lifecycle (последовательность запуска)

```
Запуск:
  1. Загрузка конфигурации (config/settings.py → Settings с профилем)
  2. Подключение к PostgreSQL (SQLAlchemy, порт 5433)
  3. Инициализация LLMEngine
     ├── Определение профиля (ASD_PROFILE=mac_studio или dev_linux)
     ├── Создание MLXBackend
     └── Проверка доступности MLX (mac_studio) / Ollama (dev_linux)
  4. Инициализация ParserEngine, RAGService, GraphService
  5. Инициализация RamManager (бюджет RAM_BUDGET_GB)
  6. Инициализация LegalService, StateGraph
  7. Регистрация 23 инструментов в FastMCP
  8. Запуск stdio транспорта (блокирующий вызов)

Остановка:
  1. Закрытие соединений с PostgreSQL
  2. Ожидание завершения активных LLM-запросов
  3. Выгрузка моделей через RamManager.unload_model()
  4. Сохранение графа знаний (GraphService.save_graph())
  5. Освобождение ресурсов и завершение процесса
```

### 2.4. Обработка ошибок

Каждый инструмент возвращает единый формат JSON, что обеспечивает консистентность
обработки ошибок на стороне Руководитель проекта. Формат включает флаг успеха, машинно-читаемый
код ошибки, человеко-понятное описание и произвольные детали.

```json
{
  "success": true,
  "error_code": null,
  "message": "Анализ завершён успешно",
  "details": { "findings_count": 5 }
}
```

```json
{
  "success": false,
  "error_code": "PARSER_ERROR",
  "message": "Не удалось распарсить PDF: файл повреждён",
  "details": { "file_path": "/data/raw/contract.pdf", "page": 3 }
}
```

**Коды ошибок:**

| Код | Описание |
|-----|----------|
| `PARSER_ERROR` | Ошибка парсинга документа (формат, кодировка, повреждение) |
| `LLM_ERROR` | Ошибка LLM (таймаут, модель недоступна, невалидный ответ) |
| `DB_ERROR` | Ошибка базы данных (соединение, запрос, ограничение) |
| `NOT_FOUND` | Объект не найден (документ, проект, запись) |
| `VALIDATION_ERROR` | Ошибка валидации входных данных |
| `MEMORY_CRITICAL` | Критический уровень памяти, задача отклонена |

---

## 3. LLM ENGINE

### 3.1. Роль

LLMEngine — единый интерфейс ко всем LLM-операциям в АСД. Заменяет OllamaClient
из ранних версий. Поддерживает основной бэкенд MLX (Mac Studio) для всех операций
(chat, embeddings, vision) и Ollama как fallback для dev-окружения. Агент указывается
по имени, модель и бэкенд определяются автоматически через профиль конфигурации.

Ключевой принцип: вызывающий код не знает, какая модель и какой бэкенд используется.
Он просто вызывает `llm_engine.chat("legal", messages)` — а LLMEngine через
`settings.get_model_config("legal")` определяет, что для профиля mac_studio это
Gemma 4 31B 4-bit через MLX-VLM, а для dev_linux — qwen3:32b через Ollama.

### 3.2. Методы

```
LLMEngine(profile="auto")
│
├── __init__()
│   ├── self._profile = settings.ASD_PROFILE
│   ├── self._ollama = OllamaBackend()
│   ├── self._mlx = MLXBackend()
│   ├── self._fallback_to_ollama = True  # Всегда разрешать fallback
│   └── Логирование: профиль и доступность MLX
│
├── chat(agent, messages, temperature=None, num_ctx=None, stream=False, keep_alive="5m")
│   → str (ответ модели)
│   │
│   ├── agent: "pm" | "pto" | "smeta" | "legal" | "procurement" | "logistics" | "archive"
│   ├── messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
│   ├── config = settings.get_model_config(agent) → {"engine": "mlx"|"ollama", "model": "..."}
│   ├── backend = self._get_backend(config["engine"])
│   ├── temperature по умолчанию: pm=0.3, pto=0.2, smeta=0.1, legal=0.1,
│   │                        procurement=0.2, logistics=0.2, archive=0.1
│   ├── num_ctx по умолчанию: pm=32768, pto=32768, smeta=32768, legal=32768,
│   │                      procurement=16384, logistics=16384, archive=8192
│   └── Делегирует вызов backend.chat(model, messages, temperature, num_ctx, stream, keep_alive)
│
├── chat_raw(agent, messages, temperature=None, num_ctx=None, keep_alive="5m")
│   → Dict[str, Any] (полный JSON-ответ Ollama API)
│   │
│   └── Аналогичен chat(), но возвращает сырой ответ API (для совместимости)
│
├── safe_chat(agent, messages, fallback_response='{"status": "error", ...}', **kwargs)
│   → str (ответ модели с автоматическим fallback)
│   │
│   ├── Основной вызов: chat(agent, messages, **kwargs)
│   ├── При ошибке: логирование предупреждения и возврат fallback_response
│   └── Гарантирует возврат результата даже при недоступности модели
│
├── vision(agent, image_base64, prompt, temperature=0.2, keep_alive="5m")
│   → str (ответ vision модели)
│   │
│   ├── config = settings.get_model_config("vision") → {"engine": "mlx", "model": "Gemma 4 31B VLM"}
│   ├── image_base64: base64-кодированное изображение
│   ├── prompt: текстовая инструкция для модели
│   └── Использует Gemma 4 31B VLM — уже загружена (shared model)
│
├── embed(text, model=None)
│   → List[float] (embedding вектор, 1024 dim для bge-m3-mlx-4bit)
│   │
│   ├── Через MLXBackend (bge-m3-mlx-4bit)
│   ├── model = settings.get_model_config("embed")["model"] если не указан
│   └── Вызов MLX API embeddings
│
├── generate(model, prompt, keep_alive=0)
│   → Dict[str, Any] (низкоуровневый generate endpoint)
│   │
│   └── Используется RamManager для загрузки/выгрузки моделей (keep_alive=0 = выгрузка)
│
└── Автоопределение профиля
    → settings.get_model_config(agent)
    │
    ├── Профиль "mac_studio":
    │   ├── pm  → MLX,  Meta-Llama-3.3-70B-Instruct-4bit
    │   ├── pto/smeta/legal/procurement/logistics → MLX-VLM, gemma-4-31b-it-4bit ← shared (128K контекст)
    │   ├── archive → MLX-VLM, gemma-4-e4b-it-4bit
    │   ├── embed → MLX, bge-m3-mlx-4bit
    │   └── vision → MLX, Gemma 4 31B VLM
    │
    ├── Профиль "dev_linux":
    │   ├── Все агенты → Ollama, qwen3:32b (кроме archive → qwen3:8b)
    │   ├── embed → MLX, bge-m3-mlx-4bit
    │   └── vision → MLX, Gemma 4 31B VLM
    │
    └── Выбор бэкенда: MlxBackend.is_available() ? MLX : Ollama (fallback)
```

### 3.3. Thinking Mode

Для Gemma 4 31B thinking mode активируется через модификацию системного промпта,
побуждающую модель к пошаговому рассуждению перед формулировкой ответа. Это
критически важно для задач, где качество анализа важнее скорости генерации.

```python
def _build_thinking_prompt(system_prompt):
    return f"""{system_prompt}

Think step by step. Analyze the input carefully before responding.
Show your reasoning process."""
```

**Thinking mode ВКЛЮЧАЕТСЯ для:**

- Юридическая экспертиза договоров (legal_analysis, contract_review)
- Генерация протоколов разногласий, претензий, исков
- Сверка ВОР/ПД (vor_check)
- Комплексный анализ проектной документации (pd_analysis)
- Сравнение смет (estimate_compare)

**Thinking mode ОТКЛЮЧАЕТСЯ для:**

- Классификация документов (archive)
- Простые ответы в чате (pm routing)
- Извлечение метаданных (archive)
- Статус системы (general)
- Embeddings и vision

Определение необходимости thinking mode реализовано в `ModelRouter.THINKING_TASKS`
— множестве типов задач, требующих расширенного рассуждения.

### 3.4. Retry и таймауты

| Операция | Таймаут | Retries | Backoff | Обоснование |
|----------|---------|---------|---------|-------------|
| chat | 300 сек (5 мин) | 2 | 2x | Длинные юридические анализы |
| chat_raw | 300 сек | 2 | 2x | Аналогично chat |
| chat_stream | 600 сек (10 мин) | 1 | — | Map-Reduce: последовательные чанки |
| embeddings | 30 сек | 3 | 1.5x | Быстрая операция, частые вызовы |
| batch_embeddings | 120 сек | 2 | 2x | Батчинг 32 чанков |
| vision | 60 сек | 2 | 2x | OCR сканов |
| generate | 60 сек | 1 | 1x | Управление моделями (load/unload) |
| is_available | 5 сек | 3 | 1x | Проверка доступности |

---

## 4. MODEL ROUTER

> **Примечание:** Начиная с v12.0, модельный роутинг полностью интегрирован
> в LLMEngine. ModelRouter существует как вспомогательный класс для определения
> типа задачи → агент → модель, но основная маршрутизация происходит через
> `settings.get_model_config(agent_name)` внутри LLMEngine.

### 4.1. Роль

Автоматический выбор модели на основе агента (имя роли). Пользователь и вызывающий
код не указывают модель — LLMEngine решает сам через профиль. ModelRouter добавляет
уровень абстракции «тип задачи → агент», позволяя инструментам MCP не знать о
внутренних агентах, а оперировать семантическими типами задач.

### 4.2. Правила маршрутизации

```
Агент (имя роли)
  │
  ├── pm (Руководитель проекта)
  │     → Llama 3.3 70B 4-bit (MLX)  [~40 GB, всегда загружена]
  │
  ├── pto (ПТО-инженер)
  │     → Gemma 4 31B 4-bit (MLX-VLM, shared memory, 128K контекст)
  │
  ├── smeta (Сметчик)
  │     → Gemma 4 31B 4-bit (MLX-VLM, shared memory)
  │
  ├── legal (Юрист)
  │     → Gemma 4 31B 4-bit (MLX-VLM, shared memory)
  │
  ├── procurement (Закупщик)
  │     → Gemma 4 31B 4-bit (MLX-VLM, shared memory)
  │
  ├── logistics (Логист)
  │     → Gemma 4 31B 4-bit (MLX-VLM, shared memory)
  │
  ├── archive (Архивариус/Делопроизводитель)
  │     → Gemma 4 E4B 4-bit (MLX-VLM)
  │
  ├── vision (Vision/OCR)
  │     → Gemma 4 31B VLM (MLX, подгружается по требованию)
  │
  └── embed (Embeddings)
        → bge-m3-mlx-4bit (MLX, всегда загружена)
```

**Таблица Task → Agent (ModelRouter.TASK_TO_AGENT):**

| Тип задачи | Агент | Модель (mac_studio) |
|-----------|-------|---------------------|
| legal_analysis | legal | Gemma 4 31B |
| contract_review | legal | Gemma 4 31B |
| normative_search | legal | Gemma 4 31B |
| claim_generation | legal | Gemma 4 31B |
| protocol_generation | legal | Gemma 4 31B |
| estimate_creation | smeta | Gemma 4 31B |
| estimate_compare | smeta | Gemma 4 31B |
| rate_lookup | smeta | Gemma 4 31B |
| lsr_creation | smeta | Gemma 4 31B |
| ocr / drawing_analysis / vision | pto | Gemma 4 31B |
| vor_extraction / vor_check | pto | Gemma 4 31B |
| pd_analysis | pto | Gemma 4 31B |
| tender_search | procurement | Gemma 4 31B |
| profitability_analysis | procurement | Gemma 4 31B |
| logistics_rfq / vendor_sourcing | logistics | Gemma 4 31B |
| quote_comparison | logistics | Gemma 4 31B |
| classification / registration | archive | Gemma 4 E4B |
| letter_generation / summary | archive | Gemma 4 E4B |
| routing / verdict | pm | Llama 3.3 70B |

### 4.3. Fallback стратегия

```
Llama 3.3 70B недоступна (pm)
  → Gemma 4 31B (сниженное качество маршрутизации, но работает)
    → Ошибка "Оркестратор недоступен"

Gemma 4 31B недоступна (5 рабочих агентов)
  → Llama 3.3 70B (сниженное качество анализа, повышенный расход RAM)
    → safe_chat fallback_response (гарантированный возврат)

bge-m3-mlx-4bit недоступна (embed)
  → Полнотекстовый поиск pg_trgm (без embeddings)
    → Ошибка "Поиск временно недоступен"

Gemma 4 31B VLM недоступен (vision/OCR)
  → pytesseract (базовый OCR, снижение качества)
    → Ошибка "OCR недоступен"
```

Fallback на уровне LLMEngine реализован в методе `safe_chat()`: при любой ошибке
основного вызова LLM возвращает предопределённый fallback_response, что гарантирует,
что инструмент MCP всегда вернёт результат (пусть и ошибочный), а не упадёт с
исключением.

---

## 5. RAM MANAGER

### 5.1. Роль

Контроль использования 128GB Unified Memory на Mac Studio M4 Max. Предотвращение
OOM (Out Of Memory) при загрузке больших PDF и одновременной работе нескольких
моделей. RamManager отслеживает потребление памяти через psutil, управляет списком
активных моделей и принудительно выгружает модели при высоком давлении памяти.

В v12.0 базовое потребление памяти составляет ~66 GB для моделей, что оставляет
значительный запас для контекста и параллельных задач. Gemma 4 31B обслуживает
5 рабочих агентов через shared memory (~23 GB), а Gemma 4 E4B (~3 GB) выделена
Делопроизводителю.

### 5.2. Мониторинг

```
RamManager
│
├── __init__()
│   ├── self.total_budget_gb = settings.RAM_BUDGET_GB (28 по умолчанию для dev_linux)
│   └── self.active_models: List[str] = []  # Список загруженных моделей
│
├── get_memory_usage_gb()
│   → float (GB использовано)
│   │
│   └── psutil.virtual_memory().used / (1024 ** 3)
│       Учитывает всю память системы, включая модели MLX
│
├── check_memory_health()
│   → bool (True если память в норме, False если критически мала)
│   │
│   ├── Сравнивает used_gb с total_budget_gb
│   └── Логирует CRITICAL при превышении бюджета
│
├── unload_model(model_name)
│   → None (принудительная выгрузка модели)
│   │
│   ├── llm_engine.generate(model=model_name, prompt="", keep_alive=0)
│   ├── Удаление из self.active_models
│   └── Логирование результата выгрузки
│
├── ensure_memory_for(incoming_model, expected_cost_gb)
│   → None (гарантия наличия памяти для загрузки модели)
│   │
│   ├── Проверка: available = total_budget_gb - used_gb
│   ├── Если available < expected_cost_gb:
│   │   ├── Логирование предупреждения
│   │   └── Выгрузка второстепенных моделей (кроме primary)
│   └── Добавление incoming_model в active_models
│
└── Модельные бюджеты (фактическое потребление на Mac Studio):
    │
    ├── llama-3.3-70b-4bit:    40.0 GB  (оркестратор, всегда загружен)
    ├── gemma-4-31b-it-4bit:   23.0 GB  (5 агентов shared, 128K контекст, всегда загружен)
    ├── gemma-4-e4b-it-4bit:    3.0 GB  (архивариус, всегда загружен)
    ├── bge-m3-mlx-4bit:         0.3 GB  (embeddings, всегда загружен)
    └── Gemma 4 31B VLM:              5.0 GB  (vision/OCR, подгружается по требованию)
```

### 5.3. Политики

Базовая загрузка моделей v12.0: ~66.3 GB (52% от 128 GB).

| Давление памяти | % RAM | GB | Действие |
|----------------|-------|-----|----------|
| **low** | < 70% | < 90 GB | Llama 70B + Gemma 4 31B + Gemma 4 E4B + bge-m3-mlx-4bit загружены, Gemma 4 31B VLM по требованию |
| **medium** | 70-80% | 90-102 GB | Нормально, пик контекста укладывается, лог-предупреждение |
| **high** | 80-90% | 102-115 GB | Gemma 4 31B VLM выгружается, задачи завершаются последовательно |
| **critical** | > 90% | > 115 GB | Новые задачи отклоняются (MEMORY_CRITICAL), возможна выгрузка Gemma 4 31B |

### 5.4. Бюджет контекста для Map-Reduce

При Map-Reduce анализе большого документа через LegalService:

```
Модели (4-bit, базово):    66.3 GB  (Llama 70B + Gemma 4 31B + Gemma 4 E4B + bge-m3-mlx-4bit)
Система (macOS + PG + App): 18.0 GB
────────────────────────────────────
Занято базово:             84.3 GB
Свободно:                  ~42 GB   (128 - 84.3 ≈ 42 с учётом overhead)
────────────────────────────────────
Безопасный лимит на чанк:  10-15 GB
Параллелизм:               1 задача (последовательно)
OCR (Gemma 4 31B VLM):           0 GB  (shared model, уже загружена)
Пик RAM:                  ~89.3 GB  (с OCR) / ~84.3 GB (без OCR)
Запас:                    ~38.7 GB  (с OCR, достаточно для устойчивой работы)
```

---

## 6. PARSER ENGINE

### 6.1. Роль

Универсальный парсер документов: PDF (текстовый/скан), Excel, JSON.
Автоматически определяет тип файла и выбирает метод извлечения. Поддерживает
двухэтапный конвейер Vision Cascade для PDF: сначала попытка извлечения текста
через PyMuPDF, затем fallback на OCR через Gemma 4 31B VLM для сканированных страниц.

ParserEngine является фундаментом для всех последующих операций: LegalService
получает текст через парсинг, LightRAG индексирует распарсенные чанки, БЛС
проверяет текст на ловушки. Качество парсинга напрямую влияет на качество
всех downstream-операций.

### 6.2. Архитектура

```
ParserEngine
│
├── parse_pdf(file_path)
│   → List[Dict[str, Any]]  (список чанков с текстом и метаданными)
│   │
│   ├── Открывает PDF через PyMuPDF (fitz.open)
│   ├── Для каждой страницы:
│   │   ├── Stage 1: page.get_text().strip()
│   │   │   └── Если текст найден → chunk с method="pymupdf_text"
│   │   └── Stage 2: _vision_ocr_fallback(page)
│   │       └── Если текста нет → OCR через Gemma 4 31B VLM с method="vision_ocr"
│   └── Возвращает список чанков [{"content", "page", "method", "metadata"}]
│
├── _vision_ocr_fallback(page)
│   → str (распознанный текст)
│   │
│   ├── Рендеринг страницы в PNG (page.get_pixmap())
│   ├── Кодирование в base64 для vision API
│   ├── llm_engine.vision("vision", image_base64, prompt)
│   └── Возвращает распознанный текст
│
├── parse_xlsx(file_path)
│   → List[Dict[str, Any]]
│   │
│   ├── openpyxl.load_workbook(file_path)
│   ├── Извлечение данных из активного листа
│   └── Возвращает чанк с метаданными spreadsheet
│
└── Типы файлов (определяются по расширению):
    ├── .pdf  → parse_pdf()
    ├── .xlsx / .xls → parse_xlsx()
    ├── .json → TelegramParser (для RFQ из Telegram)
    └── прочие → попытка чтения как текст (UTF-8)
```

### 6.3. Автомаршрутизация PDF

Конвейер Vision Cascade автоматически определяет, является ли страница текстовой
или сканированной, и выбирает оптимальный метод извлечения:

```
PDF файл
  │
  ▼
PyMuPDF: extract text per page
  │
  ├── Страница содержит текст (page.get_text().strip() != "")
  │     → Текстовый PDF
  │     → PyMuPDFParser (быстро, ~0.01 сек/страница, 100% точность)
  │
  └── Страница не содержит текста (скан / изображение)
        → Скан PDF
        │
        ▼
        Gemma 4 31B VLM уже загружена (shared, 23 GB)
          │
          ▼
        MLX Vision API (Gemma 4 31B VLM)
          ├── Рендеринг страницы: 300 DPI → PNG
          ├── Base64 кодирование изображения
          ├── Вызов Gemma 4 31B VLM с OCR-промптом
          └── Возврат распознанного текста
          │
          ▼
        Gemma 4 31B VLM остаётся в памяти (shared model)
```

### 6.4. ParsedDocument

Структура данных, возвращаемая парсером, содержит полный текст документа,
постраничную разбивку, метаданные и чанки для индексации в RAG:

```
ParsedDocument
├── text: str (полный текст документа)
├── pages: list[Page]
│   ├── page_number: int
│   ├── text: str
│   ├── images: list[Image]  (изображения на странице)
│   └── tables: list[Table]  (извлечённые таблицы)
├── metadata: Metadata
│   ├── file_name: str
│   ├── file_size: int (байты)
│   ├── page_count: int
│   ├── is_scan: bool (true если >50% страниц — сканы)
│   ├── detected_language: str ("ru", "en", "mixed")
│   └── parsed_at: datetime
└── chunks: list[Chunk] (после чанкинга, для RAG)
    ├── content: str (текст чанка)
    ├── page: int (номер страницы)
    ├── method: str ("pymupdf_text" | "vision_ocr" | "openpyxl")
    ├── metadata: dict (source, type, и т.д.)
    └── token_count: int (расчётное количество токенов)
```

### 6.5. Чанкинг

Стратегия чанкинга критически важна для качества Map-Reduce анализа и RAG-поиска.
Чанки формируются по границам абзацев, с перекрытием для сохранения контекста:

```
_chunk_text(text, chunk_size=6000, chunk_overlap=300)
  │
  ├── Размер чанка: 6000 символов (оптимально для Gemma 4 31B)
  ├── Overlap: 300 символов (контекст между чанками)
  ├── Резание по границам абзацев:
  │   ├── Приоритет: двойной перенос строки ("\n\n")
  │   ├── Fallback: одинарный перенос строки ("\n")
  │   └── Не рвёт посередине предложения
  ├── Для юридических документов: не рвёт посередине статьи/пункта
  └── Пустые чанки отбрасываются
```

---

## 7. LIGHT RAG

### 7.1. Роль

Единый поиск по нормативной базе и проектной документации. Комбинирует векторный
поиск (pgvector, bge-m3 embeddings) с графовым поиском (NetworkX, обход связей)
через RRF Fusion. Обеспечивает контекст для LegalService, БЛС, WikiEngine и
инструментов нормативного поиска.

LightRAG реализован через `RAGService` (src/core/rag_service.py) и `GraphService`
(src/core/graph_service.py). RAGService отвечает за индексацию и векторный поиск,
GraphService — за графовый контекст и связи между документами.

### 7.2. Архитектура

```
RAGService (src/core/rag_service.py)
│
├── index_document(document_id, chunks)
│   → None (индексация чанков в PostgreSQL + pgvector)
│   │
│   ├── Для каждого чанка:
│   │   ├── embedding = await llm_engine.embed(chunk["content"])  (bge-m3, 1024 dim)
│   │   └── DocumentChunk(document_id, content, embedding, page_number) → PostgreSQL
│   ├── GraphService.add_document(str(document_id), {"status": "indexed"})
│   └── Логирование: количество проиндексированных чанков
│
├── search(query, top_k=5)
│   → List[Dict[str, Any]]  (векторный поиск через pgvector)
│   │
│   ├── query_embedding = await llm_engine.embed(query)
│   ├── SQL: SELECT * FROM document_chunks ORDER BY embedding <-> query_embedding LIMIT top_k
│   ├── Оператор <-> — L2 дистанция (pgvector)
│   └── Возвращает [{"content", "page", "doc_id"}]
│
└── hybrid_search(query, top_k=5)
    → Dict[str, Any]  (векторный + графовый контекст)
    │
    ├── vector_chunks = await self.search(query, top_k)
    ├── doc_ids = уникальные ID документов из векторной выдачи
    ├── graph_context = []
    │   └── Для каждого doc_id:
    │       └── graph_service.get_related_nodes(doc_id, depth=1)
    └── Возвращает {"vector_chunks": [...], "graph_context": [...]}
```

```
GraphService (src/core/graph_service.py)
│
├── __init__()
│   ├── self.graph_dir = settings.graphs_path
│   ├── self.graph_path = graph_dir / "knowledge_graph.gpickle"
│   └── self.graph = _load_or_create_graph()  (NetworkX DiGraph, pickle)
│
├── add_document(doc_id, metadata)
│   → Добавляет узел типа "Document" в граф
│
├── add_normative_act(act_id, title)
│   → Добавляет узел типа "Normative_Act" в граф
│
├── add_reference(source_id, target_id, context="")
│   → Добавляет ребро REFERENCES между существующими узлами
│
├── get_related_nodes(node_id, depth=1)
│   → List[Dict]  (BFS обход графа на заданную глубину)
│
└── save_graph()
    → Сериализация графа в pickle файл на диск
```

### 7.3. RRF Fusion

Reciprocal Rank Fusion (RRF) — алгоритм объединения результатов векторного и
графового поиска в единый ранжированный список. RRF не требует нормализации
оценок и устойчив к разным масштабам релевантности.

```
Формула: RRF(d) = Σ 1/(k + rank_i(d))

Где:
  d — документ
  k — константа сглаживания (обычно 60)
  rank_i(d) — позиция документа d в выдаче i-го метода

Пример:
  Vector Results:  [A, B, C, D, E]     → ранги: A=1, B=2, C=3, D=4, E=5
  Graph Results:   [C, A, F, G, B]     → ранги: C=1, A=2, F=3, G=4, B=5

  RRF(A) = 1/(60+1) + 1/(60+2) = 0.01639 + 0.01613 = 0.03252
  RRF(B) = 1/(60+2) + 1/(60+5) = 0.01613 + 0.01538 = 0.03151
  RRF(C) = 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226
  RRF(D) = 1/(60+4) + 0          = 0.01563
  RRF(E) = 1/(60+5) + 0          = 0.01538
  RRF(F) = 0          + 1/(60+3) = 0.01587
  RRF(G) = 0          + 1/(60+4) = 0.01563

  Fused (по убыванию RRF): [A, C, B, F, D, G, E]
```

### 7.4. Извлечение нормативных ссылок

При индексации документа (ingest) RAGService извлекает нормативные ссылки
и регистрирует их как узлы в графе знаний через GraphService:

```
Текст чанка → LLM извлечение:
  ├── Ссылки на ГК РФ (ст. 743, ст. 333, ст. 445, ...)
  ├── Ссылки на ГрК РФ (ст. 52, ст. 55, ...)
  ├── Ссылки на ФЗ (44-ФЗ, 223-ФЗ, ...)
  ├── Ссылки на СП, ГОСТ, СНиП (СП 48.13330, ГОСТ Р 21.1101, ...)
  └── Ссылки на РД-11-02-2006 и другие формы

Каждая ссылка → узел типа "Normative_Act" в графе (NetworkX)
Связи между ссылками → рёбра REFERENCES (документ → нормативный акт)
Документы, ссылающиеся на одни и те же нормы → косвенная связь через граф
```

Это позволяет при поиске по одному документу автоматически находить связанные
документы, которые ссылаются на те же нормы права — критически важно для
юридического анализа и БЛС.

---

## 8. БЛС — БАЗА ЛОВУШЕК СУБПОДРЯДЧИКА

### 8.1. Структура ловушки

БЛС (База Ловушек Субподрядчика) — система выявления неблагоприятных условий
в договорах субподряда. Каждая ловушка описывает паттерн, который может
привести к финансовым потерям или юридическим рискам для субподрядчика.

```
Trap
├── id: int (уникальный идентификатор)
├── pattern: str (regex или текстовый паттерн для поиска)
├── description: str (человеко-читаемое описание ловушки)
├── law_reference: str (ссылка на закон, "ст. 743 ГК РФ")
├── recommendation: str (рекомендация по исправлению)
├── severity: "high" | "medium" | "low" (уровень серьёзности)
├── category: str (категория ловушки — см. 8.3)
├── subcategory: str (уточнение, например "payment_delay", "penalty_excessive")
├── jurisdiction: str (юрисдикция: "гк_рф", "грк_рф", "44фз", "223фз")
├── enabled: bool (активна ли ловушка, по умолчанию True)
└── source: str (откуда добавлена: YAML filename или "rag_discovery")
```

### 8.2. BLSChecker

BLSChecker выполняет гибридную проверку текста договора на наличие ловушек.
Начиная с v12.0 используется двухуровневый подход: YAML-файлы для базовых
известных ловушек и RAG/pgvector для динамически обнаруженных.

```
BLSChecker
│
├── load_from_yaml(directory="traps/")
│   → list[Trap]
│   │
│   ├── Загрузка YAML-файлов из директории traps/
│   ├── Парсинг полей каждой ловушки
│   └── Возвращает список активных ловушек (enabled=True)
│
├── load_from_rag(project_id)
│   → list[Trap]
│   │
│   ├── Поиск ранее обнаруженных ловушек через pgvector embeddings
│   ├── RAGService.search() с запросом по контексту проекта
│   ├── Semantic similarity (embeddings + pgvector)
│   └── Возвращает ловушки, обнаруженные в предыдущих анализах
│
├── check(text, traps)
│   → list[TrapMatch]
│   │
│   ├── Level 1: Pattern matching (regex по pattern из YAML)
│   │   └── Быстрая проверка — миллисекунды
│   ├── Level 2: Semantic similarity (embeddings + pgvector)
│   │   └── Поиск похожих конструкций через векторный поиск
│   └── Level 3: LLM verification (Gemma 4 31B)
│       └── Подтверждение/опровержение совпадений (устранение ложных срабатываний)
│
└── format_results(matches)
    → str (читаемый отчёт о найденных ловушках)
    │
    ├── Группировка по severity (high → medium → low)
    ├── Группировка по category
    ├── Форматирование с law_reference и recommendation
    └── Возврат Markdown-строки
```

### 8.3. Категории ловушек (10 штук)

| Категория | Описание | Примеры subcategory |
|-----------|----------|---------------------|
| `payment` | Условия оплаты | payment_delay, payment_guarantee, payment_hold |
| `penalty` | Штрафные санкции | penalty_excessive, penalty_one_sided, penalty_no_limit |
| `acceptance` | Приёмка работ | acceptance_unilateral, acceptance_short_term, acceptance_no_act |
| `scope` | Объём работ | scope_unilateral_change, scope_no_spec, scope_vague |
| `warranty` | Гарантийные обязательства | warranty_extended, warranty_no_limit, warranty_start |
| `subcontractor` | Ограничения субподряда | subcontractor_prohibition, subcontractor_consent |
| `liability` | Ответственность | liability_unlimited, liability_one_sided, liability_indemnity |
| `corporate_policy` | Корпоративные требования | corporate_nda, corporate_insurance, corporate_audit |
| `termination` | Расторжение договора | termination_unilateral, termination_no_notice, termination_forced |
| `insurance` | Страхование и гарантии | insurance_requirement, bank_guarantee, retention |

### 8.4. Гибридный подход: YAML + RAG/pgvector (с v12.0)

До v12.0 БЛС работала исключительно на YAML-файлах — фиксированный набор
ловушек, обновляемый вручную. Начиная с v12.0 реализован гибридный подход:

**YAML (статические ловушки):**
- Файл `traps/default_traps.yaml` — 58 ловушек
- Быстрый pattern matching (regex)
- Надёжные, проверенные паттерны
- Обновляются только вручную

**RAG/pgvector (динамические ловушки):**
- Ловушки, обнаруженные в предыдущих анализах
- Хранятся в PostgreSQL + pgvector embeddings
- Semantic similarity поиск
- Система умнеет с каждым проанализированным договором

**Конвейер проверки:**
```
Текст договора
  │
  ├── [1] YAML pattern matching → быстрые совпадения (regex)
  │
  ├── [2] RAG semantic search → похожие ловушки из предыдущих анализов
  │
  ├── [3] LLM verification → Gemma 4 31B подтверждает/опровержает совпадения
  │
  └── [4] Объединение результатов → итоговый список TrapMatch
```

### 8.5. Расширение: процесс добавления новой ловушки

При обнаружении новой ловушки в договоре (которой нет ни в YAML, ни в RAG):

1. **Обнаружение:** LLM при анализе чанка выделяет подозрительную конструкцию
2. **Подтверждение:** Пользователь подтверждает: «Это ловушка» (через `asd_add_trap`)
3. **Автозаполнение:** АСД создаёт новую Trap из контекста:
   - `subcategory` — определяется по содержанию (например, "payment_delay")
   - `jurisdiction` — извлекается из law_reference
   - `severity` — оценивается LLM на основе риска
   - `source` = "rag_discovery"
4. **Сохранение:** Trap записывается в PostgreSQL + pgvector embedding
5. **Экспорт:** Опциональный экспорт в YAML-файл для portability
6. **Эффект:** Следующая проверка уже учитывает новую ловушку через RAG

---

## 9. DOCX GENERATOR

### 9.1. Роль

Генерация документов Microsoft Word (.docx) по шаблонам. DocXGenerator
используется юридическим агентом для протоколов разногласий, претензий и
исковых заявлений, ПТО — для актов, делопроизводителем — для писем и реестров.
Шаблоны хранятся в `data/templates/` и содержат плейсхолдеры `{{key}}`, которые
заменяются на фактические данные при генерации.

### 9.2. Типы документов (9 типов)

| Тип | Шаблон | Модуль | Описание |
|-----|--------|--------|----------|
| Протокол разногласий | `protocol.docx` | Юрист | Ст. 445 ГК РФ, таблица разногласий |
| Претензия | `claim.docx` | Юрист | Досудебная претензия контрагенту |
| Исковое заявление | `lawsuit.docx` | Юрист | Иск в арбитражный суд |
| АОСР | `aosr.docx` | ПТО | Акт освидетельствования скрытых работ |
| Акт входного контроля | `incoming_control.docx` | ПТО | Акт приёмки материалов |
| Акт скрытых работ | `hidden_works.docx` | ПТО | Акт приёмки скрытых работ |
| Письмо | `letter.docx` | Дело | Официальное письмо контрагенту |
| Сопроводительное | `cover_letter.docx` | Дело | Сопроводительное письмо к пакету документов |
| Реестр отправки | `shipment_registry.docx` | Дело | Реестр отправленной документации |

### 9.3. Архитектура

```
DocXGenerator
│
├── generate(template_name, data, output_path)
│   → file_path (путь к сгенерированному файлу)
│   │
│   ├── Загрузка шаблона: data/templates/{template_name}.docx
│   ├── Замена плейсхолдеров: {{key}} → value (по data dict)
│   ├── Заполнение таблиц (для ВОР, ЛСР, реестров)
│   ├── Вставка изображений (подписи, печати)
│   ├── Сохранение: exports/{type}/{timestamp}_{template_name}.docx
│   └── Возврат пути к файлу
│
├── generate_protocol_docx(analysis_result, party_info, output_path)
│   → file_path
│   │
│   ├── Генерация протокола разногласий на основе LegalAnalysisResult
│   ├── Заполнение данных сторон из ProtocolPartyInfo (2 стороны)
│   ├── Автоматическое формирование таблицы разногласий:
│   │   ├── Столбцы: "Пункт договора", "Редакция заказчика", "Редакция подрядчика", "Обоснование"
│   │   └── Строки: из analysis_result.protocol_suggestions
│   ├── Поддержка ст. 445 ГК РФ (протокольные разногласия)
│   └── Сохранение: exports/protocols/{contract_number}_protocol.docx
│
└── fill_table(template, rows, headers)
    → заполненная таблица в DOCX
    │
    ├── Создание/поиск таблицы в шаблоне по маркеру
    ├── Заполнение заголовков (headers)
    ├── Заполнение строк данными (rows)
    └── Форматирование: шрифт, выравнивание, границы
```

### 9.4. ProtocolPartyInfo

Модель данных для представления стороны договора в протоколе разногласий.
Содержит всю юридически значимую информацию о контрагенте, необходимую для
оформления протокола в соответствии с требованиями делового оборота.

```
ProtocolPartyInfo
├── name: str (полное наименование организации, "ООО 'СтройМонтаж'")
├── legal_address: str (юридический адрес, "123456, г. Москва, ул. ...")
├── inn: str (ИНН организации, "7701234567")
├── position: str (должность подписанта, "Генеральный директор")
├── full_name: str (ФИО подписанта, "Иванов Иван Иванович")
├── basis: str (основание полномочий, "Устав" или "Доверенность №123 от 01.01.2026")
└── representative: str (краткое представление, "Генеральный директор Иванов И.И.")
```

### 9.5. Плейсхолдеры для шаблонов

Шаблоны DOCX используют двойные фигурные скобки `{{key}}` для подстановки данных.
Динамические таблицы обозначаются специальным плейсхолдером и заполняются
отдельным методом `fill_table()`.

```
Шаблон protocol.docx:
  {{contract_number}}         — номер договора
  {{contract_date}}           — дата договора
  {{party_1}}                 — наименование стороны 1
  {{party_2}}                 — наименование стороны 2
  {{disagreements_table}}     — динамическая таблица разногласий
  {{date}}                    — дата протокола
  {{signatory_1}}             — ФИО подписанта стороны 1
  {{signatory_2}}             — ФИО подписанта стороны 2
  {{basis_1}}                 — основание полномочий стороны 1
  {{basis_2}}                 — основание полномочий стороны 2

Шаблон claim.docx:
  {{creditor_name}}           — наименование кредитора
  {{debtor_name}}             — наименование должника
  {{claim_amount}}            — сумма претензии
  {{claim_basis}}             — основание претензии
  {{deadline_date}}           — срок ответа
  {{attachments}}             — приложения
```

---

## 10. LEGAL SERVICE

### 10.1. Роль

Специализированный сервис юридического анализа договоров. Инкапсулирует логику
анализа, проверку БЛС, генерацию протоколов разногласий. Реализован в Package 4.
LegalService — самый сложный компонент АСД, объединяющий ParserEngine для извлечения
текста, БЛС для проверки ловушек, LLMEngine (Gemma 4 31B) для анализа и
DocXGenerator для генерации результирующих документов.

### 10.2. Режимы анализа

LegalService автоматически выбирает режим анализа на основе длины документа.
Короткие договоры (до 6000 символов) анализируются целиком за один вызов LLM
(Quick Review), длинные — через Map-Reduce с последовательной обработкой чанков.

```
LegalService
│
├── upload_and_parse(file_path)
│   → ContractUploadResult
│   │
│   ├── .pdf  → parser_engine.parse_pdf(file_path)
│   ├── .xlsx → parser_engine.parse_xlsx(file_path)
│   └── прочие → чтение как текст (UTF-8)
│
├── analyze(request: LegalAnalysisRequest)
│   → LegalAnalysisResult
│   │
│   ├── _resolve_document_text(request)  → получение текста
│   ├── if len(text) <= chunk_size (6000):
│   │   └── _quick_review(text, review_type)
│   ├── else:
│   │   └── _map_reduce(text, chunk_size, overlap, review_type)
│   └── Добавление metadata (duration, model, engine, timestamp)
│
├── _quick_review(document_text, review_type)
│   → LegalAnalysisResult
│   │
│   ├── БЛС lookup: _blc_lookup(text[:2000])  — первые 2000 символов
│   ├── Промпт: LEGAL_QUICK_REVIEW_PROMPT с текстом + контекст БЛС
│   ├── LLM вызов: llm_engine.safe_chat("legal", messages)
│   └── Парсинг JSON-ответа → LegalAnalysisResult
│
├── _map_reduce(document_text, chunk_size, chunk_overlap, review_type)
│   → LegalAnalysisResult
│   │
│   ├── MAP Stage:
│   │   ├── _chunk_text(text, chunk_size=6000, overlap=300)
│   │   └── Для каждого чанка (последовательно):
│   │       ├── blc_context = await _blc_lookup(chunk[:2000])
│   │       ├── Промпт: LEGAL_MAP_PROMPT с чанком + контекст БЛС
│   │       ├── LLM вызов: llm_engine.safe_chat("legal", messages)
│   │       └── map_results.append({"chunk_index", "chunk_preview", "findings_raw"})
│   │
│   └── REDUCE Stage:
│       ├── Форматирование MAP результатов в текст
│       ├── Промпт: LEGAL_REDUCE_PROMPT с агрегацией MAP результатов
│       ├── LLM вызов: llm_engine.safe_chat("legal", messages)
│       └── Парсинг JSON → LegalAnalysisResult
│
├── _blc_lookup(text)
│   → str (контекст ловушек БЛС для данного фрагмента)
│   │
│   ├── rag_service.search(text, top_k=3)  — векторный поиск ловушек
│   ├── Форматирование результатов: "1. описание_ловушки..."
│   └── Fallback: "БЛС временно недоступна"
│
├── _chunk_text(text, chunk_size=6000, chunk_overlap=300)
│   → List[str]  (список чанков с перекрытием)
│   │
│   ├── Резание по границам абзацев (приоритет "\n\n")
│   ├── Fallback по границам строк ("\n")
│   └── Overlap для сохранения контекста между чанками
│
└── _parse_analysis_response(response_text, review_type)
    → LegalAnalysisResult
    │
    ├── Попытка извлечения JSON (включая из markdown code block)
    ├── Парсинг findings, verdict, normative_refs, contradictions
    ├── Безопасное преобразование Enum (_safe_enum)
    └── Fallback при ошибке парсинга: finding "Не удалось распарсить ответ LLM"
```

### 10.3. LegalAnalysisResult

Структура результата юридического анализа, возвращаемая LegalService. Содержит
полный набор данных для формирования протокола разногласий, претензии или
просто отчёта о рисках.

```
LegalAnalysisResult
├── review_type: ReviewType (FULL | EXPRESS | COMPLIANCE_ONLY)
├── findings: List[LegalFinding]
│   ├── category: LegalFindingCategory (RISK | COMPLIANCE | CONTRADICTION | TRAP)
│   ├── severity: LegalSeverity (HIGH | MEDIUM | LOW)
│   ├── clause_ref: str (пункт договора, "п. 3.2.1")
│   ├── legal_basis: str (ссылка на норму, "ст. 743 ГК РФ")
│   ├── issue: str (описание проблемы)
│   ├── recommendation: str (рекомендация по изменению)
│   └── auto_fixable: bool (можно ли автоматически исправить)
├── normative_refs: List[str] (извлечённые нормативные ссылки)
├── contradictions: List[Any] (противоречия между пунктами)
├── verdict: LegalVerdict
│   ├── APPROVED (одобрен без замечаний)
│   ├── APPROVED_WITH_COMMENTS (одобрен с замечаниями)
│   ├── REVISION_REQUIRED (требуется переработка)
│   └── REJECTED (отклонён — критические риски)
├── summary: str (краткое резюме анализа)
├── total_risks: int (количество найденных рисков)
└── analysis_metadata: Dict[str, Any]
    ├── duration_seconds: float
    ├── model: str (использованная модель)
    ├── engine: str (MLX/Ollama)
    ├── document_chars: int
    ├── review_type: str
    └── timestamp: str (ISO 8601)
```

### 10.4. Интеграция с БЛС и RAG (4-шаговая гибридная проверка)

LegalService использует 4-шаговую гибридную проверку для каждого чанка:

**Шаг 1: Pattern matching** — быстрый regex-поиск по известным ловушкам из YAML.
Выполняется мгновенно, покрывает заведомо известные паттерны (58 ловушек).
Не требует LLM, работает даже при недоступности модели.

**Шаг 2: Semantic search** — pgvector поиск по embeddings ранее обнаруженных
ловушек. Находит семантически похожие конструкции, даже если точный текст
отличается. Использует bge-m3 (1024 dim) и L2 дистанцию.

**Шаг 3: LLM verification** — Gemma 4 31B подтверждает или опровергает
совпадения, устраняя ложные срабатывания. LLM оценивает контекст и определяет,
является ли найденная конструкция действительно ловушкой.

**Шаг 4: RAG enrichment** — контекст из предыдущих анализов через LightRAG
(RAGService.hybrid_search). Обогащает аналитический контекст смежными
документами и нормативными ссылками, позволяя LLM дать более точную оценку.

### 10.5. Ст. 445 ГК РФ

При анализе договоров, заключаемых в обязательном порядке (ст. 445 ГК РФ),
LegalService автоматически выполняет следующие действия:

- **Определение применимости ст. 445:** выявляет государственные/муниципальные
  контракты, публичные договоры, договоры с обязательным заключением
- **Формирование протокола разногласий** с соблюдением 30-дневного срока
  ответа (п. 1 ст. 445 ГК РФ)
- **При отказе/уклонении контрагента** — рекомендация обращения в суд
  (п. 2 ст. 445 ГК РФ) с указанием последствий уклонения
- **Генерация уведомления** об акцепте на иных условиях (протокольные разногласия)
- **Автоматическое заполнение** ProtocolPartyInfo для обеих сторон

---

## 11. PDF GENERATION (v3 — ReportLab + TrueType)

### 11.1. Эволюция PDF-генерации

PDF-генерация в АСД прошла три основных версии, каждая из которых решала
критические проблемы предыдущей:

**v1: HTML → Playwright → PDF**
- Генерация HTML-шаблона, рендеринг через Playwright (headless Chrome), экспорт в PDF
- Проблема: Type 3 bitmap шрифты — текст не выделяется, не ищется, файл огромный
- Качество: неприемлемое для юридических документов

**v2: Улучшенный HTML → Playwright**
- Попытка исправить шрифты через CSS font-face и системные шрифты
- Частичное улучшение, но Type 3 bitmap шрифты всё равно появлялись при embed шрифтов
- Результат: лучше, но всё ещё не профессиональное качество

**v3: Чистый ReportLab + TrueType шрифты (текущая версия)**
- Полный отказ от HTML-посредника. Генерация PDF напрямую через ReportLab
- Использование TrueType шрифтов (Calibri, MicrosoftYaHei) — векторные, масштабируемые
- **Ноль Type 3 bitmap шрифтов** в выходном PDF
- Результат: 151KB PDF, профессиональное качество, полностью searchable

### 11.2. CoverPage Flowable

Обложка документа реализована как пользовательский Flowable класс ReportLab,
который позволяет точно контролировать позиционирование элементов на странице:

```python
class CoverPage(Flowable):
    """
    Пользовательский Flowable для титульной страницы PDF.
    Размещает заголовок, подзаголовок, дату и логотип
    с точным позиционированием в координатах страницы.
    """
    def __init__(self, title, subtitle, date, project_info):
        Flowable.__init__(self)
        self.title = title
        self.subtitle = subtitle
        self.date = date
        self.project_info = project_info
        self.width = A4[0]   # 595.27 points
        self.height = A4[1]  # 841.89 points

    def draw(self):
        canvas = self.canv
        # Регистрация TrueType шрифтов (если ещё не зарегистрированы)
        # Заголовок: Calibri-Bold, 24pt
        # Подзаголовок: Calibri, 14pt
        # Дата и информация: Calibri, 10pt
        # Линия-разделитель: серый цвет
```

### 11.3. Стек шрифтов

Для корректного отображения документов на русском и английском языках (а также
китайском/японском при работе с импортным оборудованием) используется стек
TrueType шрифтов:

| Назначение | Шрифт | Формат | Примечание |
|-----------|-------|--------|------------|
| Латиница (основной) | Calibri | TrueType (.ttf) | Чистый, профессиональный |
| Латиница (жирный) | Calibri-Bold | TrueType (.ttf) | Для заголовков |
| Кирилица (основной) | Calibri | TrueType (.ttf) | Полная поддержка кириллицы |
| Кирилица (жирный) | Calibri-Bold | TrueType (.ttf) | Для заголовков |
| CJK (китайский/японский) | MicrosoftYaHei | TrueType (.ttc) | Для импортных спецификаций |
| CJK (жирный) | SimHei | TrueType (.ttf) | Для CJK заголовков |

Регистрация шрифтов в ReportLab:

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('Calibri', 'fonts/Calibri.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-Bold', 'fonts/Calibri-Bold.ttf'))
pdfmetrics.registerFont(TTFont('MicrosoftYaHei', 'fonts/msyh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('SimHei', 'fonts/SimHei.ttf'))

from reportlab.lib.fonts import addMapping
addMapping('Calibri', 0, 0, 'Calibri')        # normal
addMapping('Calibri', 1, 0, 'Calibri-Bold')    # bold
```

### 11.4. Ноль Type 3 bitmap шрифтов

Ключевое требование к PDF-генерации v3: **ни одного Type 3 bitmap шрифта** в
выходном файле. Это обеспечивается следующими мерами:

- Использование только TrueType шрифтов (векторные, масштабируемые)
- Отказ от HTML → Playwright → PDF конвейера (источник Type 3)
- Прямая генерация через ReportLab Canvas / Platypus
- Проверка выходного PDF: `pdffonts output.pdf` не должен показывать Type 3

Результат проверки:

```
$ pdffonts legal_analysis_report.pdf
name                                 type              encoding
------------------------------------ ----------------- ----------------
Calibri                              TrueType          WinAnsiEncoding
Calibri-Bold                         TrueType          WinAnsiEncoding
MicrosoftYaHei                       TrueType          UniGB-UTF16-H
```

### 11.5. Результат

Показатели качества PDF-генерации v3:

| Метрика | v1 (HTML→Playwright) | v3 (ReportLab+TrueType) |
|---------|---------------------|------------------------|
| Размер файла | 800KB+ | **151KB** |
| Type 3 шрифты | Да (негативные) | **Нет** |
| Текст searchable | Нет | **Да** |
| Выделение текста | Нет | **Да** |
| Копирование текста | Искажения | **Корректно** |
| Качество | Приемлемое | **Профессиональное** |
| Кириллица | Артефакты | **Идеально** |
| CJK символы | Квадратики | **Корректно** |

---

## 12. WIKI ENGINE

### 12.1. Роль

База знаний проекта. Хранит нормативные акты, проектную информацию, извлечённые
сущности. Обеспечивает компаундинг знаний — каждый проанализированный документ
обогащает wiki, делая последующие анализы точнее. WikiEngine работает в связке
с GraphService (граф связей между статьями) и RAGService (поиск по wiki-статьям).

WikiEngine хранит статьи в формате Markdown, что обеспечивает удобство чтения,
редактирования и экспорта. Статьи организованы по проектам и связаны между собой
через нормативные ссылки и извлечённые сущности.

### 12.2. Структура

```
WikiEngine
│
├── ingest(document_id, extracted_entities[], normative_refs[])
│   → List[WikiArticle]
│   │
│   ├── Создание/обновление статей на основе извлечённых сущностей
│   ├── Обновление связей между статьями (GraphService.add_reference)
│   ├── Confidence scoring — оценка достоверности извлечённой информации
│   ├── Запись в log.md (аудит всех изменений wiki)
│   └── Возвращает созданные/обновлённые статьи
│
├── search(query)
│   → List[WikiArticle]
│   │
│   ├── RAGService.search(query) для семантического поиска
│   ├── Фильтрация по типу статьи и проекту
│   └── Ранжирование по релевантности и confidence
│
├── get_article(title)
│   → WikiArticle
│   │
│   ├── Точный поиск по заголовку статьи
│   └── Возвращает None если статья не найдена
│
├── get_project_wiki(project_id)
│   → List[WikiArticle]
│   │
│   ├── Все статьи, связанные с проектом
│   ├── Включая нормативные ссылки и связанные сущности
│   └── Отсортированные по дате обновления
│
└── export_markdown(directory)
    → файлы .md на диск
    │
    ├── Экспорт всех статей в Markdown-файлы
    ├── Структура директорий: directory/{project_id}/{title}.md
    └── Для использования в Obsidian или других wiki-системах
```

### 12.3. WikiArticle

```
WikiArticle
├── id: int (уникальный идентификатор)
├── project_id: int (ID проекта, к которому привязана статья)
├── title: str (заголовок статьи, уникальный в рамках проекта)
├── content: str (содержание в формате Markdown)
├── source: str (откуда извлечена информация: "contract_analysis", "normative_search")
├── source_document_id: int (ID документа-источника)
├── entities: List[str] (извлечённые сущности: организации, нормы, суммы)
├── normative_refs: List[str] (нормативные ссылки, упомянутые в статье)
├── confidence: float (0.0-1.0, оценка достоверности информации)
├── superseded_by: int | None (ID статьи, которая заменяет текущую при обновлении)
├── created_at: datetime (дата создания)
└── updated_at: datetime (дата последнего обновления)
```

---

## 13. EVENT MANAGER (STATE MACHINE)

### 13.1. Роль

Управляет Event-Driven Workflow и графом событий проекта. Гарантирует, что
агенты выполняют задачи в правильном порядке. Когда один этап завершается
(например, «Тендер выигран»), LangGraph StateGraph генерирует события для следующих
этапов («Начать подготовку ИД»). Реализован как конечный автомат (State Machine)
на основе NetworkX-графа.

LangGraph StateGraph является связующим звеном между MCP Server (инструменты) и
LangGraph Workflow (оркестрация агентов). Каждый инструмент MCP может
зарегистрировать событие через граф состояний, а LangGraph использует
состояние проекта для маршрутизации задач.

### 13.2. Методы

```
StateGraph
│
├── __init__()
│   └── self.graph = graph_service  (GraphService singleton)
│
├── register_event(project_id, event_type, payload)
│   → EventResult
│   │
│   ├── 1. Создание/проверка узла проекта в графе
│   │   └── Если проекта нет → graph.add_node(project_id, type="Project", status="INIT")
│   ├── 2. Создание узла события
│   │   └── event_id = f"evt_{event_type}_{timestamp}"
│   │   └── graph.add_node(event_id, type="Event", event_type=event_type, **payload)
│   ├── 3. Связывание: graph.add_reference(project_id, event_id)
│   ├── 4. Обновление статуса проекта: _map_event_to_state(event_type)
│   ├── 5. Триггер workflow: _trigger_workflow(project_id, event_type, payload)
│   └── 6. Сохранение графа: graph.save_graph()
│
├── _map_event_to_state(event_type)
│   → str (новое состояние проекта)
│   │
│   ├── "asd_tender_search_success" → "TENDER_FOUND"
│   ├── "asd_archive_done"          → "FILES_REGISTERED"
│   ├── "asd_pto_done"              → "SPECS_EXTRACTED"
│   ├── "asd_logistics_done"        → "LOGISTICS_READY"
│   ├── "asd_smeta_done"            → "ESTIMATE_READY"
│   ├── "asd_legal_done"            → "LEGAL_CHECKED"
│   ├── "hermes_verdict_signed"     → "VERDICT_READY"
│   ├── "contract_signed"           → "PROJECT_WON"
│   ├── "work_entry_closed"         → "EXECUTION"
│   ├── "ks11_signed"               → "COMPLETION"
│   └── "payment_deadline_expired"  → "CLAIM"
│
├── _trigger_workflow(project_id, event_type, payload)
│   → Автоматический запуск следующих шагов
│   │
│   ├── "asd_tender_search_success" → Trigger Archive: регистрация документов
│   ├── "asd_pto_done"              → Trigger Logistics: поиск поставщиков
│   └── "asd_logistics_done"        → Trigger Smeta: расчёт стоимости
│
├── get_project_state(project_id)
│   → Dict[str, Any] (текущее состояние и история)
│   │
│   ├── Если проект не найден → {"status": "NOT_FOUND"}
│   └── Иначе → {"project_id", "status", "history": related_nodes}
│
└── STATES (определённые состояния проекта)
    │
    ├── INIT:           "Инициализация / Поиск тендера"
    ├── TENDER_FOUND:   "Тендер найден"
    ├── FILES_REGISTERED: "Документация зарегистрирована"
    ├── SPECS_EXTRACTED: "Спецификации извлечены"
    ├── LOGISTICS_READY: "Коммерческие предложения получены"
    ├── ESTIMATE_READY: "Сметный расчёт готов"
    ├── LEGAL_CHECKED:  "Юридическая экспертиза завершена"
    ├── VERDICT_READY:  "Вердикт по тендеру сформирован"
    ├── PROJECT_WON:    "Контракт подписан / Начало СМР"
    ├── EXECUTION:      "Производство работ / Генерация ИД"
    ├── COMPLETION:     "Завершение объекта / Сдача КС-11"
    └── CLAIM:          "Претензионная работа"
```

---

## 14. ЗАВИСИМОСТИ МЕЖДУ КОМПОНЕНТАМИ

### 14.1. Диаграмма зависимостей

```
                    mcp_server.py (FastMCP, 23 tools)
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   tools/           core/            db/
   (7 модулей)      (9 модулей)     (3 модуля)
        │                │                │
        │         ┌──────┴──────┬────────────┐
        │         │             │            │
        │    LLMEngine     LightRAG    StateGraph
        │    (единый LLM)   (RAGService  (StateMachine)
        │         │        + GraphService)      │
        │    ModelRouter   ParserEngine          │
        │         │             │                │
        │    RamManager    BLSChecker            │
        │         │             │                │
        │    DocXGenerator WikiEngine            │
        │    LegalService                       │
        │    (Package 4)                        │
        │                                      │
        └───────────────┬──────────────────────┘
                        │
                 ┌──────┴──────┐
                 │             │
           PostgreSQL 16    NetworkX
           + pgvector     (in-memory)
           (векторный       + pickle
            поиск)
```

### 14.2. Таблица зависимостей инструментов (23 инструмента)

| # | Инструмент | Модуль | Зависит от |
|---|-----------|--------|------------|
| 1 | `asd_upload_document` | jurist | ParserEngine, RAGService, LLMEngine (embed) |
| 2 | `asd_analyze_contract` | jurist | ParserEngine, LLMEngine (chat), BLSChecker, RAGService, LegalService |
| 3 | `asd_normative_search` | jurist | RAGService, LLMEngine (embed) |
| 4 | `asd_generate_protocol` | jurist | DocXGenerator, PostgreSQL, LegalService |
| 5 | `asd_generate_claim` | jurist | DocXGenerator, PostgreSQL, LLMEngine |
| 6 | `asd_generate_lawsuit` | jurist | DocXGenerator, PostgreSQL, LLMEngine |
| 7 | `asd_add_trap` | jurist | BLSChecker, RAGService, PostgreSQL |
| 8 | `asd_vor_check` | pto | ParserEngine, LLMEngine (chat) |
| 9 | `asd_pd_analysis` | pto | ParserEngine, LLMEngine (chat) |
| 10 | `asd_generate_act` | pto | DocXGenerator, PostgreSQL |
| 11 | `asd_id_completeness` | pto | PostgreSQL, LLMEngine |
| 12 | `asd_estimate_compare` | smeta | ParserEngine, LLMEngine (chat) |
| 13 | `asd_create_lsr` | smeta | ParserEngine, LLMEngine |
| 14 | `asd_supplement_estimate` | smeta | ParserEngine, LLMEngine |
| 15 | `asd_register_document` | delo | PostgreSQL, StateGraph |
| 16 | `asd_generate_letter` | delo | DocXGenerator, PostgreSQL, LLMEngine |
| 17 | `asd_prepare_shipment` | delo | DocXGenerator, PostgreSQL |
| 18 | `asd_track_deadlines` | delo | PostgreSQL, StateGraph |
| 19 | `asd_tender_search` | procurement | LLMEngine, External API / Telegram |
| 20 | `asd_analyze_lot_profitability` | procurement | LLMEngine, PostgreSQL |
| 21 | `asd_source_vendors` | logistics | PostgreSQL (Vendors table) |
| 22 | `asd_add_price_list` | logistics | ParserEngine, PostgreSQL |
| 23 | `asd_get_system_status` | general | LLMEngine, PostgreSQL, RamManager |

---

## 15. СТРУКТУРА ПРОЕКТА

```
/home/oleg/MAC_ASD/
│
├── src/
│   ├── agents/
│   │   ├── workflow.py          # LangGraph (7 агентов через asd_app)
│   │   ├── nodes.py             # Логика узлов графа (legacy, shared helpers)
│   │   ├── nodes_v2.py          # Актуальные PM-узлы (май 2026, merged orchestrator)
│   │   ├── state.py             # AgentState — состояние графа
│   │   └── workflow.py          # LangGraph workflow (parallel Send + sequential)
│   │
│   ├── core/
│   │   ├── llm_engine.py        # LLMEngine — единый интерфейс к LLM
│   │   ├── backends/
│   │   │   ├── mlx_backend.py   # MLX-VLM бэкенд (Mac Studio, Gemma 4 31B + Gemma 4 E4B + Llama 70B)
│   │   │   └── ollama_backend.py # OllamaBackend (dev_linux fallback)
│   │   ├── ollama_client.py     # Legacy OllamaClient (обратная совместимость)
│   │   ├── model_router.py      # ModelRouter — тип задачи → агент → модель
│   │   ├── ram_manager.py       # RamManager — управление 128GB Unified Memory
│   │   ├── parser_engine.py     # ParserEngine — парсинг PDF/XLSX/JSON
│   │   ├── rag_service.py       # RAGService — векторный + гибридный поиск
│   │   ├── graph_service.py     # GraphService — NetworkX граф знаний
│   │   ├── evidence_graph.py    # **Evidence Graph v2** — 7 типов узлов, 11 связей, confidence
│   │   ├── inference_engine.py  # **Inference Engine** — 6 symbolic-правил
│   │   ├── project_loader.py    # **ProjectLoader** — ПД/РД → baseline WorkUnit'ов
│   │   ├── chain_builder.py     # **Chain Builder (Pkg 11)** — цепочки документов
│   │   ├── hitl_system.py       # **HITL System (Pkg 11)** — вопросы оператору
│   │   ├── journal_reconstructor.py # **Journal Reconstructor v2 (Pkg 11)** — 5 этапов
│   │   ├── event_manager.py     # StateGraph — конечный автомат проекта
│   │   ├── services/
│   │   │   └── legal_service.py # LegalService — юридический анализ (Package 4)
│   │   ├── prompts/
│   │   │   └── legal_prompts.py # Промпты MAP, REDUCE, QUICK_REVIEW
│   │   └── integrations/
│   │       └── google.py        # GoogleWorkspaceService (Gmail, Drive, Sheets)
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── legal.py             # Pydantic схемы: LegalAnalysisRequest/Result/Finding
│   │
│   ├── config.py                # Settings + PROFILE_MODELS (mac_studio / dev_linux)
│   │
│   ├── db/
│   │   ├── models.py            # SQLAlchemy модели (Document, DocumentChunk, Vendor)
│   │   ├── init_db.py           # Инициализация БД, Session factory
│   │   └── seed_lessons.py      # Сидинг данных (Lessons Learned)
│   │
│   ├── utils/
│   │   └── wiki_loader.py       # Загрузчик wiki-статей
│   │
│   ├── scripts/
│   │   └── ingest_blc_telegram.py # Импорт БЛС из Telegram канала
│   │
│   └── main.py                  # Точка входа приложения
│
├── mcp_servers/
│   └── asd_core/
│       ├── server.py            # FastMCP сервер — единая точка входа
│       └── tools/
│           ├── jurist_tools.py   # 7 инструментов Юриста
│           ├── pto_tools.py      # 4 инструмента ПТО
│           ├── smeta_tools.py    # 3 инструмента Сметчика
│           ├── delo_tools.py     # 4 инструмента Делопроизводителя
│           ├── procurement_tools.py # 2 инструмента Закупщика
│           ├── logistics_tools.py   # 3 инструмента Логиста
│           └── general_tools.py     # 1 инструмент (системный статус)
│
├── agents/                      # Конфигурации агентов (промпты + config.yaml)
│   ├── pm/                      # Руководитель проекта → Llama 3.3 70B
│   ├── pto/                     # ПТО-инженер → Gemma 4 31B (shared, 128K)
│   ├── smeta/                   # Сметчик → Gemma 4 31B (shared, 128K)
│   ├── legal/                   # Юрист → Gemma 4 31B (shared, 128K)
│   ├── procurement/             # Закупщик → Gemma 4 31B (shared, 128K)
│   ├── logistics/               # Логист → Gemma 4 31B (shared, 128K)
│   └── archive/                 # Делопроизводитель → Gemma 4 E4B
│
├── data/
│   ├── templates/               # Шаблоны DOCX (9 типов)
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
│   ├── exports/                 # Сгенерированные DOCX/PDF
│   │   ├── protocols/
│   │   ├── claims/
│   │   ├── lawsuits/
│   │   ├── acts/
│   │   ├── estimates/
│   │   └── letters/
│   ├── wiki/                    # База знаний (Markdown)
│   └── graphs/                  # NetworkX графы (knowledge_graph.gpickle)
│
├── traps/                       # YAML файлы БЛС
│   └── default_traps.yaml       # 58 ловушек
│
├── infrastructure/
│   ├── docker-compose.yml       # PostgreSQL + pgvector
│   └── setup_mac.sh            # Настройка Mac Studio
│
├── scripts/
│   ├── launch_asd.sh            # Запуск MCP сервера
│   ├── setup_db.sh              # Создание БД + миграции
│   └── test_mcp.py              # Тесты MCP инструментов
│
├── tests/
│   └── test_legal_service.py    # Тесты LegalService
│
├── docs/
│   ├── COMPONENT_ARCHITECTURE.md  # Этот документ
│   ├── CONCEPT_v12.md             # Концепция АСД v12
│   ├── MODEL_STRATEGY.md          # Модельная стратегия
│   ├── DATA_SCHEMA.md             # Схема данных
│   ├── MCP_TOOLS_SPEC.md          # Спецификация MCP инструментов
│   ├── BUILDING_LIFECYCLE_WORKFLOW.md # Жизненный цикл здания
│   └── DEPLOYMENT_PLAN.md         # План развёртывания
│
├── asd_manifest.yaml            # Манифест АСД
├── agents.md                    # Описание агентов
├── .env.example                 # Пример переменных окружения
├── requirements.txt             # Python зависимости
├── alembic.ini                  # Миграции БД
└── README.md                    # Описание проекта
```

---

## 16. ВНЕШНИЕ ИНТЕГРАЦИИ (GOOGLE WORKSPACE)

### 16.1. Роль

GoogleWorkspaceService (src/core/integrations/google.py) позволяет всем агентам
взаимодействовать с экосистемой Google. Интеграция реализована через Google API
и обеспечивает бесшовную работу с корпоративной почтой, файловым хранилищем,
таблицами и документами.

### 16.2. Функции

**Gmail:**
- Отправка RFQ (Request for Quotation) Логистом — автоматическая рассылка
  запросов коммерческих предложений поставщикам материалов
- Получение уведомлений о входящих документах и ответах от контрагентов
- Автоматическая обработка ответов на RFQ и обновление цен в БД

**Google Drive:**
- Хранение сканов ТТН и сертификатов Делопроизводителем
- Автоматическая загрузка входящих документов из почты в Drive
- Организация папок по проектам: /{project_id}/incoming/, /{project_id}/outgoing/

**Google Sheets:**
- Ведение сравнительных таблиц цен от разных поставщиков (Логист)
- Реестры отправленной документации (Делопроизводитель)
- Мониторинг сроков и дедлайнов по проектам
- Автоматическое обновление данных при изменении цен

**Google Docs:**
- Автоматическая генерация писем и претензий Юристом
- Шаблоны документов в Google Docs для совместной работы
- Экспорт DocXGenerator-результатов в Google Docs для ревью

---

*Этот документ описывает внутреннюю архитектуру всех компонентов АСД v12.0.
Документ актуализирован 2 мая 2026. Package 5 (Evidence Graph v2, Inference Engine, ProjectLoader)
и Package 11 (Chain Builder, HITL System, Journal Reconstructor v2) — реализованы.
Библиотека: 271 файл, 101 MB. Все 5 рабочих агентов используют единую копию Gemma 4 31B
(128K контекст) через shared memory, Делопроизводитель использует Gemma 4 E4B.*
