"""
ASD v13.0 — HITL System (Human-in-the-Loop).

Генерирует умные вопросы оператору по разрывам в Evidence Graph.
Приоритизирует по impact'у на комплектность ИД.
Принимает ответы → обновляет confidence в графе.

Usage:
    from src.core.hitl_system import hitl_system
    
    questions = hitl_system.generate_questions(evidence_graph, chain_report)
    for q in questions:
        print(f"[{q.priority}] {q.text}")
    
    # После ответа оператора:
    hitl_system.apply_answer(evidence_graph, question_id, answer)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════

class HITLPriority(str, Enum):
    CRITICAL = "critical"   # Без ответа невозможно продолжить восстановление
    HIGH = "high"           # Существенно влияет на комплектность
    MEDIUM = "medium"       # Важно, но не блокирует
    LOW = "low"             # Формальность


class QuestionType(str, Enum):
    MISSING_DOCUMENT = "missing_document"       # Документ отсутствует
    MISSING_DATE = "missing_date"               # Нет даты
    MISSING_SIGNATURE = "missing_signature"     # Нет подписей
    AMBIGUOUS_WORK = "ambiguous_work"           # Неясно, какие работы велись
    MATERIAL_SOURCE = "material_source"         # Откуда материал
    PERSON_IDENTITY = "person_identity"         # Кто подписант/исполнитель


@dataclass
class HITLQuestion:
    """Один вопрос оператору."""
    id: str
    priority: HITLPriority
    qtype: QuestionType
    text: str                               # Краткий вопрос
    context: str                            # Что система уже знает
    graph_nodes: List[str] = field(default_factory=list)  # Связанные узлы графа
    suggested_answers: List[str] = field(default_factory=list)
    expected_answer_type: str = "text"       # text / date / number / choice
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    answered: bool = False
    answer: Optional[str] = None


@dataclass
class HITLSession:
    """Сессия Human-in-the-Loop."""
    session_id: str = field(default_factory=lambda: str(uuid4())[:8])
    questions: List[HITLQuestion] = field(default_factory=list)
    answered_count: int = 0
    total_count: int = 0
    
    @property
    def progress(self) -> float:
        return self.answered_count / self.total_count if self.total_count else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Question Templates
# ═══════════════════════════════════════════════════════════════════════════

QUESTION_TEMPLATES = {
    QuestionType.MISSING_DOCUMENT: {
        "aosr": {
            "text": "АОСР на {work_type} — когда выполнялось освидетельствование?",
            "context": "КС-2 и сертификаты указывают, что {work_type} выполнены в объёме {volume} {unit}. АОСР в папке не обнаружен.",
            "suggestions": [
                "АОСР подписан, приложу скан",
                "АОСР не оформлялся — нужно повторное освидетельствование",
                "Работы не выполнялись",
            ],
        },
        "certificate": {
            "text": "Сертификат на {material_name} (партия {batch}) — где находится?",
            "context": "Материал использован в работе «{work_type}». КС-2 подтверждает объём {quantity} {unit}. Сертификат в папке не найден.",
            "suggestions": [
                "Сертификат есть, приложу скан",
                "Сертификат утерян — запросить копию у поставщика",
                "Сертификата не было — материал без документов",
            ],
        },
        "ks2": {
            "text": "КС-2 на {work_type} — какой объём и стоимость?",
            "context": "АОСР №{aosr_num} подтверждает {work_type}. КС-2 в папке не найден.",
            "suggestions": [
                "КС-2 есть, приложу",
                "КС-2 не оформлялся",
            ],
        },
        "executive_scheme": {
            "text": "Исполнительная схема на {work_type} — есть?",
            "context": "ГОСТ Р 51872-2024 требует ИС для {work_type}. В папке не найдена.",
            "suggestions": [
                "ИС есть, приложу",
                "ИС не делали — нужна геодезическая съёмка",
            ],
        },
        "journal": {
            "text": "{journal_name} на {work_type} — вёлся?",
            "context": "СП 70.13330.2012 требует {journal_name} для {work_type}. Журнал не найден.",
            "suggestions": [
                "Журнал есть, приложу",
                "Журнал не вёлся",
            ],
        },
    },
    QuestionType.MISSING_DATE: {
        "text": "Когда выполнялись работы «{work_type}»?",
        "context": "Есть поставка материала {delivery_date} и КС-2, но даты работ не зафиксированы. Inference Engine оценивает: {inferred_dates}.",
        "suggestions": [
            "Точные даты: ",
            "Примерно в период: ",
            "Не знаю",
        ],
    },
    QuestionType.AMBIGUOUS_WORK: {
        "text": "Какие работы велись {date_range}?",
        "context": "КС-2 показывает {work_type} на {volume} {unit}. АОСР #{aosr_num} от {aosr_date}. Между поставкой и АОСР — лакуна в журнале.",
        "suggestions": [
            "В эти дни: (опишите работы)",
            "Никакие — простой",
        ],
    },
    QuestionType.MATERIAL_SOURCE: {
        "text": "Поставщик материала «{material_name}»?",
        "context": "Сертификат есть, но нет ТТН и данных о поставщике в графе.",
        "suggestions": [
            "Поставщик: (название)",
            "Неизвестно",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# HITL System
# ═══════════════════════════════════════════════════════════════════════════

class HITLSystem:
    """
    Система Human-in-the-Loop.
    
    Анализирует Evidence Graph и ChainReport, генерирует
    приоритизированные вопросы оператору для заполнения разрывов.
    """

    def __init__(self):
        self._templates = QUESTION_TEMPLATES
        self._sessions: Dict[str, HITLSession] = {}

    def generate_questions(
        self,
        graph,
        chain_report=None
    ) -> List[HITLQuestion]:
        """
        Сгенерировать вопросы по разрывам в графе.
        
        Args:
            graph: EvidenceGraph instance
            chain_report: Optional ChainReport (если уже построен)
        
        Returns:
            Приоритизированный список вопросов
        """
        from src.core.evidence_graph import (
            DocType, DocStatus, EdgeType, WorkUnitStatus
        )
        from src.core.chain_builder import chain_builder, GapSeverity
        
        questions = []
        
        # ── 1. Анализ низкоуверенных узлов ────────────────────────────
        low_conf = graph.get_low_confidence_nodes(threshold=0.6)
        for node in low_conf:
            ntype = node.get('node_type', '')
            conf = node.get('confidence', 0)
            
            if ntype == 'WorkUnit':
                wu_type = node.get('work_type', '')
                status = node.get('status', '')
                if status == WorkUnitStatus.INFERRED.value:
                    questions.append(HITLQuestion(
                        id=f"hq_wu_{node['id']}",
                        priority=HITLPriority.HIGH,
                        qtype=QuestionType.MISSING_DATE,
                        text=f"Когда выполнялись «{wu_type}»? (inferred, conf={conf:.2f})",
                        context=f"Inference Engine вывел эту работу из косвенных данных. Требуется подтверждение.",
                        graph_nodes=[node['id']],
                        suggested_answers=["Подтверждаю", "Не выполнялись", "Другие даты:"],
                    ))
            
            elif ntype == 'Document':
                dtype = node.get('doc_type', '')
                dnum = node.get('doc_number', '')
                questions.append(HITLQuestion(
                    id=f"hq_doc_{node['id']}",
                    priority=HITLPriority.MEDIUM,
                    qtype=QuestionType.MISSING_SIGNATURE,
                    text=f"Подтвердите подлинность {dtype} {dnum} (conf={conf:.2f})",
                    context=f"Документ классифицирован с низкой уверенностью. Возможно, скан нечитаем.",
                    graph_nodes=[node['id']],
                    suggested_answers=["Подлинный", "Копия", "Не могу подтвердить"],
                ))
        
        # ── 2. Анализ orphan-документов ────────────────────────────────
        orphans = graph.get_orphan_documents()
        for orphan in orphans:
            questions.append(HITLQuestion(
                id=f"hq_orphan_{orphan['id']}",
                priority=HITLPriority.HIGH,
                qtype=QuestionType.MISSING_DOCUMENT,
                text=f"Найдите файл документа: {orphan.get('doc_type','')} {orphan.get('doc_number','')}",
                context=f"Упомянут в {orphan.get('work_unit_id','')}, но файл отсутствует",
                graph_nodes=[orphan['id']],
                suggested_answers=["Приложу файл", "Файла нет", "Не мой документ"],
            ))
        
        # ── 3. Анализ цепочек (из ChainReport) ─────────────────────────
        if chain_report is None:
            try:
                chains = chain_builder.build_chains(graph)
                chain_report = chain_builder.generate_report(chains)
            except (ValueError, AttributeError, RuntimeError) as e:
                logger.warning("Chain build failed, skipping chain questions: %s", e)
                chain_report = None
        
        if chain_report:
            for chain in chain_report.chains:
                for gap in chain.gaps:
                    q = self._gap_to_question(chain, gap)
                    if q:
                        questions.append(q)
        
        # ── 4. Лакуны в журнале (для JournalReconstructor) ────────────
        work_units = graph.get_work_units()
        dated_wus = [w for w in work_units if w.get('start_date')]
        if len(dated_wus) >= 2:
            dated_wus.sort(key=lambda w: w.get('start_date', ''))
            for i in range(len(dated_wus) - 1):
                wu1, wu2 = dated_wus[i], dated_wus[i+1]
                d1, d2 = wu1.get('start_date', ''), wu2.get('start_date', '')
                # Gaps > 5 days might need filling
                try:
                    from datetime import date, timedelta
                    date1 = date.fromisoformat(d1)
                    date2 = date.fromisoformat(d2)
                    gap_days = (date2 - date1).days
                    if gap_days > 5:
                        questions.append(HITLQuestion(
                            id=f"hq_gap_{wu1['id']}_{wu2['id']}",
                            priority=HITLPriority.MEDIUM,
                            qtype=QuestionType.AMBIGUOUS_WORK,
                            text=f"Какие работы велись {d1}–{d2} (разрыв {gap_days} дн.)?",
                            context=f"Между «{wu1.get('work_type','')}» и «{wu2.get('work_type','')}» — лакуна в {gap_days} дней. Нет записей в журнале.",
                            graph_nodes=[wu1['id'], wu2['id']],
                            suggested_answers=["Продолжались те же работы", "Другие работы:", "Простой"],
                        ))
                except (ValueError, TypeError, ImportError) as e:
                    logger.debug("Генерация лакуны не удалась: %s", e)
        
        # ── Сортировка по приоритету ───────────────────────────────────
        priority_order = {HITLPriority.CRITICAL: 0, HITLPriority.HIGH: 1,
                         HITLPriority.MEDIUM: 2, HITLPriority.LOW: 3}
        questions.sort(key=lambda q: priority_order.get(q.priority, 99))
        
        return questions

    def _gap_to_question(self, chain, gap) -> Optional[HITLQuestion]:
        """Преобразовать ChainGap в HITLQuestion."""
        from src.core.chain_builder import GapSeverity
        
        sev_to_priority = {
            GapSeverity.CRITICAL: HITLPriority.CRITICAL,
            GapSeverity.HIGH: HITLPriority.HIGH,
            GapSeverity.MEDIUM: HITLPriority.MEDIUM,
            GapSeverity.LOW: HITLPriority.LOW,
        }
        
        qtype_map = {
            "aosr": QuestionType.MISSING_DOCUMENT,
            "aosr_signatures": QuestionType.MISSING_SIGNATURE,
            "certificate": QuestionType.MISSING_DOCUMENT,
            "ks2": QuestionType.MISSING_DOCUMENT,
            "executive_scheme": QuestionType.MISSING_DOCUMENT,
            "test_protocol": QuestionType.MISSING_DOCUMENT,
            "journal": QuestionType.MISSING_DOCUMENT,
        }
        
        qtype = qtype_map.get(gap.missing_doc_type, QuestionType.MISSING_DOCUMENT)
        
        return HITLQuestion(
            id=f"hq_gap_{gap.missing_doc_type}_{chain.work_unit_id[:8]}",
            priority=sev_to_priority.get(gap.severity, HITLPriority.MEDIUM),
            qtype=qtype,
            text=gap.description,
            context=f"Требуется по: {gap.required_by}",
            graph_nodes=[chain.work_unit_id],
            suggested_answers=["Документ есть (приложу)", "Документа нет", "Уточню"],
        )

    def apply_answer(
        self,
        graph,
        question_id: str,
        answer: str,
        questions: List[HITLQuestion] = None
    ) -> bool:
        """
        Применить ответ оператора к графу.
        
        Повышает confidence узлов, создаёт новые узлы при необходимости.
        """
        from src.core.evidence_graph import FactSource, WorkUnitStatus
        
        # Найти вопрос
        q = None
        if questions:
            for qq in questions:
                if qq.id == question_id:
                    q = qq
                    break
        
        if not q:
            return False
        
        q.answered = True
        q.answer = answer
        
        # Обновить узлы графа
        for node_id in q.graph_nodes:
            if graph.graph.has_node(node_id):
                current_conf = graph.graph.nodes[node_id].get('confidence', 1.0)
                
                if any(kw in answer.lower() for kw in ['подтверждаю', 'подлинный', 'есть', 'приложу']):
                    # Повышаем уверенность
                    new_conf = min(1.0, current_conf + 0.3)
                    graph.graph.nodes[node_id]['confidence'] = new_conf
                    
                    # Если это был INFERRED WorkUnit → CONFIRMED
                    if graph.graph.nodes[node_id].get('node_type') == 'WorkUnit':
                        if graph.graph.nodes[node_id].get('status') == WorkUnitStatus.INFERRED.value:
                            graph.graph.nodes[node_id]['status'] = WorkUnitStatus.CONFIRMED.value
                            graph.graph.nodes[node_id]['source'] = FactSource.HUMAN.value
                            graph.graph.nodes[node_id]['confirmed_at'] = datetime.now().isoformat()
                    
                    logger.info("HITL: boosted %s confidence %.2f → %.2f", node_id, current_conf, new_conf)
                
                elif any(kw in answer.lower() for kw in ['нет', 'отсутствует', 'не было', 'не выполнялись']):
                    # Понижаем уверенность
                    new_conf = max(0.1, current_conf - 0.2)
                    graph.graph.nodes[node_id]['confidence'] = new_conf
                    logger.info("HITL: lowered %s confidence %.2f → %.2f", node_id, current_conf, new_conf)
        
        graph.save()
        return True

    def create_session(self, questions: List[HITLQuestion]) -> HITLSession:
        """Создать сессию HITL."""
        session = HITLSession(
            questions=questions,
            total_count=len(questions),
        )
        self._sessions[session.session_id] = session
        return session

    def format_for_telegram(self, questions: List[HITLQuestion], max_show: int = 5) -> str:
        """Форматировать вопросы для Telegram."""
        lines = ["📋 *Вопросы по ИД (HITL)*\n"]
        
        # Статистика
        stats = {}
        for q in questions:
            stats[q.priority.value] = stats.get(q.priority.value, 0) + 1
        
        lines.append(f"🔴 CRITICAL: {stats.get('critical', 0)}")
        lines.append(f"🟠 HIGH:     {stats.get('high', 0)}")
        lines.append(f"🟡 MEDIUM:   {stats.get('medium', 0)}")
        lines.append(f"⚪ LOW:      {stats.get('low', 0)}")
        lines.append("")
        
        for i, q in enumerate(questions[:max_show]):
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
            e = emoji.get(q.priority.value, "❓")
            lines.append(f"{e} *Q{i+1}*: {q.text}")
            if q.context:
                lines.append(f"   _{q.context[:120]}_")
            if q.suggested_answers:
                lines.append(f"   💡 {', '.join(q.suggested_answers[:3])}")
            lines.append("")
        
        remaining = len(questions) - max_show
        if remaining > 0:
            lines.append(f"_...и ещё {remaining} вопросов_")
        
        return "\n".join(lines)


# Модульный синглтон
hitl_system = HITLSystem()
