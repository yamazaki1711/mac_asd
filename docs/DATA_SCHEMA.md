# АСД v12.0 — СХЕМА ДАННЫХ

**Дата:** 20 апреля 2026
**Статус:** Активная разработка (Package 1, 5, 11 завершены, Package 4 частично реализован)
**СУБД:** PostgreSQL 16 + pgvector + pg_trgm
**Модели:** Gemma 4 31B 4-bit (ПТО/Юрист/Сметчик/Закупщик/Логист), Gemma 4 E4B 4-bit (Делопроизводитель), Llama 3.3 70B 4-bit (Руководитель проекта/PM), bge-m3-mlx-4bit (embeddings)

---

## 1. ОБЗОР

Полная схема реляционной базы данных АСД v12.0: таблицы, столбцы, типы, связи, индексы, триггеры. Включая векторные embeddings для pgvector (bge-m3, 1024 dim). Схема поддерживает пять рабочих агентов (Юрист, ПТО, Сметчик, Закупщик, Логист) на Gemma 4 31B, Делопроизводителя на Gemma 4 E4B и координирующего агента Руководитель проекта (PM) на Llama 3.3 70B. Данные между агентами передаются через общий shared memory, основанный на таблицах projects, contracts и ProtocolPartyInfo.

Ключевое расширение v12.0 — полноценная поддержка ProtocolPartyInfo в таблице contracts. Поля реквизитов (ОГРН, адрес, расчётный счёт, банк, БИК, подписант, должность) для обеих сторон договора теперь являются неотъемлемой частью схемы и используются при генерации протоколов разногласий, претензий, исковых заявлений и деловых писем. Это устраняет необходимость повторного извлечения реквизитов и обеспечивает единый источник правды (single source of truth) для всех агентов.

---

## 2. EXTENSIONS

```sql
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector: векторный поиск (bge-m3, 1024 dim)
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- trigram: нечёткий текстовый поиск
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- UUID генерация
```

Расширение `vector` обеспечивает хранение и поиск embeddings (bge-m3, 1024-мерные векторы). Расширение `pg_trgm` используется для нечёткого текстового поиска по наименованиям работ, позиций смет, паттернов ловушек и реквизитов контрагентов. Расширение `uuid-ossp` генерирует уникальные идентификаторы при необходимости.

---

## 3. СХЕМА

### 3.1. projects

Проекты строительной компании. Каждый проект соответствует одному объекту строительства и связан с одним или несколькими договорами подряда. Проект является корневой сущностью для всех документов, ВОР, смет, актов и писем.

```sql
CREATE TABLE projects (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(50)  UNIQUE NOT NULL,    -- "prichaly", "electra"
    name            VARCHAR(200) NOT NULL,            -- "Причалы №9 и №10"
    type            VARCHAR(50),                      -- "hydrotech" | "commercial" | "residential"
    customer        VARCHAR(200),                     -- "ФКУ Ространсмодернизация"
    customer_inn    VARCHAR(12),                      -- ИНН заказчика
    contract_number VARCHAR(50),                      -- "РТМ-066/22"
    status          VARCHAR(20)  NOT NULL DEFAULT 'active',  -- "active" | "completed" | "paused"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_slug ON projects(slug);
CREATE INDEX idx_projects_status ON projects(status);
```

### 3.2. documents

Все загруженные документы. Каждый документ привязан к проекту и классифицируется по типу (договор, ПД, РД, ВОР, смета, переписка, акт). После парсинга полный текст сохраняется в `parsed_text`, а документ разбивается на чанки для векторного поиска.

```sql
CREATE TABLE documents (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER       REFERENCES projects(id) ON DELETE SET NULL,
    type                VARCHAR(30)   NOT NULL,          -- "contract" | "pd" | "rd" | "vor" | "estimate" | "correspondence" | "act"
    file_name           VARCHAR(500)  NOT NULL,
    file_path           VARCHAR(1000) NOT NULL,          -- абсолютный путь на диске
    file_size           BIGINT,                         -- байты
    page_count          INTEGER,
    is_scan             BOOLEAN       NOT NULL DEFAULT false,
    parsed_text         TEXT,                           -- полный распознанный текст
    parsed_text_length  INTEGER,
    chunks_count        INTEGER       DEFAULT 0,
    metadata            JSONB,                          -- дополнительные метаданные
    status              VARCHAR(20)   NOT NULL DEFAULT 'uploaded',  -- "uploaded" | "parsed" | "analyzed" | "error"
    uploaded_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    parsed_at           TIMESTAMPTZ,
    analyzed_at         TIMESTAMPTZ
);

CREATE INDEX idx_documents_project_id ON documents(project_id);
CREATE INDEX idx_documents_type ON documents(type);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_file_name ON documents USING gin(file_name gin_trgm_ops);
```

### 3.3. chunks

Чанки документов для векторного поиска. Каждый чанк содержит фрагмент текста документа, его позицию в документе и векторное представление (embedding) модели bge-m3 (1024 измерений). HNSW-индекс обеспечивает быстрый поиск ближайших соседей по косинусному расстоянию.

