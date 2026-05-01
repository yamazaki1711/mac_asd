"""
ASD v12.0 — Ingest Telegram Export to BLC (База Ловушек Субподрядчика).

Parses Telegram Desktop JSON export(s), extracts legal traps via LLM,
and saves them to the database with embeddings.

Modes:
  1. Single file:  python -m src.scripts.ingest_blc_telegram result.json
  2. Batch dir:    python -m src.scripts.ingest_blc_telegram --batch data/telegram_exports
  3. With config:  python -m src.scripts.ingest_blc_telegram result.json --config config/telegram_channels.yaml

Channel catalog (telegram_channels.yaml) provides:
  - Priority & category for each channel
  - Focus areas for smarter extraction prompts
  - Auto-categorization of extracted traps
"""

import json
import os
import argparse
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import yaml
from sqlalchemy.orm import Session
from src.db.init_db import SessionLocal
from src.db.models import DomainTrap, LegalTrap
from src.core.llm_engine import llm_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default path to channels catalog
DEFAULT_CHANNELS_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "telegram_channels.yaml",
)


# =============================================================================
# Channel Catalog Loader
# =============================================================================

class ChannelCatalog:
    """Загрузчик и поисковик по каталогу Telegram-каналов."""

    def __init__(self, config_path: Optional[str] = None):
        self.channels: Dict[str, Dict[str, Any]] = {}
        self.categories: Dict[str, Dict[str, Any]] = {}
        self.parsing_config: Dict[str, Any] = {}

        if config_path and os.path.exists(config_path):
            self._load(config_path)
        elif os.path.exists(DEFAULT_CHANNELS_CONFIG):
            logger.info(f"Using default channels config: {DEFAULT_CHANNELS_CONFIG}")
            self._load(DEFAULT_CHANNELS_CONFIG)

    def _load(self, path: str):
        """Загрузка YAML-конфига каналов."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for ch in data.get("channels", []):
            username = ch.get("username", "").lower().replace("@", "")
            self.channels[username] = ch
            # Also index by display_name for fuzzy matching
            display = ch.get("display_name", "").lower()
            if display:
                self.channels[display] = ch

        self.categories = data.get("categories", {})
        self.parsing_config = data.get("parsing", {})

        logger.info(
            f"ChannelCatalog loaded: {len(data.get('channels', []))} channels, "
            f"{len(self.categories)} categories"
        )

    def lookup(self, channel_name: str) -> Optional[Dict[str, Any]]:
        """
        Поиск канала в каталоге по имени.
        Поддерживает: @username, username, display_name.
        """
        key = channel_name.lower().replace("@", "").strip()
        if key in self.channels:
            return self.channels[key]

        # Fuzzy: try partial match
        for k, v in self.channels.items():
            if key in k or k in key:
                return v

        return None

    def get_category(self, channel_name: str) -> str:
        """Возвращает категорию канала или default_category."""
        info = self.lookup(channel_name)
        if info:
            return info.get("category", self.parsing_config.get("default_category", "unknown"))
        return self.parsing_config.get("default_category", "unknown")

    def get_weight(self, channel_name: str) -> float:
        """Возвращает вес канала на основе категории."""
        info = self.lookup(channel_name)
        if info:
            cat = info.get("category", "unknown")
            cat_info = self.categories.get(cat, {})
            return cat_info.get("default_weight", 0.5)
        return 0.3

    def get_domain(self, channel_name: str) -> str:
        """Возвращает домен канала (из поля domain, по категории, или из categories)."""
        info = self.lookup(channel_name)
        if info:
            domain = info.get("domain")
            if domain:
                return domain
            # Fallback 1: derive from category prefix
            cat = info.get("category", "")
            for prefix in ("legal", "pto", "smeta", "logistics", "procurement"):
                if cat.startswith(prefix):
                    return prefix
            # Fallback 2: use category metadata from config
            cat_info = self.categories.get(cat, {})
            domain = cat_info.get("domain")
            if domain:
                return domain
        return self.parsing_config.get("default_domain", "legal")

    def get_channels_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """Возвращает список каналов для указанного домена."""
        result = []
        seen = set()
        for key, ch in self.channels.items():
            username = ch.get("username", "")
            if username in seen:
                continue
            seen.add(username)

            ch_domain = ch.get("domain")
            if not ch_domain:
                cat = ch.get("category", "")
                for prefix in ("legal", "pto", "smeta", "logistics", "procurement"):
                    if cat.startswith(prefix):
                        ch_domain = prefix
                        break
                if not ch_domain:
                    cat_info = self.categories.get(cat, {})
                    ch_domain = cat_info.get("domain", "legal")
            if ch_domain == domain:
                result.append(ch)
        return result

    def get_focus_areas(self, channel_name: str) -> List[str]:
        """Возвращает фокус-области канала для промпта."""
        info = self.lookup(channel_name)
        if info:
            return info.get("focus_areas", [])
        return []

    def get_priority(self, channel_name: str) -> str:
        """Возвращает приоритет канала (critical/high/medium/low)."""
        info = self.lookup(channel_name)
        if info:
            return info.get("priority", "medium")
        return "low"


# =============================================================================
# Extraction Prompts
# =============================================================================

EXTRACTION_PROMPT_BASE = """You are a top-tier Russian construction lawyer analyst specializing in subcontractor protection.
Read the following text from a Telegram channel post about construction law.

