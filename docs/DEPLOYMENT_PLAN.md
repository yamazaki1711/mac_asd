# АСД v12.0 — ПЛАН РАЗВЁРТЫВАНИЯ

| **Дата:** 3 мая 2026
| **Статус:** Активная разработка (Package 1, 5, 11 завершены, Auditor ✅, IDRequirementsRegistry ✅, NormativeGuard ✅, WorkEntry ✅, Mac Studio M4 Max 128GB)
**Цель:** Пошаговая инструкция по развертыванию ASD на Mac Studio M4 Max 128GB

---

## 1. ОБЗОР

Этот документ — чек-лист развёртывания АСД v12.0 на Mac Studio M4 Max 128GB. От распаковки до рабочего MCP сервера с 23 инструментами и 7 агентами. Ключевое отличие v12.0: пять рабочих агентов (Юрист, ПТО, Сметчик, Закупщик, Логист) работают через модель **Gemma 4 31B 4-bit** (MLX-VLM, 128K контекст) с разделяемой памятью, Делопроизводитель использует **Gemma 4 E4B 4-bit** (~3GB, 8K контекст), а **Руководитель проекта (PM)** использует **Llama 3.3 70B 4-bit**. Gemma 4 31B имеет встроенную vision-поддержку (MLX-VLM), что устраняет необходимость в отдельной OCR-модели.

### Бюджет памяти (пересчитан)

| Компонент | RAM (GB) | Примечание |
|-----------|----------|------------|
| Gemma 4 31B 4-bit | 23.0 | Рабочая модель (ПТО/Юрист/Сметчик/Закупщик/Логист, shared, MLX-VLM, 128K контекст) |
| Llama 3.3 70B 4-bit | 40.0 | Руководитель проекта (PM), загружается при запуске, 128K контекст |
| Gemma 4 E4B 4-bit | 3.0 | Делопроизводитель (Архив/Дело), 8K контекст |
| bge-m3-mlx-4bit | 0.3 | Embeddings (MLX), постоянно в памяти |
| **Итого модели** | **~66** | При полной загрузке |
| macOS + системные | 8.0 | OS, окна, демоны |
| PostgreSQL 16 | 2.0 | БД + pgvector |
| MLX runtime | 6.0 | Inference overhead |
| Python (MCP + LightRAG) | 4.0 | Процессы АСД |
| **Итого система** | **~20** | Базовое потребление |
| **ВСЕГО базовое** | **~86** | При полной загрузке всех моделей |
| **Доступно для контекста** | **~42** | 128 - 86 = 42 GB |

> **Важно:** Gemma 4 31B (MLX-VLM) имеет контекст 128K токенов — большинство договоров помещаются целиком без Map-Reduce. При предыдущей архитектуре (Qwen3.5-27B с 32K контекстом) требовался Map-Reduce для документов ≥6K символов. Переход на Gemma 4 31B с 128K контекстом кардинально упрощает анализ: Quick Review становится основным режимом.

---

## 2. ДЕНЬ 1: РАСПАКОВКА И БАЗОВАЯ НАСТРОЙКА

### 2.1. Распаковка и включение

- [ ] Распаковать Mac Studio
- [ ] Подключить питание, монитор, клавиатуру, сеть
- [ ] Включить
- [ ] Пройти первичную настройку macOS

### 2.2. Системные настройки

- [ ] macOS обновить до последней версии

  ```
  Системные настройки → Основные → Обновление ПО
  ```

- [ ] Включить общий доступ → Удалённое управление (для SSH)

  ```
  Системные настройки → Основные → Общий доступ → Удалённый вход
  ```

- [ ] Настроить энергосбережение (не спать!)

  ```
  Системные настройки → Энергосбережение →
  ☑ Предотвращать автоматический переход в режим сна
  ```

- [ ] Проверить объём памяти

  ```
   → Об этом Mac → Память: 128 GB
  ```

- [ ] Установить Xcode Command Line Tools

  ```bash
  xcode-select --install
  ```

### 2.3. Homebrew

- [ ] Установить Homebrew

  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

- [ ] Добавить в PATH

  ```bash
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
  source ~/.zshrc
  ```