```sql
CREATE TABLE chunks (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id          INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    position            INTEGER      NOT NULL,           -- порядковый номер чанка
    text                TEXT         NOT NULL,
    token_count         INTEGER,
    page_start          INTEGER,                        -- страница начала
    page_end            INTEGER,                        -- страница конца
    embedding           vector(1024),                   -- bge-m3 embedding (1024 dim)
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_project_id ON chunks(project_id);
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_text ON chunks USING gin(text gin_trgm_ops);

-- HNSW для быстрого векторного поиска (вместо IVFFlat)
-- HNSW не требует предварительной тренировки, лучше для динамических данных
```

### 3.4. contracts

Детали контрактов (извлечённые из документов). Таблица включает полные реквизиты обеих сторон (ProtocolPartyInfo): ОГРН, юридический адрес, расчётный счёт, банк, БИК, подписант и должность. Эти поля используются всеми агентами при генерации документов и формируют единый источник правды для реквизитов.

**Интеграция ProtocolPartyInfo:** Поля `party_1_ogrn`, `party_1_address`, `party_1_account`, `party_1_bank`, `party_1_bik`, `party_1_signatory`, `party_1_position` (и аналогичные для `party_2`) составляют структуру ProtocolPartyInfo. Они извлекаются из договора агентом Юрист (инструмент asd_analyze_contract) и сохраняются в таблице contracts. При генерации протоколов, претензий, исков и писем эти данные автоматически подставляются в шапки и подписные блоки документов. Если реквизиты не были извлечены из договора, поля содержат NULL, и агент указывает «[Заполнить]» в placeholder.

```sql
CREATE TABLE contracts (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    document_id     INTEGER      REFERENCES documents(id) ON DELETE SET NULL,
    number          VARCHAR(50),                          -- "РТМ-066/22"
    date            DATE,
    -- Сторона 1: Заказчик (ProtocolPartyInfo)
    party_1         VARCHAR(200),                         -- наименование Заказчика
    party_1_inn     VARCHAR(12),                          -- ИНН Заказчика
    party_1_ogrn    VARCHAR(15),                          -- ОГРН Заказчика
    party_1_address TEXT,                                  -- юридический адрес Заказчика
    party_1_account VARCHAR(30),                           -- расчётный счёт Заказчика
    party_1_bank    VARCHAR(200),                          -- банк Заказчика
    party_1_bik     VARCHAR(10),                           -- БИК банка Заказчика
    party_1_signatory VARCHAR(200),                        -- ФИО подписанта Заказчика
    party_1_position  VARCHAR(200),                        -- должность подписанта Заказчика
    -- Сторона 2: Подрядчик (ProtocolPartyInfo)
    party_2         VARCHAR(200),                         -- наименование Подрядчика
    party_2_inn     VARCHAR(12),                          -- ИНН Подрядчика
    party_2_ogrn    VARCHAR(15),                          -- ОГРН Подрядчика
    party_2_address TEXT,                                  -- юридический адрес Подрядчика
    party_2_account VARCHAR(30),                           -- расчётный счёт Подрядчика
    party_2_bank    VARCHAR(200),                          -- банк Подрядчика
    party_2_bik     VARCHAR(10),                           -- БИК банка Подрядчика
    party_2_signatory VARCHAR(200),                        -- ФИО подписанта Подрядчика
    party_2_position  VARCHAR(200),                        -- должность подписанта Подрядчика
    -- Прочие данные контракта
    price           NUMERIC(15,2),                        -- цена контракта
    start_date      DATE,
    end_date        DATE,
    court           VARCHAR(200),                         -- подсудность
    payment_terms   TEXT,                                 -- условия оплаты
    penalty_terms   TEXT,                                 -- условия штрафов
    parsed_data     JSONB,                                -- все извлечённые данные
    status          VARCHAR(20)  NOT NULL DEFAULT 'active',  -- "active" | "completed" | "disputed"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_contracts_project_id ON contracts(project_id);
CREATE INDEX idx_contracts_status ON contracts(status);
CREATE INDEX idx_contracts_number ON contracts(number);
```

### 3.5. traps (БЛС)

Ловушки субподрядчика (Библиотека Ловушек Субподрядчика). В v12.0 библиотека содержит 58 ловушек, сгруппированных по 10 категориям: payment, penalty, acceptance, scope, warranty, subcontractor, liability, corporate_policy, termination, insurance. Две новые категории (termination и insurance) добавлены для выявления рисков расторжения договора и страховых/гарантийных обязательств.

```sql
CREATE TABLE traps (
    id              SERIAL PRIMARY KEY,
    pattern         VARCHAR(500) NOT NULL,                -- regex или текстовый паттерн
    description     TEXT         NOT NULL,                -- описание ловушки
    law_reference   VARCHAR(200),                         -- "ст. 743 ГК РФ"
    recommendation  TEXT,                                 -- как исправить
    severity        VARCHAR(10)  NOT NULL DEFAULT 'medium',  -- "high" | "medium" | "low"
    category        VARCHAR(30)  NOT NULL,                -- "payment" | "penalty" | "acceptance" | "scope" | "warranty" | "subcontractor" | "liability" | "corporate_policy" | "termination" | "insurance"
    source_file     VARCHAR(200),                         -- YAML файл источник
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_traps_severity ON traps(severity);
CREATE INDEX idx_traps_category ON traps(category);
CREATE INDEX idx_traps_is_active ON traps(is_active);
CREATE INDEX idx_traps_pattern ON traps USING gin(pattern gin_trgm_ops);

-- Векторное представление паттерна для semantic matching
ALTER TABLE traps ADD COLUMN pattern_embedding vector(1024);
CREATE INDEX idx_traps_embedding ON traps USING hnsw (pattern_embedding vector_cosine_ops);
```

