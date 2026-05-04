# MAC_ASD v13

Мультиагентная система автоматизации исполнительной документации (ИД) для строительного подрядчика.
Действуем всегда в интересах подрядчика (ООО «КСК №1»). Полностью локальная, offline-first.

## Stack & Profiles

- **Language:** Python 3.11+
- **Framework:** LangGraph + FastMCP + SQLAlchemy + Alembic
- **DB:** PostgreSQL 16 + pgvector (localhost:5433)
- **Profiles:** `ASD_PROFILE=dev_linux` (DeepSeek API) | `mac_studio` (MLX)
- **Current:** dev_linux via DeepSeek V4 Pro[1m]

## Project Structure

```
src/core/              Evidence Graph v2, Inference Engine, ProjectLoader, LLMEngine, services
src/agents/            LangGraph StateGraph (state.py, workflow.py, nodes.py), skills
mcp_servers/asd_core/  FastMCP: 75+ tools (7 agents + auditor)
tests/                 511 tests (508 passed)
agents/                Prompts (Markdown) for 8 agents
traps/                 БЛС: 61 ловушка в 10 категориях (YAML)
library/               Local: ГОСТы, СП, шаблоны (not in Git)
infrastructure/        Docker: PostgreSQL 16 + pgvector
docs/                  Architecture, schema, MCP spec
```

## Architecture Essence

### Agents (8 total)
- **Руководитель проекта** (Llama 3.3 70B): orchestrator, weighted scoring + LLM reasoning + veto rules
- **ПТО** (Gemma 4 31B VLM): ВОР, чертежи, АОСР, 33 видов работ (IDRequirementsRegistry)
- **Юрист** (Gemma 4 31B): контракты (БЛС 61 ловушка), протоколы, претензии, иски
- **Сметчик** (Gemma 4 31B): ВОР↔смета, НМЦК, ЛСР, КС-2/КС-3
- **Закупщик** (Gemma 4 31B): тендеры, поставщики, лаб. контроль
- **Логист** (Gemma 4 31B): снабжение, КП, доставка
- **Делопроизводитель** (Gemma 4 E4B): регистрация, письма, реестр ИД
- **Auditor** (Llama 3.3 70B): rule-based RedTeam, 8 проверок (без LLM-as-Judge)

### PTO Skills
- **PTO_WorkSpec** (`work_spec.py`, 2464 loc): 33 WorkType, SSOT шлейфа ИД
- **PTO_VorCheck** (`vor_check.py`): fuzzy-сверка ВОР↔ПД (rapidfuzz + trigram fallback)
- **PTO_PDAnalysis** (`pd_analysis.py`): 3-стадийный анализ ПД (spatial + completeness + LLM)
- **PTO_ActGenerator** (`act_generator.py`): генерация DOCX актов (docxtpl + python-docx)
- **PTOComplianceSkill** (`compliance_skill.py`): объединение work_spec + idprosto + templates
### Core Systems
- **Evidence Graph v2**: единый граф (7 типов узлов, 11 связей, confidence framework)
- **Inference Engine**: 6 symbolic-правил восстановления дат/фактов из улик
- **ProjectLoader**: нулевой слой (ПД/РД → WorkUnit PLANNED baseline)
- **Chain Builder**: MaterialBatch→Cert→AOSR→KS-2 цепочки, разрывы, статусы
- **HITL System**: Human-in-the-Loop вопросы с приоритетами (critical/high/medium/low)
- **Journal Reconstructor v2**: 5 этапов восстановления ОЖР, цветовая разметка (🟢/🟡/🔴)
- **NormativeGuard**: SSOT-валидация (normative_index.json), все ГОСТ/СП/ФЗ проверяются
- **IDRequirementsRegistry**: SSOT состава ИД по 344/пр (33 вида работ → обязательный шлейф)

## Rules & Conventions

### Database
- **Миграции:** Alembic only. `alembic revision --autogenerate -m "description"` + `alembic upgrade head`
- **Never:** `Base.metadata.create_all()`
- **New models:** in `src/db/models.py`, then migrate