- [ ] Проверить

  ```bash
  brew --version
  # Homebrew 4.x.x
  ```

---

## 3. ДЕНЬ 1-2: УСТАНОВКА ЗАВИСИМОСТЕЙ

### 3.1. Python

- [ ] Установить Python 3.11+

  ```bash
  brew install python@3.11
  ```

- [ ] Проверить

  ```bash
  python3.11 --version
  # Python 3.11.x
  which python3.11
  # /opt/homebrew/bin/python3.11
  ```

### 3.2. PostgreSQL

- [ ] Установить PostgreSQL 16

  ```bash
  brew install postgresql@16
  ```

- [ ] Установить pgvector

  ```bash
  brew install pgvector
  ```

- [ ] Запустить

  ```bash
  brew services start postgresql@16
  ```

- [ ] Проверить

  ```bash
  psql --version
  # psql (PostgreSQL) 16.x
  brew services list | grep postgresql
  # postgresql@16 started
  ```

### 3.3. Ollama (опционально)

Ollama больше не требуется для основной работы АСД v12.0 — все модели работают через MLX. Устанавливайте только если нужна совместимость с другими инструментами.

- [ ] Установить Ollama (опционально)

  ```bash
  brew install ollama
  ```

  Если устанавливаете:

  ```bash
  brew services start ollama
  ```

### 3.4. Tesseract OCR

- [ ] Установить Tesseract

  ```bash
  brew install tesseract
  ```

- [ ] Установить русские данные

  ```bash
  brew install tesseract-lang
  ```

- [ ] Проверить

  ```bash
  tesseract --version
  # tesseract 5.x.x
  ```

### 3.5. ReportLab и шрифты (PDF v3)

- [ ] Установить ReportLab (входит в requirements.txt)

  ```bash
  # Будет установлен в venv (шаг 6.2)
  pip install reportlab
  ```

- [ ] Скачать TrueType-шрифты для корректного отображения кириллицы

  ```bash
  mkdir -p /Users/oleg/MAC_ASD/data/fonts
  # Скопировать TTF-шрифты (Liberation Sans, DejaVu Sans, или системные SF Pro)
  # PDF v3 использует чистый ReportLab + TrueType, без LaTeX
  ```

---

## 4. ДЕНЬ 2: ЗАГРУЗКА МОДЕЛЕЙ

### 4.1. Модели MLX (embeddings + Дело)

Embeddings модель bge-m3-mlx-4bit и модель Делопроизводителя (Gemma 4 E4B) работают через MLX. Ollama больше не требуется — все модели используют MLX inference.

- [ ] bge-m3-mlx-4bit (~0.3 GB download, embeddings)

  ```bash
  python -m mlx_lm.download --model bge-m3-mlx-4bit
  # Или скопировать в ~/models/bge-m3-mlx-4bit/
  # Время загрузки: ~1-2 мин
  ```

- [ ] Gemma 4 E4B 4-bit (~3 GB download, Делопроизводитель)

  ```bash
  python -m mlx_lm.download --model google/gemma-4-e4b --quantize --bits 4
  # Или
  huggingface-cli download google/gemma-4-e4b-4bit --local-dir ~/models/gemma4-e4b-4bit
  # Время загрузки: ~5-10 мин
  ```

### 4.2. Модели MLX (LLM inference)

MLX обеспечивает нативную производительность на Apple Silicon с полной утилизацией Neural Engine и GPU. Модели загружаются через mlx-lm или напрямую из HuggingFace.

- [ ] Gemma 4 31B 4-bit (~23 GB download, ПТО/Юрист/Сметчик/Закупщик/Логист, MLX-VLM)

  ```bash
  # Через mlx-lm
  pip install mlx-lm
  python -m mlx_lm.download --model google/gemma-4-31b --quantize --bits 4
  # Или через huggingface-cli
  huggingface-cli download google/gemma-4-31b-4bit --local-dir ~/models/gemma4-31b-4bit
  # Время загрузки: ~15-45 мин (зависит от интернета)
  ```

