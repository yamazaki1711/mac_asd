# MAC ASD v13.0

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
pytest tests/ -v                           # 752 passed, 15 skipped, 767 collected

# Веб-интерфейс
PYTHONPATH=. python src/web/app.py        # http://localhost:8080

# E2E forensic
PYTHONPATH=. python tests/test_e2e_forensic.py

# MCP-сервер
python -m mcp_servers.asd_core.server
```

## Что внутри

### Агенты

8 агентов на LangGraph StateGraph + Auditor (RedTeam). Продакшен-таргет: Gemma 4 31B (одна копия на 5 агентов, 128K контекст), оркестратор — Llama 3.3 70B. Разработка на DeepSeek API + Ollama Cloud.

| Агент | Модель | Задачи |
|-------|--------|--------|
| Руководитель проекта | Llama 3.3 70B | Оркестрация, PM Agent (weighted scoring → LLM reasoning → veto) |
| ПТО | Gemma 4 31B VLM | ВОР, чертежи, АОСР, сверка ПД, 33 вида работ, OCR |
| Юрист | Gemma 4 31B | БЛС (61 ловушка, 11 категорий), контракты, претензии, иски |
| Сметчик | Gemma 4 31B | ФЕР/ТЕР, НМЦК, рентабельность, КС-2/КС-3 |
| Закупщик | Gemma 4 31B | Тендеры, поставщики, лаб. контроль |
| Логист | Gemma 4 31B | Снабжение, КП, доставка |
| Делопроизводитель | Gemma 4 E4B | Регистрация, архив, реестр ИД, NumberingService |
| Auditor (RedTeam) | Rule-based | 8 forensic-проверок, перекрёстный аудит агентов, без LLM-as-Judge |

### Веб-интерфейс (локальный)

6 страниц на Flask (localhost:8080): дашборд проекта, проекты, документы, evidence graph, HITL-вопросы, отчёты. Drag & drop загрузка. Авто-бэкапы БД/графов/артефактов. Telegram-бот для приёма WorkEntry от полевых инженеров.

### Ключевые модули

| Модуль | Файл | Что делает |
|--------|------|------------|
|| Ingestion Pipeline | `src/core/ingestion.py` | Сканы → OCR → классификация (18 типов) → извлечение сущностей → VLM fallback |
|| **Quality Cascade** | `src/core/quality_metrics.py` | Каскад качества (АФИДА): измерение потерь на 5 этапах конвейера, waterfall |
|| **Evidence Graph v2** | `src/core/evidence_graph.py` | Единый граф: 7 типов узлов, 11 типов связей, confidence на всём |
| **Inference Engine** | `src/core/inference_engine.py` | Symbolic inference: 6 правил вывода дат/фактов из улик |
| **ProjectLoader** | `src/core/project_loader.py` | Нулевой слой: парсинг ПД/РД → baseline WorkUnit'ов |
| Forensic KAG | `src/core/graph_service.py` | Оригинальный граф (12 типов узлов) — обратная совместимость |
| Auditor | `src/core/auditor.py` | Rule-based RedTeam: 8 проверок (кросс-агентные + forensic + классификация), без LLM-as-Judge |
| Output Pipeline | `src/core/output_pipeline.py` | Генерация DOCX по 344/пр (АОСР, Times New Roman 12pt, нумерация) |
| Hybrid Classifier | `src/core/hybrid_classifier.py` | Классификация документов: keyword + LLM fallback + Guidance System |
| PPR Generator | `src/core/services/ppr_generator/` | Генерация ППР: 6 ТТК + разделы ПЗ + графика + экспорт |
| ИС Generator | `src/core/services/is_generator/` | Исполнительные схемы: DXF-аннотации, допуски СП 126, SVG/PDF |
| PM Agent | `src/core/pm_agent.py` | Принятие решений: weighted scoring → LLM reasoning → veto, оркестрация агентов |
| AgentState v2.0 | `src/agents/state.py` | Состояние конвейера: audit trail, confidence, rollback |
| LLMEngine | `src/core/llm_engine.py` | Единый интерфейс к MLX/Ollama |
| WorkTypeRegistry | `src/agents/skills/common/` | SSOT: 33 вида работ → маппинги (сметные, юридические, ФЕР), из Пособия по ИД Вып.2 |
| БЛС | `traps/default_traps.yaml` | 61 ловушка субподрядчика в 11 категориях + pgvector RAG |
| Lessons Learned | `src/core/lessons_service.py` | Институциональная память: БД → RAG-инъекция → Skill Mutation |
| Knowledge Engine | `src/core/knowledge/` | Инвалидация знаний, реестр шаблонов (149 DOCX из id-prosto), загрузчик |
| Journal Restorer | `src/core/services/journal_restorer.py` | Forensic-восстановление ОЖР по косвенным документам |
| Chain Builder | `src/core/chain_builder.py` | **Package 11**. Цепочки MaterialBatch→Cert→AOSR→KS-2, разрывы, confidence |
| HITL System | `src/core/hitl_system.py` | **Package 11**. Вопросы оператору, приоритеты, обновление графа |
| Journal Reconstructor v2 | `src/core/journal_reconstructor.py` | **Package 11**. 5 этапов, цветовая разметка, вывод JSON/таблица |
| Completeness Matrix | `src/core/completeness_matrix.py` | Матрица комплектности ИД по 344/пр (13 позиций) + замечания |
| **IDRequirementsRegistry** | `src/core/services/id_requirements.py` | SSOT состава ИД: 33 вида работ → обязательный шлейф документов по 344/пр |
| **NormativeGuard** | `src/core/services/legal_service.py` | Валидация: все ГОСТ/СП/ФЗ из ответов LLM проверяются по library/normative/ |
| **PTO_VorCheck** | `src/agents/skills/pto/vor_check.py` | Сверка ВОР↔ПД: fuzzy-мэтчинг, 4 типа расхождений (rapidfuzz + trigram) |
| **PTO_PDAnalysis** | `src/agents/skills/pto/pd_analysis.py` | 3-стадийный анализ ПД: пространственные коллизии + комплектность ГОСТ 21.1101 + LLM-семантика |
| **PTO_ActGenerator** | `src/agents/skills/pto/act_generator.py` | Генерация DOCX актов: АОСР/входной/скрытые/освидетельствование (docxtpl + python-docx) |
| **ConstructionElement** | `src/db/models.py` | Физическая структура: Захватки + Конструктивы + ElementDocument |
| **WorkEntry** | `src/core/services/work_entry.py` | Цифровой ОЖР: парсер Telegram-сообщений → WorkEntry → триггер АОСР |
| Batch ID Generator | `src/core/services/batch_id_generator.py` | Сквозная нумерация документов АОСР-{project}-{seq:04d} |
| Telegram Scout | `src/core/telegram_scout.py` | Мониторинг Telegram-каналов: тендеры, поставщики, стройки |
| Container (DI) | `src/core/container.py` | Dependency Injection: единая точка сборки компонентов |
| Google Workspace | `src/core/integrations/google.py` | Drive, Sheets, Docs, Gmail через OAuth2/Service Account |
| Document Repository | `src/core/document_repository.py` | Абстракция хранилища документов (локальные + Google Drive) |
| **Web UI** | `src/web/app.py` | Flask-интерфейс: дашборд, проекты, документы, HITL, evidence graph, отчёты |
| **Backup System** | `src/core/backup_service.py` | Авто-бэкапы: PostgreSQL, NetworkX-графы, артефакты |
| **Telegram Scout** | `src/core/telegram_scout.py` | Мониторинг 40+ Telegram-каналов: тендеры, поставщики |
| **Forensic Checks** | `src/core/evidence_graph.py` | batch_coverage, orphan_certificates, certificate_reuse |
| **NumberingService** | `src/core/services/numbering_service.py` | Сквозная нумерация документов: АОСР, письма, реестры |

### Evidence Graph v2 — два режима, один граф

**Сопровождение:** ProjectLoader создаёт baseline из ПД/РД → агенты ведут стройку: PLANNED → IN_PROGRESS → COMPLETED, confidence=1.0.

**Антикризис (forensic):** ProjectLoader создаёт baseline → Inference Engine восстанавливает хронологию из улик (ТТН, сертификаты, КС-2, фото) → дельта = план − улики.

Четыре оси forensic-проверок:

**Документарная целостность.** Полнота и непротиворечивость цепочек: АОСР → акты освидетельствования скрытых работ → исполнительные схемы → сертификаты и паспорта → ТТН → журнал входного контроля → акты лабораторных испытаний. Любой разрыв или несоответствие — нарушение.

**Количественная согласованность.** Объёмы в АОСР не превышают партий в сертификатах; количество использованного материала сходится с остатками по ЖВК; геометрические параметры в исполнительных схемах соответствуют проектным. Физика и математика, а не формальная сверка.

**Темпоральная непротиворечивость.** Хронология: запись в общем журнале работ → акт скрытых работ → АОСР → следующий этап. С учётом технологической карты (допустимые перекрытия, сезонные ограничения, последовательность захваток). Журнал — первоисточник; если он не заполнен или утерян, цепочка восстанавливается по косвенным документам, фото/видео, свидетельским показаниям — но это зона эксперта, а не алгоритма.

**Нормативное соответствие.** Сертификат не просрочен, поставщик не ликвидирован, материал не снят с производства, ГОСТ актуален, протокол испытаний содержит обязательные реквизиты. Плюс 61 ловушка субподрядчика (БЛС) — от скрытых условий контракта до уловок генподрядчика.

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
├── agents/          # LangGraph: workflow.py, nodes.py, nodes_v2.py, state.py
│   └── skills/      # PTO: work_spec, vor_check, pd_analysis, act_generator, compliance_skill
├── core/
│   ├── evidence_graph.py, inference_engine.py   # Evidence Graph v2 (+ forensic checks)
│   ├── project_loader.py                        # Нулевой слой: ПД/РД → baseline
│   ├── chain_builder.py, hitl_system.py          # Package 11: цепочки, HITL
│   ├── journal_reconstructor.py                  # Package 11: реконструкция ОЖР
│   ├── scan_detector.py, vlm_classifier.py      # VLM-интеграция
│   ├── quality_metrics.py                       # Каскад качества
│   ├── ingestion.py, output_pipeline.py         # Пайплайны
│   ├── graph_service.py, auditor.py        # Forensic KAG
│   ├── hybrid_classifier.py                # Classifier + Guidance
│   ├── completeness_matrix.py              # Матрица комплектности ИД
│   ├── backup_service.py                   # Авто-бэкапы БД/графов/артефактов
│   ├── llm_engine.py, backends/            # MLX/Ollama/DeepSeek
│   ├── knowledge/                          # Инвалидация знаний, реестр шаблонов
│   ├── integrations/google.py              # Google Workspace (Drive, Sheets, Docs, Gmail)
│   ├── services/                           #   pto_agent, smeta_agent, legal_documents,
│   │   │   id_requirements.py, work_entry.py  #   NormativeGuard, WorkEntry, NumberingService
│   │   ├── ppr_generator/                  #   Генератор ППР (6 ТТК + ПЗ + графика)
│   │   ├── is_generator/                   #   Генератор исполнительных схем
│   │   └── shared/                         #   gost_stamp (ГОСТ 21.101-2020)
│   ├── rag_pipeline.py, parser_engine.py
│   └── ram_manager.py, container.py, lessons_service.py
├── web/               # Flask UI (6 страниц, HITL-интерфейс)
├── schemas/           # Pydantic
├── db/                # SQLAlchemy + Alembic
└── config.py          # Профили (dev_linux / mac_studio)

mcp_servers/asd_core/  # FastMCP (74 инструмента)
tests/                 # 767 тестов (752 passed, 15 skipped)
agents/                # Промпты агентов (Markdown)
scripts/               # Утилиты: run_inventory.py, run_benchmark.py, generate_synthetic_docs.py
traps/                 # БЛС — 61 ловушка, 10 категорий (YAML)
infrastructure/        # Docker Compose
library/               # 284 файла, 101 MB — ГОСТы, СП, шаблоны, образцы (локально, не в Git)
```