### LLM & Inference
- **All LLM calls:** через LLMEngine только. Никаких прямых import deepseek/anthropic
- **LLMEngine route:** dev_linux → DeepSeek API, mac_studio → MLX backend
- **Prompts:** in `agents/` (Markdown), referenced by agent name
- **Thinking mode:** используется для Юриста (contracts, трудные решения) и ПТО (сложная сверка)

### Validation & Quality
- **NormativeGuard:** запуск на выходе всех LLM-ответов из Юриста/ПТО (проверка ГОСТ/СП/норм)
- **IDRequirementsRegistry:** lookup состава ИД по типу работы из 33 видов
- **Auditor.check_*:** 8 правил кросс-проверки между агентами (не пропускать)

### Code Style
- Type hints everywhere (strict mode)
- Pydantic models for all schemas
- Named exports only (no default exports)
- SQLAlchemy ORM (не raw SQL)
- Async/await when dealing with I/O

### Graph (NetworkX)
- Evidence Graph in-memory, serialized to `data/graphs/`
- Never mutate nodes directly — use `evidence_graph.add_node(...)` with confidence
- All temporal checks через Inference Engine rules, не через LLM reasoning

### Testing
- `pytest tests/ -v` — всегда после изменений модулей
- Test coverage: 508/511 passed (99.4%)
- E2E: `PYTHONPATH=. python tests/test_e2e_forensic.py`

### Git & Commits
- Feature branches always: `git checkout -b feature/X`
- Alembic version changes → include in PR
- Never commit `.env`, API keys, or `library/normative/` (local only)

## When to Use What

| Task | Start With | Reference |
|------|-----------|-----------|
| New MCP tool | `mcp_servers/asd_core/tools/` + LangGraph node | @docs/MCP_TOOLS_SPEC.md |
| Agent prompt | `agents/{agent_name}/prompt.md` | @agents/{agent_name}/config.yaml |
| DB schema | `src/db/models.py` + Alembic migration | @docs/DATA_SCHEMA.md |
| Evidence Graph query | `EvidenceGraphService` + Inference Engine | @docs/COMPONENT_ARCHITECTURE.md |
| Normative check | `NormativeGuard.validate()` against normative_index.json | @src/core/services/legal_service.py |
| Document parsing | ParserEngine (OCR/PDF) + VLM fallback | @src/core/ingestion.py |

## Key Files to Keep Open

- `AGENTS.md` — workflow, event bus, маршрутизация между агентами
- `src/agents/state.py` — единое состояние конвейера
- `src/agents/workflow.py` — LangGraph StateGraph
- `src/core/llm_engine.py` — интерфейс к LLM (LLMEngine)
- `src/core/services/legal_service.py` — NormativeGuard, Юрист сервис
- `src/core/services/id_requirements.py` — IDRequirementsRegistry (SSOT видов работ)
- `mcp_servers/asd_core/server.py` — FastMCP регистрация инструментов

## Performance & Memory

- **Dev (DeepSeek V4 Pro[1m]):** 1M контекст, reasoning режим для сложных задач
- **Tokens:** Кэширование system prompt + проект контекст (DeepSeek cache цены ~1/4 от input)
- **Session:** одна сессия = один package, не переключайся между задачами (горячий кэш)
- **Контекст:** `/compact` при длинных сессиях (>100K tokens)

## Common Commands

```bash
# Тесты
pytest tests/ -v
pytest tests/test_agents.py::TestLegalAgent -v

# Запуск MCP сервера
python -m mcp_servers.asd_core.server

# Миграции БД
alembic revision --autogenerate -m "add_new_model"
alembic upgrade head

# Бенчмарк качества
PYTHONPATH=. python scripts/run_benchmark.py --project-dir data/test_projects/LOS --quality-cascade

# Синтетические документы
PYTHONPATH=. python scripts/generate_synthetic_docs.py --count 100 --all-types
```

## Emergency Rollback

```bash
git reset --hard HEAD      # отмена всех изменений
alembic downgrade -1       # откат одной миграции
/rewind                    # в Claude Code: откат сессии
```