**Категории ловушек (10):**

| Категория | Описание | Кол-во (примерно) |
|-----------|----------|-------------------|
| payment | Условия оплаты: задержка, аванс, одностороннее изменение цены | 8 |
| penalty | Штрафы и неустойки: чрезмерные ставки, без ограничений | 7 |
| acceptance | Условия приёмки: односторонняя, затягивание сроков | 6 |
| scope | Объём работ: одностороннее изменение, размытые формулировки | 7 |
| warranty | Гарантийные обязательства: завышенные сроки, безусловное устранение | 5 |
| subcontractor | Риски субподряда: запрет, передача ответственности, ограничения | 6 |
| liability | Гражданская ответственность: ограничение, расширение, непропорция | 5 |
| corporate_policy | Корпоративная политика: регламенты заказчика, доп. согласования | 4 |
| termination | Расторжение договора: одностороннее, без компенсации, штрафы | 6 |
| insurance | Страхование и гарантии: обяз. страхование, гарантийные удержания | 4 |
| **Итого** | | **58** |

### 3.6. trap_matches

Найденные ловушки в конкретных документах. Каждое совпадение связывает паттерн из таблицы traps с конкретным фрагментом документа (chunk). Тип совпадения может быть: pattern (regex/trigram), semantic (векторный поиск), llm (обнаружено моделью Gemma 4 31B).

```sql
CREATE TABLE trap_matches (
    id              SERIAL PRIMARY KEY,
    trap_id         INTEGER      NOT NULL REFERENCES traps(id) ON DELETE CASCADE,
    document_id     INTEGER      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id        INTEGER      REFERENCES chunks(id) ON DELETE SET NULL,
    matched_text    TEXT,                                 -- найденный текст
    location        VARCHAR(200),                         -- "Раздел 4, п. 4.3, страница 23"
    match_type      VARCHAR(20)  NOT NULL,                -- "pattern" | "semantic" | "llm"
    detected_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_trap_matches_document_id ON trap_matches(document_id);
CREATE INDEX idx_trap_matches_trap_id ON trap_matches(trap_id);
```

### 3.7. claims

Претензии. Каждая претензия привязана к договору и содержит сумму задолженности, расчёт неустойки (ст. 395 ГК РФ), описание выполненных работ и сроки. Статусная модель: draft → sent → satisfied / rejected / ignored. При отклонении или игнорировании претензии инициируется генерация искового заявления.

```sql
CREATE TABLE claims (
    id                  SERIAL PRIMARY KEY,
    contract_id         INTEGER       REFERENCES contracts(id) ON DELETE SET NULL,
    document_id         INTEGER       REFERENCES documents(id) ON DELETE SET NULL,  -- исходный договор
    debt_amount         NUMERIC(15,2) NOT NULL,
    penalty_amount      NUMERIC(15,2) DEFAULT 0,
    total_amount        NUMERIC(15,2) GENERATED ALWAYS AS (debt_amount + penalty_amount) STORED,
    works_description   TEXT,
    works_completed_date DATE,
    payment_deadline    DATE,
    claim_deadline      DATE,                                 -- срок ответа на претензию
    file_path           VARCHAR(1000),                        -- путь к DOCX
    status              VARCHAR(20)   NOT NULL DEFAULT 'sent',  -- "draft" | "sent" | "satisfied" | "rejected" | "ignored"
    sent_at             TIMESTAMPTZ,
    responded_at        TIMESTAMPTZ,
    response_text       TEXT,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_claims_contract_id ON claims(contract_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_claim_deadline ON claims(claim_deadline);
```

### 3.8. lawsuits

Исковые заявления. Каждый иск привязан к претензии (claim_id) и договору. Содержит данные о суде, сторонах, суммах требований и статусе рассмотрения. Вычисляемый столбец `total_amount` автоматически суммирует исковые требования, неустойку и судебные расходы.

```sql
CREATE TABLE lawsuits (
    id                  SERIAL PRIMARY KEY,
    claim_id            INTEGER       NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    contract_id         INTEGER       REFERENCES contracts(id) ON DELETE SET NULL,
    court               VARCHAR(200)  NOT NULL,
    plaintiff           VARCHAR(200)  NOT NULL,
    defendant           VARCHAR(200)  NOT NULL,
    claim_amount        NUMERIC(15,2) NOT NULL,
    penalty_amount      NUMERIC(15,2) DEFAULT 0,
    legal_costs         NUMERIC(15,2) DEFAULT 0,
    total_amount        NUMERIC(15,2) GENERATED ALWAYS AS (claim_amount + penalty_amount + legal_costs) STORED,
    attachments         JSONB,                                -- список приложений
    file_path           VARCHAR(1000),                        -- путь к DOCX
    case_number         VARCHAR(50),                          -- номер дела (после регистрации)
    status              VARCHAR(20)   NOT NULL DEFAULT 'draft',  -- "draft" | "filed" | "accepted" | "in_progress" | "won" | "lost" | "settled"
    filed_at            TIMESTAMPTZ,
    hearing_date        DATE,
    decision_date       DATE,
    decision_text       TEXT,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_lawsuits_claim_id ON lawsuits(claim_id);
CREATE INDEX idx_lawsuits_status ON lawsuits(status);
CREATE INDEX idx_lawsuits_court ON lawsuits(court);
```

