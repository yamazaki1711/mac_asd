# ASD Evidence Graph v2 — Единый граф для сопровождения и антикризиса

**Дата:** 02.05.2026  
**Статус:** Проект архитектуры  
**Заменяет:** `src/core/graph_service.py` (NetworkX v1 — только сертификат→партия→АОСР)

---

## 0. Нулевой слой: Проектная документация — источник истины

**Фундаментальный принцип:** ПД/РД есть всегда. Даже на проблемном объекте — кто-то же его спроектировал. ASD не начинает «с пожара» — она начинает с того, что **должно быть построено**.

```
ПД/РД (всегда есть)
  │
  ├─ Спецификации и ведомости → WorkUnit'ы (ЧТО строим) — status=PLANNED
  ├─ ВОР (ведомость объёмов) → Volume на каждый WorkUnit
  ├─ ПОС/ППР → последовательность (TEMPORAL_BEFORE)
  ├─ Генплан/стройгенплан → Location-иерархия
  ├─ Смета/спецификации → ожидаемые MaterialBatch (ЧТО закупаем)
  └─ Требования к качеству → ГОСТы/СП → ожидаемые сертификаты и документы
```

**ProjectLoader** — компонент, который парсит ПД/РД и заполняет граф плановыми узлами. Это **первый шаг любой работы ASD с объектом**, до любой инвентаризации.

Дальше два пути от одного и того же дерева PLANNED WorkUnit'ов:

| | Сопровождение | Антикризис |
|---|---|---|
| WorkUnit'ы | PLANNED → IN_PROGRESS → COMPLETED (агенты) | PLANNED → INFERRED (inference из улик) |
| Journal | Заполняется по факту → сверка с планом | Реконструируется → сравнение с «должно быть» |
| Дельта | План vs Факт (что недоделано) | План vs Улики (чего не хватает для подтверждения) |
| MaterialBatch | Заказ по спецификации → поставка → входной контроль | Поиск ТТН/сертификатов → сверка с ожидаемым |

**Ключевое следствие:** ASD знает, что искать ДО начала инвентаризации. Не «найди все документы и разберись», а «вот список из 47 ожидаемых АОСР, 12 сертификатов, 8 журналов — проверь наличие каждого».

---

## 1. Зачем нужен v2

Текущий граф (`graph_service.py`, 12 типов узлов) — это склад: загрузил документ → создал узел. Он не умеет **выводить неизвестное из известного**.

Evidence Graph v2 делает три вещи, которых не умеет v1:

| Возможность | v1 (сейчас) | v2 (цель) |
|-------------|------------|-----------|
| Хранение фактов | ✅ | ✅ |
| **Вывод фактов** (inference) | ❌ | ✅ Из ТТН + КС-2 + темпа → даты работ |
| **Оценка уверенности** каждого факта | ❌ Только у классификации | ✅ Каждый узел и ребро имеет confidence |
| **Единый граф для двух режимов** | ❌ | ✅ Сопровождение и антикризис — одни узлы |

---

## 2. Два режима — один граф

```
                    Evidence Graph v2
                    ┌─────────────────┐
                    │  WorkUnit        │
                    │  MaterialBatch   │
                    │  Document        │
                    │  Person          │
                    │  DateEvent       │
                    │  Volume          │
                    │  Location        │
                    └────────┬────────┘
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                      ▼
   Сопровождение                          Антикризис
   ─────────────                          ──────────
   Факты от агентов                      Факты от Inference Engine
   confidence = 1.0                       confidence = 0.4–0.9
   WorkUnit.status = COMPLETED            WorkUnit.status = INFERRED
   Journal: запись по факту              Journal: реконструкция
   HITL: «подпишите АОСР»                HITL: «подтвердите, что B001 погружён 15.03?»
   Результат: ИД к сдаче                 Результат: восстановленная ИД
```

