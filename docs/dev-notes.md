# Dev Notes — MAC_ASD v13.0

## Последние обновления (4 мая 2026)

### Новые компоненты (с момента последнего обновления docs)

- **Auditor agent** (agents/auditor/config.yaml + prompt.md) — 8-й агент, rule-based (не LLM), RedTeam-аудит
- **NormativeGuard** — SSOT-валидация в legal_service.py, проверка документов через library/normative/normative_index.json
- **IDRequirementsRegistry** — реестр требований к ИД по 33 типам работ (config/id_requirements.yaml + src/core/services/id_requirements.py)
- **ConstructionElement** — модель БД: элементы строительства (ростверки, сваи, колонны, плиты)
- **ConstructionZone** — модель БД: строительные зоны (захватки, участки, этажи)
- **ElementDocument** — модель БД: связь документов с элементами строительства
- **WorkEntry** — модель БД + парсер + сервис (src/core/services/work_entry.py): записи журнала работ
- **MCP tools заполнены**: artifact_tools, legal_tools, vision_tools (были stubs, теперь реализованы)
- **Telegram ingest cron** — скрипт приёма WorkEntry через Telegram

### Текущий статус

- **Агенты**: 8 (PM, ПТО, Сметчик, Юрист, Закупщик, Логист, Делопроизводитель, Аудитор)
- **MCP инструментов**: 82+
- **БЛС**: 61 ловушка в 10 категориях
- **Библиотека**: 284 файла, 101 MB
- **Тесты**: 478/493 пройдено (97%)
- **Нормативная база**: normative_index.json в library/normative/
- **Виды работ**: 33 типа (IDRequirementsRegistry)

### Package 5 (завершён)
- Evidence Graph v2: граф связей документов с отслеживанием целостности комплекта ИД
- Inference Engine: механизм логического вывода на основе графа доказательств
- ProjectLoader: унифицированная загрузка проектных данных

### Package 11 (завершён)
- Chain Builder: цепочечная генерация АОСР по технологическим картам (ТТК)
- HITL System: сбор и валидация данных от оператора (human-in-the-loop)
- Journal Reconstructor v2: восстановление журналов работ по косвенным данным

### WorkEntry → AOSR Trigger Flow (новое)
- WorkEntryService парсит записи журнала → ConstructionElement → IDRequirementsRegistry → NormativeGuard → AOSR
- Telegram ingest cron для приёма записей

### DeepSeek API — временный backend для разработки
пока недоступно целевое железо:

| Компонент | Временное решение | Целевое решение |
|-----------|-------------------|-----------------|
| PM (оркестратор) | `deepseek-reasoner` (DeepSeek-R1) | Llama 3.3 70B 4-bit (MLX) |
| Агенты (ПТО, Юрист, Сметчик, Закупщик, Логист) | `deepseek-chat` (DeepSeek-V3) | Gemma 4 31B 4-bit (MLX-VLM) |
| Делопроизводитель | `deepseek-chat` (DeepSeek-V3) | Gemma 4 E4B 4-bit (MLX) |
| Embeddings | bge-m3 (Ollama) | bge-m3 (Ollama) — без изменений |
| Vision | Недоступен (тех.долг) | Gemma 4 31B (MLX-VLM) |

### Что нужно сделать после получения Mac Studio

1. Переключить профиль: `export ASD_PROFILE=mac_studio`
2. Удалить `DEEPSEEK_API_KEY` из `.env`
3. Реализовать `MLXBackend` (сейчас полный stub, 174 строки `NotImplementedError`)
4. Реализовать Vision для ПТО-агента (анализ чертежей)
5. Оценить — оставить ли DeepSeekBackend как fallback на случай проблем с MLX

### Почему DeepSeek, а не OpenAI/Claude

- OpenAI-совместимый API (стандарт де-факто)
- 128K контекст (как у целевой Gemma 4 31B)
- Низкая стоимость (~$0.14/1M input)
- Не зависит от санкционных ограничений