If the text contains a description of a "Subcontractor Trap" (a risk, unfair clause, legal danger, or problematic contract condition for a construction subcontractor), extract it.
If the text is just chatter, news without legal substance, or irrelevant, return {"is_trap": false}.

If it IS a trap, format your output exactly as the following JSON:
{
  "is_trap": true,
  "title": "Short descriptive title in Russian (max 10 words)",
  "description": "Full description of the trap, context, and why it is dangerous for the subcontractor.",
  "court_cases": ["List of any mentioned court definitions, case numbers like А40-123/23. Leave empty if none."],
  "mitigation": "What the author recommends to do to avoid this (e.g., add to protocol of disagreements, specific contract wording).",
  "confidence": 0.9
}

Respond ONLY with valid JSON."""


def build_extraction_prompt(catalog: ChannelCatalog, channel_name: str) -> str:
    """
    Строит промпт с учётом специфики канала из каталога.
    Если канал известен — добавляем фокус-области для лучшей экстракции.
    """
    focus_areas = catalog.get_focus_areas(channel_name)
    priority = catalog.get_priority(channel_name)

    prompt = EXTRACTION_PROMPT_BASE

    if focus_areas:
        areas_text = ", ".join(focus_areas)
        prompt += f"""

This post is from a channel specializing in: {areas_text}.
Pay special attention to content related to these areas when identifying traps."""

    if priority == "critical":
        prompt += "\n\nThis channel is a critical source with real court practice. Be thorough in extraction."

    return prompt


# =============================================================================
# Telegram Export Parser
# =============================================================================

def extract_text_from_message(msg: Dict[str, Any]) -> str:
    """
    Извлекает текст из сообщения Telegram Desktop JSON export.
    Обрабатывает вложенные структуры (mixed string/dict arrays).
    """
    text_entities = msg.get("text", "")
    if isinstance(text_entities, list):
        extracted_text = ""
        for entity in text_entities:
            if isinstance(entity, str):
                extracted_text += entity
            elif isinstance(entity, dict) and "text" in entity:
                extracted_text += entity["text"]
        return extracted_text
    return str(text_entities) if text_entities else ""


async def process_telegram_post(
    db: Session,
    text: str,
    source_name: str,
    catalog: ChannelCatalog,
    domain: str = "legal",
    category: str = "unknown",
    weight: float = 0.5,
) -> bool:
    """
    Sends the text to LLM to extract domain trap, inserts if valid.
    Returns True if a trap was saved.
    """
    min_length = catalog.parsing_config.get("min_text_length", 50)
    max_length = catalog.parsing_config.get("max_text_length", 8000)

    if len(text.strip()) < min_length:
        return False  # Too short

    # Truncate if too long
    analysis_text = text[:max_length] if len(text) > max_length else text

    # 1. Build channel-specific prompt
    prompt = build_extraction_prompt(catalog, source_name)

    # 2. Ask LLM to extract trap
    response_text = await llm_engine.safe_chat(
        "legal",
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": analysis_text},
        ],
        fallback_response='{"is_trap": false}',
        temperature=0.1,
    )

    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse LLM JSON response: {e}")
        return False

    if not data.get("is_trap"):
        return False

    # Confidence check
    confidence = data.get("confidence", 1.0)
    threshold = catalog.parsing_config.get("confidence_threshold", 0.7)
    if confidence < threshold:
        logger.info(f"Trap below confidence threshold ({confidence} < {threshold}): {data.get('title')}")
        return False

    logger.info(f"Identified Trap (confidence={confidence}): {data.get('title')}")

    # 3. Get Embedding
    description = data.get("description", "")
    embedding = await llm_engine.embed(description) if description else None

    # 4. Create ORM Model & Save
    trap = DomainTrap(
        domain=domain,
        title=data.get("title", "Untitled Trap"),
        description=description,
        source=source_name,
        channel=source_name,
        category=category,
        weight=int(weight * 100),  # Convert 0-1 catalog weight to 0-100 DB weight
        court_cases=data.get("court_cases", []),
        mitigation=data.get("mitigation", ""),
        embedding=embedding,
    )

    db.add(trap)
    db.commit()
    return True


async def parse_telegram_export(
    json_path: str,
    catalog: Optional[ChannelCatalog] = None,
    throttle: float = 0.5,
) -> Dict[str, int]:
    """
    Parses a native Telegram Desktop JSON export file.
    Returns stats dict: {processed, trapped, skipped_short, errors}.
    """
    if catalog is None:
        catalog = ChannelCatalog()

    if not os.path.exists(json_path):
        logger.error(f"File not found: {json_path}")
        return {"processed": 0, "trapped": 0, "skipped_short": 0, "errors": 1}

    with open(json_path, "r", encoding="utf-8") as f:
        export_data = json.load(f)

    chat_name = export_data.get("name", "Unknown Telegram Channel")
    messages = export_data.get("messages", [])

    # Lookup channel in catalog
    channel_info = catalog.lookup(chat_name)
    domain = catalog.get_domain(chat_name)
    category = catalog.get_category(chat_name)
    weight = catalog.get_weight(chat_name)
    priority = catalog.get_priority(chat_name)

    logger.info(
        f"Loaded {len(messages)} messages from '{chat_name}' "
        f"(domain={domain}, category={category}, priority={priority}, weight={weight})"
    )

    if channel_info:
        logger.info(f"  Channel found in catalog: {channel_info.get('display_name')}")

    throttle = catalog.parsing_config.get("llm_throttle_seconds", throttle)

    db = SessionLocal()
    stats = {"processed": 0, "trapped": 0, "skipped_short": 0, "errors": 0}
    source_name = f"Telegram: {chat_name}"

    try:
        for i, msg in enumerate(messages):
            text = extract_text_from_message(msg)

            if not text or len(text.strip()) < catalog.parsing_config.get("min_text_length", 50):
                stats["skipped_short"] += 1
                continue

            stats["processed"] += 1

            try:
                is_saved = await process_telegram_post(
                    db, text, chat_name, catalog,
                    domain=domain,
                    category=category,
                    weight=weight,
                )
                if is_saved:
                    stats["trapped"] += 1

                # Throttle to avoid MLX overload
                if throttle > 0:
                    await asyncio.sleep(throttle)

            except Exception as e:
                logger.error(f"Error processing message {i}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Finished '{chat_name}': "
            f"evaluated={stats['processed']}, "
            f"traps={stats['trapped']}, "
            f"skipped={stats['skipped_short']}, "
            f"errors={stats['errors']}"
        )

    finally:
        db.close()

    return stats


async def batch_parse_exports(
    exports_dir: str,
    catalog: Optional[ChannelCatalog] = None,
) -> Dict[str, Dict[str, int]]:
    """
    Пакетная обработка всех JSON-файлов в директории.
    Возвращает словарь {filename: stats}.
    """
    if catalog is None:
        catalog = ChannelCatalog()

    exports_path = Path(exports_dir)
    if not exports_path.exists():
        logger.error(f"Exports directory not found: {exports_dir}")
        return {}

    json_files = list(exports_path.glob("*.json")) + list(exports_path.glob("**/result.json"))
    logger.info(f"Found {len(json_files)} JSON export files in {exports_dir}")

    results = {}
    for json_file in sorted(json_files):
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {json_file.name}")
        logger.info(f"{'='*60}")

        stats = await parse_telegram_export(str(json_file), catalog)
        results[json_file.name] = stats

    # Summary
    total_processed = sum(s.get("processed", 0) for s in results.values())
    total_trapped = sum(s.get("trapped", 0) for s in results.values())
    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH COMPLETE: {len(results)} files processed")
    logger.info(f"Total messages evaluated: {total_processed}")
    logger.info(f"Total traps found: {total_trapped}")
    logger.info(f"{'='*60}")

    return results


async def list_channels(catalog: Optional[ChannelCatalog] = None) -> None:
    """Выводит каталог каналов в консоль."""
    if catalog is None:
        catalog = ChannelCatalog()

    print("\n" + "=" * 70)
    print("MAC_ASD v12.0 — Каталог Telegram-каналов для БЛС")
    print("=" * 70)

    # Group by priority
    priorities = {"critical": [], "high": [], "medium": [], "low": []}
    seen = set()

    for key, ch in catalog.channels.items():
        username = ch.get("username", "")
        if username in seen:
            continue
        seen.add(username)

        priority = ch.get("priority", "low")
        if priority in priorities:
            priorities[priority].append(ch)

    for priority_name, channels in priorities.items():
        if not channels:
            continue
        print(f"\n  [{priority_name.upper()}]")
        for ch in sorted(channels, key=lambda x: x.get("display_name", "")):
            print(f"    @{ch['username']:25s}  {ch.get('display_name', '')}")
            print(f"    {'':25s}  cat={ch.get('category', '?')}  focus={', '.join(ch.get('focus_areas', [])[:2])}")

    print(f"\n  Всего каналов: {len(seen)}")
    print("=" * 70 + "\n")


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MAC_ASD v12.0 — Ingest Telegram JSON exports to BLC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file import
  python -m src.scripts.ingest_blc_telegram result.json

  # Batch import from directory
  python -m src.scripts.ingest_blc_telegram --batch data/telegram_exports

  # With custom channels config
  python -m src.scripts.ingest_blc_telegram result.json --config config/telegram_channels.yaml

  # List available channels
  python -m src.scripts.ingest_blc_telegram --list-channels
        """,
    )

    parser.add_argument(
        "file_path",
        nargs="?",
        help="Path to result.json from Telegram Desktop export",
    )
    parser.add_argument(
        "--batch",
        metavar="DIR",
        help="Batch process all JSON files in directory",
    )
    parser.add_argument(
        "--config",
        metavar="YAML",
        default=DEFAULT_CHANNELS_CONFIG,
        help=f"Path to telegram_channels.yaml (default: {DEFAULT_CHANNELS_CONFIG})",
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        help="List available channels from catalog and exit",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=0.5,
        help="Delay between LLM calls in seconds (default: 0.5)",
    )

    args = parser.parse_args()

    # Load channel catalog
    catalog = ChannelCatalog(args.config if os.path.exists(args.config) else None)

    if args.list_channels:
        asyncio.run(list_channels(catalog))
    elif args.batch:
        asyncio.run(batch_parse_exports(args.batch, catalog))
    elif args.file_path:
        asyncio.run(parse_telegram_export(args.file_path, catalog, args.throttle))
    else:
        parser.print_help()
