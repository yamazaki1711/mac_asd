# АСД v13.0 — Сводный статус проекта

**Дата:** 4 мая 2026
**Ветка:** main (clean)
**Контекст:** 7 раундов v13.0 hardening после концептуального завершения v12.0

---

## 1. Что сделано (апрель–май 2026)

### v13.0 Hardening Pass (текущий раунд)
- **1666704** refactor: hardening pass — логирование, типы, дедупликация, константы, инкапсуляция
- **c1cb0c9** fix: замена всех `except Exception:` на конкретные типы исключений + логирование
- **d030c39** lazy imports: отложенная загрузка тяжёлых модулей в `src/core/`
- **d9ea16e** import guards, ленивые сервисы, синхронизация версий
- **e972c96** доработка nodes, config, db/models, vor_check через Claude Code
- **35625b3** auto(v13.0): round 3 — финальные правки (4 файла, 45 строк)
- **b9e034b** fix: tighten hypothesis assume в scoring invariance тесте

### v13.0 Инженерный май
- **c180f79** feat(v13.0): доработка PM-оркестратора и Делопроизводителя
- **7bf046b** feat(v13.0): PTO skills — vor_check, pd_analysis, act_generator вместо заглушек (реальные модули)

### v12.0 Завершение (концептуальный финал)
- Package 5: Evidence Graph v2, Inference Engine, ProjectLoader
- Package 11: Chain Builder, HITL System, Journal Reconstructor v2
- Package 4 (Legal): генератор претензий, исков, мотивированных отказов (DOCX)
- IDRequirementsRegistry: 33 вида работ заполнены реальными данными
- Knowledge Base: pgvector RAG + DomainClassifier + TelegramIngester
- Knowledge Invalidation: движок проверки актуальности нормативных ссылок
- Auditor: 8 правил кросс-проверки (rule-based, без LLM-as-Judge)
- NormativeGuard: SSOT-валидация (normative_index.json)
- Vision Cascade: Stage 1/2, Gemma 4 31B Cloud VLM
- БЛС: 61 ловушка в 10 категориях
- Структурный чанкинг: 12000/2400, без разрыва разделов и таблиц
- Google Workspace: Gmail, Drive, Sheets, Docs
- MCP Server: 74 инструмента (7 агентов + auditor)

---

## 2. Состояние кодовой базы

| Метрика | Значение |
|---------|----------|
| Python-файлов (src/) | ~120 |
| Строк Python (всего) | 77,502 |
| Строк Python (src/) | 50,391 |
| Строк Python (tests/) | ~12,600 |
| MCP-инструментов | 74 |
| Агентов | 7 + Auditor |
| Тестовых файлов | 20 |

### Крупнейшие модули

| Модуль | LOC | Назначение |
|--------|-----|------------|
| `work_spec.py` | 2,464 | PTO WorkSpec: 33 WorkType, SSOT шлейфа ИД |
| `test_is_generator.py` | 1,600 | Тесты исполнительных схем |
| `pm_agent.py` | 1,293 | PM-оркестратор (Llama 3.3 70B) |
| `lab_tools.py` | 1,239 | Лабораторный контроль (13 инструментов) |
| `nodes.py` | 1,209 | LangGraph-узлы (legacy) |
| `legal_documents.py` | 1,178 | Генератор протоколов/претензий/исков |
| `test_smoke.py` | 1,153 | Дымовые тесты |
| `ingestion.py` | 975 | Конвейер приёма документов |
| `legal_service.py` | 973 | Юридический анализ (Quick Review + Map-Reduce) |
| `rate_lookup.py` | 930 | Сметчик: поиск расценок ФЕР/ГЭСН |

---

## 3. Состояние тестов

```
590 passed, 15 skipped in 4.86s
```

### Покрытие по категориям

| Файл тестов | Что покрывает | Статус |
|-------------|---------------|--------|
| `test_smoke.py` | Дымовые тесты (все компоненты) | ✅ |
| `test_legal_service.py` | LegalService, БЛС, чанкинг | ✅ |
| `test_legal_documents.py` | Генерация протоколов/претензий/исков | ✅ |
| `test_vor_check.py` | PTO VorCheck: fuzzy-сверка ВОР↔ПД | ✅ |
| `test_pd_analysis.py` | PTO PDAnalysis: 3-стадийный анализ ПД | ✅ |
| `test_act_generator.py` | PTO ActGenerator: DOCX актов | ✅ |
| `test_orchestration.py` | PM-оркестратор, взвешенный скоринг | ✅ |
| `test_workplan.py` | WorkPlan, dispatch, evaluation | ✅ |
| `test_delo_agent.py` | Делопроизводитель: письма, регистрация | ✅ |
| `test_is_generator.py` | Исполнительные схемы (IS Generator) | ✅ |
| `test_ppr_generator.py` | ППР-генератор | ✅ |
| `test_e2e_forensic.py` | E2E: forensic-восстановление ИД | ✅ |
| `test_e2e_parallel_graph.py` | E2E: параллельный граф | ✅ |
| `test_output_pipeline.py` | Output Pipeline: экспорт PDF/XLSX | ✅ |
| `test_rag_pipeline.py` | RAG Pipeline: векторный + графовый поиск | ✅ |
| `test_model_queue.py` | ModelQueue: управление моделями | ✅ |
| `test_hypothesis_scoring.py` | Hypothesis: инварианты скоринга | ✅ |
| `test_journal_restorer.py` | Journal Reconstructor v2 | ✅ |
| `test_container.py` | DI-контейнер | ✅ |
| `test_google_integration.py` | Google Workspace (моки) | ✅ |

