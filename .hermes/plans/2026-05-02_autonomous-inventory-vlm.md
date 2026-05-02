# План: Автономная инвентаризация ASD со VLM-анализом сканов

**Цель**: Довести ASD до способности самостоятельной инвентаризации (метризации) папок со сканированными документами без ручного вмешательства. Сейчас keyword-классификатор выдаёт 67% ошибок на сканах (8/12 в ЛОС).

**Дата**: 02.05.2026  
**Контекст**: папка ЛОС (12 PDF, 9 сканов) — ручной VLM-анализ через Hermes занял ~6 мин. ASD должен делать это сам.

---

## Текущее состояние (что сломано)

```
scan_folder() → pdftotext (1-2 зн. для сканов) → DocumentClassifier(keyword) → UNKNOWN (67%)
```

8 из 12 файлов ЛОС — невидимы для классификатора. Сертификаты внутри PDF (как встроенные ссылки) не детектируются.

## Целевое состояние

```
scan_folder() → pdftotext → ScanDetector →
  ├─ текст (≥100 зн.): keyword-классификатор → ingest
  └─ скан (<100 зн. + >200KB): pdftoppm → VLM-классификатор (Gemma 4 31B) → ingest
→ ingest_to_graph → get_inventory_report → generate_inventory_pdf
```

---

## Шаг 1: Модуль детекции сканов (`src/core/scan_detector.py`)

Новый модуль. Никаких внешних зависимостей — только `os.path.getsize` и `subprocess` (pdfinfo).

```python
class ScanDetector:
    SCAN_TEXT_THRESHOLD = 100      # зн.
    SCAN_SIZE_THRESHOLD = 200 * 1024  # байт
    
    def is_scanned(self, filepath: Path) -> bool:
        """PDF — скан, если pdftotext дал < 100 зн. И файл > 200KB"""
    
    def get_scanner_info(self, filepath: Path) -> str | None:
        """Извлечь модель сканера из pdfinfo (Creator/Producer)"""
    
    def detect_all(self, file_list: list[Path]) -> dict:
        """Возвращает {path: ScanInfo(text_chars, size, scanner, pages)}"""
```

**Файлы**: `src/core/scan_detector.py` (~80 строк)  
**Тесты**: `tests/test_scan_detector.py` — на файлах ЛОС (9 сканов, 3 текстовых)

---

## Шаг 2: VLM-классификатор (`src/core/vlm_classifier.py`)

Отправляет страницы сканированных PDF в Ollama Cloud VLM, получает структурированный ответ.

```python
class VLMClassifier:
    def __init__(self, model="gemma4:31b-cloud", base_url="http://127.0.0.1:11434"):
        ...
    
    async def classify_page(self, image_bytes: bytes) -> VlmPageResult:
        """Отправить страницу в VLM, получить: тип, номер, дата, работы, приложения, подписи"""
    
    async def classify_document(self, pdf_path: Path) -> VlmDocResult:
        """pdftoppm каждую страницу → VLM → агрегировать результат"""
```

**Промпт VLM** (отработан на ЛОС):
```
Опиши кратко (5 пунктов): 1) Тип документа 2) Номер и дата 3) Какие работы 
4) Какие приложения перечислены (ищи сертификаты, паспорта, документы качества) 
5) Заполнены ли штампы и подписи?
```

**Файлы**: `src/core/vlm_classifier.py` (~150 строк)  
**Зависимости**: `requests`, `base64`, `subprocess` (pdftoppm)  
**Тесты**: `tests/test_vlm_classifier.py` — мок Ollama, проверка парсинга ответа

---

## Шаг 3: Модификация IngestionPipeline (`src/core/ingestion.py`)

Интегрировать ScanDetector + VLMClassifier в `process_single()`:

```python
async def process_single(self, filepath: Path) -> DocumentRecord:
    text = self._extract_text(filepath)  # pdftotext
    
    if self.scan_detector.is_scanned(filepath):
        # VLM-путь
        vlm_result = await self.vlm_classifier.classify_document(filepath)
        doc_type = vlm_result.doc_type
        confidence = 0.85  # VLM confidence
        metadata = {
            'scan': True,
            'scanner': self.scan_detector.get_scanner_info(filepath),
            'vlm_type': doc_type,
            'embedded_refs': vlm_result.embedded_refs,  # сертификаты, акты внутри
            'signatures': vlm_result.signatures_filled,
        }
    else:
        # Текстовый путь (старый)
        doc_type, confidence = self.classifier.classify(text)
        metadata = {}
    
    return DocumentRecord(filepath, doc_type, confidence, text, metadata)
```