### 3.9. vor_items

Позиции ВОР (ведомости объёмов работ). Каждая позиция содержит наименование работ, объём, единицу измерения и цену за единицу. Вычисляемый столбец `total_price` автоматически рассчитывает стоимость позиции (объём × цена).

```sql
CREATE TABLE vor_items (
    id              SERIAL PRIMARY KEY,
    vor_id          INTEGER       NOT NULL REFERENCES vor(id) ON DELETE CASCADE,
    position        INTEGER       NOT NULL,                   -- порядковый номер
    name            VARCHAR(500)  NOT NULL,                   -- наименование работ
    volume          NUMERIC(12,3),                            -- объём
    unit            VARCHAR(20),                              -- единица измерения
    unit_price      NUMERIC(12,2),                            -- цена за единицу
    total_price     NUMERIC(15,2) GENERATED ALWAYS AS (volume * unit_price) STORED,
    source_section  VARCHAR(100),                             -- раздел ПД/РД
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_vor_items_vor_id ON vor_items(vor_id);
CREATE INDEX idx_vor_items_name ON vor_items USING gin(name gin_trgm_ops);
```

### 3.10. vor

ВОРы (шапки). Каждая запись соответствует одной ведомости объёмов работ. Флаг `is_from_pd` различает ВОР, полученный от заказчика, и ВОР, извлечённый из проектной документации.

```sql
CREATE TABLE vor (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    contract_id     INTEGER      REFERENCES contracts(id) ON DELETE SET NULL,
    file_path       VARCHAR(1000) NOT NULL,
    file_name       VARCHAR(500)  NOT NULL,
    items_count     INTEGER       DEFAULT 0,
    is_from_pd      BOOLEAN       NOT NULL DEFAULT false,   -- true = из ПД, false = полученный
    source          VARCHAR(200),                            -- источник (кто прислал)
    parsed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_vor_project_id ON vor(project_id);
CREATE INDEX idx_vor_contract_id ON vor(contract_id);
```

### 3.11. estimates

Сметные расчёты. Каждый расчёт привязан к проекту, договору и (опционально) ВОР. Содержит итоговые суммы по статьям затрат (прямые, материалы, машины), процент накладных расходов и прибыли. Флаг `is_supplement` отмечает расчёты, являющиеся дополнением к основному (supplement_of).

```sql
CREATE TABLE estimates (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    contract_id     INTEGER      REFERENCES contracts(id) ON DELETE SET NULL,
    vor_id          INTEGER      REFERENCES vor(id) ON DELETE SET NULL,
    file_path       VARCHAR(1000),
    file_name       VARCHAR(500),
    price_base      VARCHAR(20),                            -- "ФЕР-2024" | "ГЭСН-2024" | "ТЕР-2024"
    total_direct    NUMERIC(15,2),                          -- прямые затраты
    materials_cost  NUMERIC(15,2),                          -- материалы
    machines_cost   NUMERIC(15,2),                          -- машины
    overhead_percent NUMERIC(5,2),                          -- накладные расходы
    profit_percent  NUMERIC(5,2),                           -- прибыль
    grand_total     NUMERIC(15,2),                          -- итого
    items_count     INTEGER       DEFAULT 0,
    is_supplement   BOOLEAN       NOT NULL DEFAULT false,
    supplement_of   INTEGER       REFERENCES estimates(id) ON DELETE SET NULL,  -- если это ЛСР допсоглашения
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_estimates_project_id ON estimates(project_id);
CREATE INDEX idx_estimates_contract_id ON estimates(contract_id);
```

### 3.12. estimate_items

Позиции сметы. Каждая позиция содержит код расценки (ФЕР/ГЭСН), наименование, объём, единицу измерения, цену за единицу и тип затрат (труд, материалы, машины). Вычисляемый столбец `total_price` автоматически рассчитывает стоимость позиции.

```sql
CREATE TABLE estimate_items (
    id              SERIAL PRIMARY KEY,
    estimate_id     INTEGER       NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    position        INTEGER       NOT NULL,
    name            VARCHAR(500)  NOT NULL,
    volume          NUMERIC(12,3),
    unit            VARCHAR(20),
    rate_code       VARCHAR(50),                            -- код расценки (ГЭСН/ФЕР)
    unit_price      NUMERIC(12,2),
    total_price     NUMERIC(15,2) GENERATED ALWAYS AS (volume * unit_price) STORED,
    cost_type       VARCHAR(20),                            -- "labor" | "materials" | "machines"
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_estimate_items_estimate_id ON estimate_items(estimate_id);
CREATE INDEX idx_estimate_items_name ON estimate_items USING gin(name gin_trgm_ops);
CREATE INDEX idx_estimate_items_rate_code ON estimate_items(rate_code);
```

### 3.13. supplements

Дополнительные соглашения. Каждое допсоглашение привязано к договору, может ссылаться на ВОР (дополнительные объёмы) и сметный расчёт (осмечивание дополнительных работ).

