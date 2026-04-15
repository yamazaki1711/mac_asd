from typing import Annotated, TypedDict, List, Dict, Any, Union, Optional
from langgraph.graph import add_messages

class AgentState(TypedDict):
    """
    Состояние графа ASD. Передается между агентами.
    """
    # Список сообщений (используется add_messages для накопления истории)
    messages: Annotated[List[Any], add_messages]
    
    # Текущий проект и документы
    project_id: int
    current_lot_id: Optional[str]
    
    # Краткосрочная память/контекст задачи
    task_description: str
    intermediate_data: Dict[str, Any] # Здесь ПТО кладет ВОР, Сметчик - расчеты
    
    # Аналитическая часть
    findings: List[Dict[str, Any]] # Список найденных ловушек или ошибок
    
    # Метаданные оркестрации
    next_step: str # Имя следующего узла
    is_complete: bool
