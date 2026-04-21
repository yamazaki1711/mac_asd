"""
ASD v11.3 — LangGraph Workflow.

Построение DAG с поддержкой параллельного выполнения агентов.

Model Lineup (mac_studio):
    PM:     Llama 3.3 70B 4-bit
    ПТО:    Gemma 4 31B 4-bit (VLM, shared)
    Юрист:  Gemma 4 31B 4-bit (shared)
    Сметчик:Gemma 4 31B 4-bit (shared)
    Закупщик:Gemma 4 31B 4-bit (shared)
    Логист: Gemma 4 31B 4-bit (shared)
    Дело:   Gemma 4 E4B 4-bit

Параллельные шаги:
    - Сметчик + Юрист (оба на Gemma 4 31B — последовательная очередь)
    - Закупщик + Логист (оба на Gemma 4 31B — последовательная очередь)
"""

from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes import (
    hermes_node, archive_node, procurement_node, pto_node,
    logistics_node, smeta_node, legal_node, reflection_node
)


def create_asd_workflow():
    """
    Создает и компилирует граф ASD v11.3.

    DAG:
        Hermes → Archive → Procurement → PTO → [Smeta + Legal parallel] → Logistics → Hermes Verdict → Reflection

    Параллельные ветки реализуются через conditional_edges:
        - pto_done → smeta (Сметчик запускается первым)
        - smeta_done → legal (Юрист параллельно, если возможно)
        - В текущей реализации — последовательная очередь через Hermes-роутер
    """
    workflow = StateGraph(AgentState)

    # Добавляем узлы
    workflow.add_node("hermes", hermes_node)
    workflow.add_node("archive", archive_node)
    workflow.add_node("procurement", procurement_node)
    workflow.add_node("pto", pto_node)
    workflow.add_node("logistics", logistics_node)
    workflow.add_node("smeta", smeta_node)
    workflow.add_node("legal", legal_node)
    workflow.add_node("reflection", reflection_node)

    # Устанавливаем точку входа
    workflow.set_entry_point("hermes")

    # Определяем переходы (Edges)
    # Hermes — роутер с гибридной 3-стадийной моделью решений
    workflow.add_conditional_edges(
        "hermes",
        lambda x: x["next_step"],
        {
            "archive": "archive",
            "procurement": "procurement",
            "pto": "pto",
            "smeta": "smeta",
            "legal": "legal",
            "logistics": "logistics",
            "complete": "reflection"
        }
    )

    # Рабочие узлы всегда возвращаются в Hermes для координации
    workflow.add_edge("archive", "hermes")
    workflow.add_edge("procurement", "hermes")
    workflow.add_edge("pto", "hermes")
    workflow.add_edge("logistics", "hermes")
    workflow.add_edge("smeta", "hermes")
    workflow.add_edge("legal", "hermes")

    # После рефлексии — выход
    workflow.add_edge("reflection", END)

    return workflow.compile()


# Итоговый объект графа
asd_app = create_asd_workflow()