Ключевой принцип: **одни и те же узлы, разные источники данных**. WorkUnit, созданный агентом ПТО при сопровождении, и WorkUnit, выведенный из ТТН при антикризисе — это одинаковые узлы графа. Различаются только `confidence` и `source`.

---

## 3. Типы узлов (7)

### 3.1. WorkUnit — единица работы

```python
@dataclass
class WorkUnit:
    id: str                          # "WU_pile_driving_zone1"
    work_type: str                   # "погружение_шпунта", "бетонирование_фундамента"
    description: str                 # "Погружение шпунта Л5-УМ, захватка 1, 100 шт"
    
    # Даты (могут быть inferred)
    start_date: Optional[date]
    end_date: Optional[date]
    planned_start: Optional[date]    # Из ППР/графика
    planned_end: Optional[date]
    
    # Объёмы
    volume: Optional[float]
    unit: str                        # "шт", "м³", "т"
    
    # Статус и уверенность
    status: WorkUnitStatus           # PLANNED | IN_PROGRESS | COMPLETED | INFERRED | CONFIRMED
    confidence: float                # 1.0 (прямой факт) … 0.4 (inference)
    source: FactSource               # AGENT | INFERENCE | HUMAN
    
    # Связи
    location_id: Optional[str]       # → Location
    parent_id: Optional[str]         # → WorkUnit (декомпозиция: фундамент → опалубка/армирование/бетонирование)
    depends_on: List[str]            # → WorkUnit[] (технологическая последовательность)
    
    # Аудит
    created_by: str                  # "pto_agent", "inference_engine", "human"
    created_at: datetime
    confirmed_by: Optional[str]      # Кто подтвердил (в HITL)
    confirmed_at: Optional[datetime]
```

**Источник фактов:**
- **Сопровождение**: ПТО-агент создаёт WorkUnit из графика работ. status=IN_PROGRESS→COMPLETED по факту. confidence=1.0, source=AGENT.
- **Антикризис**: Inference Engine выводит WorkUnit из MaterialBatch + Volume + typical_rate. status=INFERRED, confidence=0.4–0.9, source=INFERENCE. После HITL → CONFIRMED, confidence=1.0, source=HUMAN.

### 3.2. MaterialBatch — партия материала

```python
@dataclass
class MaterialBatch:
    id: str                          # "MB_evraz_B001"
    material_name: str               # "Шпунт Ларсена Л5-УМ"
    batch_number: str                # "B001"
    quantity: float                  # 55
    unit: str                        # "шт"
    gost: Optional[str]              # "ГОСТ Р 53629-2009"
    supplier: Optional[str]          # "ПАО ЕВРАЗ НТМК"
    delivery_date: Optional[date]    # Из ТТН
    certificate_id: Optional[str]    # → Document (сертификат качества)
    ttn_id: Optional[str]            # → Document (ТТН)
    confidence: float                # 1.0 если сертификат подлинный, <1.0 если копия/фото
```

### 3.3. Document — любой документ

```python
@dataclass
class Document:
    id: str
    doc_type: DocType                # AOSR | CERTIFICATE | TTN | KS2 | KS3 | PHOTO | LETTER | JOURNAL | ...
    doc_number: Optional[str]
    doc_date: Optional[date]
    file_path: Optional[str]         # Путь к файлу (None для EmbeddedReference)
    content_summary: str             # Краткое описание (первые 500 зн. или VLM-резюме)
    
    signatures_present: bool         # Подписан?
    stamps_present: bool             # Печати?
    
    confidence: float                # 1.0 — оригинал, 0.7 — скан без подписей, 0.5 — упомянут
    status: DocStatus                # ORIGINAL | SCAN | RECONSTRUCTED | REFERENCED (встроенная ссылка)
    
    # Ссылки на другие узлы
    work_unit_id: Optional[str]      # К какому WorkUnit относится
    references: List[str]            # → Document[] (упомянутые документы)
    signed_by: List[str]             # → Person[]
```

