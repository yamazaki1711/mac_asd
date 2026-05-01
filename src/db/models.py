from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Boolean, Index
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    status = Column(String(50), default="active") # active, archived, completed
    
    documents = relationship("Document", back_populates="project")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512))
    doc_type = Column(String(50)) # VOR, Smeta, Contract, Drawing
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    
    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    content = Column(Text, nullable=False)
    # Вектор эмбеддинга (bge-m3 = 1024 dim)
    embedding = Column(Vector(1024)) 
    page_number = Column(Integer)
    
    document = relationship("Document", back_populates="chunks")

class AuditLog(Base):
    """
    Критически важная таблица для обучения Hermes.
    Сюда пишутся все действия агентов для последующей рефлексии.
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(50)) # Hermes, PTO, Smeta...
    action = Column(String(100))
    input_data = Column(JSON)
    output_data = Column(JSON)
    duration_ms = Column(Integer)
    timestamp = Column(DateTime, server_default=func.now())
    # Поле для отметки, было ли это действие проанализировано для обучения
    is_learned = Column(Boolean, default=False)

class DomainTrap(Base):
    """
    Доменные ловушки — структурированные риски из Telegram или опыта.
    v12.0.0: Обобщено с LegalTrap до DomainTrap — поддержка всех 5 доменов агентов.

    Домены: legal, pto, smeta, logistics, procurement
    """
    __tablename__ = "domain_traps"

    id = Column(Integer, primary_key=True)
    domain = Column(String(50), nullable=False, default="legal")  # legal | pto | smeta | logistics | procurement
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    source = Column(String(255))  # e.g., "Telegram @advokatgrikevich", "Internal"
    channel = Column(String(255))  # Username канала (e.g., "advokatgrikevich")
    category = Column(String(100))  # Доменно-специфичная категория
    weight = Column(Integer, default=100)  # Вес 0-100 для RAG scoring
    court_cases = Column(JSON)  # e.g. ["А40-123/2023"]
    mitigation = Column(Text)  # Рекомендация по защите
    created_at = Column(DateTime, server_default=func.now())

    # Вектор для RAG (bge-m3 = 1024 dim)
    embedding = Column(Vector(1024))

# Обратная совместимость
LegalTrap = DomainTrap

# --- LOGISTICS & PROCUREMENT TABLES ---

class Vendor(Base):
    """
    База поставщиков и транспортных компаний.
    """
    __tablename__ = "vendors"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    contact_info = Column(JSON) # {email, phone, representative}
    rating = Column(Integer, default=5) # 1-5
    category = Column(String(100)) # "Materials", "Transport", "Services"
    inn = Column(String(12), unique=True) # ИНН для идентификации
    created_at = Column(DateTime, server_default=func.now())
    
    price_lists = relationship("PriceList", back_populates="vendor")

class MaterialCatalog(Base):
    """
    Мастер-данные ТМЦ (Номенклатура).
    """
    __tablename__ = "materials_catalog"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(512), nullable=False) # Наименование (ГОСТ, ТУ)
    category = Column(String(100)) # "Металл", "Бетон", "Инертные"
    unit = Column(String(20)) # "т", "м3", "шт"
    avg_price = Column(Integer) # Средневзвешенная цена (копейки)
    
    # Вектор для нечеткого поиска (bge-m3 = 1024 dim)
    embedding = Column(Vector(1024))
    
    # Индекс для быстрого поиска по наименованию
    __table_args__ = (
        Index('ix_material_name_trgm', name, postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'}),
    )

class PriceList(Base):
    """
    Заголовки коммерческих предложений или прайс-листов.
    """
    __tablename__ = "price_lists"
    
    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    document_id = Column(Integer, ForeignKey("documents.id")) # Ссылка на PDF в базе документов
    valid_until = Column(DateTime)
    currency = Column(String(3), default="RUB")
    created_at = Column(DateTime, server_default=func.now())
    
    vendor = relationship("Vendor", back_populates="price_lists")
    items = relationship("PriceListItem", back_populates="price_list")

class PriceListItem(Base):
    """
    Позиции в прайс-листах (конкретные цены на материалы).
    """
    __tablename__ = "price_list_items"
    
    id = Column(Integer, primary_key=True)
    price_list_id = Column(Integer, ForeignKey("price_lists.id"))
    material_id = Column(Integer, ForeignKey("materials_catalog.id"))
    price_value = Column(Integer, nullable=False) # В копейках
    quantity_available = Column(Integer) # Остаток у поставщика
    
    price_list = relationship("PriceList", back_populates="items")

# --- LABORATORY CONTROL TABLES ---

class LabOrganization(Base):
    """Аккредитованные лаборатории для строительного контроля."""
    __tablename__ = "lab_organizations"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(512), nullable=False)
    inn = Column(String(12), unique=True)
    accreditation_number = Column(String(50))
    accreditation_date = Column(DateTime)
    category = Column(String(100))  # construction_lab, geotechnical_lab, welding_lab, concrete_lab
    rating = Column(Integer, default=5)  # 1-5
    contact_info = Column(JSON)  # {email, phone, address, representative}
    test_methods = Column(JSON)  # List of accredited test methods
    created_at = Column(DateTime, server_default=func.now())
    
    requests = relationship("LabRequest", back_populates="organization")

class LabRequest(Base):
    """Заявки в лабораторию на испытания."""
    __tablename__ = "lab_requests"
    
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("lab_organizations.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    request_type = Column(String(100))  # commercial_proposal, sample_testing, field_inspection
    status = Column(String(50), default="draft")  # draft, sent, received, in_progress, completed, cancelled
    description = Column(Text)
    deadline = Column(DateTime)
    commercial_proposal = Column(JSON)  # {price, terms, delivery_time}
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    organization = relationship("LabOrganization", back_populates="requests")
    samples = relationship("LabSample", back_populates="request")

class LabSample(Base):
    """Образцы для лабораторных испытаний."""
    __tablename__ = "lab_samples"
    
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("lab_requests.id"))
    sample_type = Column(String(100))  # concrete_cube, steel_specimen, soil, asphalt
    sample_identifier = Column(String(100))  # Маркировка образца
    manufacture_date = Column(DateTime)
    delivery_date = Column(DateTime)
    test_date = Column(DateTime)
    test_method = Column(String(200))  # ГОСТ метода испытания
    result_value = Column(String(100))  # Результат (прочность, марка и т.п.)
    result_status = Column(String(50))  # pass, fail, pending
    created_at = Column(DateTime, server_default=func.now())
    
    request = relationship("LabRequest", back_populates="samples")

class LabContract(Base):
    """Договоры с лабораториями."""
    __tablename__ = "lab_contracts"
    
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("lab_organizations.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    contract_number = Column(String(100))
    contract_date = Column(DateTime)
    contract_value = Column(Integer)  # В копейках
    valid_until = Column(DateTime)
    status = Column(String(50), default="active")  # active, expired, cancelled
    document_id = Column(Integer, ForeignKey("documents.id"))
    created_at = Column(DateTime, server_default=func.now())

class LabAct(Base):
    """Акты выполненных работ лаборатории."""
    __tablename__ = "lab_acts"
    
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey("lab_contracts.id"))
    act_number = Column(String(100))
    act_date = Column(DateTime)
    act_value = Column(Integer)  # В копейках
    description = Column(Text)
    status = Column(String(50), default="issued")  # issued, accepted, rejected
    document_id = Column(Integer, ForeignKey("documents.id"))
    created_at = Column(DateTime, server_default=func.now())

class LabReport(Base):
    """Заключения лаборатории (результаты испытаний)."""
    __tablename__ = "lab_reports"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    organization_id = Column(Integer, ForeignKey("lab_organizations.id"))
    report_number = Column(String(100))
    report_date = Column(DateTime)
    report_type = Column(String(200))  # Тип заключения (прочность бетона, сварка и т.п.)
    conclusion = Column(Text)  # Текст заключения
    status = Column(String(50), default="received")  # received, reviewed, accepted, rejected
    review_notes = Column(Text)
    document_id = Column(Integer, ForeignKey("documents.id"))
    created_at = Column(DateTime, server_default=func.now())

class LabControlPlan(Base):
    """Планы лабораторного контроля по проектам."""
    __tablename__ = "lab_control_plans"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    plan_name = Column(String(255))
    work_types = Column(JSON)  # List of work types requiring lab control
    test_schedule = Column(JSON)  # Schedule of tests
    status = Column(String(50), default="draft")  # draft, approved, in_progress, completed
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# --- LESSONS LEARNED (Опытный контур MAC_ASD v12.0) ---

class LessonLearned(Base):
    """
    Уроки из анализа лотов — институциональная память системы.
    
    Каждый анализ лота может порождать уроки, которые:
    1. Хранятся в БД с эмбеддингами (pgvector)
    2. Извлекаются через RAG при анализе нового лота
    3. После N подтверждений — мутируют в автоматические правила агентов
    
    Категории уроков:
    - coeff_error: Ошибочные коэффициенты в сметах
    - risk: Риски, неочевидные при поверхностном анализе
    - false_risk: Ложные риски (генерируются, но не применимы)
    - norm_violation: Нарушения нормативных требований
    - contract_trap: Опасные условия контракта
    - best_practice: Лучшая практика, выявленная опытным путём
    """
    __tablename__ = "lessons_learned"
    
    id = Column(Integer, primary_key=True)
    lot_number = Column(String(50))        # Номер извещения на Госзакупках
    work_type = Column(String(100))        # Код WorkTypeRegistry (demolition, construction...)
    agent_name = Column(String(50))        # ПТО, Юрист, Сметчик, Закупщик, Логист, Дело
    category = Column(String(50))          # coeff_error, risk, false_risk, norm_violation, contract_trap, best_practice
    title = Column(String(512), nullable=False)   # Краткое описание урока
    description = Column(Text, nullable=False)     # Подробное описание
    severity = Column(String(20))          # critical, high, medium, low
    norm_reference = Column(String(512))   # Ссылка на нормативку (СП, ГОСТ, Приказ...)
    lot_context = Column(JSON)             # Контекст лота: {region, nmck, object_type, ...}
    verified = Column(Boolean, default=False)     # Подтверждено пользователем
    verification_count = Column(Integer, default=0)  # Сколько раз подтвердилось на практике
    auto_rule = Column(Boolean, default=False)    # Мутировало в автоматическое правило?
    auto_rule_text = Column(Text)          # Текст правила для инъекции в промпт
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Вектор для RAG-поиска (bge-m3 = 1024 dim)
    embedding = Column(Vector(1024))


# --- DOMAIN REFERENCE DATA ---

class ReferenceData(Base):
    """
    Унифицированный справочник нормативных данных для всех доменов.

    Заменяет разрозненные Python-дикты (rate_lookup.py, work_spec.py, contract_risks.py)
    единой таблицей с версионированием и кэшированием.

    Домены: legal, pto, smeta, logistics, procurement
    """
    __tablename__ = "domain_references"

    id = Column(Integer, primary_key=True)
    domain = Column(String(50), nullable=False)  # legal | pto | smeta | logistics | procurement
    code = Column(String(100), nullable=False)   # Уникальный код в домене (ФЕР, ГОСТ, тип работы)
    description = Column(Text)                    # Человекочитаемое описание
    data = Column(JSON)                           # Произвольные данные справочника
    valid_from = Column(DateTime)                 # Начало действия
    valid_to = Column(DateTime)                   # Конец действия (null = действующий)
    source = Column(String(255))                  # Источник (ФГИС ЦС, Минстрой, ГОСТ, internal)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Вектор для семантического поиска (bge-m3 = 1024 dim)
    embedding = Column(Vector(1024))

    __table_args__ = (
        Index('ix_ref_domain_code', 'domain', 'code', unique=True),
    )
