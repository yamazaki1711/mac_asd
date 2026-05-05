#!/usr/bin/env python3
"""
ASD v13.0 — Индексация нормативных документов в domain_traps.

Читает library/normative/normative_index.json, для каждого документа
создаёт запись в domain_traps с source='normative', weight=90.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/index_normative.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("index_normative")

# ── Category mapping ──────────────────────────────────────────────────
CATEGORY_MAP = {
    "gost": "gost",
    "sp": "sp",
    "snip": "snip",
    "prikaz": "prikaz",
    "pp_rf": "pp_rf",
    "fz": "federal_law",
    "kodeks": "code",
}


def make_description(doc: dict) -> str:
    """Build searchable description from document metadata."""
    parts = []

    title = doc.get("display", doc.get("title", ""))
    if title:
        parts.append(title)

    scope = doc.get("scope", "")
    if scope:
        parts.append(f"Область применения: {scope}")

    replaces = doc.get("replaces", "")
    if replaces:
        parts.append(f"Заменяет: {replaces}")

    warning = doc.get("warning", "")
    if warning:
        parts.append(f"⚠ {warning}")

    aliases = doc.get("aliases", [])
    if aliases:
        parts.append(f"Синонимы: {', '.join(aliases)}")

    return "\n".join(parts) if parts else title


def main():
    parser = argparse.ArgumentParser(description="Index normative documents → domain_traps")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    index_path = Path("library/normative/normative_index.json")
    if not index_path.exists():
        logger.error("normative_index.json not found at %s", index_path)
        sys.exit(1)

    with open(index_path) as f:
        index = json.load(f)

    # Filter: documents are under 'documents' key
    doc_dict = index.get("documents", {})
    if not doc_dict:
        # Fallback: try treating top-level entries as documents
        doc_dict = {k: v for k, v in index.items() if isinstance(v, dict) and "file" in v}

    documents = list(doc_dict.items())

    logger.info("Found %d normative documents", len(documents))

    if args.limit:
        documents = documents[: args.limit]

    from src.core.knowledge.knowledge_base import knowledge_base

    stats = {"total": 0, "indexed": 0, "duplicates": 0, "errors": 0}

    for doc_id, doc in documents:
        stats["total"] += 1

        # Determine domain
        category = doc.get("category", "")
        path_str = doc.get("path", "")
        domain = "legal"  # default

        # Map path-based category to domain
        for key, dom in {
            "gost": "pto",
            "sp": "pto",
            "snip": "pto",
            "prikaz": "pto",
            "pp_rf": "legal",
            "fz": "legal",
            "kodeksy": "legal",
        }.items():
            if key in path_str.lower():
                domain = dom
                break

        title = doc.get("display", doc.get("title", doc_id))
        description = make_description(doc)

        if args.dry_run:
            logger.info(
                "[DRY-RUN] %s [%s] → %s",
                doc_id, domain, title[:100],
            )
            stats["indexed"] += 1
            continue

        try:
            trap_id = knowledge_base.index_trap(
                domain=domain,
                title=title,
                description=description,
                source="normative",
                channel="",
                category=CATEGORY_MAP.get(category, "normative"),
                weight=90,
                mitigation="",
            )
            if trap_id:
                stats["indexed"] += 1
                if stats["indexed"] % 10 == 0:
                    logger.info("Progress: %d/%d", stats["indexed"], len(documents))
            else:
                stats["duplicates"] += 1
        except Exception as e:
            logger.error("Failed to index %s: %s", doc_id, e)
            stats["errors"] += 1

    print(f"\n=== Normative Index Summary ===")
    print(f"Total:       {stats['total']}")
    print(f"Indexed:     {stats['indexed']}")
    print(f"Duplicates:  {stats['duplicates']}")
    print(f"Errors:      {stats['errors']}")


if __name__ == "__main__":
    main()
