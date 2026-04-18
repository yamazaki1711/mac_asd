# АСД v11.0 — ПЛАН РАЗВЁРТЫВАНИЯ

**Дата:** 17 апреля 2026
**Статус:** Активная разработка (Mac Studio ожидается)
**Цель:** Пошаговая инструкция по развертыванию ASD на Mac Studio M4 Max 128GB

---

## 1. ОБЗОР

Этот документ — чек-лист развёртывания АСД на Mac Studio M4 Max 128GB.
От распаковки до рабочего MCP сервера с 23 инструментами и 7 агентами.

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

### 3.3. Ollama

- [ ] Установить Ollama

  ```bash
  brew install ollama
  ```

- [ ] Запустить

  ```bash
  brew services start ollama
  ```

- [ ] Проверить

  ```bash
  ollama --version
  curl http://localhost:11434/api/tags
  # {"models":[]}
  ```

### 3.4. Tesseract OCR

- [ ] Установить Tesseract

  ```bash
  brew install tesseract
  ```

- [ ] Установить русские данные (если есть)

  ```bash
  brew install tesseract-lang
  ```

- [ ] Проверить

  ```bash
  tesseract --version
  # tesseract 5.x.x
  ```

---

## 4. ДЕНЬ 2: ЗАГРУЗКА МОДЕЛЕЙ

### 4.1. Модели (последовательно, ~29 GB суммарно)

- [ ] Gemma 4 31B FP16 (~62 GB download)

  ```bash
  ollama pull gemma-4-31b:fp16
  # Время загрузки: ~20-60 мин (зависит от интернета)
  ```

- [ ] Gemma 4 31B Q8_0 (~33 GB download, emergency fallback)

  ```bash
  ollama pull gemma-4-31b:q8_0
  ```

- [ ] Gemma 4 E4B Q4_K_M (~2.5 GB download)

  ```bash
  ollama pull gemma-4-e4b:q4_k_m
  ```

- [ ] bge-m3 (~2.2 GB download)

  ```bash
  ollama pull bge-m3
  ```

- [ ] minicpm-v Q4_K_M (~5 GB download)

  ```bash
  ollama pull minicpm-v:q4_k_m
  ```

### 4.2. Проверка моделей

- [ ] Список загруженных

  ```bash
  ollama list
  # NAME                    ID           SIZE
  # gemma-4-31b:fp16        xxxxxxx      62 GB
  # gemma-4-31b:q8_0        xxxxxxx      33 GB
  # gemma-4-e4b:q4_k_m      xxxxxxx      2.5 GB
  # bge-m3                  xxxxxxx      2.2 GB
  # minicpm-v:q4_k_m        xxxxxxx      5 GB
  ```

- [ ] Тест Gemma 4 31B FP16

  ```bash
  ollama run gemma-4-31b:fp16 "Привет! Как тебя зовут?"
  # Должен ответить на русском
  ```

- [ ] Тест Gemma 4 31B Q8_0 (fallback)

  ```bash
  ollama run gemma-4-31b:q8_0 "Привет! Как тебя зовут?"
  # Должен ответить на русском
  ```

- [ ] Тест embeddings

  ```bash
  curl http://localhost:11434/api/embeddings \
    -d '{"model":"bge-m3","prompt":"строительный договор"}'
  # Должен вернуть массив из 1024 чисел
  ```

- [ ] Тест vision

  ```bash
  curl http://localhost:11434/api/chat \
    -d '{
      "model": "minicpm-v:q4_k_m",
      "messages": [{"role":"user","content":"Что на этом изображении?","images":["base64..."]}]
    }'
  ```

---

## 5. ДЕНЬ 2: НАСТРОЙКА БАЗЫ ДАННЫХ

### 5.1. Создание БД

- [ ] Создать пользователя и базу

  ```bash
  sudo -u $(whoami) createuser --createdb asd_user
  sudo -u $(whoami) createdb -O asd_user asd_v11
  ```

- [ ] Подключиться

  ```bash
  psql -U asd_user -d asd_v11
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
  psql -U asd_user -d asd_v11 -f scripts/create_schema.sql
  ```

  Или через Alembic:

  ```bash
  cd /Users/oleg/MAC_ASD
  source venv/bin/activate
  alembic upgrade head
  ```

### 5.3. Загрузка БЛС

- [ ] Загрузить 27 ловушек из YAML
  ```bash
  python scripts/load_traps.py traps/default_traps.yaml
  ```
- [ ] Сидинг данных для Логиста (Поставщики, Каталог ТМЦ)
  ```bash
  python src/db/seed_logistics.py
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
  ```

### 6.3. Конфигурация

- [ ] Создать config/settings.py

  ```python
  # config/settings.py
  OLLAMA_URL = "http://localhost:11434"
  DB_HOST = "localhost"
  DB_PORT = 5432
  DB_NAME = "asd_v11"
  DB_USER = "asd_user"
  DB_PASSWORD = ""  # если нужен парольок
  ```

- [ ] Создать директории

  ```bash
  mkdir -p data/{raw,processed,exports,wiki,graphs}
  mkdir -p data/exports/{protocols,claims,lawsuits,acts,estimates,letters}
  mkdir -p data/templates
  ```

### 6.4. Шаблоны DOCX

- [ ] Создать шаблоны в data/templates/
  - [ ] protocol.docx
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

- [ ] Тест Ollama Client

  ```bash
  python -c "
  from src.core.ollama_client import OllamaClient
  client = OllamaClient()
  print('Ollama доступен:', client.is_available())
  print('Модели:', client.get_models())
  "
  ```

