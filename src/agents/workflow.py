"""
ASD v12.0 — PM-driven LangGraph Workflow.

Вместо статического pipeline (archive → procurement → pto → smeta → legal → logistics),
PM (Руководитель проекта) динамически строит WorkPlan и диспетчеризует агентов.

Граф:
  START → pm_node → pm_dispatch → [agent_node] → pm_evaluate → pm_dispatch → ... → END

pm_node:
  - Первый вход: строит WorkPlan через LLM (Llama 3.3 70B)
  - Последующие входы: оценивает результат агента → решает, что дальше

pm_dispatch (conditional edge):
  - Выбирает следующего агента из WorkPlan
  - Если план завершён → END
  - RAM Manager проверяет, можно ли принять задачу

agent_node:
  - Выполняет задачу (archive/procurement/pto/smeta/legal/logistics)
  - Возвращает результат в PM через pm_evaluate

pm_evaluate:
  - PM оценивает результат агента
  - Принимает/отклоняет/перестраивает план
  - Возвращает управление в pm_dispatch

Model Lineup (mac_studio):
  PM:     Llama 3.3 70B 4-bit
  ПТО:    Gemma 4 31B 4-bit (VLM, shared)
  Юрист:  Gemma 4 31B 4-bit (shared)
  Сметчик:Gemma 4 31B 4-bit (shared)
  Закупщик:Gemma 4 31B 4-bit (shared)
  Логист: Gemma 4 31B 4-bit (shared)
  Дело:   Gemma 4 E4B 4-bit
"""

from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes_v2 import (
    pm_planning_node,
    pm_evaluate_node,
    pm_dispatch_router,
    agent_executor_node,
)


def create_asd_workflow():
    """
    Создать и скомпилировать PM-driven граф ASD v12.0.

    Flow:
      START → pm_planning → agent_executor → pm_evaluate → [цикл] → END
    """
    workflow = StateGraph(AgentState)

    # Регистрируем узлы
    workflow.add_node("pm_planning", pm_planning_node)
    workflow.add_node("agent_executor", agent_executor_node)
    workflow.add_node("pm_evaluate", pm_evaluate_node)

    # Точка входа — PM планирование
    workflow.set_entry_point("pm_planning")

    # PM планирует → диспетчеризует агента
    workflow.add_conditional_edges(
        "pm_planning",
        pm_dispatch_router,
        {
            "archive": "agent_executor",
            "procurement": "agent_executor",
            "pto": "agent_executor",
            "pto_inventory": "agent_executor",
            "pto_verify_trail": "agent_executor",
            "smeta": "agent_executor",
            "legal": "agent_executor",
            "logistics": "agent_executor",
            "__end__": END,
        },
    )

    # Агент выполнил → PM оценивает
    workflow.add_edge("agent_executor", "pm_evaluate")

    # PM оценил → диспетчеризует следующего или завершает
    workflow.add_conditional_edges(
        "pm_evaluate",
        pm_dispatch_router,
        {
            "archive": "agent_executor",
            "procurement": "agent_executor",
            "pto": "agent_executor",
            "pto_inventory": "agent_executor",
            "pto_verify_trail": "agent_executor",
            "smeta": "agent_executor",
            "legal": "agent_executor",
            "logistics": "agent_executor",
            "__end__": END,
        },
    )

    return workflow.compile()


# Итоговый объект графа
asd_app = create_asd_workflow()
