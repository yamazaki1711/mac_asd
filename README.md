# MAC ASD v12.0 — Мультиагентная ИИ-система для строительного субподряда

**MAC ASD** (Multi-Agent Construction AI System) — полностью локальная ИИ-система для двух стратегических задач:

1. **Forensic-восстановление исполнительной документации (ИД)** — полевое восстановление полного комплекта ИД на проблемных ОКС, где из-за хаоса в документации зависли миллиардные оплаты. Заменяет выездные команды 15–20 человек на Mac Studio + сканер + 4 оператора. Срок: 2–3 недели вместо месяцев.
2. **Сопровождение строительства** — производный «лайт»-режим: тендеры, снабжение, входной контроль, генерация ИД, претензионная работа.

> **Человек принимает финальное решение.** Система — штурман, а не автопилот.

---

## Что умеет прямо сейчас

### 🔍 Forensic-конвейер (E2E: PASS ✅)
```
Сканы (PDF/JPEG) → PaddleOCR → Classify (18 типов) → Extract (даты/партии/ГОСТ) 
→ NetworkX Knowledge Graph → Forensic Checks (4 типа) → Guidance (задачи оператору) 
→ Output Pipeline (DOCX по 344/пр)
```

**На реальном тесте (шпунт Л5, сертификат 55/60):**
- 🔴 **CRITICAL #1:** Сертификат на 55 шпунтин покрывает 2 АОСР по 30 шт (превышение на 5 шт, +9%) — подлог/ксерокопия
- 🔴 **CRITICAL #2:** Шпунт Л5 снят с производства (СССР, г. Луганск) — требуется замена на Л5-УМ
- 🟠 **HIGH:** Сертификат использован в 2 АОСР без входного контроля
- 📋 **9 задач оператору** через Guidance System с приоритезацией

### 🧠 7+1 агентов на MLX

| Агент | Модель | Ключевая специализация |
|-------|--------|----------------------|
| **Руководитель проекта** | Llama 3.3 70B 4-bit | Оркестрация, вердикты, HermesRouter |
| **ПТО** | Gemma 4 31B 4-bit (VLM) | Чертежи, ВОР, спецификации, OCR, 20 видов работ |
| **Юрист** | Gemma 4 31B 4-bit (shared) | БЛС (58 ловушек), контракты, претензии, иски |
| **Сметчик** | Gemma 4 31B 4-bit (shared) | ФЕР/ТЕР, НМЦК, рентабельность, КС-2/КС-3 |
| **Закупщик** | Gemma 4 31B 4-bit (shared) | Тендеры, поставщики, лаб. контроль |
| **Логист** | Gemma 4 31B 4-bit (shared) | Снабжение, КП, доставка |
| **Делопроизводитель** | Gemma 4 E4B 4-bit | Регистрация, архив, реестр ИД |
| **Auditor (RedTeam)** | Llama 3.3 70B | Forensic-проверки, стройконтроль |

> Gemma 4 31B — одна копия в памяти (~23 GB) на 5 агентов. 3 уникальные модели, ~66 GB RAM.

### ⚙️ Ключевые компоненты v12.0

| Компонент | Файл | Назначение |
|-----------|------|------------|
| **Ingestion Pipeline** | `src/core/ingestion.py` | Сканы → OCR → Classify (18 типов) → Extract (regex) → Graph |
| **PaddleOCR Adapter** | `src/core/paddle_ocr.py` | PP-OCRv5 (109 языков, +13% точность на русском) → rapidocr → tesseract |
| **Forensic KAG** | `src/core/graph_service.py` | NetworkX DiGraph: AOSR/Certificate/Batch/Supplier/TTN. 4 forensic checks |
| **Auditor** | `src/core/auditor.py` | Batch coverage, certificate reuse, orphan certificates, material spec |
| **Hybrid Classifier** | `src/core/hybrid_classifier.py` | Keyword-based (<1ms) + LLM fallback (90%+) для спорных документов |
| **Guidance System** | `src/core/hybrid_classifier.py` | Задачи оператору из forensic-находок и inventory-пробелов |
| **Output Pipeline** | `src/core/output_pipeline.py` | DOCX-генерация: АОСР по 344/пр, нумерация, Times New Roman 12pt |
| **Context Manager** | `src/core/context_manager.py` | Per-agent 128K budget, auto-summarization |
| **Agent Mailbox** | `src/core/agent_mailbox.py` | Gmail API: RFQ, incoming classification |
| **HermesRouter** | `src/agents/hermes_router.py` | Гибридная 3-стадийная модель: scoring → LLM reasoning → veto |
| **WorkTypeRegistry** | `src/agents/skills/common/` | SSOT: 20 видов работ → сметные/юридические/ФЕР маппинги |
| **БЛС** | `traps/default_traps.yaml` | 58 ловушек в 10 категориях + pgvector RAG |

