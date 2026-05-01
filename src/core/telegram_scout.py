"""
ASD v12.0 — TelegramScout: Live Multi-Domain Trap Ingestion via Telethon.

Weekly cron: for each domain (legal, pto, smeta, logistics, procurement),
fetches new messages from configured Telegram channels, filters noise via LLM,
and saves as DomainTrap records with embeddings.

Requires: telethon>=1.36.0, apscheduler, Telegram API credentials.
Gracefully degrades if credentials are not configured.

Usage:
    from src.core.telegram_scout import telegram_scout

    # One-off scan
    await telegram_scout.scan_domain("legal")

    # Start scheduler (weekly, per domain)
    telegram_scout.start_scheduler()

    # CLI
    python -m src.core.telegram_scout --domain legal --once
"""

from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

logger = logging.getLogger(__name__)

# =============================================================================
# Domain-specific extraction prompts
# =============================================================================

DOMAIN_EXTRACTION_PROMPTS: Dict[str, str] = {
    "legal": """You are a construction law expert. Read this Telegram post.
Extract PRACTICAL knowledge: contract traps, court precedents, regulatory changes, subcontractor risks.
SKIP: ads, self-promotion, news without legal substance, beginner questions, reposts.
If it contains actionable legal insight for a construction subcontractor, extract it.
Otherwise return {"is_trap": false}.""",

    "pto": """You are a construction documentation (ПТО) expert. Read this Telegram post.
Extract PRACTICAL knowledge: typical mistakes in as-built documentation (ИД), hidden work inspection tricks,
journal filling nuances, regulatory requirements for executive documentation.
SKIP: ads, self-promotion, general chatter, questions, reposts.
If it contains actionable insight for a ПТО engineer, extract it.
Otherwise return {"is_trap": false}.""",

    "smeta": """You are a construction cost estimation (Сметчик) expert. Read this Telegram post.
Extract PRACTICAL knowledge: pricing tricks, coefficient manipulation, ФЕР/ТЕР nuances,
index application errors, НМЦК calculation pitfalls, КС-2/КС-3 issues.
SKIP: ads, self-promotion, general chatter, questions, reposts.
If it contains actionable insight for a cost estimator, extract it.
Otherwise return {"is_trap": false}.""",

    "procurement": """You are a construction procurement (Закупщик) expert. Read this Telegram post.
Extract PRACTICAL knowledge: tender traps, supplier verification methods, ФЗ-44/ФЗ-223 nuances,
bid documentation analysis, material quality verification, competitor analysis.
SKIP: ads, self-promotion, general chatter, questions, reposts.
If it contains actionable insight for a procurement specialist, extract it.
Otherwise return {"is_trap": false}.""",

    "logistics": """You are a construction logistics (Логист) expert. Read this Telegram post.
Extract PRACTICAL knowledge: supply chain risks, delivery timing issues, certificate verification,
warehouse management, transportation regulations, TTN documentation.
SKIP: ads, self-promotion, general chatter, questions, reposts.
If it contains actionable insight for a logistics specialist, extract it.
Otherwise return {"is_trap": false}.""",
}

# =============================================================================
# Default channels config path
# =============================================================================

DEFAULT_CHANNELS_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "telegram_channels.yaml",
)

# =============================================================================
# Noise patterns (regex for filtering out obvious junk)
# =============================================================================

NOISE_PATTERNS = [
    re.compile(r"реклама", re.IGNORECASE),
    re.compile(r"купить.*со?скидк", re.IGNORECASE),
    re.compile(r"прайс[-\s]?лист", re.IGNORECASE),
    re.compile(r"акция.*дня", re.IGNORECASE),
    re.compile(r"подписывайт[еь]сь.*канал", re.IGNORECASE),
    re.compile(r"розыгрыш|конкурс|приз", re.IGNORECASE),
    re.compile(r"^\d{1,2}\s*(июл|июн|авг|сен|окт|ноя|дек|янв|фев|мар|апр|ма).*\d{4}", re.IGNORECASE),  # date-only posts
]


def _is_noise(text: str) -> bool:
    """Quick pre-filter: detect obvious ads/spam without LLM call."""
    if len(text.strip()) < 30:
        return True
    for pattern in NOISE_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =============================================================================
# Build domain-specific prompt from channel catalog
# =============================================================================

def _build_domain_prompt(
    catalog: Any, channel_name: str, domain: str, priority: str
) -> str:
    """Build extraction prompt with channel-specific focus areas."""
    base = DOMAIN_EXTRACTION_PROMPTS.get(domain, DOMAIN_EXTRACTION_PROMPTS["legal"])
    focus_areas = catalog.get_focus_areas(channel_name) if catalog else []

    if focus_areas:
        areas_text = ", ".join(focus_areas)
        base += f"\n\nThis channel specializes in: {areas_text}. Pay special attention to these areas."

    if priority == "critical":
        base += "\n\nThis is a critical-priority channel. Be thorough."

    return base


