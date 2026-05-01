"""
ASD v12.0 — Migrate Python reference dicts to PostgreSQL domain_references table.

Reads existing Python dict data (rate_lookup, work_spec, contract_risks)
and writes them to domain_references via ReferenceService.

Usage:
    python -m src.scripts.migrate_references
    python -m src.scripts.migrate_references --domain smeta
    python -m src.scripts.migrate_references --dry-run
"""

import asyncio
import logging
import argparse
from datetime import datetime
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_rate_lookup(dry_run: bool = False) -> int:
    """Migrate rate_lookup.py FER rates to domain_references."""
    try:
        from src.agents.skills.smeta.rate_lookup import FER_RATES
    except ImportError:
        logger.warning("rate_lookup.py not found — skipping")
        return 0

    from src.core.reference_service import reference_service

    count = 0
    for code, data in FER_RATES.items():
        if dry_run:
            logger.info("  [DRY] %s: %s", code, data.get("name", ""))
            count += 1
            continue

        success = await reference_service.upsert(
            domain="smeta",
            code=code,
            description=data.get("name", ""),
            data={
                "unit": data.get("unit", ""),
                "base_price_kop": data.get("base_price_kop", 0),
                "category": data.get("category", ""),
            },
            source="ФСНБ-2024",
        )
        if success:
            count += 1
            logger.info("  Migrated: %s", code)

    return count


async def migrate_work_spec(dry_run: bool = False) -> int:
    """Migrate work_spec.py work types to domain_references."""
    try:
        from src.agents.skills.common.work_spec import WORK_SPEC
    except ImportError:
        logger.warning("work_spec.py not found — skipping")
        return 0

    from src.core.reference_service import reference_service

    count = 0
    for work_type, spec in WORK_SPEC.items():
        if dry_run:
            logger.info("  [DRY] pto/%s: %s", work_type, str(spec)[:80])
            count += 1
            continue

        description = spec.get("description", "") if isinstance(spec, dict) else str(spec)
        success = await reference_service.upsert(
            domain="pto",
            code=f"WORK-{work_type}",
            description=description,
            data=spec if isinstance(spec, dict) else {"raw": str(spec)},
            source="internal",
        )
        if success:
            count += 1
            logger.info("  Migrated: WORK-%s", work_type)

    return count


async def migrate_contract_risks(dry_run: bool = False) -> int:
    """Migrate contract_risks.py BLC seed data to domain_references."""
    try:
        from src.agents.skills.legal.contract_risks import BLC_SEED_DATA
    except ImportError:
        logger.warning("contract_risks.py not found — skipping")
        return 0

    from src.core.reference_service import reference_service

    count = 0
    for item in BLC_SEED_DATA:
        code = item.get("id", f"RISK-{count:03d}")
        title = item.get("title", "")
        if dry_run:
            logger.info("  [DRY] legal/%s: %s", code, title)
            count += 1
            continue

        success = await reference_service.upsert(
            domain="legal",
            code=code,
            description=title,
            data={
                "description": item.get("description", ""),
                "category": item.get("category", ""),
                "pattern": item.get("pattern", ""),
                "recommendation": item.get("recommendation", ""),
            },
            source="BLC_YAML",
        )
        if success:
            count += 1
            logger.info("  Migrated: %s", code)

    return count


async def migrate_all(dry_run: bool = False) -> Dict[str, int]:
    """Run all reference migrations."""
    logger.info("Migrating reference data to domain_references...")
    if dry_run:
        logger.info("DRY RUN mode — no changes will be made")

    results = {}

    logger.info("\n=== SMETA: FER Rates ===")
    results["smeta"] = await migrate_rate_lookup(dry_run)

    logger.info("\n=== PTO: Work Specs ===")
    results["pto"] = await migrate_work_spec(dry_run)

    logger.info("\n=== LEGAL: Contract Risks ===")
    results["legal"] = await migrate_contract_risks(dry_run)

    total = sum(results.values())
    logger.info(
        "\n%sReference migration complete: %d total entries across %d domains",
        "[DRY RUN] " if dry_run else "",
        total,
        len([v for v in results.values() if v > 0]),
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate Python reference dicts to domain_references table"
    )
    parser.add_argument(
        "--domain",
        choices=["smeta", "pto", "legal", "all"],
        default="all",
        help="Domain to migrate (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be migrated without making changes",
    )

    args = parser.parse_args()

    if args.domain == "smeta":
        count = asyncio.run(migrate_rate_lookup(args.dry_run))
        logger.info("Smeta entries: %d", count)
    elif args.domain == "pto":
        count = asyncio.run(migrate_work_spec(args.dry_run))
        logger.info("PTO entries: %d", count)
    elif args.domain == "legal":
        count = asyncio.run(migrate_contract_risks(args.dry_run))
        logger.info("Legal entries: %d", count)
    else:
        asyncio.run(migrate_all(args.dry_run))
