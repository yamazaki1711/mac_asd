"""
ASD v11.0 — Ingest Telegram Export to BLC (База Ловушек Субподрядчика).

Parses Telegram Desktop JSON export, extracts legal traps via LLM,
and saves them to the database with embeddings.
"""

import json
import os
import argparse
import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session
from src.db.init_db import SessionLocal
from src.db.models import LegalTrap
from src.core.llm_engine import llm_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System prompt for extracting legal traps from Telegram text.
EXTRACTION_PROMPT = """
You are a top-tier construction lawyer analyst. Read the following text from a Telegram channel post.
If the text contains a description of a "Subcontractor Trap" (a risk, unfair clause, or legal danger for a construction subcontractor), extract it.
If the text is just chatter, news, or irrelevant, return {"is_trap": false}.

If it IS a trap, format your output exactly as following JSON:
{
  "is_trap": true,
  "title": "Short descriptive title (max 10 words)",
  "description": "Full description of the trap, context, and why it is dangerous.",
  "court_cases": ["List of any mentioned court definitions, case numbers like А40-123/23. Leave empty if none."],
  "mitigation": "What the author recommends to do to avoid this (e.g., add to protocol, specific wording)."
}

Respond ONLY with valid JSON.
"""


async def process_telegram_post(db: Session, text: str, source_name: str) -> bool:
    """Sends the text to LLM to extract BLC trap, inserts if valid."""
    if len(text.strip()) < 50:
        return False  # Too short to be a valid case study

    # 1. Ask LLM to extract trap
    response_text = await llm_engine.safe_chat(
        "legal",
        [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": text},
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

    logger.info(f"Identified Trap: {data.get('title')}")

    # 2. Get Embedding for the trap description
    embedding = await llm_engine.embed(data.get("description", ""))

    # 3. Create ORM Model & Save
    trap = LegalTrap(
        title=data.get("title", "Untitled Trap"),
        description=data.get("description", ""),
        source=source_name,
        court_cases=data.get("court_cases", []),
        mitigation=data.get("mitigation", ""),
        embedding=embedding,
    )

    db.add(trap)
    db.commit()
    return True


async def parse_telegram_export(json_path: str):
    """Parses a native Telegram Desktop JSON export."""
    if not os.path.exists(json_path):
        logger.error(f"File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        export_data = json.load(f)

    chat_name = export_data.get("name", "Unknown Telegram Channel")
    messages = export_data.get("messages", [])

    logger.info(f"Loaded {len(messages)} messages from {chat_name}")

    db = SessionLocal()
    processed_count = 0
    trapped_count = 0
    try:
        for msg in messages:
            # Native telegram exports can have nested text structures
            text_entities = msg.get("text", "")
            if isinstance(text_entities, list):
                extracted_text = ""
                for entity in text_entities:
                    if isinstance(entity, str):
                        extracted_text += entity
                    elif isinstance(entity, dict) and "text" in entity:
                        extracted_text += entity["text"]
            else:
                extracted_text = text_entities

            if extracted_text:
                processed_count += 1
                is_saved = await process_telegram_post(
                    db, extracted_text, f"Telegram: {chat_name}"
                )
                if is_saved:
                    trapped_count += 1

        logger.info(
            f"Finished processing. Evaluated {processed_count} texts, "
            f"found {trapped_count} Traps."
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Telegram JSON to BLC")
    parser.add_argument("file_path", help="Path to result.json from Telegram export")
    args = parser.parse_args()

    asyncio.run(parse_telegram_export(args.file_path))