- [ ] Тест PostgreSQL

  ```bash
  python -c "
  import sqlalchemy as sa
  engine = sa.create_engine('postgresql://asd_user@localhost/asd_v11')
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

### 7.3. Подключение Hermes

- [ ] Настроить MCP в Hermes config

  ```yaml
  mcp_servers:
    asd:
      command: "/opt/homebrew/bin/python3.11"
      args: ["/Users/oleg/Projects/MAC_ASD/src/mcp_server.py"]
      env:
        ASD_OLLAMA_URL: "http://localhost:11434"
        ASD_DB_HOST: "localhost"
        ASD_DB_NAME: "asd_v11"
  ```

- [ ] Перезапустить Hermes

---

## 8. ДЕНЬ 3-4: E2E ТЕСТИРОВАНИЕ

### 8.1. Юрист

- [ ] Загрузить тестовый договор через MCP
- [ ] Запустить анализ
- [ ] Проверить ловушки
- [ ] Сгенерировать протокол
- [ ] Открыть DOCX, проверить содержимое

### 8.2. ПТО

- [ ] Загрузить тестовый ВОР
- [ ] Загрузить тестовую ПД
- [ ] Запустить сверку
- [ ] Проверить расхождения
- [ ] Сгенерировать АОСР

### 8.3. Сметчик

- [ ] Загрузить ВОР + смету
- [ ] Запустить сверку
- [ ] Создать ЛСР по ВОРу

### 8.4. Архив (Делопроизводитель)

- [ ] Зарегистрировать входящий документ
- [ ] Сгенерировать письмо
- [ ] Подготовить отправку

### 8.5. Закупщик и Логист

- [ ] Поиск поставщиков (asd_source_vendors)
- [ ] Парсинг прайс-листа
- [ ] Сравнение КП

### 8.5. Общий

- [ ] Проверить статус системы
- [ ] Проверить потребление памяти
- [ ] Проверить время ответов

---

## 9. ДЕНЬ 4-5: ОПТИМИЗАЦИЯ

### 9.1. Производительность

- [ ] Настроить num_gpu, num_thread в Modelfile
- [ ] Настроить параллелизм Map-Reduce
- [ ] Настроить батчинг embeddings
- [ ] Проверить время ответа каждого инструмента

### 9.2. Память

- [ ] Проверить RAM Budget при пиковой нагрузке
- [ ] Настроить пороги давления памяти
- [ ] Проверить fallback-цепочки

### 9.3. Автозапуск

- [ ] Создать launchd plist для Ollama
- [ ] Создать launchd plist для PostgreSQL
- [ ] Создать скрипт запуска MCP сервера

### 9.4. Резервное копирование

- [ ] Настроить бэкап PostgreSQL

  ```bash
  pg_dump -U asd_user asd_v11 > backup_$(date +%Y%m%d).sql
  ```

- [ ] Настроить бэкап файловой системы
- [ ] Настроить бэкап моделей Ollama

---

## 10. ДЕНЬ 5+: ПРОДУКТИВНАЯ ЭКСПЛУАТАЦИЯ

### 10.1. Мониторинг

- [ ] Настроить логирование
- [ ] Настроить алерты (память, ошибки)
- [ ] Создать dashboard статуса

### 10.2. Документация

- [ ] Обновить README проекта
- [ ] Создать пользовательскую инструкцию
- [ ] Создать troubleshooting guide

### 10.3. Обучение

- [ ] Показать зам. ген. директора как работать через Hermes
- [ ] Показать ПТО-инженеру как сверять ВОР
- [ ] Показать юристу как анализировать договоры

---

## 11. ЧЕК-ЛИСТ ГОТОВНОСТИ

### Минимум для работы

- [ ] Mac Studio включён, macOS настроен
- [ ] Homebrew установлен
- [ ] Python 3.11 установлен
- [ ] PostgreSQL 16 + pgvector запущен
- [ ] Ollama запущен
- [ ] **Gemma 4 31B FP16** загружена
- [ ] Gemma 4 31B Q8_0 загружена (emergency fallback)
- [ ] bge-m3 загружена
- [ ] Tesseract установлен
- [ ] Проект скопирован, venv создан
- [ ] MCP сервер запускается
- [ ] Hermes подключён

### Полная готовность

- [ ] Все модели загружены (FP16 31B, Q8_0 31B, E4B, bge-m3, minicpm-v)
- [ ] БД создана, схема применена
- [ ] БЛС загружена (27 ловушек)
- [ ] Шаблоны DOCX созданы
- [ ] Все 23 MCP инструмента работают
- [ ] E2E тесты пройдены (на 7 агентах)
- [ ] RAM Manager настроен (пороги: low 70%, medium 80%, high 90%)
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
psql -d asd_v11 -c "CREATE EXTENSION vector;"
```

### Модели не загружаются (медленный интернет)

```bash
# Продолжить загрузку — ollama resume
ollama pull gemma-4-31b:q8_0
# Если прервалось — просто запустить заново, продолжит с места
```

### OOM (Out Of Memory)

```bash
# Проверить потребление
ps aux | grep -i ollama
# Выгрузить неиспользуемые модели
ollama stop gemma-4-e4b:q4_k_m
```

### pytesseract не работает

```bash
brew reinstall tesseract
# Проверить
tesseract --list-langs
```

---

Документ актуализирован. При развертывании использовать переменную ASD_PROFILE=mac_studio и конфигурацию из .env.