```sql
CREATE TABLE supplements (
    id                  SERIAL PRIMARY KEY,
    contract_id         INTEGER       NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    number              INTEGER       NOT NULL,               -- номер допсоглашения
    date                DATE,
    vor_id              INTEGER       REFERENCES vor(id) ON DELETE SET NULL,
    estimate_id         INTEGER       REFERENCES estimates(id) ON DELETE SET NULL,
    additional_cost     NUMERIC(15,2),
    description         TEXT,
    file_path           VARCHAR(1000),
    status              VARCHAR(20)   NOT NULL DEFAULT 'draft',  -- "draft" | "signed" | "pending"
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_supplements_contract_id ON supplements(contract_id);
CREATE INDEX idx_supplements_number ON supplements(contract_id, number);
```

### 3.14. acts

Акты (АОСР, входной контроль, скрытые работы, освидетельствование). Каждый акт привязан к проекту и договору, содержит описание работ, представителей (JSONB), материалы (JSONB) и чертежи (JSONB). Генерация актов осуществляется агентом ПТО через инструмент asd_generate_act.

```sql
CREATE TABLE acts (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    contract_id     INTEGER      REFERENCES contracts(id) ON DELETE SET NULL,
    type            VARCHAR(30)  NOT NULL,                   -- "aosr" | "incoming_control" | "hidden_works" | "inspection"
    number          INTEGER,                                 -- номер акта
    act_date        DATE,
    work_description TEXT,
    representatives JSONB,                                   -- подписанты
    materials       JSONB,                                   -- материалы
    drawings        JSONB,                                   -- чертежи
    file_path       VARCHAR(1000),                           -- путь к DOCX
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft',   -- "draft" | "signed" | "sent"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_acts_project_id ON acts(project_id);
CREATE INDEX idx_acts_type ON acts(type);
CREATE INDEX idx_acts_act_date ON acts(act_date);
```

### 3.15. letters

Письма, уведомления, заявки. Каждое письмо привязано к проекту и (опционально) договору, содержит получателя, тему, текст, срочность и вложения. Направление (входящее/исходящее) различается полем `direction`. Генерация писем осуществляется агентом Делопроизводитель через инструмент asd_generate_letter.

```sql
CREATE TABLE letters (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    contract_id     INTEGER      REFERENCES contracts(id) ON DELETE SET NULL,
    type            VARCHAR(20)  NOT NULL,                   -- "notification" | "request" | "application" | "claim" | "inquiry"
    recipient       VARCHAR(200) NOT NULL,
    subject         VARCHAR(500),
    content         TEXT,
    urgency         VARCHAR(10)  NOT NULL DEFAULT 'normal',  -- "normal" | "urgent"
    attachments     JSONB,
    file_path       VARCHAR(1000),
    direction       VARCHAR(10)  NOT NULL,                   -- "outgoing" | "incoming"
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft',   -- "draft" | "sent" | "received" | "answered"
    sent_at         TIMESTAMPTZ,
    received_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_letters_project_id ON letters(project_id);
CREATE INDEX idx_letters_type ON letters(type);
CREATE INDEX idx_letters_direction ON letters(direction);
CREATE INDEX idx_letters_status ON letters(status);
CREATE INDEX idx_letters_recipient ON letters USING gin(recipient gin_trgm_ops);
```

### 3.16. registrations

Регистрация входящих документов. Каждая запись содержит регистрационный номер, источник, тип документа и срок ответа. Триггер автоматически обновляет статус на «overdue» при просрочке. Регистрационный номер генерируется по формату «ВХ-{год}-{порядковый номер}».

```sql
CREATE TABLE registrations (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER      REFERENCES documents(id) ON DELETE SET NULL,
    letter_id           INTEGER      REFERENCES letters(id) ON DELETE SET NULL,
    project_id          INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    registration_number VARCHAR(50)  NOT NULL,                -- "ВХ-2026-127"
    registration_date   DATE         NOT NULL DEFAULT CURRENT_DATE,
    source              VARCHAR(200) NOT NULL,
    doc_type            VARCHAR(20)  NOT NULL,
    deadline            DATE,
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',  -- "active" | "answered" | "overdue"
    answered_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_registrations_project_id ON registrations(project_id);
CREATE INDEX idx_registrations_status ON registrations(status);
CREATE INDEX idx_registrations_deadline ON registrations(deadline);
CREATE INDEX idx_registrations_number ON registrations(registration_number);

-- Автоматическая генерация номера
-- Реализуется на уровне приложения: "ВХ-{year}-{seq}"
```

### 3.17. shipments

Отправки документов Заказчику. Каждая отправка содержит тип пакета (ИД, КС, протокол, претензия, прочее), сопроводительное письмо, реестр и список документов. Отслеживается статус доставки и трекинг-номер.

```sql
CREATE TABLE shipments (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    contract_id     INTEGER      REFERENCES contracts(id) ON DELETE SET NULL,
    type            VARCHAR(20)  NOT NULL,                   -- "id" | "ks" | "protocol" | "claim" | "other"
    cover_letter_path VARCHAR(1000),
    registry_path   VARCHAR(1000),
    documents       JSONB        NOT NULL,                   -- [{id, name, type}]
    recipient_name  VARCHAR(200) NOT NULL,
    recipient_address TEXT,
    recipient_inn   VARCHAR(12),
    recipient_contact VARCHAR(100),
    sent_at         TIMESTAMPTZ,
    tracking_number VARCHAR(50),
    status          VARCHAR(20)  NOT NULL DEFAULT 'prepared',  -- "prepared" | "sent" | "delivered" | "returned"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_shipments_project_id ON shipments(project_id);
CREATE INDEX idx_shipments_status ON shipments(status);
CREATE INDEX idx_shipments_sent_at ON shipments(sent_at);
```