# =============================================================================
# Channel Catalog (minimal inline version — uses the one from ingest script)
# =============================================================================

def _load_channels_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load telegram_channels.yaml."""
    path = config_path or DEFAULT_CHANNELS_CONFIG
    if not os.path.exists(path):
        logger.warning("Channels config not found: %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_channels_for_domain(config: Dict[str, Any], domain: str) -> List[Dict[str, Any]]:
    """Extract channels belonging to a specific domain from config."""
    result = []
    seen = set()
    for ch in config.get("channels", []):
        username = ch.get("username", "")
        if username in seen:
            continue
        seen.add(username)

        ch_domain = ch.get("domain")
        if not ch_domain:
            cat = ch.get("category", "")
            if cat.startswith("legal_"):
                ch_domain = "legal"
            elif cat.startswith("pto_"):
                ch_domain = "pto"
            elif cat.startswith("smeta_"):
                ch_domain = "smeta"
            elif cat.startswith("logistics_"):
                ch_domain = "logistics"
            elif cat.startswith("procurement_"):
                ch_domain = "procurement"
            else:
                ch_domain = "legal"

        if ch_domain == domain:
            result.append(ch)
    return result


# =============================================================================
# TelegramScout
# =============================================================================

class TelegramScout:
    """
    Live Telegram monitor for domain-specific trap ingestion.

    Architecture:
      1. Connect via Telethon (API ID + hash + phone)
      2. For each domain: iterate configured channels
      3. Fetch messages since last check
      4. Pre-filter noise (regex)
      5. LLM relevance check (confidence >= 0.7)
      6. Deduplicate by channel + message_id hash
      7. Save as DomainTrap with embedding
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or DEFAULT_CHANNELS_CONFIG
        self._config = None
        self._client = None
        self._scheduler = None
        self._last_check: Dict[str, datetime] = {}  # domain → last check time
        self._seen_messages: Set[str] = set()  # hash(channel + msg_id) for dedup
        self._stats: Dict[str, Dict[str, int]] = {}  # domain → stats

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    @property
    def config(self) -> Dict[str, Any]:
        if self._config is None:
            self._config = _load_channels_config(self._config_path)
        return self._config

    @property
    def is_configured(self) -> bool:
        """Check if Telegram credentials are available."""
        api_id = os.environ.get("TG_API_ID")
        api_hash = os.environ.get("TG_API_HASH")
        return bool(api_id and api_hash)

    def get_credentials(self) -> tuple:
        """Get Telegram API credentials from environment."""
        api_id = os.environ.get("TG_API_ID")
        api_hash = os.environ.get("TG_API_HASH")
        phone = os.environ.get("TG_PHONE")
        if not api_id or not api_hash:
            raise ValueError(
                "Telegram API credentials not configured. "
                "Set TG_API_ID, TG_API_HASH, TG_PHONE environment variables."
            )
        return api_id, api_hash, phone

    # -------------------------------------------------------------------------
    # Telethon client
    # -------------------------------------------------------------------------

    async def _get_client(self):
        """Lazy-init Telethon client."""
        if self._client is not None:
            return self._client

        try:
            from telethon import TelegramClient
        except ImportError:
            raise ImportError(
                "telethon is required for live Telegram monitoring. "
                "Install: pip install telethon>=1.36.0"
            )

        api_id, api_hash, phone = self.get_credentials()
        self._client = TelegramClient("asd_scout_session", int(api_id), api_hash)
        await self._client.start(phone=phone)
        logger.info("Telethon client connected")
        return self._client

    async def _disconnect(self):
        if self._client:
            await self._client.disconnect()
            self._client = None

    # -------------------------------------------------------------------------
    # Message processing
    # -------------------------------------------------------------------------

    def _make_msg_key(self, channel: str, msg_id: int) -> str:
        """Generate unique dedup key for a message."""
        raw = f"{channel}:{msg_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _build_extraction_json_schema(self) -> str:
        """JSON schema for LLM extraction output."""
        return json.dumps({
            "is_trap": True,
            "title": "Short title (max 10 words, Russian)",
            "description": "Full description and why it matters for the specialist",
            "mitigation": "How to avoid or use this knowledge",
            "confidence": 0.85,
        }, ensure_ascii=False)

    async def _extract_and_save(
        self, text: str, channel_info: Dict[str, Any], domain: str
    ) -> bool:
        """
        LLM extraction + save to DomainTrap.
        Returns True if a trap was saved.
        """
        from src.core.llm_engine import llm_engine
        from src.db.init_db import SessionLocal
        from src.db.models import DomainTrap

        channel_name = channel_info.get("username", "unknown")
        channel_display = channel_info.get("display_name", channel_name)
        priority = channel_info.get("priority", "medium")
        category = channel_info.get("category", "unknown")
        weight = int(channel_info.get("weight", 0.5) * 100) if isinstance(
            channel_info.get("weight"), float
        ) else channel_info.get("weight", 50)

        # Build prompt
        system_prompt = _build_domain_prompt(None, channel_name, domain, priority)
        schema = self._build_extraction_json_schema()

        full_prompt = f"""{system_prompt}

Output ONLY valid JSON following this exact schema:
{schema}

Respond ONLY with the JSON. No other text."""

        try:
            response = await llm_engine.safe_chat(
                domain if domain != "legal" else "legal",
                [
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": text[:8000]},
                ],
                fallback_response='{"is_trap": false}',
                temperature=0.1,
            )

            data = json.loads(response)
        except (json.JSONDecodeError, TypeError, Exception) as e:
            logger.debug("LLM extraction failed for %s: %s", channel_name, e)
            return False

        if not data.get("is_trap"):
            return False

        confidence = data.get("confidence", 1.0)
        if confidence < 0.7:
            logger.debug("Trap below confidence threshold: %.2f", confidence)
            return False

        title = data.get("title", "Untitled")
        description = data.get("description", "")
        mitigation = data.get("mitigation", "")

        # Generate embedding
        embed_text = f"{title}\n{description}"
        embedding = await llm_engine.embed(embed_text) if embed_text.strip() else None

        # Save
        db = SessionLocal()
        try:
            trap = DomainTrap(
                domain=domain,
                title=title,
                description=description,
                source=f"Telegram @{channel_name}",
                channel=channel_name,
                category=category,
                weight=weight,
                mitigation=mitigation,
                embedding=embedding,
            )
            db.add(trap)
            db.commit()
            logger.info("New %s trap: %s (@%s)", domain, title, channel_name)
            return True
        except Exception as e:
            db.rollback()
            logger.error("Failed to save trap: %s", e)
            return False
        finally:
            db.close()

    # -------------------------------------------------------------------------
    # Channel scanning
    # -------------------------------------------------------------------------

    async def _scan_channel(
        self,
        client,
        channel_username: str,
        channel_info: Dict[str, Any],
        domain: str,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> int:
        """
        Scan a single Telegram channel for new messages.
        Returns number of traps found.
        """
        trapped = 0
        channel_name = channel_info.get("display_name", channel_username)

        try:
            entity = await client.get_entity(channel_username)
        except Exception as e:
            logger.warning("Cannot access channel @%s: %s", channel_username, e)
            return 0

        try:
            messages = await client.get_messages(entity, limit=limit)
        except Exception as e:
            logger.warning("Failed to fetch messages from @%s: %s", channel_username, e)
            return 0

        for msg in messages:
            if msg is None or not msg.text:
                continue

            msg_key = self._make_msg_key(channel_username, msg.id)
            if msg_key in self._seen_messages:
                continue

            self._seen_messages.add(msg_key)

            text = msg.text
            if _is_noise(text):
                continue

            if since and msg.date and msg.date < since:
                continue

            try:
                saved = await self._extract_and_save(text, channel_info, domain)
                if saved:
                    trapped += 1
            except Exception as e:
                logger.error("Error processing message %s: %s", msg.id, e)

        if trapped:
            logger.info("@%s: %d traps found", channel_username, trapped)
        return trapped

    # -------------------------------------------------------------------------
    # Domain scan
    # -------------------------------------------------------------------------

    async def scan_domain(
        self,
        domain: str,
        since: Optional[datetime] = None,
        limit_per_channel: int = 50,
    ) -> Dict[str, int]:
        """
        Scan all channels for a given domain.

        Args:
            domain: legal | pto | smeta | logistics | procurement
            since: Only process messages newer than this (default: 7 days ago)
            limit_per_channel: Max messages to fetch per channel

        Returns:
            {"channels_scanned": N, "traps_found": N, "errors": N}
        """
        if not self.is_configured:
            logger.warning(
                "TelegramScout: credentials not configured. "
                "Set TG_API_ID, TG_API_HASH, TG_PHONE env vars."
            )
            return {"channels_scanned": 0, "traps_found": 0, "errors": 1}

        channels = _get_channels_for_domain(self.config, domain)
        if not channels:
            logger.warning("No channels configured for domain: %s", domain)
            return {"channels_scanned": 0, "traps_found": 0, "errors": 0}

        if since is None:
            since = datetime.now() - timedelta(days=7)

        logger.info(
            "Scanning domain=%s: %d channels, since=%s",
            domain, len(channels), since.isoformat(),
        )

        try:
            client = await self._get_client()
        except Exception as e:
            logger.error("Failed to connect Telethon: %s", e)
            return {"channels_scanned": 0, "traps_found": 0, "errors": 1}

        stats = {"channels_scanned": 0, "traps_found": 0, "errors": 0}

        for ch in channels:
            username = ch.get("username", "")
            if not username:
                continue

            try:
                trapped = await self._scan_channel(
                    client, username, ch, domain,
                    since=since, limit=limit_per_channel,
                )
                stats["channels_scanned"] += 1
                stats["traps_found"] += trapped
            except Exception as e:
                logger.error("Error scanning @%s: %s", username, e)
                stats["errors"] += 1

        self._last_check[domain] = datetime.now()
        self._stats[domain] = stats

        logger.info(
            "Domain '%s' scan complete: %d channels, %d traps, %d errors",
            domain, stats["channels_scanned"], stats["traps_found"], stats["errors"],
        )
        return stats

    async def scan_all_domains(
        self, since: Optional[datetime] = None, limit_per_channel: int = 50
    ) -> Dict[str, Dict[str, int]]:
        """Scan all 5 domains sequentially."""
        results = {}
        for domain in ["legal", "pto", "smeta", "logistics", "procurement"]:
            results[domain] = await self.scan_domain(
                domain, since=since, limit_per_channel=limit_per_channel,
            )
        return results

    # -------------------------------------------------------------------------
    # Scheduler
    # -------------------------------------------------------------------------

    def start_scheduler(self, weekly: bool = True):
        """
        Start APScheduler for periodic scanning.

        Args:
            weekly: True = once per week (Sunday 03:00), False = daily at 03:00
        """
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError:
            logger.warning(
                "apscheduler not installed. Install: pip install apscheduler"
            )
            return

        if self._scheduler is not None:
            return

        self._scheduler = AsyncIOScheduler()
        domains = ["legal", "pto", "smeta", "logistics", "procurement"]

        for i, domain in enumerate(domains):
            if weekly:
                # Stagger: each domain on a different day to spread LLM load
                days = ["sun", "mon", "tue", "wed", "thu"]
                day = days[i % len(days)]
                hour = 3 + (i % 3)  # 03:00, 04:00, 05:00
                self._scheduler.add_job(
                    self.scan_domain,
                    "cron",
                    args=[domain],
                    kwargs={"limit_per_channel": 100},
                    day_of_week=day,
                    hour=hour,
                    minute=13 + (i * 7),  # Jitter: avoid round numbers
                    id=f"scout_{domain}",
                    name=f"TelegramScout: {domain}",
                )
            else:
                self._scheduler.add_job(
                    self.scan_domain,
                    "cron",
                    args=[domain],
                    kwargs={"limit_per_channel": 50},
                    hour=3,
                    minute=13 + (i * 7),
                    id=f"scout_{domain}",
                )

        self._scheduler.start()
        logger.info(
            "TelegramScout scheduler started: %d domains, %s schedule",
            len(domains),
            "weekly (staggered days)" if weekly else "daily",
        )

    def stop_scheduler(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return scout status for health checks."""
        return {
            "configured": self.is_configured,
            "scheduler_running": self._scheduler is not None and self._scheduler.running,
            "last_checks": {
                k: v.isoformat() for k, v in self._last_check.items()
            },
            "seen_messages": len(self._seen_messages),
            "stats": self._stats,
        }


# =============================================================================
# Singleton
# =============================================================================

telegram_scout = TelegramScout()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    import asyncio

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="MAC_ASD v12.0 — TelegramScout: Multi-domain trap ingestion"
    )
    parser.add_argument(
        "--domain",
        choices=["legal", "pto", "smeta", "logistics", "procurement", "all"],
        default="all",
        help="Domain to scan (default: all)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no scheduler)",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=7,
        help="Process messages from last N days (default: 7)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max messages per channel (default: 50)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show scout status and exit",
    )

    args = parser.parse_args()

    if args.status:
        import json as _json
        print(_json.dumps(telegram_scout.status(), indent=2, ensure_ascii=False))
    elif args.once:
        since = datetime.now() - timedelta(days=args.since_days)
        if args.domain == "all":
            results = asyncio.run(
                telegram_scout.scan_all_domains(since=since, limit_per_channel=args.limit)
            )
            for dom, stats in results.items():
                print(f"  {dom}: {stats}")
        else:
            stats = asyncio.run(
                telegram_scout.scan_domain(
                    args.domain, since=since, limit_per_channel=args.limit
                )
            )
            print(f"  {args.domain}: {stats}")
    else:
        telegram_scout.start_scheduler(weekly=True)
        print("TelegramScout scheduler started. Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            telegram_scout.stop_scheduler()
            print("Stopped.")
