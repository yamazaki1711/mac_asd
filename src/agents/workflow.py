from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes import hermes_node, pto_node, smeta_node, legal_node, reflection_node

def create_asd_workflow():
    """
    Создает и компилирует граф ASD v11.0.
    """
    workflow = StateGraph(AgentState)

    # Добавляем узлы
    workflow.add_node("hermes", hermes_node)
    workflow.add_node("pto", pto_node)
    workflow.add_node("smeta", smeta_node)
    workflow.add_node("legal", legal_node)
    workflow.add_node("reflection", reflection_node)

    # Устанавливаем точку входа
    workflow.set_entry_point("hermes")

    # Определяем переходы (Edges)
    # Hermes - это роутер
    workflow.add_conditional_edges(
        "hermes",
        lambda x: x["next_step"],
        {
            "pto": "pto",
            "smeta": "smeta",
            "legal": "legal",
            "complete": "reflection"
        }
    )

    # Рабочие узлы всегда возвращаются в Hermes для координации
    workflow.add_edge("pto", "hermes")
    workflow.add_edge("smeta", "hermes")
    workflow.add_edge("legal", "hermes")
    
    # После рефлексии - выход
    workflow.add_edge("reflection", END)

    return workflow.compile()

# Итоговый объект графа
asd_app = create_asd_workflow()