### 3.18. wiki_articles

Статьи базы знаний. Каждая статья содержит Markdown-контент, извлечённые сущности (JSONB), нормативные ссылки (JSONB) и оценку достоверности. Статьи могут замещать друг друга (superseded_by), что обеспечивает версионность знаний.

```sql
CREATE TABLE wiki_articles (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    title               VARCHAR(500) NOT NULL,
    content             TEXT         NOT NULL,                 -- Markdown
    source              VARCHAR(200),
    source_document_id  INTEGER      REFERENCES documents(id) ON DELETE SET NULL,
    entities            JSONB,                                  -- извлечённые сущности
    normative_refs      JSONB,                                  -- нормативные ссылки
    confidence          NUMERIC(3,2) DEFAULT 0.5,
    superseded_by       INTEGER      REFERENCES wiki_articles(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_wiki_project_id ON wiki_articles(project_id);
CREATE INDEX idx_wiki_title ON wiki_articles USING gin(title gin_trgm_ops);
CREATE INDEX idx_wiki_content ON wiki_articles USING gin(content gin_trgm_ops);
```

### 3.19. vendors

Поставщики материалов и услуг (контрагенты). Каждый поставщик идентифицируется по ИНН, имеет внутренний рейтинг (0–5) и статус (active/blacklisted). Данные используются агентами Закупщик и Логист для поиска и сравнения поставщиков.

```sql
CREATE TABLE vendors (
    id              SERIAL PRIMARY KEY,
    inn             VARCHAR(12)  UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    contact_person  VARCHAR(200),
    email           VARCHAR(100),
    phone           VARCHAR(50),
    rating          NUMERIC(3,2),                           -- внутренний рейтинг 0..5
    status          VARCHAR(20)  NOT NULL DEFAULT 'active', -- "active" | "blacklisted"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_vendors_inn ON vendors(inn);
CREATE INDEX idx_vendors_name ON vendors USING gin(name gin_trgm_ops);
```

### 3.20. materials_catalog

Единый справочник номенклатуры материалов (ТМЦ). Каждая позиция имеет уникальный артикул (SKU), наименование, категорию и единицу измерения. Используется для сопоставления позиций из коммерческих предложений с внутренним справочником.

```sql
CREATE TABLE materials_catalog (
    id              SERIAL PRIMARY KEY,
    sku             VARCHAR(100) UNIQUE,                    -- артикул (если есть)
    name            VARCHAR(500) NOT NULL,
    category        VARCHAR(100),                           -- "Металлопрокат", "Нерудные"
    unit            VARCHAR(20)  NOT NULL,                  -- "тн", "м3", "шт"
    description     TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_materials_name ON materials_catalog USING gin(name gin_trgm_ops);
CREATE INDEX idx_materials_category ON materials_catalog(category);
```

### 3.21. price_lists

Прайс-листы и коммерческие предложения от поставщиков. Каждый прайс-лист привязан к поставщику, имеет срок действия и статус. Если КП получено по запросу (RFQ), указывается идентификатор партии запроса.

```sql
CREATE TABLE price_lists (
    id              SERIAL PRIMARY KEY,
    vendor_id       INTEGER      NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    document_id     INTEGER      REFERENCES documents(id) ON DELETE SET NULL,
    valid_from      DATE,
    valid_until     DATE,
    file_path       VARCHAR(1000),
    rfq_batch_id    INTEGER,                                -- если получено по запросу (RFQ)
    status          VARCHAR(20)  NOT NULL DEFAULT 'parsed', -- "parsed" | "active" | "expired"
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_price_lists_vendor_id ON price_lists(vendor_id);
CREATE INDEX idx_price_lists_status ON price_lists(status);
```

### 3.22. price_list_items

Конкретные позиции из КП/прайс-листов (цены). Каждая позиция содержит наименование как в КП (raw_name), единицу измерения, цену, валюту и условия доставки. Опционально привязывается к позиции справочника материалов (material_id). Флаг `is_best_offer` отмечает лучшие предложения по результатам сравнения агентом Закупщик.

```sql
CREATE TABLE price_list_items (
    id              SERIAL PRIMARY KEY,
    price_list_id   INTEGER       NOT NULL REFERENCES price_lists(id) ON DELETE CASCADE,
    material_id     INTEGER       REFERENCES materials_catalog(id) ON DELETE SET NULL,
    raw_name        VARCHAR(500)  NOT NULL,                 -- как названо в КП
    unit            VARCHAR(20)   NOT NULL,
    price           NUMERIC(15,2) NOT NULL,                 -- цена за единицу
    currency        VARCHAR(10)   DEFAULT 'RUB',
    delivery_terms  VARCHAR(100),                           -- "EXW", "DDP"
    is_best_offer   BOOLEAN       DEFAULT false,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_price_list_items_list_id ON price_list_items(price_list_id);
CREATE INDEX idx_price_list_items_material_id ON price_list_items(material_id);
CREATE INDEX idx_price_list_items_raw_name ON price_list_items USING gin(raw_name gin_trgm_ops);
```