**REFERENCED-документы** (встроенные ссылки): сертификат №21514 упомянут в АОСР, но файла нет. Это НЕ ошибка — это валидный узел графа с `status=REFERENCED` и `confidence=0.5`. Он участвует в матрице комплектности как «упомянут, но не предоставлен».

### 3.4. Person — участник

```python
@dataclass
class Person:
    id: str
    name: str
    role: PersonRole                 # PTO_ENGINEER | FOREMAN | SUPPLIER | CUSTOMER | INSPECTOR | WORKER
    organization: Optional[str]
    contacts: Dict[str, str]         # {"phone": "...", "email": "..."}
    
    # Для HITL: приоритизация вопросов
    reliability: float               # 0.0–1.0 (насколько достоверны показания)
    last_contacted: Optional[datetime]
```

### 3.5. DateEvent — временная метка

```python
@dataclass
class DateEvent:
    id: str
    event_type: EventType            # DELIVERY | INSPECTION | SIGNING | PHOTO_TAKEN | STATEMENT | INFERRED
    timestamp: datetime              # Точное или выведенное время
    precision: TimePrecision         # EXACT | DAY | WEEK | MONTH (насколько точно известно)
    description: str
    
    source_document_id: Optional[str] # → Document (откуда взята дата)
    source_person_id: Optional[str]   # → Person (кто сообщил)
    confidence: float                 # 1.0 (ТТН с датой) … 0.4 (показания рабочего «где-то в марте»)
```

### 3.6. Volume — объём

```python
@dataclass
class Volume:
    id: str
    value: float
    unit: str
    source: VolumeSource             # PROJECT | VOR | KS2 | INFERRED
    
    work_unit_id: Optional[str]      # → WorkUnit
    confidence: float                # 1.0 (подписанный КС-2) … 0.5 (выведено из ВОР)
```

### 3.7. Location — место

```python
@dataclass
class Location:
    id: str                          # "zone1", "section_A", "floor_3"
    name: str                        # "Захватка 1", "Секция А", "Этаж 3"
    parent_id: Optional[str]         # → Location (иерархия: площадка → захватка → ось)
    description: Optional[str]
    coordinates: Optional[dict]      # {lat, lon} или осевые привязки
```

---

## 4. Типы связей (рёбер)

| Связь | От | К | Семантика |
|-------|----|---|-----------|
| **USED_IN** | MaterialBatch | WorkUnit | Партия использована в работе (quantity на ребре) |
| **CONFIRMED_BY** | WorkUnit | Document | Работа подтверждена документом |
| **REFERENCES** | Document | Document | Документ ссылается на другой |
| **TEMPORAL_BEFORE** | WorkUnit | WorkUnit | Технологически предшествует |
| **LOCATED_AT** | WorkUnit | Location | Где выполнялась |
| **SUPPLIED_BY** | MaterialBatch | Person | Кто поставил |
| **SIGNED_BY** | Document | Person | Кто подписал |
| **DERIVED_FROM** | WorkUnit | WorkUnit | Выведен из другого (антикризис) |
| **HAS_EVENT** | WorkUnit | DateEvent | Временная метка работы |
| **DEFINES_VOLUME** | Volume | WorkUnit | Объём привязан к работе |
| **MENTIONS** | Document | MaterialBatch | Документ упоминает партию |

**Атрибуты на рёбрах:**
```python
@dataclass
class EdgeAttributes:
    confidence: float = 1.0          # Насколько достоверна связь
    quantity: Optional[float] = None # Для USED_IN
    evidence: List[str] = []         # На каких документах основана связь
```

---

## 5. Inference Engine — вывод фактов

Symbolic rules (не LLM) — быстрые, объяснимые, без галлюцинаций.

### Правило 1: Поставка → даты работ
```
IF MaterialBatch.delivery_date = D
   AND MaterialBatch -> [USED_IN] -> WorkUnit
   AND WorkUnit.volume = V
   AND typical_daily_rate(WorkUnit.work_type) = R
THEN
   INFER WorkUnit.start_date ≈ D + 1 day
   INFER WorkUnit.end_date ≈ D + ceil(V / R) days
   confidence = min(MaterialBatch.confidence * 0.9, 0.85)
```

