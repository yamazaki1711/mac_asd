import os
from src.config import settings

def load_wiki_page(page_name: str) -> str:
    """
    Загружает содержимое страницы из Obsidian Wiki.
    Пример: page_name="Hermes_Core"
    """
    if not page_name.endswith(".md"):
        page_name += ".md"
    
    file_path = os.path.join(settings.WIKI_PATH, page_name)
    
    if not os.path.exists(file_path):
        return f"Warning: Wiki page {page_name} not found."
    
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def get_all_rules() -> str:
    """
    Собирает все ключевые правила в один блок контекста (для инициализации сессии).
    """
    core_rules = load_wiki_page("Hermes_Core")
    # Можно добавить другие страницы по мере роста Wiki
    return f"--- ACTUAL SYSTEM RULES FROM WIKI ---\n{core_rules}\n--- END OF RULES ---"