- [ ] Llama 3.3 70B 4-bit (~40 GB download, Руководитель проекта PM)

  ```bash
  python -m mlx_lm.download --model meta-llama/Llama-3.3-70B --quantize --bits 4
  # Или
  huggingface-cli download meta-llama/Llama-3.3-70B-4bit --local-dir ~/models/llama-3.3-70b-4bit
  # Время загрузки: ~30-90 мин
  ```

- [ ] Gemma 4 31B MLX-VLM (vision capabilities встроены в основную модель)

  ```bash
  # Gemma 4 31B (MLX-VLM) поддерживает vision natively — отдельная vision-модель не нужна
  # Vision OCR выполняется через основную модель Gemma 4 31B
  ```

### 4.3. Проверка моделей

- [ ] Список MLX-моделей

  ```bash
  ls ~/models/
  # gemma4-31b-4bit/
  # llama-3.3-70b-4bit/
  # gemma4-e4b-4bit/
  # bge-m3-mlx-4bit/
  ```

- [ ] Тест Gemma 4 31B (основная рабочая модель)

  ```bash
  python -m mlx_lm.generate --model ~/models/gemma4-31b-4bit --prompt "Привет! Как тебя зовут?" --max-tokens 50
  # Должен ответить на русском
  ```

- [ ] Тест Gemma 4 E4B (Делопроизводитель)

  ```bash
  python -m mlx_lm.generate --model ~/models/gemma4-e4b-4bit --prompt "Привет!" --max-tokens 50
  ```

- [ ] Тест Llama 3.3 70B (Руководитель проекта PM)

  ```bash
  python -m mlx_lm.generate --model ~/models/llama-3.3-70b-4bit --prompt "Привет! Как тебя зовут?" --max-tokens 50
  # Должен ответить на русском
  ```

- [ ] Тест embeddings (bge-m3-mlx-4bit)

  ```bash
  python -c "
  from src.core.embedding_engine import EmbeddingEngine
  engine = EmbeddingEngine()
  emb = engine.get_embeddings('строительный подряд')
  print('Embeddings размерность:', len(emb))
  # Ожидание: 1024
  "
  ```

- [ ] Тест vision (Gemma 4 31B MLX-VLM)

  ```bash
  python -c "
  from src.core.llm_engine import LLMEngine
  engine = LLMEngine()
  result = engine.chat_vision('gemma4-31b', 'Что на этом изображении?', image_path='test_scan.png')
  print('Vision ответ:', result[:200])
  "
  ```

---

## 5. ДЕНЬ 2: НАСТРОЙКА БАЗЫ ДАННЫХ

### 5.1. Создание БД

- [ ] Создать пользователя и базу

  ```bash
  sudo -u $(whoami) createuser --createdb asd_user
  sudo -u $(whoami) createdb -O asd_user asd_v12
  ```

- [ ] Подключиться

  ```bash
  psql -U asd_user -d asd_v12
  ```

