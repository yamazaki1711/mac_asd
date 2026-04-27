"""
MAC_ASD v11.3 — Load BLC Traps from YAML to Database.

Reads traps/default_traps.yaml (58 traps, 10 categories),
generates embeddings via bge-m3, and inserts into legal_traps table.

Categories: payment, penalty, acceptance, scope, warranty,
            subcontractor, liability, corporate_policy,
            termination (NEW), insurance (NEW)

Usage:
    python -m src.scripts.load_traps
    python -m src.scripts.load_traps --file traps/custom_traps.yaml
    python -m src.scripts.load_traps --force   # overwrite existing traps
"""

import os
import argparse
import asyncio
import logging
from pathlib import Path

import yaml
from sqlalchemy import select

from src.db.init_db import SessionLocal
from src.db.models import LegalTrap
from src.core.llm_engine import llm_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default path to traps YAML
DEFAULT_TRAPS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "traps",
    "default_traps.yaml",
)


async def load_traps(yaml_path: str, force: bool = False) -> dict:
    """
    Load traps from YAML file into the database.

    Args:
        yaml_path: Path to YAML file with trap definitions
        force: If True, delete existing traps before loading

    Returns:
        {"loaded": N, "skipped": N, "errors": N}
    """
    if not os.path.exists(yaml_path):
        logger.error(f"Traps file not found: {yaml_path}")
        return {"loaded": 0, "skipped": 0, "errors": 1}

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    traps = data.get("traps", [])
    if not traps:
        logger.warning("No traps found in YAML file")
        return {"loaded": 0, "skipped": 0, "errors": 0}

    logger.info(f"Found {len(traps)} traps in {yaml_path}")

    # Category → weight mapping (v11.3.0: 10 categories, 58 traps)
    category_weights = {
        "payment": 100,
        "penalty": 100,
        "acceptance": 100,
        "scope": 100,
        "warranty": 90,
        "subcontractor": 100,
        "liability": 100,
        "corporate_policy": 90,
        "termination": 100,     # ★ NEW — расторжение договора
        "insurance": 90,        # ★ NEW — страхование
    }

    db = SessionLocal()
    stats = {"loaded": 0, "skipped": 0, "errors": 0}

    try:
        if force:
            deleted = db.query(LegalTrap).delete()
            db.commit()
            logger.info(f"Force mode: deleted {deleted} existing traps")

        for trap_def in traps:
            trap_id = trap_def.get("id", "unknown")
            title = trap_def.get("title", "Untitled Trap")
            category = trap_def.get("category", "unknown")

            # Check if trap already exists (by title)
            existing = db.query(LegalTrap).filter(LegalTrap.title == title).first()
            if existing and not force:
                logger.info(f"  Skipping (exists): {title}")
                stats["skipped"] += 1
                continue

            # Generate embedding from description + pattern
            embed_text = f"{trap_def.get('description', '')} {trap_def.get('pattern', '')}"
            try:
                embedding = await llm_engine.embed(embed_text)
            except Exception as e:
                logger.error(f"  Embedding failed for '{title}': {e}")
                stats["errors"] += 1
                continue

            # Create trap record
            weight = category_weights.get(category, 80)

            trap = LegalTrap(
                title=title,
                description=trap_def.get("description", ""),
                source="BLC_YAML",
                channel=f"builtin:{trap_id}",
                category=category,
                weight=weight,
                court_cases=trap_def.get("court_cases", []),
                mitigation=trap_def.get("recommendation", ""),
                embedding=embedding,
            )

            if existing and force:
                # Update existing
                existing.title = trap.title
                existing.description = trap.description
                existing.source = trap.source
                existing.channel = trap.channel
                existing.category = trap.category
                existing.weight = trap.weight
                existing.court_cases = trap.court_cases
                existing.mitigation = trap.mitigation
                existing.embedding = trap.embedding
                logger.info(f"  Updated: {title} [{category}|w={weight}]")
            else:
                db.add(trap)
                logger.info(f"  Loaded: {title} [{category}|w={weight}]")

            stats["loaded"] += 1

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to load traps: {e}")
        stats["errors"] += 1
    finally:
        db.close()

    logger.info(
        f"\n{'='*50}\n"
        f"BLC Load Complete:\n"
        f"  Loaded:  {stats['loaded']}\n"
        f"  Skipped: {stats['skipped']}\n"
        f"  Errors:  {stats['errors']}\n"
        f"{'='*50}"
    )

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load BLC traps from YAML to DB")
    parser.add_argument(
        "--file",
        default=DEFAULT_TRAPS_FILE,
        help=f"Path to traps YAML (default: {DEFAULT_TRAPS_FILE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing traps before loading",
    )

    args = parser.parse_args()
    asyncio.run(load_traps(args.file, args.force))