---

## Быстрый старт

```bash
# 1. Инфраструктура
cd infrastructure && docker compose up -d    # PostgreSQL 16 + pgvector

# 2. Окружение
cp .env.example .env
export ASD_PROFILE=dev_linux    # или mac_studio

# 3. Прогнать E2E forensic-тест
PYTHONPATH=. python tests/test_e2e_forensic.py

# 4. Все тесты
.venv/bin/python -m pytest tests/ -v

# 5. MCP-сервер
python -m mcp_servers.asd_core.server
```

---

## Состояние: 209/247 тестов (84.6%)

```
✅ E2E Forensic Pipeline — PASS (2 CRITICAL findings)
✅ Ingestion Pipeline — OCR → Classify → Extract → Graph
✅ Hybrid Classifier — keyword + LLM fallback
✅ PaddleOCR Adapter — PP-OCRv5 ready
✅ Output Pipeline — DOCX generation
✅ Guidance System — operator task generation
✅ Context Manager — per-agent token budget
✅ Agent Mailbox — Gmail RFQ builder
✅ Auditor — 4 forensic check types
✅ Юрист — БЛС, претензии, иски
✅ Сметчик — ФЕР/ТЕР, рентабельность
✅ Делопроизводитель — реестр, шаблоны
✅ Lab Control — полный цикл испытаний
✅ Lessons Learned — 3 уровня (БД → RAG → Skill Mutation)
🔧 Google Workspace — интеграция (STUB в коде, работает через Hermes Agent)
🔧 Закупщик/Логист — базовые workflow, требуют доработки
🔲 Multi-user Telegram — Guidance → операторы (запланировано)
🔲 Полный Output Pipeline — все 13 позиций по 344/пр (сейчас АОСР)
🔲 Real PDF/JPEG ingestion — PaddleOCR интегрирован, ждёт боевых сканов
```

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                     │
│  ┌─────────┐  ┌──────┐  ┌────────┐  ┌──────────┐          │
│  │ Hermes  │→│ ПТО  │→│ Сметчик│→│  Юрист   │→ ...     │
│  │  (PM)   │  │      │  │        │  │          │          │
│  └─────────┘  └──────┘  └────────┘  └──────────┘          │
│       ↓           ↓          ↓            ↓               │
│  ┌──────────────────────────────────────────────────┐     │
│  │              LLMEngine (MLX / Ollama)             │     │
│  │   Llama 70B │ Gemma 4 31B │ Gemma 4 E4B │ bge-m3 │     │
│  └──────────────────────────────────────────────────┘     │
│       ↓                                                    │
│  ┌──────────────────────────────────────────────────┐     │
│  │                  MCP Server (FastMCP)              │     │
│  │   66+ tools: PTO, Legal, Smeta, Lab, Google, ...  │     │
│  └──────────────────────────────────────────────────┘     │
│       ↓                                                    │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐      │
│  │PostgreSQL│  │ NetworkX │  │  Artifact Store    │      │
│  │+pgvector │  │ (KAG)    │  │  (DOCX/PDF/DXF)    │      │
│  └──────────┘  └──────────┘  └────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Хранение состояния

| Хранилище | Назначение |
|-----------|------------|
| **NetworkX DiGraph** | Forensic KAG: документы → партии → сертификаты → АОСР. In-memory + файлы `data/graphs/` |
| **PostgreSQL + pgvector** | Реляционные данные, БЛС (58 ловушек), прайс-листы, Lessons Learned, Lab модели |
| **In-process cache** | Кэш состояний и результатов (cachetools, Redis удалён) |
| **Artifact Store** | Сгенерированные документы: `data/artifacts/{project_id}/` |

---

## RAM Budget (Mac Studio M4 Max 128GB)

| Компонент | RAM |
|-----------|-----|
| Llama 3.3 70B 4-bit | 40.0 GB |
| Gemma 4 31B 4-bit (5 агентов shared) | 23.0 GB |
| Gemma 4 E4B 4-bit | 3.0 GB |
| bge-m3 embeddings | 0.3 GB |
| **Модели** | **66.3 GB** |
| Система + PostgreSQL | 12.0 GB |
| Буфер | ~42 GB |

---

## 20 видов работ (WorkTypeRegistry)

