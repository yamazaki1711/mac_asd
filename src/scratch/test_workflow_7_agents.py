import asyncio
import json
from src.agents.workflow import asd_app

async def test_workflow():
    print("Testing 7-Agent Workflow...")
    initial_state = {
        "messages": [{"role": "user", "content": "Анализ нового тендера на строительство моста."}],
        "project_id": 101,
        "task_description": "Анализ нового тендера на строительство моста. Требуется полный цикл: регистрация, закупка, ПТО, логистика, смета, юрист.",
        "intermediate_data": {},
        "findings": [],
        "next_step": "start",
        "is_complete": False
    }
    
    try:
        # В нашем окружении Ollama может быть недоступна, сработают моки в nodes.py
        result = await asd_app.ainvoke(initial_state)
        print("\n--- Workflow Result ---")
        print(f"Final Step: {result.get('next_step')}")
        print(f"Is Complete: {result.get('is_complete')}")
        print(f"Intermediate Data Keys: {list(result.get('intermediate_data', {}).keys())}")
        print(f"Findings: {len(result.get('findings', []))}")
        
        # Проверка наличия всех агентов в данных
        expected_keys = ["archive", "procurement", "vor", "logistics", "costs"]
        for key in expected_keys:
            if key in result["intermediate_data"]:
                print(f"✅ {key} present")
            else:
                print(f"❌ {key} missing")
                
    except Exception as e:
        print(f"Workflow failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_workflow())
