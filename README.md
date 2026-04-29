# MAC ASD v12.0

Мультиагентная система на базе LLM для строительного субподряда. Два режима: forensic-восстановление исполнительной документации на проблемных ОКС и сопровождение стройки (тендеры, снабжение, генрация ИД, претензии).

Полностью локальная. Linux (Ollama, RTX 5060) для разработки, Mac Studio (MLX, M4 Max) для продакшена.

## Быстрый старт

```bash
# Зависимости
cd infrastructure && docker compose up -d    # PostgreSQL 16 + pgvector

# Окружение
cp .env.example .env
export ASD_PROFILE=dev_linux    # или mac_studio

# Тесты
pip install -e ".[dev]"
pytest tests/ -v                           # 244 passed, 88.7%

# E2E forensic
PYTHONPATH=. python tests/test_e2e_forensic.py

# MCP-сервер
python -m mcp_servers.asd_core.server
```

## Что внутри

### Агенты

7 агентов на LangGraph StateGraph + Auditor (RedTeam). Все на Gemma 4 31B (одна копия в памяти на 5 агентов, 128K контекст). Оркестратор — Llama 3.3 70B.

| Агент | Модель | Задачи |
|-------|--------|--------|
| Руководитель проекта | Llama 3.3 70B | Оркестрация, HermesRouter (weighted scoring → LLM reasoning → veto) |
| ПТО | Gemma 4 31B VLM | ВОР, чертежи, спецификации, OCR, 20 видов работ |
| Юрист | Gemma 4 31B | БЛС (58 ловушек), контракты, претензии, иски |
| Сметчик | Gemma 4 31B | ФЕР/ТЕР, НМЦК, рентабельность, КС-2/КС-3 |
| Закупщик | Gemma 4 31B | Тендеры, поставщики, лаб. контроль |
| Логист | Gemma 4 31B | Снабжение, КП, доставка |
| Делопроизводитель | Gemma 4 E4B | Регистрация, архив, реестр ИД |
| Auditor (RedTeam) | Llama 3.3 70B | Forensic-проверки, перекрёстный аудит агентов |

### Ключевые модули

| Модуль | Файл | Что делает |
|--------|------|------------|
| Ingestion Pipeline | `src/core/ingestion.py` | Сканы → OCR → классификация (18 типов) → извлечение сущностей |
| Forensic KAG | `src/core/graph_service.py` | NetworkX-граф: документы → партии → сертификаты → АОСР |
| Auditor | `src/core/auditor.py` | 4 forensic-проверки (batch coverage, certificate reuse, orphan certs, material spec) |
| Output Pipeline | `src/core/output_pipeline.py` | Генерация DOCX по 344/пр (АОСР, Times New Roman 12pt, нумерация) |
| Hybrid Classifier | `src/core/hybrid_classifier.py` | Классификация документов: keyword + LLM fallback + Guidance System |
| PPR Generator | `src/core/services/ppr_generator/` | Генерация ППР: 6 ТТК + разделы ПЗ + графика + экспорт |
| ИС Generator | `src/core/services/is_generator/` | Исполнительные схемы: DXF-аннотации, допуски СП 126, SVG/PDF |
| HermesRouter | `src/agents/hermes_router.py` | Принятие решений: scoring → reasoning → veto |
| AgentState v2.0 | `src/agents/state.py` | Состояние конвейера: audit trail, confidence, rollback |
| LLMEngine | `src/core/llm_engine.py` | Единый интерфейс к MLX/Ollama |
| WorkTypeRegistry | `src/agents/skills/common/` | SSOT: 20 видов работ → маппинги (сметные, юридические, ФЕР) |
| БЛС | `traps/default_traps.yaml` | 58 ловушек субподрядчика в 10 категориях + pgvector RAG |
| Lessons Learned | `src/core/lessons_service.py` | Институциональная память: БД → RAG-инъекция → Skill Mutation |

