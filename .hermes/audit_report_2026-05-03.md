# MAC_ASD v12.0 — Аудит целостности

**Дата:** 3 мая 2026  
**Метод:** Deep Sweep + Goal Alignment (7 пассов)  
**Охват:** src/ (151 .py), tests/ (20 .py), mcp_servers/ (16 .py), config/, agents/, library/

---

## Сводка

| Pass | Результат | Находок |
|------|:---------:|---------|
| 1. Синтаксис | ✅ | 0 ошибок |
| 2. Stale refs | ✅ | 0 (только комментарии + pre-prod stub'ы) |
| 3. __init__.py | ✅ | 0 пропущенных |
| 3.5. Git-утечки | 🔴 | 4 файла |
| 4. AgentState | ⚠️ | Auditor пуст |
| 5. Workflow | ✅ | 8/8 агентов |
| 6. MCP tools | ⚠️ | 3 файла-заглушки (0 функций) |
| 7. Resource mgr | ✅ | RAM Manager интегрирован |

**Итог:** 481 тест, 478 прошли, 15 пропущены. Проект функционально целостен.

---

## 🔴 Критические несоответствия

### 1. `data/templates/` — неверный путь в манифесте
**Файл:** `asd_manifest.yaml` — `templates_path: data/templates/`  
**Реальность:** `data/templates/` **не существует**. Шаблоны лежат в `library/templates/` (251 файл, 7.7 MB).  
**Риск:** любой код, читающий `templates_path` из манифеста, упадёт.  
**Исправление:** `templates_path: library/templates/`

### 2. Заголовок БЛС устарел
**Файл:** `traps/default_traps.yaml`, строка 3: «58 ловушек»  
**Реальность:** 61 ловушка (58 именованных + 3 BA-*). Категории `acceptance` (8, не 7) и `subcontractor` (6, не 5).  
**Исправление:** обновить числа в заголовке и категориях.

### 3. `library/` — расхождение числа файлов
**README:** 271 файл  
**Реальность:** 283 файла (+12).  
**Исправление:** обновить README.

### 4. Утечка сгенерированных PDF в git
**Файлы:** `data/forensic_61.17.pdf`, `data/inventory_61.17.pdf`, `data/inventory_LOS.pdf`, `data/inventory_LOS_v2.pdf`  
Отслеживаются git'ом, но должны быть в `.gitignore`.  
**Исправление:** добавить маску `inventory_*.pdf` и `forensic_*.pdf` в `.gitignore`, `git rm --cached`.

---

## 🟡 Значительные несоответствия

### 5. Агент Auditor — пустая директория
`agents/auditor/` существует, но **нет** `config.yaml` и `prompt.md`.  
**README** говорит «8 agents (incl. Auditor)», но `agents.md` и `asd_manifest.yaml` — «7 agents». Auditor как RedTeam упоминается в `agents.md` вне таблицы.

### 6. `artifact_tools.py`, `legal_tools.py`, `vision_tools.py` — нулевые заглушки
3 MCP-файла с 0 `async def`. Задокументированы как «not_implemented, deferred to MLX».  
Не блокирует работу, но 74 total tools ≠ 66 реальных.  
**Исправление:** убрать из подсчёта в README или заменить заглушки реальными функциями (legal/vision — уже частично покрыты в `jurist_tools.py`/`pto_tools.py`).

### 7. LOC: заявлено 42K, реально ~58K Python
**README:** «42,000 строк»  
**Реальность:** 57,808 строк Python в src/ + tests/ + mcp_servers/ (45,758 + 8,431 + 3,619).  
**Исправление:** обновить README.

### 8. Telegram-каналы: 0 для smeta/logistics/procurement
`config/telegram_channels.yaml` — 19 каналов (18 legal + 1 pto).  
Smeta, logistics, procurement — пустые секции. Олег сообщил, что список был отобран ранее, но утерян.

---

## 🟢 Мелкие несоответствия

### 9. `config/config.yaml` и `config/settings.py` — отсутствуют
Не импортируются кодом. Конфигурация через `asd_manifest.yaml` + `telegram_channels.yaml` + `.env.example`.  
**Риск:** нулевой. Но упоминаются в плане развёртывания.  
**Исправление:** удалить упоминания из документации, если не планируются.

### 10. Trap-категории: 32 инструмента в manifest tool_groups
Манифест перечисляет 32 из 66 реальных MCP-инструментов — неполный список.

### 11. `datetime.utcnow()` deprecation
`src/core/pm_agent.py:1008` — использует устаревший `datetime.utcnow()`.  
484 warnings в тестах.  
**Исправление:** `datetime.now(datetime.UTC)`.

---

## Что НЕ является проблемой

- **MLX-заглушки** (`mlx_backend.py` — 6× NotImplementedError) — ожидаемо до Mac Studio
- **PPR graphics (5× placeholder)** — v0.1, явно документировано
- **PaddleOCR в комментарии** — не код, историческая справка
- **Неимпортируемые модули** — 0, все импорты разрешаются
- **Циклические зависимости** — не обнаружены
- **Битые тесты** — 0 (478/478 passed)

---

## Аудит: выполненные и отложенные обещания (с точки зрения целостности)

| Обещание (README/manifest) | Статус |
|---|---|
| 7 агентов (pm, pto, smeta, legal, logistics, procurement, delo) | ✅ Все имеют config.yaml + prompt.md |
| Auditor / RedTeam | ⚠️ Пустая директория |
| 66+ MCP tools | ✅ 66 реальных (+ 8 серверных = 74 total) |
| 493 теста (478 passed) | ✅ Совпадает |
| Evidence Graph v2 (7 типов узлов) | ✅ `evidence_graph.py` |
| Chain Builder, HITL, Inference Engine | ✅ Package 11 |
| Journal Reconstructor v2 | ✅ |
| ProjectLoader (нулевой слой) | ✅ |
| VLM fallback (Gemma 4 31B Cloud) | ✅ Протестирован на ЛОС (12 PDF, 0 UNKNOWN) |
| Google Workspace integration | ✅ OAuth токены, Service Account |
| БЛС: 27 → 58 → 61 ловушка | ✅ Растёт (README устарел на 3) |
| library/ — нормативка + шаблоны | ✅ 283 файла, 101 MB |
| Telegram-каналы для БЛС | ⚠️ 19 каналов (legal+pto), 0 smeta/logistics/procurement |
| Инжест Telegram → БЛС через cron | ❌ Не настроен (пустая `data/telegram_exports/`) |
| DOCX-генерация (АОСР, КС-2, КС-3) | ✅ `output_pipeline.py` |
| PPR Generator | ⚠️ v0.1, graphics — placeholder'ы |
| IS Generator (исполнительные схемы) | ✅ 50+ tolerance profiles |
