"""
MAC_ASD v12.0 — Lessons Learned Service.

Опытный контур системы: CRUD + RAG-поиск по урокам из анализа лотов.

Три уровня:
  1. База уроков (PostgreSQL + pgvector) — хранение и поиск
  2. RAG-инъекция — автоматическая подстановка уроков в контекст агентов
  3. Skill Mutation — автообновление промптов после N подтверждений

Использование:
  from src.core.lessons_service import lessons_service
  
  # Создать урок
  await lessons_service.create_lesson(...)
  
  # Найти похожие уроки для контекста агента
  context = await lessons_service.get_lessons_context("demolition", "Сметчик")
  
  # Верифицировать урок
  await lessons_service.verify_lesson(lesson_id=1)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, and_
from src.core.llm_engine import llm_engine
from src.db.models import LessonLearned
from src.db.init_db import Session

logger = logging.getLogger(__name__)


# Порог подтверждений для мутации в автоматическое правило
AUTO_RULE_THRESHOLD = 3


class LessonsService:
    """
    Сервис для работы с уроками (Lessons Learned).
    
    Обеспечивает:
    - Создание уроков с автоматической генерацией эмбеддингов
    - RAG-поиск похожих уроков по вектору
    - Верификацию уроков пользователем
    - Автоматическую мутацию в правила при достижении порога
    - Формирование контекста для инъекции в промпты агентов
    """

    async def create_lesson(
        self,
        title: str,
        description: str,
        agent_name: str,
        category: str,
        severity: str = "medium",
        work_type: str = "*",
        lot_number: Optional[str] = None,
        norm_reference: Optional[str] = None,
        lot_context: Optional[Dict] = None,
        verified: bool = False,
    ) -> LessonLearned:
        """
        Создать новый урок с автоматической генерацией эмбеддинга.
        
        Args:
            title: Краткое описание урока (до 512 символов)
            description: Подробное описание урока
            agent_name: Имя агента-владельца (ПТО, Юрист, Сметчик...)
            category: Категория (coeff_error, risk, false_risk, norm_violation, contract_trap, best_practice)
            severity: Критичность (critical, high, medium, low)
            work_type: Код вида работ из WorkTypeRegistry (* = все виды)
            lot_number: Номер извещения на Госзакупках
            norm_reference: Ссылка на нормативный документ
            lot_context: Контекст лота (регион, НМЦК, тип объекта...)
            verified: Подтверждено пользователем
            
        Returns:
            Созданный объект LessonLearned
        """
        # Генерируем эмбеддинг из title + description для качественного RAG-поиска
        embed_text = f"{title}\n{description}"
        embedding = await llm_engine.embed(embed_text)
        
        lesson = LessonLearned(
            lot_number=lot_number,
            work_type=work_type,
            agent_name=agent_name,
            category=category,
            title=title,
            description=description,
            severity=severity,
            norm_reference=norm_reference,
            lot_context=lot_context,
            verified=verified,
            verification_count=1 if verified else 0,
            embedding=embedding,
        )
        
        with Session() as session:
            session.add(lesson)
            session.commit()
            session.refresh(lesson)
            logger.info(f"Lesson #{lesson.id} created: [{severity}] {title}")
            return lesson

    async def search_lessons(
        self,
        query: str,
        work_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        verified_only: bool = False,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        RAG-поиск уроков по семантической близости.
        
        Сначала фильтрует по work_type/agent/category/severity,
        затем ранжирует по векторной дистанции.
        
        Args:
            query: Поисковый запрос (например, "снос демонтаж отходы коэффициент")
            work_type: Фильтр по виду работ (demolition, construction...) или None
            agent_name: Фильтр по агенту (ПТО, Юрист...) или None
            category: Фильтр по категории урока или None
            severity: Фильтр по критичности или None
            verified_only: Только верифицированные уроки
            top_k: Количество результатов
            
        Returns:
            Список словарей с данными уроков
        """
        query_embedding = await llm_engine.embed(query)
        
        with Session() as session:
            stmt = select(LessonLearned)
            
            # Фильтры
            conditions = []
            if work_type and work_type != "*":
                # Ищем уроки конкретного вида работ ИЛИ универсальные (*)
                conditions.append(
                    (LessonLearned.work_type == work_type) | (LessonLearned.work_type == "*")
                )
            if agent_name:
                conditions.append(LessonLearned.agent_name == agent_name)
            if category:
                conditions.append(LessonLearned.category == category)
            if severity:
                conditions.append(LessonLearned.severity == severity)
            if verified_only:
                conditions.append(LessonLearned.verified == True)
            
            if conditions:
                stmt = stmt.where(and_(*conditions))
            
            # Векторный поиск
            stmt = stmt.order_by(
                LessonLearned.embedding.l2_distance(query_embedding)
            ).limit(top_k)
            
            results = session.execute(stmt).scalars().all()
            
            return [
                {
                    "id": r.id,
                    "lot_number": r.lot_number,
                    "work_type": r.work_type,
                    "agent_name": r.agent_name,
                    "category": r.category,
                    "title": r.title,
                    "description": r.description,
                    "severity": r.severity,
                    "norm_reference": r.norm_reference,
                    "verified": r.verified,
                    "verification_count": r.verification_count,
                    "auto_rule": r.auto_rule,
                }
                for r in results
            ]

    async def get_lessons_context(
        self,
        work_type: str,
        agent_name: Optional[str] = None,
        task_description: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """
        Сформировать текстовый контекст из уроков для инъекции в промпт агента.
        
        Это ключевой метод для Уровня 2 (RAG-инъекция).
        Агент получает релевантные уроки прямо в своём промпте.
        
        Args:
            work_type: Вид работ из WorkTypeRegistry
            agent_name: Имя агента (для фильтрации по релевантности)
            task_description: Описание задачи (для семантического поиска)
            top_k: Количество уроков в контексте
            
        Returns:
            Строка с отформатированными уроками для вставки в промпт
        """
        # Формируем поисковый запрос из описания задачи или вида работ
        search_query = task_description or f"работы вида {work_type}"
        
        # Ищем уроки: сначала верифицированные, затем все
        verified_lessons = await self.search_lessons(
            query=search_query,
            work_type=work_type,
            agent_name=agent_name,
            verified_only=True,
            top_k=top_k,
        )
        
        if len(verified_lessons) < top_k:
            all_lessons = await self.search_lessons(
                query=search_query,
                work_type=work_type,
                agent_name=agent_name,
                top_k=top_k - len(verified_lessons),
            )
            # Исключаем дубли
            verified_ids = {l["id"] for l in verified_lessons}
            additional = [l for l in all_lessons if l["id"] not in verified_ids]
            verified_lessons.extend(additional)
        
        if not verified_lessons:
            return ""
        
        # Формируем контекст
        severity_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        
        lines = ["\n📚 УРОКИ ИЗ ПРЕДЫДУЩИХ АНАЛИЗОВ (Lessons Learned):"]
        lines.append("=" * 60)
        
        for lesson in verified_lessons[:top_k]:
            icon = severity_icons.get(lesson["severity"], "⚪")
            verified_mark = "✅" if lesson["verified"] else "⚠️"
            lines.append(
                f"{icon} [{lesson['severity'].upper()}] {lesson['title']} {verified_mark}"
            )
            lines.append(f"   Агент: {lesson['agent_name']} | Категория: {lesson['category']}")
            lines.append(f"   {lesson['description']}")
            if lesson["norm_reference"]:
                lines.append(f"   📖 Нормативка: {lesson['norm_reference']}")
            if lesson["verification_count"] > 1:
                lines.append(f"   🔁 Подтверждено {lesson['verification_count']} раз")
            lines.append("")
        
        lines.append("ВНИМАНИЕ: Учти эти уроки при анализе. Не повторяй выявленные ошибки.")
        lines.append("=" * 60)
        
        return "\n".join(lines)

    async def verify_lesson(self, lesson_id: int) -> Optional[LessonLearned]:
        """
        Верифицировать урок (подтвердить пользователем).
        
        При достижении порога подтверждений (AUTO_RULE_THRESHOLD)
        урок помечается как кандидат на мутацию в автоматическое правило.
        
        Args:
            lesson_id: ID урока
            
        Returns:
            Обновлённый объект LessonLearned или None
        """
        with Session() as session:
            lesson = session.query(LessonLearned).filter_by(id=lesson_id).first()
            if not lesson:
                return None
            
            lesson.verified = True
            lesson.verification_count = (lesson.verification_count or 0) + 1
            
            # Проверяем порог для мутации
            if lesson.verification_count >= AUTO_RULE_THRESHOLD and not lesson.auto_rule:
                lesson.auto_rule = True
                lesson.auto_rule_text = self._generate_auto_rule(lesson)
                logger.info(
                    f"Lesson #{lesson.id} reached threshold ({lesson.verification_count}), "
                    f"mutated to auto_rule: {lesson.auto_rule_text[:100]}..."
                )
            
            session.commit()
            session.refresh(lesson)
            return lesson

    async def reject_lesson(self, lesson_id: int) -> bool:
        """
        Отклонить урок (ложное срабатывание).
        
        Удаляет урок из базы.
        
        Args:
            lesson_id: ID урока
            
        Returns:
            True если удалён, False если не найден
        """
        with Session() as session:
            lesson = session.query(LessonLearned).filter_by(id=lesson_id).first()
            if not lesson:
                return False
            session.delete(lesson)
            session.commit()
            logger.info(f"Lesson #{lesson_id} rejected and deleted")
            return True

    async def get_auto_rules(self, work_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получить все автоматические правила для инъекции в промпты.
        
        Это Уровень 3 (Skill Mutation) — правила, которые подтвердились
        достаточное количество раз и теперь автоматически влияют на поведение
        агентов без необходимости RAG-поиска.
        
        Args:
            work_type: Фильтр по виду работ
            
        Returns:
            Список автоматических правил
        """
        with Session() as session:
            stmt = select(LessonLearned).where(LessonLearned.auto_rule == True)
            if work_type and work_type != "*":
                stmt = stmt.where(
                    (LessonLearned.work_type == work_type) | (LessonLearned.work_type == "*")
                )
            
            results = session.execute(stmt).scalars().all()
            
            return [
                {
                    "id": r.id,
                    "work_type": r.work_type,
                    "agent_name": r.agent_name,
                    "category": r.category,
                    "auto_rule_text": r.auto_rule_text,
                    "verification_count": r.verification_count,
                }
                for r in results
            ]

    async def list_lessons(
        self,
        work_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        category: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Список уроков с фильтрацией (без векторного поиска).
        
        Args:
            work_type: Фильтр по виду работ
            agent_name: Фильтр по агенту
            category: Фильтр по категории
            verified_only: Только верифицированные
            limit: Максимум записей
            
        Returns:
            Список словарей с данными уроков
        """
        with Session() as session:
            stmt = select(LessonLearned)
            
            if work_type and work_type != "*":
                stmt = stmt.where(
                    (LessonLearned.work_type == work_type) | (LessonLearned.work_type == "*")
                )
            if agent_name:
                stmt = stmt.where(LessonLearned.agent_name == agent_name)
            if category:
                stmt = stmt.where(LessonLearned.category == category)
            if verified_only:
                stmt = stmt.where(LessonLearned.verified == True)
            
            stmt = stmt.order_by(LessonLearned.created_at.desc()).limit(limit)
            
            results = session.execute(stmt).scalars().all()
            
            return [
                {
                    "id": r.id,
                    "lot_number": r.lot_number,
                    "work_type": r.work_type,
                    "agent_name": r.agent_name,
                    "category": r.category,
                    "title": r.title,
                    "severity": r.severity,
                    "verified": r.verified,
                    "verification_count": r.verification_count,
                    "auto_rule": r.auto_rule,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in results
            ]

    def _generate_auto_rule(self, lesson: LessonLearned) -> str:
        """
        Сгенерировать текст автоматического правила из урока.
        
        Правило формулируется как прямое указание агенту.
        """
        if lesson.category == "coeff_error":
            return (
                f"ОБЯЗАТЕЛЬНО проверяй коэффициенты пересчёта в сметах на {lesson.work_type}. "
                f"Урок: {lesson.title}. {lesson.description}"
            )
        elif lesson.category == "risk":
            return (
                f"УЧИТЫВАЙ риск: {lesson.title}. "
                f"{lesson.description}"
            )
        elif lesson.category == "false_risk":
            return (
                f"НЕ ГЕНЕРИРУЙ ложный риск: {lesson.title}. "
                f"{lesson.description}"
            )
        elif lesson.category == "contract_trap":
            return (
                f"ВНИМАНИЕ на ловушку контракта: {lesson.title}. "
                f"{lesson.description}"
            )
        elif lesson.category == "norm_violation":
            return (
                f"ПРОВЕРЯЙ соблюдение нормативки: {lesson.title}. "
                f"{lesson.description}"
            )
        else:  # best_practice
            return (
                f"ПРИМЕНЯЙ лучшую практику: {lesson.title}. "
                f"{lesson.description}"
            )


# Синглтон
lessons_service = LessonsService()
