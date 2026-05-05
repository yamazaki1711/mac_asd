#!/usr/bin/env python3
"""
ASD v13.0 — Синхронизация Telegram Knowledge Base → PostgreSQL domain_traps.

Читает data/telegram_knowledge.yaml (820+ записей) и инжестит в
PostgreSQL через KnowledgeBase.index_trap(). Дедупликация встроена.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/ingest_blc_telegram.py [--dry-run] [--limit N] [--domain legal]
    PYTHONPATH=. .venv/bin/python scripts/ingest_blc_telegram.py --stats  # только статистика
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_blc")


# ── Mapping: YAML categories → ASD domains ──────────────────────────
CATEGORY_DOMAIN_MAP = {
    "case_law": "legal",
    "regulatory_changes": "legal",
    "industry_analysis": "pto",
    "technical_knowledge": "pto",
    "document_rules": "pto",
}

# ── Mapping: domain → default weight ───────────────────────────────
DOMAIN_WEIGHT = {
    "legal": 80,
    "pto": 60,
    "smeta": 50,
    "procurement": 40,
    "logistics": 30,
}


def load_yaml_kb(path: str = "data/telegram_knowledge.yaml") -> list:
    """Load YAML knowledge base. Returns list of entry dicts."""
    kb_path = Path(path)
    if not kb_path.exists():
        logger.error("Knowledge base file not found: %s", kb_path)
        return []
    with open(kb_path) as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    return data if isinstance(data, list) else []


def map_category_to_domain(categories: list[str]) -> str:
    """Map Telegram content categories to ASD domains."""
    for cat in categories:
        domain = CATEGORY_DOMAIN_MAP.get(cat)
        if domain:
            return domain
    return "pto"  # default


def ingest_entries(
    entries: list,
    dry_run: bool = False,
    domain_filter: str | None = None,
    limit: int = 0,
) -> dict:
    """Ingest entries into PostgreSQL via KnowledgeBase.index_trap()."""
    from src.core.knowledge.knowledge_base import knowledge_base

    stats = {"total": 0, "indexed": 0, "duplicates": 0, "errors": 0, "skipped_filter": 0}

    for i, entry in enumerate(entries):
        if limit and stats["total"] >= limit:
            break

        # Determine domain
        source_domain = entry.get("source_domain", "pto")
        categories = entry.get("categories", [])

        # Use source_domain as primary, fall back to category mapping
        domain = source_domain if source_domain in DOMAIN_WEIGHT else map_category_to_domain(categories)

        if domain_filter and domain != domain_filter:
            stats["skipped_filter"] += 1
            continue

        stats["total"] += 1

        # Extract fields
        text = entry.get("text", "")
        if not text or len(text) < 50:
            stats["skipped_filter"] += 1
            continue

        title = text[:150].replace("\n", " ").strip()
        description = text
        source = "telegram"
        channel = entry.get("source_channel", "")
        category = categories[0] if categories else ""
        weight = DOMAIN_WEIGHT.get(domain, 50)

        if dry_run:
            logger.info(
                "[DRY-RUN] domain=%s cat=%s ch=%s title=%s",
                domain, category, channel, title[:80],
            )
            stats["indexed"] += 1
            continue

        try:
            trap_id = knowledge_base.index_trap(
                domain=domain,
                title=title,
                description=description,
                source=source,
                channel=channel,
                category=category,
                weight=weight,
            )
            if trap_id:
                stats["indexed"] += 1
                if stats["indexed"] % 50 == 0:
                    logger.info("Progress: %d/%d indexed", stats["indexed"], len(entries))
            else:
                stats["duplicates"] += 1
        except Exception as e:
            logger.error("Failed to index entry %d: %s", i, e)
            stats["errors"] += 1

    return stats


def show_stats():
    """Display current state of YAML + PostgreSQL."""
    entries = load_yaml_kb()
    print(f"YAML knowledge base: {len(entries)} entries")

    from collections import Counter

    domains = Counter(e.get("source_domain", "?") for e in entries)
    print("By source_domain:", dict(domains.most_common()))

    categories = Counter()
    for e in entries:
        for c in e.get("categories", []):
            categories[c] += 1
    print("By category:", dict(categories.most_common()))

    try:
        from src.core.knowledge.knowledge_base import knowledge_base

        results = knowledge_base.search("строительство", top_k=1, min_weight=0)
        print(f"PostgreSQL search test: {len(results)} results")
    except Exception as e:
        print(f"PostgreSQL check: {e}")


def main():
    parser = argparse.ArgumentParser(description="Telegram KB → PostgreSQL sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    parser.add_argument("--limit", type=int, default=0, help="Max entries to process")
    parser.add_argument("--domain", type=str, default=None, help="Filter by domain (legal|pto|smeta|procurement)")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    entries = load_yaml_kb()
    if not entries:
        logger.error("No entries to ingest")
        sys.exit(1)

    logger.info("Loaded %d entries from YAML", len(entries))

    stats = ingest_entries(
        entries,
        dry_run=args.dry_run,
        domain_filter=args.domain,
        limit=args.limit,
    )

    print(f"\n=== Ingestion Summary ===")
    print(f"Total processed:    {stats['total']}")
    print(f"Indexed (new):      {stats['indexed']}")
    print(f"Duplicates skipped: {stats['duplicates']}")
    print(f"Errors:             {stats['errors']}")
    print(f"Skipped (filter):   {stats['skipped_filter']}")


if __name__ == "__main__":
    main()
