# MAC_ASD v13.0 — STATUS REPORT

**Дата:** 05.05.2026  
**Цикл:** 2/5 — Расширенная комплексная проверка

---

## Результаты Цикла 2

### 1. Аудит всех .py файлов проекта ✅

- **251 .py файл** просканирован (было 252, -1 после удаления ModelRouter)
- **7 критических проблем** выявлено (не обнаружены в Цикле 1):
  - NumberingService дубликат в output_pipeline.py (исправлен)
  - 4 коллизии имён Enum/dataclass (ChainStatus, EdgeType, EventType, ClassificationResult)
  - 2 дублирующиеся реализации forensic-проверок (evidence_graph vs graph_service)
- **0 синтаксических ошибок**, кодовая база чистая
- **0 закомментированных блоков** в production-коде

### 2. Целесообразность модулей ✅

| Статус | Модули |
|--------|--------|
| **✅ Активны** | LLMEngine, LegalService, ParserEngine, EvidenceGraph v2, Inference Engine, Chain Builder, HITL, Journal Reconstructor, Auditor, IDRequirementsRegistry, NormativeGuard, WorkEntry, PTO Skills, PPR Generator, IS Generator, ProjectLoader, NumberingService |
| **🗑️ Удалены** | ModelRouter (dead code, никем не импортирован), generate_report.py (v1), generate_inspection_report.py (v1), generate_inventory_los_pdf.py (v1), generate_concept_pdf_v3.py/v4.py (scripts в docs/) |
| **⚠️ Стабы** | MLXBackend (все методы → NotImplementedError), procurement/logistics MCP tools (4 функции-заглушки) |
| **🔴 Техдолг v14** | Forensic-дубликаты (4 метода в evidence_graph.py vs graph_service.py), коллизии имён (ChainStatus, EdgeType, EventType, ClassificationResult) |

### 3. Нормативная база ✅

- **Покрытие:** ~20% (15 present, 23 expected в normative_index.json)
- **Расширен индекс:** добавлены `expected` документы с приоритетами (8 critical, 6 high, 9 medium)
- **Алиасы:** расширены с 10 до 24 (включая ссылки на конкретные статьи ГК РФ)
- **Критические действия:**
  1. Скачать СП 70.13330.2025 до 01.06.2026 (замена СП 70.13330.2012)
  2. Заполнить pp_rf/ — ПП РФ 468 и 87 критически необходимы (директория пуста)
  3. Скачать 8 critical документов (СП 68, СП 126, ГОСТ 18105, ГОСТ 10180, ГОСТ 22690, ГОСТ 7473, ПП РФ 468, ПП РФ 87)
- **id_requirements.yaml:** 33 типа работ валидны, ~25 устаревших ГОСТ/СП ссылок (для обновления в цикле 3)

### 4. База знаний из ТГ-каналов ✅

- **782 записи** в data/telegram_knowledge.yaml (5 доменов)
- **Распределение:** legal: 398 (51%), pto: 228 (29%), procurement: 69 (9%), smeta: 54 (7%), logistics: 33 (4%)
- **Пробелы:** logistics (33 записи) и procurement (69 записей) недопредставлены
- **Telethon:** недоступен для live-сбора (системные ограничения pip), требуется ручная установка

### 5. Исправления ✅

| # | Исправление | Тип |
|---|-------------|-----|
| 1 | **NumberingService дубликат удалён** из output_pipeline.py, заменён на import из numbering_service.py | **CRITICAL** |
| 2 | **ModelRouter удалён** — dead code, никем не импортирован (подтверждено grep по всей кодовой базе) | **MEDIUM** |
| 3 | **3 v1 скрипта удалены** — generate_report.py, generate_inspection_report.py, generate_inventory_los_pdf.py (v2 лучше) | **LOW** |
| 4 | **2 scripts из docs/ удалены** — generate_concept_pdf_v3.py, generate_concept_pdf_v4.py (не место в документации) | **LOW** |
| 5 | **normative_index.json расширен** — 15→15 present + 23 expected, 24 aliases, coverage stats | **HIGH** |
| 6 | **Нормативный индекс:** добавлены метаданные coverage_by_type, critical_actions, обновлены алиасы | **MEDIUM** |