### Правило 2: КС-2 → существование работ
```
IF Document[doc_type=KS2].doc_date = D
   AND Document[KS2] -> [REFERENCES] -> WorkUnit
   AND Document[KS2].signatures_present = True
THEN
   INFER WorkUnit existed at time D
   confidence = 0.8
   IF WorkUnit.status == INFERRED → promote to CONFIRMED if confidence crosses 0.8
```

### Правило 3: Фото → временная метка
```
IF Document[doc_type=PHOTO].metadata contains timestamp = T
   AND Document[PHOTO] -> [CONFIRMED_BY] -> WorkUnit
THEN
   CREATE DateEvent(event_type=PHOTO_TAKEN, timestamp=T, confidence=0.85)
   LINK DateEvent -> [HAS_EVENT] -> WorkUnit
```

### Правило 4: Цепочка поставок → локация
```
IF MaterialBatch[location_id = L] -> [USED_IN] -> WorkUnit
   AND WorkUnit.location_id IS NULL
THEN
   INFER WorkUnit.location_id = L
   confidence = 0.7
```

### Правило 5: Технологическая последовательность
```
IF WorkUnit_A -> [TEMPORAL_BEFORE] -> WorkUnit_B
   AND WorkUnit_A.end_date IS KNOWN
   AND WorkUnit_B.start_date IS NULL
THEN
   INFER WorkUnit_B.start_date = WorkUnit_A.end_date + 1 day
   confidence = WorkUnit_A.confidence * 0.85
```

### Правило 6: Повышение уверенности через подтверждение
```
IF WorkUnit_A -> [DERIVED_FROM] -> WorkUnit_B
   AND WorkUnit_B.status = CONFIRMED
THEN
   WorkUnit_A.confidence = min(WorkUnit_A.confidence * 1.2, 0.95)
```

**Библиотека typical_daily_rate** (внешний YAML/JSON, не хардкод):
```yaml
погружение_шпунта: 12    # шт/день
бетонирование_фундамента: 25  # м³/день
монтаж_металлоконструкций: 2.5  # т/день
кирпичная_кладка: 8      # м³/день
```

---

## 6. Confidence Framework

| Диапазон | Цвет | Значение | Действие |
|----------|------|----------|----------|
| 1.0 | 🟢 Зелёный | Прямой факт. Агент создал, документ подписан, человек подтвердил | Готово к использованию |
| 0.8–0.99 | 🟢 Зелёный | Подтверждено несколькими независимыми источниками | Пригодно для генерации документов |
| 0.6–0.79 | 🟡 Жёлтый | Один источник + inference. Требует проверки | HITL: умный вопрос человеку |
| 0.4–0.59 | 🔴 Красный | Только inference. Критически требует подтверждения | HITL: приоритетный вопрос |
| 0.0–0.39 | ⚫ Серый | Чистая догадка | Не использовать, не показывать |

**Пересчёт при добавлении данных:**
Каждый новый факт в графе запускает пересчёт confidence для связанных узлов. Если к WorkUnit с confidence 0.5 добавился DateEvent (фото) с confidence 0.85 — confidence WorkUnit поднимается до 0.65 (переход красный→жёлтый).

---

## 7. Режим: Сопровождение

```
Агент ПТО создаёт WorkUnit из графика
  │  status = PLANNED, confidence = 1.0, source = AGENT
  ▼
Стройка идёт → WorkUnit.status = IN_PROGRESS
  │  Агент привязывает MaterialBatch (USES связь с quantity)
  ▼
Работа завершена → WorkUnit.status = COMPLETED
  │  Агент создаёт Document[doc_type=AOSR] → [CONFIRMED_BY] → WorkUnit
  │  Агент записывает в Journal
  ▼
Chain Builder генерирует всю цепочку АОСР
  │
  ▼
HITL: запрос подписей → человек подписывает → Document.signatures_present = True
  │
  ▼
Package Generator → папка ИД под сдачу
```

