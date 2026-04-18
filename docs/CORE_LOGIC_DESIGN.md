# АСД v11.0 — ДЕТАЛЬНЫЙ ДИЗАЙН LOGIC & WORKFLOW

## 1. Event Manager (State Machine)

EventManager управляет графом состояний проекта. Мы используем **NetworkX** для хранения графа событий в оперативной памяти с периодической синхронизацией в **PostgreSQL + NetworkX**.

### 1.1. Узлы (Nodes) — События

- `INIT`: Начало жизненного цикла (поиск тендера).
- `TENDER_FOUND`: Закупщик нашел лот.
- `FILES_REGISTERED`: Архив (Делопроизводитель) рассортировал документы.
- `PD_ANALYZED`: ПТО проанализировал ПД.
- `SPEC_EXTRACTED`: ПТО извлек спецификацию.
- `COSTS_ESTIMATED`: Сметчик сформировал ЛСР.
- `CONTRACT_ANALYZED`: Юрист проверил договор по БЛС.
- `VENDORS_SOURCED`: Логист нашел поставщиков.
- `QUOTES_COMPARED`: Логист выбрал КП.
- `ARCHIVED`: Архив сохранил финальный пакет.
- `PROJECT_WON`: Тендер выигран, старт СМР.
- `DEADLINE_MISSED`: Просрочка (триггер для Юриста).

### 1.2. Переходы (Transitions)

| Откуда (Source) | Событие (Trigger) | Куда (Target) | Исполнитель |
|------------------|-------------------|---------------|-------------|
| `INIT`           | `asd_tender_search` | `TENDER_FOUND` | Закупщик |
| `TENDER_FOUND`   | `asd_upload_doc`  | `FILES_REGISTERED` | Архив |
| `FILES_REGISTERED`| `asd_pd_analysis` | `PD_ANALYZED` | ПТО |
| `PD_ANALYZED`    | `asd_vor_check`    | `SPEC_EXTRACTED` | ПТО |
| `SPEC_EXTRACTED` | `asd_create_lsr`   | `COSTS_ESTIMATED` | Сметчик |
| `COSTS_ESTIMATED`| `asd_analyze_contract` | `CONTRACT_ANALYZED` | Юрист |
| `CONTRACT_ANALYZED` | `asd_source_vendors` | `VENDORS_SOURCED` | Логист |
| `VENDORS_SOURCED`| `asd_compare_quotes` | `QUOTES_COMPARED` | Логист |
| `QUOTES_COMPARED`| `asd_prepare_shipment` | `ARCHIVED` | Архив |

---

## 2. Агент Логист: Детальная логика

Логист — самый сложный агент в плане взаимодействия с внешней средой.

### 2.1. Цикл работы Логиста (Inner Loop)

1. **Анализ спецификации:** Получает от ПТО список ТМЦ (напр. "Шпунт Л5-УМ, 150т").
2. **Поиск (Web Search):** Ищет актуальных поставщиков в регионе через `WebSearch` MCP.
3. **Формирование RFQ:** Генерирует PDF/Email запрос.
4. **Коммуникация:** Имитация или реальная отправка через инструменты интеграции (Email/Telegram).
5. **Сбор данных:** Ожидание входящих писем, парсинг КП через `asd_parse_price_list`.
6. **Сравнение:** Формирование сравнительной таблицы (Конкурентный лист).

---

## 3. База данных ТМЦ (Реляционная)

В `DATA_SCHEMA.md` добавлены таблицы:

- `materials_catalog`: мастер-данные (наименование, ед. изм).
- `vendors`: база проверенных поставщиков с рейтингом.
- `price_lists`: история цен для предиктивного анализа НМЦК.

---

## 4. OCR Стратегия (Mac Studio Fallback)

Как заметил USER, OCR будет уточняться.

- **Tier 1 (Base):** `pytesseract` для простых документов.
- **Tier 2 (Vision):** `Gemma 4 31B (Vision mode через LLMEngine)` через Ollama для сложных таблиц и печатей.
- **Tier 3 (Complex):** Специализированные Fine-tuned модели (если появятся через 2 месяца).

---

Документ актуализирован. Логика переходов реализована в EventManager и LangGraph StateGraph.