### 3.23. audit_log

Журнал аудита (все действия в системе). Каждая запись содержит имя MCP-инструмента, действие, входные/выходные данные, статус выполнения и длительность. Для больших объёмов рекомендуется партиционирование по времени.

```sql
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    project_id      INTEGER      REFERENCES projects(id) ON DELETE SET NULL,
    tool_name       VARCHAR(50)  NOT NULL,                   -- имя MCP инструмента
    action          VARCHAR(50)  NOT NULL,                   -- "upload" | "analyze" | "generate" | "search"
    input_data      JSONB,                                   -- входные аргументы
    output_data     JSONB,                                   -- результат
    status          VARCHAR(10)  NOT NULL,                   -- "success" | "error"
    error_message   TEXT,
    duration_ms     INTEGER,                                 -- время выполнения в мс
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_project_id ON audit_log(project_id);
CREATE INDEX idx_audit_tool_name ON audit_log(tool_name);
CREATE INDEX idx_audit_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_status ON audit_log(status);

-- Партиционирование по времени для больших объёмов (опционально)
-- PARTITION BY RANGE (created_at)
```

---

## 4. ОБЩИЕ СВЯЗИ

Диаграмма связей между таблицами. Стрелки обозначают отношение «один ко многим» (1 → N) или «один к одному» (1 → 1). Корневой сущностью является таблица `projects`, от которой расходятся связи ко всем основным таблицам. Таблица `contracts` является центральным узлом для ProtocolPartyInfo — реквизиты сторон, сохранённые в contracts, используются всеми агентами при генерации документов.

```
projects (1) ──── (N) documents
projects (1) ──── (N) vor
projects (1) ──── (N) estimates
projects (1) ──── (N) acts
projects (1) ──── (N) letters
projects (1) ──── (N) registrations
projects (1) ──── (N) wiki_articles
projects (1) ──── (N) shipments
projects (1) ──── (N) contracts

documents (1) ──── (N) chunks
documents (1) ──── (1) contracts
documents (1) ──── (N) trap_matches

contracts (1) ──── (N) claims        [ProtocolPartyInfo → шапки документов]
contracts (1) ──── (N) vor
contracts (1) ──── (N) estimates
contracts (1) ──── (N) supplements

claims (1) ──── (1) lawsuits

vor (1) ──── (N) vor_items
vor (1) ──── (1) estimates (через vor_id)

estimates (1) ──── (N) estimate_items
estimates (1) ──── (N) supplements (через supplement_of)

traps (1) ──── (N) trap_matches

letters (1) ──── (1) registrations

vendors (1) ──── (N) price_lists
materials_catalog (1) ──── (N) price_list_items
price_lists (1) ──── (N) price_list_items
```

---

## 5. ИНДЕКСЫ — СВОДКА

### B-tree (стандартные)
- Все PRIMARY KEY
- Все FOREIGN KEY (для JOIN)
- Статусы, даты, числа для фильтрации

### GIN (полнотекстовый)
- `documents.file_name` — нечёткий поиск по имени
- `chunks.text` — полнотекстовый поиск
- `traps.pattern` — поиск паттернов
- `vor_items.name`, `estimate_items.name` — fuzzy поиск наименований
- `letters.recipient`, `wiki_articles.title`, `wiki_articles.content`
- `vendors.name`, `materials_catalog.name`, `price_list_items.raw_name` — fuzzy-мэтчинг ТМЦ и КА

### HNSW (векторный, pgvector)
- `chunks.embedding` — основной векторный поиск (bge-m3, 1024 dim)
- `traps.pattern_embedding` — semantic matching ловушек

### Вычисляемые столбцы (GENERATED ALWAYS)
- `claims.total_amount` = debt + penalty
- `lawsuits.total_amount` = claim + penalty + legal
- `vor_items.total_price` = volume * unit_price
- `estimate_items.total_price` = volume * unit_price

---

## 6. ТРИГГЕРЫ

### 6.1. Автоматическое обновление updated_at

При каждом обновлении записи в таблицах, содержащих столбец `updated_at`, триггер автоматически устанавливает текущую временную метку. Это обеспечивает корректное отслеживание времени последнего изменения без необходимости явного указания в коде приложения.

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- На все таблицы с updated_at
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
-- ... аналогично для contracts, claims, lawsuits, estimates, acts, letters,
--     registrations, shipments, wiki_articles, vendors, materials_catalog,
--     price_lists, traps, supplements
```

### 6.2. Автоматическое обновление статуса registrations

Триггер проверяет срок ответа при каждой вставке или обновлении записи в таблице `registrations`. Если срок истёк, а статус всё ещё «active», он автоматически меняется на «overdue». Это обеспечивает своевременное выявление просроченных входящих документов.

```sql
CREATE OR REPLACE FUNCTION check_registration_deadline()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.deadline IS NOT NULL AND NEW.deadline < CURRENT_DATE AND NEW.status = 'active' THEN
        NEW.status = 'overdue';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_registrations_deadline
    BEFORE INSERT OR UPDATE ON registrations
    FOR EACH ROW EXECUTE FUNCTION check_registration_deadline();
