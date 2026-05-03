"""
ASD v12.0 — Telegram Ingestion Pipeline.

Receives forwarded Telegram messages, filters noise/ads via DomainClassifier,
stores relevant content in KnowledgeBase.

Two modes:
  1. Manual: forward a post to @My_os_hermes_bot → auto-processed
  2. Batch:   python scripts/telegram_ingest.py /path/to/export.json

Usage:
    python scripts/telegram_ingest.py export.json --domain-filter legal,pto
    python scripts/telegram_ingest.py --batch-file posts.txt

Architecture:
    Forwarded msg → DomainClassifier.classify() →
        ✓ relevant → KnowledgeBase.add_knowledge() → agents can search
        ✗ noise/ad → logged, rejected
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Core Ingester
# =============================================================================

class TelegramIngester:
    """
    Ingests Telegram posts into ASD Knowledge Base.

    Filters: ads, spam, news fluff, short messages, duplicates.
    Classifies: legal, pto, smeta, procurement.
    Stores: KnowledgeBase (pgvector + keyword index).
    """

    # Minimum characters for a meaningful post
    MIN_CHARS = 80

    # Source channel tracking
    _processed_ids: set = set()
    _stats: Dict[str, int] = {"received": 0, "accepted": 0, "rejected": 0, "ad": 0, "spam": 0, "short": 0}

    def __init__(self):
        from src.core.knowledge.domain_classifier import domain_classifier
        from src.core.knowledge.knowledge_base import knowledge_base
        self._classifier = domain_classifier
        self._kb = knowledge_base

    def ingest_message(
        self,
        text: str,
        source_channel: Optional[str] = None,
        message_id: Optional[int] = None,
        post_date: Optional[str] = None,
        author: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingest a single Telegram message.

        Args:
            text: Message text content
            source_channel: @username of source channel
            message_id: Telegram message ID (for dedup)
            post_date: ISO date of post (defaults to now)
            author: Post author if known
            force: Skip noise filtering (debug only)

        Returns:
            {
                "status": "accepted" | "rejected",
                "domain": "legal" | "pto" | ... | None,
                "confidence": float,
                "reason": str,  # For rejections
                "knowledge_id": str | None,  # KB entry ID if stored
            }
        """
        self._stats["received"] += 1

        # Dedup
        if message_id and message_id in self._processed_ids:
            logger.debug("Duplicate message %s, skipping", message_id)
            return {"status": "rejected", "reason": "duplicate", "confidence": 0.0}

        if message_id:
            self._processed_ids.add(message_id)

        # Pre-filter: too short
        if len(text) < self.MIN_CHARS:
            self._stats["short"] += 1
            self._stats["rejected"] += 1
            logger.debug("Message too short (%d chars), skipping", len(text))
            return {"status": "rejected", "reason": "too_short", "confidence": 0.0}

        # Strip forwarded message headers
        clean_text = self._clean_forwarded_text(text)

        # Classify
        result = self._classifier.classify(
            text=clean_text,
            source_channel=source_channel,
            strict_noise=not force,
        )

        if result.is_noise and not force:
            self._stats[result.noise_type] = self._stats.get(result.noise_type, 0) + 1
            self._stats["rejected"] += 1
            return {
                "status": "rejected",
                "reason": f"noise:{result.noise_type}",
                "confidence": result.confidence,
                "signals": result.signals,
            }

        if not result.domain and not force:
            self._stats["rejected"] += 1
            return {"status": "rejected", "reason": "no_domain", "confidence": 0.0}

        # Build and store
        domain = result.domain or "legal"
        title = self._extract_title(clean_text)
        
        trap_id = self._kb.index_trap(
            domain=domain,
            title=title,
            description=clean_text[:3000],
            source=f"telegram:{source_channel}" if source_channel else "telegram:manual",
            channel=source_channel or "",
            category=result.suggested_category or "",
            weight=int(result.confidence * 100),
        )

        self._stats["accepted"] += 1
        logger.info(
            "Ingested: domain=%s, title='%s', chars=%d, trap_id=%s",
            domain, title[:50], len(clean_text), trap_id,
        )

        return {
            "status": "accepted",
            "domain": domain,
            "confidence": round(result.confidence, 2),
            "knowledge_id": str(trap_id) if trap_id else None,
            "signals": result.signals,
        }

    def ingest_batch(
        self,
        messages: List[Dict[str, Any]],
        domain_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest batch of messages.

        Args:
            messages: List of {text, source_channel, message_id, date, author}
            domain_filter: Optional list of domains to accept (e.g. ["legal", "pto"])

        Returns:
            {total, accepted, rejected, by_domain: {domain: count}, errors: [...]}
        """
        results = {
            "total": len(messages),
            "accepted": 0,
            "rejected": 0,
            "by_domain": {},
            "by_status": {},
            "errors": [],
        }

        for i, msg in enumerate(messages):
            try:
                result = self.ingest_message(
                    text=msg.get("text", ""),
                    source_channel=msg.get("source_channel"),
                    message_id=msg.get("message_id"),
                    post_date=msg.get("date"),
                    author=msg.get("author"),
                )

                status = result["status"]
                results["by_status"][status] = results["by_status"].get(status, 0) + 1

                if status == "accepted":
                    dom = result.get("domain", "unknown")
                    if domain_filter and dom not in domain_filter:
                        continue
                    results["accepted"] += 1
                    results["by_domain"][dom] = results["by_domain"].get(dom, 0) + 1
                else:
                    results["rejected"] += 1
                    reason = result.get("reason", "unknown")
                    results["by_status"][f"rejected:{reason}"] = (
                        results["by_status"].get(f"rejected:{reason}", 0) + 1
                    )

            except Exception as e:
                results["errors"].append({"index": i, "error": str(e)})
                logger.error("Batch ingest error at index %d: %s", i, e)

        logger.info(
            "Batch ingest: %d messages → %d accepted, %d rejected, %d errors",
            results["total"], results["accepted"], results["rejected"],
            len(results["errors"]),
        )
        return results

    def get_stats(self) -> Dict[str, int]:
        """Get ingestion statistics."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        for key in self._stats:
            self._stats[key] = 0

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _clean_forwarded_text(text: str) -> str:
        """Remove Telegram forwarded message headers like 'Forwarded from ...'."""
        # Remove "Forwarded from XXX" header
        text = re.sub(r'^Forwarded from .+\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^Переслано от .+\n', '', text)
        text = re.sub(r'^📢\s*.+\n', '', text)  # Channel announcement prefix
        return text.strip()

    @staticmethod
    def _extract_title(text: str) -> str:
        """Extract title from message text — first meaningful line."""
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith(("http", "@", "#"))]
        if lines:
            title = lines[0][:120]
            # Remove emoji at start
            title = re.sub(r'^[\U0001F300-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+\s*', '', title)
            return title.strip()
        return text[:80]

    @classmethod
    def from_export_file(cls, filepath: str) -> List[Dict[str, Any]]:
        """
        Parse Telegram channel export JSON into message list.

        Expected format: Telegram Desktop export JSON
        {
            "name": "Channel Name",
            "messages": [
                {"id": 123, "type": "message", "date": "...", "text": ["..."]},
                ...
            ]
        }
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        channel_name = data.get("name", "")
        messages = []

        for msg in data.get("messages", []):
            if msg.get("type") != "message":
                continue
            text_parts = msg.get("text", [])
            if isinstance(text_parts, list):
                text = " ".join(
                    part if isinstance(part, str) else part.get("text", "")
                    for part in text_parts
                )
            else:
                text = str(text_parts)

            if text.strip():
                messages.append({
                    "text": text,
                    "source_channel": channel_name,
                    "message_id": msg.get("id"),
                    "date": msg.get("date"),
                    "author": msg.get("from", ""),
                })

        return messages


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI: process Telegram export or batch file."""
    import argparse

    parser = argparse.ArgumentParser(description="ASD Telegram ingestion")
    parser.add_argument("input", help="JSON export file or --batch-file")
    parser.add_argument("--batch-file", action="store_true", help="Input is a text file with one post per line")
    parser.add_argument("--domain-filter", help="Comma-separated domains to accept")
    parser.add_argument("--force", action="store_true", help="Skip noise filtering")
    parser.add_argument("--stats", action="store_true", help="Show stats only, no ingestion")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    ingester = TelegramIngester()

    if args.stats:
        print(json.dumps(ingester.get_stats(), indent=2))
        return

    if args.batch_file:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()
        messages = [{"text": text, "source_channel": "manual"}]
    else:
        messages = TelegramIngester.from_export_file(args.input)

    domain_filter = args.domain_filter.split(",") if args.domain_filter else None

    results = ingester.ingest_batch(messages, domain_filter=domain_filter)
    print(json.dumps(results, indent=2, ensure_ascii=False))


# Singleton
telegram_ingester = TelegramIngester()


if __name__ == "__main__":
    main()