## Документация

| Файл | Содержание |
|------|-----------|
| `agents.md` | Манифест оркестратора — протоколы, workflow, правила |
| `docs/COMPREHENSIVE_ANALYSIS_20260505.md` | **Свежий** комплексный анализ: 752 теста, 83K LOC, Grok P0 |
| `docs/STATUS.md` | Сводный статус проекта (актуализирован 05.05.2026) |
| `docs/CONCEPT_v13.md` | Концепция системы |
| `docs/COMPONENT_ARCHITECTURE.md` | Внутренняя архитектура компонентов |
| `docs/CORE_LOGIC_DESIGN.md` | Логика переходов, OCR-конвейер, RAM-менеджмент |
| `docs/MCP_TOOLS_SPEC.md` | Спецификация MCP инструментов |
| `docs/DATA_SCHEMA.md` | Схема PostgreSQL |
| `docs/MODEL_STRATEGY.md` | Стратегия моделей и управление памятью |
| `docs/DEPLOYMENT_PLAN.md` | План развёртывания на Mac Studio |
| `docs/STRATEGY.md` | Стратегия антикризисной команды (4 человека) |
| `docs/BUILDING_LIFECYCLE_WORKFLOW.md` | Жизненный цикл объекта строительства |
| `docs/id_pipeline_architecture.md` | Архитектура единого конвейера ИД (ИС + ППР + АОСР) |
| `docs/ppr_generator.md` | Концепция ППР-генератора |