```

### 6.3. Автоматический audit_log

Заготовка триггера для расширенной логики аудита. Может быть дополнена уведомлениями и алертами при определённых событиях (например, при ошибке выполнения MCP-инструмента).

```sql
CREATE OR REPLACE FUNCTION log_tool_call()
RETURNS TRIGGER AS $$
BEGIN
    -- Вызывается при каждой записи в audit_log
    -- Можно добавить дополнительную логику (уведомления, алерты)
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## 7. РАЗМЕР ДАННЫХ И ОЦЕНКА RAM

Для проекта типа «Причалы» (~2 года строительства):

| Таблица | Строк | Размер | RAM при загрузке |
|---------|-------|--------|------------------|
| documents | ~200 | 50 MB | ~20 MB |
| chunks | ~8000 | 500 MB (вкл. embeddings) | ~200 MB |
| contracts | ~10 | 1 MB | ~0.5 MB |
| traps | 58 | 1 MB | ~0.5 MB |
| trap_matches | ~200 | 5 MB | ~2 MB |
| claims | ~5 | 1 MB | ~0.5 MB |
| lawsuits | ~2 | 1 MB | ~0.5 MB |
| vor | ~30 | 5 MB | ~2 MB |
| vor_items | ~15000 | 10 MB | ~5 MB |
| estimates | ~20 | 10 MB | ~5 MB |
| estimate_items | ~3000 | 5 MB | ~2 MB |
| acts | ~100 | 5 MB | ~2 MB |
| letters | ~50 | 5 MB | ~2 MB |
| registrations | ~100 | 5 MB | ~2 MB |
| shipments | ~20 | 5 MB | ~2 MB |
| wiki_articles | ~500 | 10 MB | ~5 MB |
| vendors | ~100 | 2 MB | ~1 MB |
| materials_catalog | ~5000 | 10 MB | ~5 MB |
| price_lists | ~50 | 5 MB | ~2 MB |
| price_list_items | ~2000 | 5 MB | ~2 MB |
| audit_log | ~2000 | 10 MB | ~5 MB |
| **Итого** | **~36,000** | **~650 MB** | **~265 MB** |

Embeddings — основной потребитель места:
- 8000 chunks × 1024 dim × 4 byte (float32) ≈ 32 MB
- Индекс HNSW ≈ 2-3x данных ≈ 64-96 MB

Оценка RAM для LLM-моделей (4-bit квантизация):
- Gemma 4 31B 4-bit (VLM): ~23 GB (5 рабочих агентов, shared)
- Llama 3.3 70B 4-bit: ~40 GB (Руководитель проекта/PM, отдельный профиль)
- Gemma 4 E4B 4-bit: ~3 GB (Делопроизводитель)
- bge-m3-mlx-4bit (embeddings): ~0.3 GB
- **Итого VRAM:** ~66 GB (3 уникальные модели: Llama 70B + Gemma 4 31B + Gemma 4 E4B)

При последовательной обработке агентов (один Gemma 4 31B экземпляр, переключение контекста):
- **Минимальная конфигурация:** 78 GB VRAM (Gemma 4 31B + Gemma 4 E4B + bge-m3)
- **Полная конфигурация:** 128 GB VRAM (Gemma 4 31B + Llama 3.3 70B + Gemma 4 E4B + bge-m3)

---

## 8. МИГРАЦИИ (Alembic)

При первом развёртывании:

```
migrations/
├── versions/
│   ├── 001_initial.py           # Все таблицы, индексы, расширения
│   ├── 002_add_supplements.py   # Если добавляем supplements
│   ├── 003_add_registrations.py # Если добавляем регистрации
│   └── ...
├── env.py
└── script.py.mako
```

```bash
alembic upgrade head  # Применить все миграции
```

---

## 9. ДОКУМЕНТАЦИЯ — ПЕРЕКРЁСТНЫЕ ССЫЛКИ

| Документ | Описание | Связь с DATA_SCHEMA |
|----------|----------|---------------------|
| `docs/PROMPTS_GEMMA4.md` | Системные промпты агентов | Промпты извлечения реквизитов → таблица contracts (ProtocolPartyInfo); промпты ловушек → таблица traps (10 категорий); промпты ВОР → vor_items; промпты смет → estimate_items |
| `docs/COMPONENT_ARCHITECTURE.md` | Архитектура АСД v12.0 | LLMEngine → профили mac_studio (Gemma 4 31B), dev_linux (Gemma 4 31B), hermes_pm (Llama 3.3 70B); shared memory → таблицы projects, contracts |
| `docs/MCP_TOOLS_SPEC.md` | Спецификация MCP-инструментов | Каждый инструмент читает/пишет в определённые таблицы; asd_analyze_contract → contracts + trap_matches; asd_generate_protocol → contracts.ProtocolPartyInfo |
| `traps/default_traps.yaml` | Библиотека ловушек субподрядчика | 58 ловушек, 10 категорий → таблица traps; YAML-файлы → source_file |
| `docs/DEPLOYMENT_PLAN.md` | Развёртывание | PostgreSQL 16 + pgvector; VRAM оценки; конфигурация LLMEngine |

---

Документ актуализирован (v12.0, 20 апреля 2026). SQLAlchemy модели реализованы в `src/db/models.py`. Схема будет расширяться по мере реализации Packages 2-10. ProtocolPartyInfo интегрирован в таблицу contracts и является единым источником реквизитов для всех агентов.
