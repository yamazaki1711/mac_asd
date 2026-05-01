# Dev Notes — MAC_ASD v12.0

## DeepSeek API — временный backend для разработки

**Дата**: 2026-05-01
**Статус**: Активно (временно)

DeepSeek API (`ASD_PROFILE=deepseek`) используется как мост на время разработки,
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
