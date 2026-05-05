#!/usr/bin/env python3
"""
ASD v13.0 — LLM-трансформер: сырой Telegram-пост → структурированная БЛС-ловушка.

Берёт посты из domain_traps (source='telegram'), прогоняет через LLM,
извлекает юридический паттерн и создаёт curated-ловушку с полями:
  title, description, category, mitigation, is_trap.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/transform_traps.py [--dry-run] [--limit N] [--channel @advokatgrikevich]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("transform_traps")

# ═══════════════════════════════════════════════════════════════════════════
# LLM Prompt — превращает сырой пост в структурированную ловушку
# ═══════════════════════════════════════════════════════════════════════════

TRANSFORM_PROMPT = """Ты — строительный юрист, специалист по договорам подряда (ГК РФ, 44-ФЗ, 223-ФЗ).
Твоя задача — проанализировать пост из Telegram-канала и, если он содержит
юридический риск/ловушку для подрядчика, переработать его в структурированную
карточку знания.

Формат ответа — СТРОГО JSON:
{{
  "is_trap": true/false,
  "title": "Короткое название ловушки (до 120 символов)",
  "description": "Подробное описание: в чём ловушка, как работает механизм, какие статьи закона применимы (200-500 символов)",
  "category": "одна из: advance_payment, deadlines, penalties, scope_price, acceptance, warranty, subcontracting, termination, jurisdiction, force_majeure",
  "mitigation": "Конкретные действия подрядчика для защиты: что прописать в договоре, на какие статьи ссылаться (100-300 символов)"
}}

Правила:
1. Если пост — просто новость/мнение без конкретного юридического риска → is_trap: false, остальные поля пустые.
2. Если пост описывает ловушку/риск/уловку заказчика → is_trap: true, заполни все поля.
3. Title должен быть actionable: не «Проблема с актами», а «Заказчик уклоняется от приёмки — акты не подписываются месяцами».
4. В description обязательно указывай статьи ГК РФ, АПК РФ, 44-ФЗ, ПП РФ, если применимы.
5. Mitigation — конкретные шаги, а не общие советы. Указывай пункты договора и процессуальные действия.
6. Пиши на русском, стиль — деловой, без эмоций.

Вот пост для анализа:
---
{post_text}
---"""


def transform_post(post_text: str, llm_url: str = "http://127.0.0.1:11434/api/chat") -> Optional[dict]:
    """
    Отправить пост в LLM и получить структурированную ловушку.

    Использует Ollama (Gemma 4 31B Cloud) или DeepSeek API.
    Возвращает dict с полями ловушки или None при ошибке.
    """
    import requests

    payload = {
        "model": "gemma4:31b-cloud",
        "messages": [{"role": "user", "content": TRANSFORM_PROMPT.format(post_text=post_text[:3000])}],
        "format": "json",
        "stream": False,
    }

    try:
        resp = requests.post(llm_url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]

        # Extract JSON from response (LLM may wrap in markdown)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
            if content.startswith("json"):
                content = content[4:].strip()

        result = json.loads(content)
        return result

    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return None


def main():
    parser = argparse.ArgumentParser(description="Transform raw Telegram posts → structured БЛС traps")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--limit", type=int, default=10, help="Max posts to process (default: 10)")
    parser.add_argument("--channel", type=str, default=None, help="Filter by channel (e.g. @advokatgrikevich)")
    parser.add_argument("--domain", type=str, default="legal", help="Domain filter (default: legal)")
    parser.add_argument("--llm-url", type=str, default="http://127.0.0.1:11434/api/chat", help="Ollama API URL")
    args = parser.parse_args()

    from src.core.knowledge.knowledge_base import knowledge_base, _lazy_db

    _, _, DomainTrap = _lazy_db()

    # Fetch raw posts from PostgreSQL
    with knowledge_base._get_session() as db:
        query = db.query(DomainTrap).filter(
            DomainTrap.source == "telegram",
            DomainTrap.domain == args.domain,
        )
        if args.channel:
            query = query.filter(DomainTrap.channel == args.channel)
        posts = query.order_by(DomainTrap.id.desc()).limit(args.limit).all()

    logger.info("Fetched %d raw posts (domain=%s, channel=%s)", len(posts), args.domain, args.channel or "all")

    stats = {"processed": 0, "traps_found": 0, "skipped": 0, "indexed": 0, "errors": 0}

    for post in posts:
        stats["processed"] += 1
        text = post.description or ""

        if len(text) < 100:
            stats["skipped"] += 1
            continue

        logger.info("[%d/%d] Analyzing post #%d: %s...", stats["processed"], len(posts), post.id, text[:80])

        result = transform_post(text, llm_url=args.llm_url)
        if not result:
            stats["errors"] += 1
            continue

        if not result.get("is_trap", False):
            logger.info("  → Not a trap, skipping")
            stats["skipped"] += 1
            continue

        stats["traps_found"] += 1
        logger.info(
            "  → TRAP FOUND: [%s] %s",
            result.get("category", "?"),
            result.get("title", "")[:100],
        )

        if args.dry_run:
            logger.info("    DRY-RUN: would index with weight=95, source=curated")
            logger.info("    Mitigation: %s", result.get("mitigation", "")[:150])
            stats["indexed"] += 1
            continue

        # Index as curated trap
        try:
            trap_id = knowledge_base.index_trap(
                domain="legal",
                title=result["title"],
                description=result["description"],
                source="curated",
                channel=post.channel or "",
                category=result.get("category", ""),
                weight=95,
                mitigation=result.get("mitigation", ""),
            )
            if trap_id:
                stats["indexed"] += 1
                logger.info("    Indexed as trap #%d", trap_id)
            else:
                logger.info("    Duplicate, skipped")
        except Exception as e:
            logger.error("    Failed to index: %s", e)
            stats["errors"] += 1

    print(f"\n=== Transformation Summary ===")
    print(f"Posts processed:    {stats['processed']}")
    print(f"Traps found:        {stats['traps_found']}")
    print(f"Traps indexed:      {stats['indexed']}")
    print(f"Skipped (not trap): {stats['skipped']}")
    print(f"Errors:             {stats['errors']}")


if __name__ == "__main__":
    main()
