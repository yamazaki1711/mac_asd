import logging
from typing import Dict, Any, List
from src.core.graph_service import graph_service

logger = logging.getLogger(__name__)

class EventManager:
    """
    Управляющий событиями (State Machine) для АСД v11.0.
    Отвечает за переходы между этапами жизненного цикла проекта.
    """

    # Определенные состояния (Nodes)
    STATES = {
        "INIT": "Инициализация / Поиск тендера",
        "TENDER_FOUND": "Тендер найден",
        "FILES_REGISTERED": "Документация зарегистрирована и структурирована",
        "SPECS_EXTRACTED": "Спецификации извлечены",
        "LOGISTICS_READY": "Коммерческие предложения получены",
        "ESTIMATE_READY": "Сметный расчет готов",
        "LEGAL_CHECKED": "Юридическая экспертиза завершена",
        "VERDICT_READY": "Вердикт по тендеру сформирован",
        "PROJECT_WON": "Контракт подписан / Начало СМР",
        "EXECUTION": "Производство работ / Генерация ИД",
        "COMPLETION": "Завершение объекта / Сдача КС-11",
        "CLAIM": "Претензионная работа"
    }

    def __init__(self):
        self.graph = graph_service

    def register_event(self, project_id: str, event_type: str, payload: Dict[str, Any] = None):
        """Регистрирует событие в системе и обновляет состояние графа."""
        logger.info(f"Event received: {event_type} for project {project_id}")
        
        # 1. Запись события в аудит/лог (placeholder)
        # TODO: Добавить запись в PostgreSQL audit_log
        
        # 2. Обновление графа состояний
        self._update_project_state(project_id, event_type, payload)
        
        # 3. Триггер следующих действий
        self._trigger_workflow(project_id, event_type, payload)

    def _update_project_state(self, project_id: str, event_type: str, payload: Dict[str, Any]):
        """Обновляет узел проекта в графе и добавляет ребро события."""
        # Убеждаемся, что узел проекта существует
        if not self.graph.graph.has_node(project_id):
            self.graph.graph.add_node(project_id, type="Project", status="INIT")
        
        # Создаем узел события
        event_id = f"evt_{event_type}_{payload.get('timestamp', 'now')}"
        self.graph.graph.add_node(event_id, type="Event", event_type=event_type, **(payload or {}))
        
        # Связываем
        self.graph.add_reference(project_id, event_id, context=f"State changed by {event_type}")
        
        # Обновляем текущий статус проекта
        new_status = self._map_event_to_state(event_type)
        if new_status:
            self.graph.graph.nodes[project_id]['status'] = new_status
        
        self.graph.save_graph()

    def _map_event_to_state(self, event_type: str) -> str:
        """Определяет новое состояние проекта на основе типа события."""
        mapping = {
            "asd_tender_search_success": "TENDER_FOUND",
            "asd_archive_done": "FILES_REGISTERED",
            "asd_pto_done": "SPECS_EXTRACTED",
            "asd_logistics_done": "LOGISTICS_READY",
            "asd_smeta_done": "ESTIMATE_READY",
            "asd_legal_done": "LEGAL_CHECKED",
            "hermes_verdict_signed": "VERDICT_READY",
            "contract_signed": "PROJECT_WON",
            "work_entry_closed": "EXECUTION",
            "ks11_signed": "COMPLETION",
            "payment_deadline_expired": "CLAIM"
        }
        return mapping.get(event_type)

    def _trigger_workflow(self, project_id: str, event_type: str, payload: Dict[str, Any]):
        """
        Логика автоматических триггеров.
        """
        if event_type == "asd_tender_search_success":
            logger.info("Triggering Archive: Registering documents...")
            # logic to call archive_node via asd_app...
        
        elif event_type == "asd_pto_done":
            logger.info("Triggering Logistics: Material sourcing...")
            # logic to call logistics_node...
            
        elif event_type == "asd_logistics_done":
            logger.info("Triggering Smeta: Pricing...")
            # logic to call smeta_node...

    def get_project_state(self, project_id: str) -> Dict[str, Any]:
        """Возвращает текущее состояние и историю событий проекта."""
        if not self.graph.graph.has_node(project_id):
            return {"status": "NOT_FOUND"}
            
        return {
            "project_id": project_id,
            "status": self.graph.graph.nodes[project_id].get('status', 'INIT'),
            "history": self.graph.get_related_nodes(project_id, depth=1)
        }

event_manager = EventManager()