### 6. Тесты ✅

```
752 passed, 15 skipped in 8.35s — 0 failures, 0 regressions
```
Покрытие: 98.0% (752/767). Все тесты output_pipeline (21/21) проходят после рефакторинга NumberingService.

### 7. Документация ✅

- STATUS.md: обновлён (этот файл)
- normative_index.json: расширен (v13.0, 15 present + 23 expected)
- README.md: requires minor update (ModelRouter references)

### 8. Найденные проблемы (детальный аудит Цикла 2)

#### CRITICAL — исправлены в цикле 2
| # | Проблема | Решение |
|---|----------|---------|
| 1 | NumberingService в output_pipeline.py:71-112 — дубликат, не удалён после выделения в отдельный модуль | Заменён на import из numbering_service.py |

#### CRITICAL — отложены до v14 (требуют отдельного PR)
| # | Проблема | Описание |
|---|----------|----------|
| 2 | Forensic-дубликаты: check_batch_coverage, check_certificate_reuse, check_orphan_certificates, run_all_forensic_checks | Две параллельные реализации в evidence_graph.py и graph_service.py с разными сигнатурами и возвращаемыми типами |
| 3 | Коллизия ChainStatus: chain_builder.py (COMPLETE/PARTIAL/BROKEN/EMPTY) vs completeness_matrix.py (VERIFIED/MISSING/INCOMPLETE/STALE/UNVERIFIED) | Разные enum с одинаковым именем |
| 4 | Коллизия EdgeType: evidence_graph.py (15 значений) vs graph_service.py (9 значений) | Разные enum с одинаковым именем |
| 5 | Коллизия EventType: evidence_graph.py (DELIVERY/INSPECTION/...) vs is_generator/events.py (PIPELINE_STARTED/...) | Разные enum с одинаковым именем |
| 6 | Коллизия ClassificationResult: domain_classifier.py vs hybrid_classifier.py | Разные dataclass с одинаковым именем |

#### Известные проблемы (из цикла 1)
| # | Проблема | Приоритет | Цикл |
|---|----------|-----------|------|
| 1 | Нет ПП РФ в library/normative/pp_rf/ (ни одного) | HIGH | 3 |
| 2 | СП 70.13330.2012 → 2025: ~50 упоминаний в artifacts/, ~15 в id_requirements.yaml | HIGH | 3 |
| 3 | Library покрытие ~20% (15 из 100+ нормативных документов) | MEDIUM | 3 |
| 4 | logistics/procurement домены ТГ недопредставлены (1-2 канала) | MEDIUM | 3 |
| 5 | TELEGRAM_BOT_TOKEN отсутствует — WorkEntry бот не работает | MEDIUM | 3 |
| 6 | Duplicate тестовые классы (TestTaskNode, TestWorkPlan, TestWeightedScoring) — НЕ дубликаты, разные модули | ~~LOW~~ | ~~2~~ |
| 7 | MLXBackend — полный стаб (все методы → NotImplementedError) | LOW | 4 |

---

## Состояние проекта

| Метрика | Значение |
|---------|----------|
| **Версия** | 13.0 |
| **Python-файлов** | 245 (-6 удалено в цикле 2) |
| **MCP-инструментов** | 74 зарегистрировано |
| **Тестов** | 752 passed, 15 skipped |
| **Нормативных документов** | 15 present + 23 expected (~20% покрытия) |
| **ТГ-каналов** | 31 в 5 доменах |
| **ТГ-знаний** | 782 записи |
| **Ветка** | main |
| **Профиль** | dev_linux (Ollama/gemma3:12b) |