**Пропущено (15):** тесты, требующие внешних зависимостей (Ollama, API-ключи, VLM).

---

## 4. Архитектурная зрелость

| Компонент | Зрелость | Примечание |
|-----------|----------|------------|
| Evidence Graph v2 | 🟢 Стабильно | 7 типов узлов, 11 связей, confidence |
| Inference Engine | 🟢 Стабильно | 6 symbolic-правил |
| Chain Builder | 🟢 Стабильно | Цепочки MaterialBatch→Cert→AOSR→KS-2 |
| HITL System | 🟢 Стабильно | Приоритеты critical/high/medium/low |
| Journal Reconstructor v2 | 🟢 Стабильно | 5 этапов, цветовая разметка |
| Legal Service | 🟢 Стабильно | Quick Review + Map-Reduce + БЛС |
| PTO Skills | 🟢 Стабильно | VorCheck, PDAnalysis, ActGenerator |
| PM-оркестратор | 🟡 Активная доработка | WorkPlan, dispatch, weighted scoring |
| LLM Engine | 🟢 Стабильно | Lazy imports, fallback, retry |
| Auditor | 🟢 Стабильно | 8 правил, rule-based |
| NormativeGuard | 🟢 Стабильно | SSOT-валидация ссылок |
| Knowledge Invalidation | 🟡 Требует наполнения | Движок готов, данных в индексе мало |
| Vision Cascade | 🟡 Зависит от VLM | Stage 1/2 реализованы, качество от модели |
| Google Workspace | 🟡 Моки | Требует OAuth-токенов для продакшена |

---

## 5. Что дальше

### Ближайший горизонт (май 2026)
1. **Стабилизация PM-оркестратора** — завершить интеграцию WorkPlan с реальными MCP-вызовами
2. **Раунд 4 hardening** — финальная чистка typing, docstrings, консистентность API
3. **15 skipped тестов** — закрыть моками там, где нужны внешние зависимости
4. **CI/quality gate** — pre-commit hook: pytest + ruff + mypy

### Средний горизонт (июнь–июль 2026)
5. **E2E tender pipeline** — сквозной тест: тендер → контракт → ИД → сдача
6. **Knowledge Invalidation** — наполнить индекс реальными данными об отменённых ГОСТ/СП
7. **UI (Gradio)** — минимальный веб-интерфейс для HITL-вопросов и мониторинга
8. **Продакшен-деплой** — Mac Studio, настройка OAuth, мониторинг

### Стратегический горизонт (конец 2026)
9. **v14.0** — мультипроектность,增量-обучение на инженерных решениях, мобильный клиент

---

## 6. Известные риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| VLM-модель недоступна на dev_linux | Средняя | OCR сканов падает до Tesseract | Fallback-цепочка реализована |
| Gemma 4 31B не тянет сложный legal-анализ | Низкая | Качество анализа ниже целевого | Map-Reduce + thinking mode |
| 128K контекста не хватает на большие контракты | Низкая | Разрыв контекста между чанками | Structural chunking + overlap |
| Зависимость от Ollama на dev_linux | Средняя | Модели могут не запуститься | DeepSeek API как fallback |
| Нет продакшен-токенов Google | Высокая | Google Workspace не работает | Реализован, ждёт OAuth |

---

## 7. Команда и ресурсы

- **Разработка:** 1 разработчик (Oleg Shcherbakov) + Claude Code
- **Модели (dev):** Ollama gemma3:12b (RTX 5060), DeepSeek API (fallback)
- **Модели (prod target):** Mac Studio M4 Max 128GB — Llama 3.3 70B + Gemma 4 31B + Gemma 4 E4B
- **Инфраструктура:** PostgreSQL 16 + pgvector (localhost:5433), Docker
- **Библиотека:** 284 файла, 101 MB (ГОСТы, СП, шаблоны)

---

*Документ сгенерирован 04.05.2026 на основе анализа кодовой базы и git-истории.*