**Здесь Inference Engine НЕ работает** — все факты прямые, confidence = 1.0. Граф используется как шина данных между агентами.

---

## 8. Режим: Антикризис

```
Ingestion Pipeline загружает улики:
  ├─ ТТН (MaterialBatch с delivery_date)
  ├─ Сертификаты (MaterialBatch.certificate_id)
  ├─ КС-2/КС-3 (Volume с source=KS2)
  ├─ Фото (Document[doc_type=PHOTO])
  ├─ Переписка (Document[doc_type=LETTER])
  └─ Показания (Person + DateEvent[STATEMENT])
  │
  ▼
Inference Engine запускает правила:
  ├─ Правило 1: ТТН + typical_rate → даты работ
  ├─ Правило 2: КС-2 → WorkUnit существовал
  ├─ Правило 3: Фото → DateEvent
  ├─ Правило 4: поставка → локация
  └─ Правило 5: цепочка → даты
  │
  ▼
WorkUnit'ы созданы (status=INFERRED, confidence=0.4-0.85)
  │
  ▼
Journal Reconstructor:
  1. Timeline известных DateEvent'ов
  2. Заполнение пробелов WorkUnit'ами
  3. Цветовая разметка по confidence
  4. HITL-вопросы для красного/жёлтого
  5. Итерация: ответы → пересчёт → новый журнал
  │
  ▼
Chain Builder: цепочки АОСР на основе журнала
  │
  ▼
HITL: умные вопросы → человек подтверждает → confidence повышается
  │
  ▼
Когда все WorkUnit.status = CONFIRMED:
  Package Generator → восстановленная папка ИД
```

---

## 9. HITL — умные вопросы вместо списка дыр

**Плохо (сейчас):**
> «Отсутствует АОСР на погружение шпунта»
> «Отсутствует сертификат качества»

Инженер ПТО должен сам понять, что делать.

**Хорошо (с Evidence Graph v2):**
> «Партия шпунта B001 (ЕВРАЗ) поставлена 15.03.2025 по ТТН №089.  
> Объём по КС-2: 100 шт. Типовой темп: 12 шт/день.  
> Система предполагает: погружение велось 16.03–25.03.2025 (уверенность 76%).  
> **Вопрос:** подтверждаете эти даты?»
> 
> [Да] → WorkUnit.confidence = 1.0, status = CONFIRMED  
> [Нет, было 20.03–30.03] → пересчёт журнала  
> [Уточнить: фото шпунта на площадке есть?] → показываем фото

**Приоритизация вопросов:**
1. Вопросы, закрывающие максимум «красных» узлов за один ответ
2. Вопросы к людям с высоким reliability
3. Вопросы, после которых можно запустить цепочку inference

---

## 10. ProjectLoader — нулевой слой графа

**Первый шаг ASD на любом объекте.** Парсит ПД/РД и заполняет граф плановыми узлами.

### Входные данные
- **Спецификации оборудования/материалов** (из ПД, разделы КМ, КЖ, АР, ОВ) → WorkUnit'ы + MaterialBatch
- **Ведомость объёмов работ (ВОР)** → Volume на каждый WorkUnit
- **ПОС/ППР/Календарный план** → TEMPORAL_BEFORE + planned_start/end
- **Генплан/Стройгенплан** → Location-иерархия
- **Смета/ЛСР** → ожидаемые MaterialBatch (наименование, количество, ГОСТ)
- **Требования к качеству** (ПД раздел «Проект организации строительства») → ожидаемые сертификаты, акты испытаний

### API