## Нормативная база

Приказ 344/пр (состав ИД), 1026/пр (журналы), ГОСТ Р 70108-2025 (электронная ИД), СП 543.1325800.2024 (стройконтроль), СП 70.13330.2025 (монтаж), ВСН 012-88 (сварка), ПП РФ №468 и №249, ФЗ-44, ФЗ-223.

## Оценка качества (Domain Benchmark)

Доменный бенчмарк на реальных строительных документах (ЛОС, 12 PDF). Вдохновлён подходом АФИДЫ (Газпром ЦПС, 2025): каскад потерь качества + собственный бенчмарк на доменных данных.

| Метрика | Без VLM | С VLM (Gemma 4 31B) |
|---------|:-------:|:--------------------:|
| Точность классификации | 36% | **92%** |
| Доля VLM-фолбэков | 0% | 92% |
| UNKNOWN документов | 3 (25%) | **0 (0%)** |
| АОСР найдено | 1 из 2 | **2 из 2** |
| Встроенные ссылки | 0 | **4** |
| Время обработки | 47 сек | ~6 мин |

**Micro-errors (2/12):** КС-3 → ks2 (VLM путает визуально похожие формы), КС-6а → journal (таблица с датами).

**Каскад качества:** OCR 91% → Классификация 83% → VLM 100% → Сущности 100% → Граф 100%.

Запуск: `PYTHONPATH=. python scripts/run_benchmark.py --project-dir data/test_projects/LOS --quality-cascade`

Генерация синтетических документов: `PYTHONPATH=. python scripts/generate_synthetic_docs.py --count 100 --all-types --output-dir data/synthetic_docs`
