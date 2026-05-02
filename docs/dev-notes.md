# Dev Notes — MAC_ASD v12.0

## DeepSeek API — временный backend для разработки

**Дата**: 2026-05-02
**Статус**: Активно (временно)

### Package 5 (завершён)
- Evidence Graph v2: граф связей документов с отслеживанием целостности комплекта ИД
- Inference Engine: механизм логического вывода на основе графа доказательств
- ProjectLoader: унифицированная загрузка проектных данных

### Package 11 (завершён)
- Chain Builder: цепочечная генерация АОСР по технологическим картам (ТТК)
- HITL System: сбор и валидация данных от оператора (human-in-the-loop)
- Journal Reconstructor v2: восстановление журналов работ по косвенным данным

### Библиотека
- Расширена до 271 файла, 101 MB
- Добавлены скрипты загрузки нормативов Meganorm

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
