# MAC_ASD v13.0 — STATUS REPORT

**Дата:** 05.05.2026  
**Цикл:** 1/5 — Расширенная комплексная проверка

---

## Результаты Цикла 1

### 1. Аудит всех файлов проекта ✅

- **252 .py файла** просканированы в src/, tests/, mcp_servers/
- **46 проблем** выявлено: 16 dead code, 6 unused imports, 3 duplicate code, 8 legacy, 5 bugs, 8 stubs
- **0 закомментированных блоков кода** — кодовая база чистая

### 2. Целесообразность модулей ✅

| Статус | Модули |
|--------|--------|
| **✅ Активны** | LLMEngine, LegalService, ParserEngine, EvidenceGraph v2, Inference Engine, Chain Builder, HITL, Journal Reconstructor, Auditor, IDRequirementsRegistry, NormativeGuard, WorkEntry, PTO Skills (VorCheck, PDAnalysis, ActGenerator), PPR Generator, IS Generator, ProjectLoader, NumberingService |
| **⚠️ Стабы** | MLXBackend (все методы → NotImplementedError), procurement/logistics MCP tools (4 функции-заглушки), web_search |
| **🔴 Dead code** | ModelRouter (никем не импортирован), archive_ingest_node, audit_classification, src/tools/, src/integrations/ |

### 3. Нормативная база ⚠️

- **Покрытие:** ~20% (15 из ~100+ упомянутых нормативных документов)
- **Критически отсутствуют:** Все ПП РФ (ни одного в library/normative/pp_rf/), Приказы Ростехнадзора, 384-ФЗ, 116-ФЗ
- **Исправлено:** ГОСТ Р 51872-2019 → 2024 (3 файла), добавлен СП 70.13330.2025 (pending, с 01.06.2026)
- **СП 70.13330.2012** будет заменён на СП 70.13330.2025 с 01.06.2026 (26 дней) — ~50 упоминаний в коде

### 4. База знаний из ТГ-каналов ✅

- **32 канала** в 5 доменах (legal: 15, pto: 10, smeta: 2, procurement: 2, logistics: 1)
- **32,505 записей** в data/telegram_knowledge.yaml
- **Инфраструктура рабочая:** telegram_scout.py, telegram_kb_ingest.py, telegram_content_quality.py
- **Пробелы:** logistics и procurement домены недопредставлены, TELEGRAM_BOT_TOKEN отсутствует

### 5. Исправления ✅

| # | Исправление | Тип |
|---|-------------|-----|
| 1 | auth_telegram.py: удалены хардкод-креды (API_ID/API_HASH/PHONE), теперь из .env | **CRITICAL** |
| 2 | .gitignore: добавлены .env.local, *.session, data/uploads/ | **CRITICAL** |
| 3 | .env.local: удалён из git tracking (содержал DEEPSEEK_API_KEY) | **CRITICAL** |
| 4 | telegram_session.session: удалён из git tracking (сессионные данные) | **HIGH** |
| 5 | asd_id_search/asd_id_download: добавлены реализации в pto_tools.py (исправлен ImportError) | **CRITICAL** |
| 6 | Artifact/Legal/Vision tools: зарегистрированы в server.py (3 dead-модуля активированы) | **MEDIUM** |
| 7 | ГОСТ Р 51872-2019 → 2024: 4 файла исправлены (generate_inspection_report.py, _v2.py, PTO_Rules.md) | **HIGH** |
| 8 | fallback_router.py: исправлен баг — PM теперь используется при healthy, а не игнорируется | **BUG** |
| 9 | normative_index.json: добавлен СП 70.13330.2025 (pending), обновлён total: 14→15 | **MEDIUM** |
| 10 | general_tools.py: mcp_tools_active: 18→74 | **LOW** |
| 11 | id_requirements.yaml: version 12.0→13.0 | **LOW** |
| 12 | agents/logistics/__init__.py: удалён (stray Python file в prompts-директории) | **LOW** |
| 13 | data/uploads/: очищено 147 тестовых стабов | **LOW** |
| 14 | data/inspection_report_LOS.pdf: удалён из git tracking | **LOW** |

### 6. Тесты ✅

```
752 passed, 15 skipped in 8.00s — 0 failures, 0 regressions
```

Покрытие: 98.0% (752/767)

### 7. Документация ✅

- STATUS.md: создан (этот файл)
- normative_index.json: актуализирован
- id_requirements.yaml: версия обновлена

### 8. Известные проблемы (не исправлены в цикле 1)

| # | Проблема | Приоритет | Цикл |
|---|----------|-----------|------|
| 1 | Нет ПП РФ в library/normative/pp_rf/ (ни одного) | HIGH | 2 |
| 2 | СП 70.13330.2012 → 2025: ~50 упоминаний нужно обновить к 01.06.2026 | HIGH | 2 |
| 3 | Library покрытие ~20% (15 из 100+ нормативных документов) | MEDIUM | 2-3 |
| 4 | logistics/procurement домены ТГ недопредставлены (1-2 канала) | MEDIUM | 2 |
| 5 | TELEGRAM_BOT_TOKEN отсутствует — WorkEntry бот не работает | MEDIUM | 3 |
| 6 | Duplicate-v1/v2 скрипты в scripts/ (3 пары) | LOW | 2 |
| 7 | Scripts в docs/ (generate_concept_pdf_v3.py, v4.py) | LOW | 2 |
| 8 | Duplicate тестовые классы (TestTaskNode, TestWorkPlan, TestWeightedScoring) | LOW | 2 |
| 9 | MLXBackend — полный стаб (все методы → NotImplementedError) | LOW | 4 |
| 10 | ModelRouter — dead code, никем не импортирован | LOW | 2 |

---

## Состояние проекта

| Метрика | Значение |
|---------|----------|
| **Версия** | 13.0 |
| **Python-файлов** | 252 |
| **MCP-инструментов** | 74 зарегистрировано |
| **Тестов** | 752 passed, 15 skipped |
| **Нормативных документов** | 15 в индексе (~20% покрытия) |
| **ТГ-каналов** | 32 в 5 доменах |
| **ТГ-знаний** | 32,505 записей |
| **Ветка** | main |
| **Профиль** | dev_linux (Ollama/gemma3:12b) |
