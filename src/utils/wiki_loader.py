"""
ASD v11.0 — Wiki Loader.

Loads Obsidian Wiki pages for agent context.
Uses pathlib for cross-platform path handling.
"""

from pathlib import Path
from src.config import settings


def load_wiki_page(page_name: str) -> str:
    """
    Загружает содержимое страницы из Obsidian Wiki.

    Args:
        page_name: Имя страницы (без расширения), например "Hermes_Core"

    Returns:
        Содержимое страницы или предупреждение, если не найдена
    """
    if not page_name.endswith(".md"):
        page_name += ".md"

    file_path = settings.wiki_path / page_name

    if not file_path.exists():
        return f"Warning: Wiki page {page_name} not found at {file_path}"

    return file_path.read_text(encoding="utf-8")


def get_all_rules() -> str:
    """
    Собирает все ключевые правила в один блок контекста (для инициализации сессии).
    """
    core_rules = load_wiki_page("Hermes_Core")
    return f"--- ACTUAL SYSTEM RULES FROM WIKI ---\n{core_rules}\n--- END OF RULES ---"