```python
from src.core.project_loader import project_loader

# Загрузить ПД в граф
summary = project_loader.load_project(evidence_graph, pd_folder="/path/to/PD")

# Результат:
#   WorkUnit'ы: 47 (все PLANNED)
#   Volume: 47 (по одному на каждый WorkUnit)
#   Location: 12 (иерархия: площадка → захватка → ось)
#   MaterialBatch: 23 (ожидаемые поставки из спецификации)
#   TEMPORAL_BEFORE: 46 связей (из календарного плана)
```

### Извлечение из ПД

| Источник в ПД | Что извлекается | Куда в графе |
|--------------|----------------|-------------|
| Спецификация КМ (лист 1-3) | Наименование, марка, ГОСТ, кол-во | MaterialBatch (expected=True) |
| ВОР (раздел «Ведомость объёмов») | WorkType, объём, ед. изм. | WorkUnit + Volume |
| Календарный план (ПОС, лист 5) | Последовательность, сроки | TEMPORAL_BEFORE, planned_start/end |
| Генплан (лист ГП-1) | Захватки, оси, отметки | Location-иерархия |
| Смета/ЛСР | Расценки, материалы | MaterialBatch.expected_quantity |
| Требования к качеству | ГОСТ, СП, СНиП | Document (норматив, expected=True) |

### Режим работы

**С сопровождением:** ProjectLoader создаёт baseline → агенты ведут стройку от него → сверка план/факт автоматическая.

**С антикризисом:** ProjectLoader создаёт baseline → Ingestion Pipeline загружает улики → Inference Engine сопоставляет: «WorkUnit "Погружение шпунта" запланирован — есть ли подтверждающие документы?» → дельта = план – улики.

### Форматы ПД

- **PDF** (наиболее частый) — через pdftotext + keyword extraction + VLM для таблиц и схем
- **DWG** (чертежи КМ/КЖ) — через ezdxf/ODA File Converter → извлечение блок-спецификаций
- **XLSX** (сметы, ВОР) — через openpyxl → парсинг таблиц
- **DOCX** (пояснительные записки) — через python-docx → извлечение перечней

## 11. Что меняется в кодовой базе

| Текущий файл | Что происходит |
|-------------|---------------|
| `src/core/graph_service.py` (874 LOC) | **Заменяется** на `src/core/evidence_graph.py` — новый API с 7 типами узлов |
| `src/core/graph_service.py` | Не удаляется — работает рядом для обратной совместимости тестов |
| `src/core/inference_engine.py` | **Новый** — symbolic inference rules |
| `src/core/journal_reconstructor.py` | **Заменяется** (текущий — зачаток) — 5-этапный процесс |
| `src/core/hitl_questions.py` | **Новый** — приоритизация и генерация умных вопросов |
| `src/core/chain_builder.py` | **Новый** — генерация цепочек АОСР |
| `src/core/services/pto_agent.py` | **Модифицируется** — создание WorkUnit'ов в графе |
| `src/core/pm_agent.py` | **Модифицируется** — delta-driven оркестрация через граф |
| `data/typical_rates.yaml` | **Новый** — темпы работ для inference |

---

## 12. Порядок реализации

0. **ProjectLoader** — нулевой слой: парсинг ПД/РД → WorkUnit'ы PLANNED (~400 LOC)
1. **Evidence Graph v2** — ядро, без которого всё остальное не имеет смысла (~600 LOC) ✅ Реализован
2. **Inference Engine** — правила 1-6 (~400 LOC) + typical_rates.yaml ✅ Реализован
3. **Journal Reconstructor v2** — 5 этапов, питается от графа (~500 LOC)
4. **HITL Questions** — генератор умных вопросов (~300 LOC)
5. **Chain Builder** — цепочки АОСР от журнала (~250 LOC)
6. **Интеграция с агентами** — ПТО, PM, Auditor через новый API графа (~200 LOC)

**Итого: ~2450 строк нового кода.** Вся бизнес-логика инференса — symbolic (правила, не LLM). LLM используется только агентами для генерации текстов документов и анализа содержания.