### Forensic-проверки

| Проверка | Что выявляет |
|----------|-------------|
| `batch_coverage` | Σ материалов в АОСР > размер партии в сертификате |
| `certificate_reuse` | Один сертификат в нескольких АОСР без ЖВК |
| `orphan_certificates` | Сертификат без ТТН и входного контроля |
| `material_spec_validation` | Материал снят с производства / не соответствует ГОСТ |

### Хранение

| Хранилище | Что хранит |
|-----------|------------|
| PostgreSQL + pgvector | Документы, БЛС, прайс-листы, Lessons Learned, Lab |
| NetworkX DiGraph | Forensic KAG: связи документов (in-memory + файлы) |
| In-process cache | Кэш состояний (cachetools) |
| Artifact Store | Сгенерированные DOCX/PDF/DXF: `data/artifacts/{project}/` |

### RAM (Mac Studio M4 Max 128GB)

| Модель | RAM |
|--------|-----|
| Llama 3.3 70B 4-bit | 40 GB |
| Gemma 4 31B 4-bit (5 агентов) | 23 GB |
| Gemma 4 E4B 4-bit | 3 GB |
| bge-m3 | 0.3 GB |
| **Модели** | **66.3 GB** |

## Структура

```
src/
├── agents/          # LangGraph: граф (workflow.py), узлы (nodes.py), состояние (state.py)
│   ├── hermes_router.py
│   └── skills/      # WorkTypeRegistry, work_spec, contract_risks, rate_lookup
├── core/
│   ├── ingestion.py, output_pipeline.py    # Пайплайны
│   ├── graph_service.py, auditor.py        # Forensic KAG
│   ├── hybrid_classifier.py                # Classifier + Guidance
│   ├── llm_engine.py, backends/            # MLX/Ollama
│   ├── services/                           # pto_agent, smeta_agent, legal_documents,
│   │   ├── ppr_generator/                  #   ppr_generator, is_generator
│   │   └── is_generator/
│   ├── rag_pipeline.py, parser_engine.py
│   └── ram_manager.py
├── schemas/          # Pydantic
├── db/               # SQLAlchemy + Alembic
└── config.py         # Профили (dev_linux / mac_studio)

mcp_servers/asd_core/ # FastMCP (66+ инструментов)
tests/                # 275 тестов
agents/               # Промпты агентов (Markdown)
traps/                # БЛС — 58 ловушек (YAML)
infrastructure/       # Docker Compose
library/              # ГОСТы, СП, шаблоны (локально, не в Git)
```

## Документация

| Файл | Содержание |
|------|-----------|
| `AGENTS.md` | Манифест оркестратора — протоколы, workflow, правила |
| `docs/CONCEPT_v12.md` | Концепция системы |
| `docs/COMPONENT_ARCHITECTURE.md` | Внутренняя архитектура компонентов |
| `docs/CORE_LOGIC_DESIGN.md` | Логика переходов, OCR-конвейер, RAM-менеджмент |
| `docs/MCP_TOOLS_SPEC.md` | Спецификация MCP инструментов |
| `docs/DATA_SCHEMA.md` | Схема PostgreSQL |
| `docs/MODEL_STRATEGY.md` | Стратегия моделей и управление памятью |
| `docs/DEPLOYMENT_PLAN.md` | План развёртывания на Mac Studio |
| `docs/id_pipeline_architecture.md` | Архитектура единого конвейера ИД (ИС + ППР + АОСР) |
| `docs/ppr_generator.md` | Концепция ППР-генератора |

## Нормативная база

Приказ 344/пр (состав ИД), 1026/пр (журналы), ГОСТ Р 70108-2025 (электронная ИД), СП 543.1325800.2024 (стройконтроль), СП 70.13330.2012 (монтаж), ВСН 012-88 (сварка), ПП РФ №468 и №249, ФЗ-44, ФЗ-223.
