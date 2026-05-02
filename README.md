# MAC ASD v12.0

Мультиагентная система на базе LLM для строительного документооборота. Два режима: forensic-восстановление исполнительной документации на проблемных ОКС и сопровождение стройки (тендеры, снабжение, генерация ИД, претензии).

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
pytest tests/ -v                           # 478 passed, 15 skipped, 493 total

# E2E forensic
PYTHONPATH=. python tests/test_e2e_forensic.py

# MCP-сервер
python -m mcp_servers.asd_core.server
```

## Что внутри

### Агенты

7 агентов на LangGraph StateGraph + Auditor (RedTeam). Продакшен-таргет: Gemma 4 31B (одна копия на 5 агентов, 128K контекст), оркестратор — Llama 3.3 70B. Разработка на Ollama с моделями, помещающимися в 8GB VRAM.

| Агент | Модель | Задачи |
|-------|--------|--------|
| Руководитель проекта | Llama 3.3 70B | Оркестрация, PM Agent (weighted scoring → LLM reasoning → veto) |
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
| Auditor | `src/core/auditor.py` | Адверсариальный аудит: LLM ищет противоречия ГОСТ/СП в выводах агентов → APPROVED / NOTES / REJECT |
| Output Pipeline | `src/core/output_pipeline.py` | Генерация DOCX по 344/пр (АОСР, Times New Roman 12pt, нумерация) |
| Hybrid Classifier | `src/core/hybrid_classifier.py` | Классификация документов: keyword + LLM fallback + Guidance System |
| PPR Generator | `src/core/services/ppr_generator/` | Генерация ППР: 6 ТТК + разделы ПЗ + графика + экспорт |
| ИС Generator | `src/core/services/is_generator/` | Исполнительные схемы: DXF-аннотации, допуски СП 126, SVG/PDF |
| PM Agent | `src/core/pm_agent.py` | Принятие решений: weighted scoring → LLM reasoning → veto, оркестрация агентов |
| AgentState v2.0 | `src/agents/state.py` | Состояние конвейера: audit trail, confidence, rollback |
| LLMEngine | `src/core/llm_engine.py` | Единый интерфейс к MLX/Ollama |
| WorkTypeRegistry | `src/agents/skills/common/` | SSOT: 20 видов работ → маппинги (сметные, юридические, ФЕР) |
| БЛС | `traps/default_traps.yaml` | 58 ловушек субподрядчика в 10 категориях + pgvector RAG |
| Lessons Learned | `src/core/lessons_service.py` | Институциональная память: БД → RAG-инъекция → Skill Mutation |
| Knowledge Engine | `src/core/knowledge/` | Инвалидация знаний, реестр шаблонов (149 DOCX из id-prosto), загрузчик |
| Journal Restorer | `src/core/services/journal_restorer.py` | Forensic-восстановление ОЖР по косвенным документам |
| Completeness Matrix | `src/core/completeness_matrix.py` | Матрица комплектности ИД по 344/пр (13 позиций) + замечания |
| Batch ID Generator | `src/core/services/batch_id_generator.py` | Сквозная нумерация документов АОСР-{project}-{seq:04d} |
| Telegram Scout | `src/core/telegram_scout.py` | Мониторинг Telegram-каналов: тендеры, поставщики, стройки |
| Container (DI) | `src/core/container.py` | Dependency Injection: единая точка сборки компонентов |
| Google Workspace | `src/core/integrations/google.py` | Drive, Sheets, Docs, Gmail через OAuth2/Service Account |
| Document Repository | `src/core/document_repository.py` | Абстракция хранилища документов (локальные + Google Drive) |

### Forensic-проверки — методология

Система не перебирает список из N проверок — она строит сетевую модель документов (KAG) и проверяет её на нарушения по четырём осям:

**Документарная целостность.** Полнота и непротиворечивость цепочек: АОСР → акты освидетельствования скрытых работ → исполнительные схемы → сертификаты и паспорта → ТТН → журнал входного контроля → акты лабораторных испытаний. Любой разрыв или несоответствие — нарушение.

**Количественная согласованность.** Объёмы в АОСР не превышают партий в сертификатах; количество использованного материала сходится с остатками по ЖВК; геометрические параметры в исполнительных схемах соответствуют проектным. Физика и математика, а не формальная сверка.

**Темпоральная непротиворечивость.** Хронология: запись в общем журнале работ → акт скрытых работ → АОСР → следующий этап. С учётом технологической карты (допустимые перекрытия, сезонные ограничения, последовательность захваток). Журнал — первоисточник; если он не заполнен или утерян, цепочка восстанавливается по косвенным документам, фото/видео, свидетельским показаниям — но это зона эксперта, а не алгоритма.

**Нормативное соответствие.** Сертификат не просрочен, поставщик не ликвидирован, материал не снят с производства, ГОСТ актуален, протокол испытаний содержит обязательные реквизиты. Плюс 58 ловушек субподрядчика (БЛС) — от скрытых условий контракта до уловок генподрядчика.

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
│   └── skills/      # WorkTypeRegistry, work_spec, contract_risks, rate_lookup
├── core/
│   ├── ingestion.py, output_pipeline.py    # Пайплайны
│   ├── graph_service.py, auditor.py        # Forensic KAG
│   ├── hybrid_classifier.py                # Classifier + Guidance
│   ├── completeness_matrix.py              # Матрица комплектности ИД
│   ├── llm_engine.py, backends/            # MLX/Ollama/DeepSeek
│   ├── knowledge/                          # Инвалидация знаний, реестр шаблонов
│   ├── integrations/google.py              # Google Workspace (Drive, Sheets, Docs, Gmail)
│   ├── services/                           # pto_agent, smeta_agent, legal_documents,
│   │   ├── ppr_generator/                  #   ppr_generator, is_generator
│   │   ├── is_generator/                   #   journal_restorer, batch_id_generator
│   │   └── shared/                         #   gost_stamp (ГОСТ 21.101-2020)
│   ├── rag_pipeline.py, parser_engine.py
│   └── ram_manager.py, container.py, lessons_service.py
├── schemas/          # Pydantic
├── db/               # SQLAlchemy + Alembic
└── config.py         # Профили (dev_linux / mac_studio)

mcp_servers/asd_core/ # FastMCP (66+ инструментов)
tests/                # 493 теста (478 passed, 15 skipped)
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