**Ключевое**: `embedded_refs` — список документов, упомянутых внутри (сертификаты, ИС, акты). Добавляются в граф как `ReferenceNode`.

**Файлы**: `src/core/ingestion.py` — модификация `process_single()` (+40 строк)

---

## Шаг 4: GraphService — узлы для встроенных ссылок

Документы, найденные только как ссылки внутри других PDF (сертификат №21514, акт №1-ДШ), должны создавать узлы типа `EmbeddedReference`:

```python
# Новый тип узла
class EmbeddedReference:
    doc_type: str       # "certificate", "aosr", "executive_scheme"
    identifier: str     # "Сертификат качества №21514"
    date: str | None
    found_in: str       # "АОСР_погружение_ЛОС.pdf, стр.2"
    status: str         # "missing" — отсутствует как файл
```

**Файлы**: `src/core/graph_service.py` — новый метод `add_embedded_reference()` (+25 строк)

---

## Шаг 5: Inventory Report с учётом VLM-данных

Модифицировать `get_inventory_report()` и `generate_inventory_pdf.py`:

- Добавить секцию «Сканированные документы» (count, scanner info)
- Добавить секцию «Встроенные ссылки» (embedded references)
- В секции «Ошибки классификатора» сравнивать keyword vs VLM
- Корректно считать `doc_types_found` с учётом VLM-типов

**Файлы**: 
- `src/core/ingestion.py` — `get_inventory_report()` (+20 строк)
- `scripts/generate_inventory_pdf.py` — новый раздел (+30 строк)

---

## Шаг 6: Обновлённый run_inventory.py

Скрипт должен автоматически выбирать профиль (dev_linux → Ollama Cloud) и запускать полный пайплайн с VLM:

```bash
ASD_PROFILE=dev_linux PYTHONPATH=. python scripts/run_inventory.py \
  data/test_projects/LOS --project-id LOS --vlm
```

**Файлы**: `scripts/run_inventory.py` — флаг `--vlm`, инициализация VLMClassifier (+25 строк)

---

## Оценка трудозатрат

| Шаг | Модуль | Строк кода | Сложность |
|-----|--------|-----------|-----------|
| 1 | `scan_detector.py` | 80 | Низкая |
| 2 | `vlm_classifier.py` | 150 | Средняя (async, VLM API) |
| 3 | `ingestion.py` (mod) | 40 | Средняя (интеграция) |
| 4 | `graph_service.py` (mod) | 25 | Низкая |
| 5 | inventory report (mod) | 50 | Низкая |
| 6 | `run_inventory.py` (mod) | 25 | Низкая |
| **Итого** | | **~370 строк** | ~3-4 часа |

---

## Риски

1. **Ollama Cloud latency**: VLM-запросы к gemma4:31b-cloud идут 30-240 сек на страницу. Для 12-страничного документа — до 5 мин. Решение: параллельная отправка страниц (asyncio.gather).
2. **VLM-ответ неструктурирован**: Gemma может ответить не по формату. Решение: fallback-парсинг, несколько попыток.
3. **pdftoppm не установлен**: на некоторых машинах. Решение: проверка в ScanDetector, graceful degradation.
4. **Стоимость VLM**: gemma4:31b-cloud на Ollama.com — free tier, но есть лимиты. Для продакшена на Mac Studio — локальный MLX.

## Валидация

Прогнать на папке ЛОС (12 файлов) и сравнить с ручным отчётом:
- Все 12 файлов классифицированы верно
- 9 сканов детектированы
- 4 встроенные ссылки найдены
- 5 документов отнесены к ИД, 7 исключены
- Отчёт inventory_LOS_v3.pdf совпадает с inventory_LOS_v2.pdf по ключевым метрикам

---

## Что НЕ входит в этот план

- VLM-анализ исполнительных схем на соответствие ГОСТ Р 51872 (это отдельный шаг — Inspection Pipeline)
- Автоматическая матрица комплектности по 344/пр (требует knowledge base нормативки)
- Генерация предписаний подрядчику (Inspection Pipeline, следующий этап)