- [ ] Включить расширения

  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

  -- Проверить
  \dx
  -- vector | 0.7.x | ...
  -- pg_trgm | 1.6 | ...
  ```

### 5.2. Создание схемы

- [ ] Создать таблицы (по DATA_SCHEMA.md)

  ```bash
  psql -U asd_user -d asd_v12 -f scripts/create_schema.sql
  ```

  Или через Alembic:

  ```bash
  cd /Users/oleg/MAC_ASD
  source venv/bin/activate
  alembic upgrade head
  ```

### 5.3. Загрузка БЛС

- [ ] Загрузить 61 ловушка из YAML (10 категорий)
  ```bash
  python scripts/load_traps.py traps/default_traps.yaml
  # Ожидаемый вывод: "Загружено 61 ловушка БЛС (10 категорий)"
  ```

- [ ] Загрузить нормативный индекс (SSOT)
  ```bash
  # normative_index.json — SSOT для NormativeGuard
  # Находится в library/normative/normative_index.json
  python scripts/load_normative_index.py library/normative/normative_index.json
  ```

- [ ] Загрузить реестр требований ИД
  ```bash
  # id_requirements.yaml — 33 типа работ с требованиями к документам
  python scripts/load_id_requirements.py config/id_requirements.yaml
  ```

- [ ] Сидинг данных для Логиста (Поставщики, Каталог ТМЦ)
  ```bash
  # seed_logistics удалён — данные загружаются через Procurement Agent
  ```

---

## 6. ДЕНЬ 3: НАСТРОЙКА ПРОЕКТА

### 6.1. Клонирование / копирование проекта

- [ ] Создать директорию

  ```bash
  mkdir -p ~/Projects/MAC_ASD
  cd ~/Projects/MAC_ASD
  ```

- [ ] Склонировать или скопировать файлы проекта

### 6.2. Виртуальное окружение

- [ ] Создать venv

  ```bash
  python3.11 -m venv venv
  source venv/bin/activate
  ```

- [ ] Установить зависимости

  ```bash
  pip install -r requirements.txt
  # Включает: reportlab, python-docx, sqlalchemy, alembic, pgvector,
  # lightrag-hku, networkx, pytesseract, mlx-lm, ollama
  ```

### 6.3. Конфигурация

- [ ] Создать config/settings.py

  ```python
  # config/settings.py
  ASD_VERSION = "12.0.0"
  ASD_PROFILE = "mac_studio"

  # LLM Models
  PRIMARY_MODEL = "gemma4-31b"       # ПТО/Юрист/Сметчик/Закупщик/Логист (MLX-VLM, 128K)
  DELO_MODEL = "gemma4-e4b"           # Делопроизводитель (8K)
  PM_MODEL = "llama-3.3-70b"          # Руководитель проекта (PM, 128K)
  EMBEDDING_MODEL = "bge-m3-mlx-4bit" # Embeddings (MLX)

  # Ollama
  OLLAMA_URL = "http://localhost:11434"

  # MLX
  MLX_MODELS_DIR = "~/models"

  # Database
  DB_HOST = "localhost"
  DB_PORT = 5432
  DB_NAME = "asd_v12"
  DB_USER = "asd_user"
  DB_PASSWORD = ""

  # Memory thresholds
  RAM_LOW_THRESHOLD = 0.70
  RAM_MEDIUM_THRESHOLD = 0.80
  RAM_HIGH_THRESHOLD = 0.90

  # Map-Reduce
  MAP_REDUCE_CHUNK_SIZE = 12000  # символов (20% overlap)
  MAP_REDUCE_MAX_CHUNKS = 20

  # PDF v3
  PDF_ENGINE = "reportlab"
  PDF_FONTS_DIR = "data/fonts"
  ```

- [ ] Создать директории

  ```bash
  mkdir -p data/{raw,processed,exports,wiki,graphs,fonts}
  mkdir -p data/exports/{protocols,claims,lawsuits,acts,estimates,letters}
  mkdir -p data/templates
  ```

### 6.4. Шаблоны DOCX

- [ ] Создать шаблоны в data/templates/
  - [ ] protocol.docx (включает блок ProtocolPartyInfo)
  - [ ] claim.docx
  - [ ] lawsuit.docx
  - [ ] aosr.docx
  - [ ] incoming_control.docx
  - [ ] hidden_works.docx
  - [ ] letter.docx
  - [ ] cover_letter.docx
  - [ ] shipment_registry.docx

---

## 7. ДЕНЬ 3: ПЕРВЫЙ ЗАПУСК

### 7.1. Тест компонентов

- [ ] Тест LLMEngine (Gemma 4 31B + Llama 3.3 70B)

  ```bash
  python -c "
  from src.core.llm_engine import LLMEngine
  engine = LLMEngine()
  print('Gemma 4 31B доступна:', engine.is_available('gemma4-31b'))
  print('Llama 3.3 70B доступна:', engine.is_available('llama-3.3-70b'))
  print('Shared memory:', engine.shared_memory_enabled)
  result = engine.chat('gemma4-31b', 'Тест: назови 3 статьи ГК РФ о строительстве')
  print('Ответ Gemma 4 31B:', result[:100])
  "
  ```

- [ ] Тест PostgreSQL

  ```bash
  python -c "
  import sqlalchemy as sa
  engine = sa.create_engine('postgresql://asd_user@localhost/asd_v12')
  with engine.connect() as conn:
      result = conn.execute(sa.text('SELECT 1'))
      print('PostgreSQL подключён:', result.scalar())
  "
  ```

- [ ] Тест RAM Manager

  ```bash
  python -c "
  from src.core.ram_manager import RAMManager
  rm = RAMManager()
  print('Всего:', rm.get_total_memory_gb(), 'GB')
  print('Использовано:', rm.get_used_memory_gb(), 'GB')
  print('Давление:', rm.get_memory_pressure())
  print('Доступно для контекста:', rm.get_available_for_context_gb(), 'GB')
  # Ожидание: ~42 GB при загруженных моделях
  "
  ```

- [ ] Тест Embeddings (bge-m3-mlx-4bit)

  ```bash
  python -c "
  from src.core.embedding_engine import EmbeddingEngine
  engine = EmbeddingEngine()
  emb = engine.get_embeddings('строительный подряд')
  print('Embeddings размерность:', len(emb))
  # Ожидание: 1024
  "
  ```

### 7.2. Запуск MCP сервера

- [ ] Тест в HTTP mode

  ```bash
  python src/mcp_server.py --http --port 8001
  ```

  В другом терминале:

  ```bash
  curl http://localhost:8001/mcp
  ```

- [ ] Тест в stdio mode

  ```bash
  python src/mcp_server.py
  # Должен ждать ввод на stdin
  # Ctrl+C для выхода
  ```

- [ ] Тест asd_get_system_status

  ```bash
  # Через MCP клиент
  python -c "
  from src.mcp_client import MCPClient
  client = MCPClient()
  status = client.call('asd_get_system_status')
  print(status)
  # Ожидание: primary_model=gemma4-31b, pm_model=llama-3.3-70b
  "
  ```

### 7.3. Подключение Руководитель проекта

- [ ] Настроить MCP в Руководитель проекта config

  ```yaml
  mcp_servers:
    asd:
      command: "/opt/homebrew/bin/python3.11"
      args: ["/Users/oleg/Projects/MAC_ASD/src/mcp_server.py"]
      env:
        ASD_OLLAMA_URL: "http://localhost:11434"
        ASD_DB_HOST: "localhost"
        ASD_DB_NAME: "asd_v12"
        ASD_PROFILE: "mac_studio"
        ASD_PRIMARY_MODEL: "gemma4-31b"
        ASD_PM_MODEL: "llama-3.3-70b"
  ```

- [ ] Перезапустить Руководитель проекта

---

## 8. ДЕНЬ 3-4: E2E ТЕСТИРОВАНИЕ

### 8.1. Юрист

- [ ] Загрузить тестовый договор через MCP
- [ ] Запустить анализ (quick review <6K символов)
- [ ] Запустить анализ (map-reduce ≥6K символов)
- [ ] Проверить все 61 ловушка БЛС (10 категорий)
- [ ] Сгенерировать протокол с ProtocolPartyInfo
- [ ] Открыть DOCX, проверить реквизиты сторон
- [ ] Сгенерировать претензию
- [ ] Сгенерировать иск

### 8.2. ПТО

- [ ] Загрузить тестовый ВОР
- [ ] Загрузить тестовую ПД
- [ ] Запустить сверку (asd_vor_check)
- [ ] Проверить расхождения
- [ ] Сгенерировать АОСР
- [ ] Проверить комплектность ИД (asd_id_completeness)

### 8.3. Сметчик

- [ ] Загрузить ВОР + смету
- [ ] Запустить сверку (asd_estimate_compare)
- [ ] Создать ЛСР по ВОРу (asd_create_lsr)
- [ ] Осметить допсоглашение (asd_supplement_estimate)

### 8.4. Архив (Делопроизводитель)

- [ ] Зарегистрировать входящий документ
- [ ] Сгенерировать письмо с реквизитами ProtocolPartyInfo
- [ ] Подготовить отправку (asd_prepare_shipment)
- [ ] Проверить отслеживание дедлайнов

### 8.5. Закупщик и Логист

- [ ] Поиск поставщиков (asd_source_vendors)
- [ ] Поиск тендеров (asd_tender_search)
- [ ] Анализ рентабельности (asd_analyze_lot_profitability)
- [ ] Парсинг прайс-листа (asd_parse_price_list)
- [ ] Сравнение КП (asd_compare_quotes)

### 8.6. Общий

- [ ] Проверить статус системы (asd_get_system_status)
- [ ] Проверить потребление памяти (ожидание: ~86 GB при полной загрузке)
- [ ] Проверить доступно для контекста (~42 GB)
- [ ] Проверить время ответов каждого инструмента

---

## 9. ДЕНЬ 4-5: ОПТИМИЗАЦИЯ

### 9.1. Производительность

- [ ] Настроить параметры MLX inference (batch_size, cache_size)
- [ ] Настроить параллелизм Map-Reduce (количество чанков, concurrent map)
- [ ] Настроить батчинг embeddings (bge-m3 batch size)
- [ ] Проверить время ответа каждого инструмента
- [ ] Оптимизировать on-demand загрузку Gemma 4 31B VLM (время холодного старта)

### 9.2. Память

- [ ] Проверить RAM Budget при пиковой нагрузке (все модели + контекст)
  - Ожидание: ~86 GB базовое + контекст
  - Доступно для контекста: ~42 GB
- [ ] Настроить пороги давления памяти (low 70%, medium 80%, high 90%)
- [ ] Проверить fallback-цепочки:
  - При MEMORY_CRITICAL: выгрузить Gemma 4 E4B (если загружена), приостановить некритичные задачи
  - При MEMORY_HIGH: отключить map-reduce, перейти на quick review
- [ ] Проверить shared memory Gemma 4 31B между агентами (ПТО/Юрист/Сметчик/Закупщик/Логист)

### 9.3. PDF v3 (ReportLab)

- [ ] Проверить генерацию PDF через чистый ReportLab + TrueType
- [ ] Убедиться в корректном отображении кириллицы
- [ ] Протестировать генерацию протоколов, претензий, исков
- [ ] Сравнить качество с предыдущим PDF-движком

### 9.4. Автозапуск

- [ ] Создать launchd plist для PostgreSQL
- [ ] Создать скрипт запуска MCP сервера

### 9.5. Резервное копирование

- [ ] Настроить бэкап PostgreSQL

  ```bash
  pg_dump -U asd_user asd_v12 > backup_$(date +%Y%m%d).sql
  ```

- [ ] Настроить бэкап файловой системы
- [ ] Настроить бэкап MLX-моделей

---

## 10. ДЕНЬ 5+: ПРОДУКТИВНАЯ ЭКСПЛУАТАЦИЯ

### 10.1. Мониторинг

- [ ] Настроить логирование (структурированные логи в JSON)
- [ ] Настроить алерты (память >80%, ошибки LLM, просроченные дедлайны)
- [ ] Создать dashboard статуса (через asd_get_system_status)

### 10.2. Документация

- [ ] Обновить README проекта
- [ ] Создать пользовательскую инструкцию
- [ ] Создать troubleshooting guide

### 10.3. Обучение

- [ ] Показать зам. ген. директора как работать через Руководитель проекта
- [ ] Показать ПТО-инженеру как сверять ВОР
- [ ] Показать юристу как анализировать договоры и генерировать протоколы с реквизитами

---

## 11. ЧЕК-ЛИСТ ГОТОВНОСТИ

### Минимум для работы

- [ ] Mac Studio включён, macOS настроен
- [ ] Homebrew установлен
- [ ] Python 3.11 установлен
- [ ] PostgreSQL 16 + pgvector запущен
- [ ] **Gemma 4 31B 4-bit** загружена (ПТО/Юрист/Сметчик/Закупщик/Логист через shared memory)
- [ ] **Gemma 4 E4B 4-bit** загружена (Делопроизводитель)
- [ ] **Llama 3.3 70B 4-bit** загружена (Руководитель проекта PM)
- [ ] bge-m3-mlx-4bit загружена (embeddings)
- [ ] Tesseract установлен
- [ ] TrueType-шрифты установлены (для PDF v3)
- [ ] GOST PDF шрифты настроены (GOST type A/B, `data/fonts/gost/`)
- [ ] Нормативный индекс загружен (`library/normative/normative_index.json`) — NormativeGuard SSOT
- [ ] Реестр требований ИД загружен (`config/id_requirements.yaml`) — 33 типа работ
- [ ] Скрипты загрузки Meganorm развёрнуты (`scripts/meganorm/download.sh`)
- [ ] Проект скопирован, venv создан
- [ ] MCP сервер запускается
- [ ] Руководитель проекта подключён

### Полная готовность

- [ ] Все модели загружены (Gemma 4 31B, Gemma 4 E4B, Llama 3.3 70B, bge-m3-mlx-4bit)
- [ ] БД создана, схема применена
- [ ] БЛС загружена (61 ловушка в 10 категориях)
- [ ] Шаблоны DOCX созданы (с блоком ProtocolPartyInfo)
- [ ] Все 23 MCP инструмента работают
- [ ] E2E тесты пройдены (на 7 агентах)
- [ ] RAM Manager настроен (пороги: low 70%, medium 80%, high 90%)
- [ ] Доступно для контекста: ~42 GB (подтверждено)
- [ ] Автозапуск настроен
- [ ] Бэкапы настроены
- [ ] Пользователи обучены

---

## 12. ВОЗМОЖНЫЕ ПРОБЛЕМЫ И РЕШЕНИЯ

### Ollama не запускается

```bash
brew services restart ollama
tail -f /opt/homebrew/var/log/ollama.log
```

### PostgreSQL не принимает подключения

```bash
brew services restart postgresql@16
# Проверить pg_hba.conf — разрешены ли локальные подключения
```

### pgvector не установлен

```bash
brew reinstall pgvector
psql -d asd_v12 -c "CREATE EXTENSION vector;"
```

### Модели MLX не загружаются (медленный интернет)

```bash
# Продолжить загрузку — huggingface-cli поддерживает resume
huggingface-cli download google/gemma-4-31b-4bit --local-dir ~/models/gemma4-31b-4bit
# Если прервалось — просто запустить заново, продолжит с места
```

### OOM (Out Of Memory)

```bash
# Проверить потребление
ps aux | rg -i "ollama|mlx|python"
# Выгрузить Gemma 4 E4B (если загружена и не нужна)
# Модели MLX выгружаются автоматически при нехватке памяти
# Проверить доступную память
python -c "from src.core.ram_manager import RAMManager; rm = RAMManager(); print(rm.get_available_for_context_gb(), 'GB available')"
# Ожидание: ~42 GB при нормальной нагрузке
```

### Gemma 4 31B не отвечает через LLMEngine

```bash
# Проверить, загружена ли модель
python -c "from src.core.llm_engine import LLMEngine; e = LLMEngine(); print(e.is_available('gemma4-31b'))"
# Перезапустить MLX inference
pkill -f mlx_lm
# Проверить логи
tail -f logs/asd_llm.log
```

### pytesseract не работает

```bash
brew reinstall tesseract
# Проверить
tesseract --list-langs
# Должен включать 'rus'
```

### PDF v3: кириллица отображается некорректно

```bash
# Проверить наличие TrueType-шрифтов
ls data/fonts/
# Должны быть: DejaVuSans.ttf, DejaVuSans-Bold.ttf (или аналоги)
# Проверить конфигурацию
python -c "from config.settings import PDF_FONTS_DIR; print(PDF_FONTS_DIR)"
```

### Shared memory Gemma 4 31B не работает

```bash
# Проверить, что LLMEngine использует разделяемую память
python -c "from src.core.llm_engine import LLMEngine; e = LLMEngine(); print('Shared:', e.shared_memory_enabled)"
# Если False — проверить конфигурацию ASD_PROFILE=mac_studio
```

---

Документ актуализирован для АСД v12.0 (20 апреля 2026). При развертывании использовать переменную ASD_PROFILE=mac_studio и конфигурацию из .env. Основная модель — Gemma 4 31B 4-bit (все агенты), PM — Llama 3.3 70B 4-bit (Руководитель проекта).
