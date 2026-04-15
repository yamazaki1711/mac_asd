from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Boolean
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