| Категория | Виды работ | ФЕР |
|-----------|-----------|-----|
| earthwork | Выемка, засыпка | ФЕР01 |
| foundation | Фундаменты, сваи | ФЕР05-08 |
| concrete | Бетонные работы | ФЕР06 |
| metal | Металлоконструкции | ФЕР09 |
| masonry | Кладка | ФЕР08 |
| finishing | Полы, стены, окна | ФЕР10,11,15 |
| water_sewer | Водоснабжение, канализация | ФЕР16,22 |
| hvac | Отопление, вентиляция | ФЕР18,20 |
| electrical | Электромонтаж | ФЕР46 |
| communication | Сети связи | ФЕР46 |

---

## Forensic-проверки (4 типа)

| Проверка | Что выявляет | Severity |
|----------|-------------|----------|
| **batch_coverage** | Σ АОСР > batch_size сертификата | 🔴 CRITICAL |
| **certificate_reuse** | Сертификат в >1 АОСР без ЖВК | 🟠 HIGH |
| **orphan_certificates** | Сертификат без цепочки поставки | 🟡 MEDIUM |
| **material_spec_validation** | Материал снят с производства / не соответствует ГОСТ | 🔴 CRITICAL |

---

## Нормативная база

| Документ | Описание |
|----------|----------|
| **Приказ 344/пр** | Состав и порядок ведения ИД (заменил РД-11-02-2006) |
| **Приказ 1026/пр** | Формы журналов работ |
| **ГОСТ Р 70108-2025** | Электронная исполнительная документация |
| **СП 543.1325800.2024** | Строительный контроль |
| **ПП РФ №468** | Порядок ведения ИД (уведомление за 3 р.д.) |
| **ПП РФ №249** | Электронная ИД обязательна для бюджета с 2025 |

---

## Структура проекта

```
mac_asd/
├── src/
│   ├── agents/              # LangGraph: граф, состояние, HermesRouter
│   │   ├── workflow.py      # StateGraph сборка
│   │   ├── nodes.py         # Логика 7 агентов
│   │   ├── state.py         # AgentState v2.0
│   │   ├── hermes_router.py # 3-стадийная модель решений
│   │   └── skills/          # Навыки: work_spec, contract_risks, rate_lookup...
│   ├── core/                # Ядро
│   │   ├── ingestion.py     # Ingestion Pipeline (OCR → Classify → Extract)
│   │   ├── output_pipeline.py # Output Pipeline (DOCX генерация)
│   │   ├── graph_service.py # NetworkX Forensic KAG
│   │   ├── auditor.py       # Forensic-проверки (4 типа)
│   │   ├── paddle_ocr.py    # PaddleOCR PP-OCRv5 адаптер
│   │   ├── hybrid_classifier.py # HybridClassifier + GuidanceSystem
│   │   ├── context_manager.py   # Per-agent 128K token budget
│   │   ├── agent_mailbox.py     # Gmail RFQ builder
│   │   ├── llm_engine.py        # MLX/Ollama интерфейс
│   │   ├── backends/            # MLXBackend, OllamaBackend
│   │   ├── services/            # pto_agent, smeta_agent, legal_documents...
│   │   ├── rag_pipeline.py      # Гибридный RAG
│   │   ├── parser_engine.py     # PDF/XLSX парсинг
│   │   └── ram_manager.py       # 128GB бюджет
│   ├── schemas/             # Pydantic модели
│   ├── db/                  # SQLAlchemy + Alembic миграции
│   └── config.py            # Профили (dev_linux / mac_studio)
├── mcp_servers/asd_core/    # FastMCP сервер (66+ tools)
├── tests/                   # 247 тестов
│   └── test_e2e_forensic.py # E2E forensic-конвейер
├── agents/                  # Промпты агентов (Markdown)
├── traps/                   # БЛС — 58 ловушек
├── infrastructure/          # Docker Compose (PostgreSQL)
└── data/                    # wiki/, artifacts/, graphs/
```

---

## Документация

| Документ | Описание |
|----------|----------|
| `AGENTS.md` | Манифест оркестратора — главная инструкция для Hermes |
| `docs/CONCEPT_v12.md` | Концепция системы |
| `docs/COMPONENT_ARCHITECTURE.md` | Внутренняя архитектура |
| `docs/MCP_TOOLS_SPEC.md` | Спецификация MCP инструментов |
| `docs/DATA_SCHEMA.md` | Схема БД |
| `docs/MODEL_STRATEGY.md` | Стратегия моделей и RAM |
| `docs/DEPLOYMENT_PLAN.md` | План развёртывания на Mac Studio |
