"""
MAC_ASD v13.0 — Backup Service (P0, May 2026).

Автоматические бэкапы: БД (pg_dump), графы, артефакты.
Ротация: 24 часовых + 7 дневных + 4 недельных.

Usage:
    from src.core.backup import backup_service
    await backup_service.backup_all()

CLI:
    python -m src.core.backup          # single backup
    python -m src.core.backup --rotate  # backup + rotate
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


class BackupService:
    """
    Сервис автоматического резервного копирования.

    Политика ротации:
        hourly  — 24 последних часовых бэкапа (один в час)
        daily   — 7 последних дневных (первый бэкап каждого дня)
        weekly  — 4 последних недельных (первый бэкап каждой недели)
    """

    def __init__(self):
        self.backup_root = Path(settings.BASE_DIR) / "backups"
        self.hourly_dir = self.backup_root / "hourly"
        self.daily_dir = self.backup_root / "daily"
        self.weekly_dir = self.backup_root / "weekly"

        for d in [self.hourly_dir, self.daily_dir, self.weekly_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ═════════════════════════════════════════════════════════════════════
    # Public API
    # ═════════════════════════════════════════════════════════════════════

    async def backup_all(self) -> Dict[str, any]:
        """
        Выполнить полный бэкап: БД + графы + артефакты.

        Returns:
            {"status": "ok"|"partial"|"error", "files": [...], "errors": [...]}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = {"status": "ok", "files": [], "errors": []}

        # 1. Database
        db_file = self.backup_root / f"db_{timestamp}.sql.gz"
        try:
            self._backup_database(db_file)
            results["files"].append(str(db_file))
            logger.info("DB backup: %s", db_file.name)
        except Exception as e:
            results["errors"].append(f"DB backup failed: {e}")
            logger.error("DB backup failed: %s", e)

        # 2. Graphs
        graphs_file = self.backup_root / f"graphs_{timestamp}.tar.gz"
        try:
            self._backup_graphs(graphs_file)
            results["files"].append(str(graphs_file))
            logger.info("Graphs backup: %s", graphs_file.name)
        except Exception as e:
            results["errors"].append(f"Graphs backup failed: {e}")
            logger.error("Graphs backup failed: %s", e)

        # 3. Artifacts
        artifacts_file = self.backup_root / f"artifacts_{timestamp}.tar.gz"
        try:
            if settings.artifacts_path.exists():
                self._backup_artifacts(artifacts_file)
                results["files"].append(str(artifacts_file))
                logger.info("Artifacts backup: %s", artifacts_file.name)
        except Exception as e:
            results["errors"].append(f"Artifacts backup failed: {e}")
            logger.error("Artifacts backup failed: %s", e)

        # Determine status
        if len(results["errors"]) == 3:
            results["status"] = "error"
        elif results["errors"]:
            results["status"] = "partial"

        return results

    async def rotate(self, dry_run: bool = False) -> Dict[str, any]:
        """
        Применить политику ротации: переместить свежие бэкапы в
        hourly/daily/weekly и удалить старые.

        Returns:
            {"rotated": int, "deleted": int, "kept": {...}}
        """
        now = datetime.now()
        all_backups = sorted(
            self.backup_root.glob("db_*.sql.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not all_backups:
            return {"rotated": 0, "deleted": 0, "kept": {}}

        # ── Hourly: keep the last 24, one per hour ─────────────────────
        hourly_kept = self._rotate_tier(
            all_backups,
            self.hourly_dir,
            max_count=24,
            granularity="hour",
            now=now,
            dry_run=dry_run,
        )

        # ── Daily: keep the first of each day, last 7 days ─────────────
        daily_candidates = sorted(self.hourly_dir.glob("db_*.sql.gz*")) if not dry_run else all_backups
        daily_kept = self._rotate_tier(
            daily_candidates if not dry_run else all_backups,
            self.daily_dir,
            max_count=7,
            granularity="day",
            now=now,
            dry_run=dry_run,
        )

        # ── Weekly: keep the first of each week, last 4 weeks ─────────
        weekly_candidates = sorted(self.daily_dir.glob("db_*.sql.gz*")) if not dry_run else all_backups
        weekly_kept = self._rotate_tier(
            weekly_candidates if not dry_run else all_backups,
            self.weekly_dir,
            max_count=4,
            granularity="week",
            now=now,
            dry_run=dry_run,
        )

        return {
            "rotated": len(all_backups),
            "deleted": 0,  # computed inside _rotate_tier
            "kept": {
                "hourly": hourly_kept,
                "daily": daily_kept,
                "weekly": weekly_kept,
            },
        }

    # ═════════════════════════════════════════════════════════════════════
    # Backup Methods
    # ═════════════════════════════════════════════════════════════════════

    def _backup_database(self, output_path: Path) -> None:
        """pg_dump базы данных в сжатый файл."""
        cmd = [
            "pg_dump",
            "-h", settings.POSTGRES_HOST,
            "-p", str(settings.POSTGRES_PORT),
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "--no-password",
            "--no-owner",
            "--no-acl",
        ]
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)

        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr[:500]}")

        # Write compressed
        with gzip.open(str(output_path), "wt", encoding="utf-8") as f:
            f.write(result.stdout)

    def _backup_graphs(self, output_path: Path) -> None:
        """Архивировать папку с графами."""
        graphs_dir = settings.graphs_path
        if not graphs_dir.exists() or not list(graphs_dir.iterdir()):
            # Create empty tar even if no graphs — consistency
            with tarfile.open(output_path, "w:gz") as tar:
                pass
            return
        self._tar_directory(graphs_dir, output_path)

    def _backup_artifacts(self, output_path: Path) -> None:
        """Архивировать папку с артефактами."""
        artifacts_dir = settings.artifacts_path
        if not artifacts_dir.exists() or not list(artifacts_dir.iterdir()):
            with tarfile.open(output_path, "w:gz") as tar:
                pass
            return
        self._tar_directory(artifacts_dir, output_path)

    # ═════════════════════════════════════════════════════════════════════
    # Helpers
    # ═════════════════════════════════════════════════════════════════════

    @staticmethod
    def _tar_directory(source_dir: Path, output_path: Path) -> None:
        """Создать tar.gz из директории."""
        source_dir = Path(source_dir)
        with tarfile.open(output_path, "w:gz") as tar:
            for item in sorted(source_dir.rglob("*")):
                if item.is_file():
                    arcname = str(item.relative_to(source_dir.parent))
                    tar.add(str(item), arcname=arcname)

    def _rotate_tier(
        self,
        candidates: List[Path],
        target_dir: Path,
        max_count: int,
        granularity: str,
        now: datetime,
        dry_run: bool = False,
    ) -> int:
        """
        Применить ротацию к уровню (hourly/daily/weekly).

        Для hourly: оставляем последние max_count файлов (по времени).
        Для daily: группируем по дням, в каждом дне оставляем первый.
        Для weekly: группируем по ISO-неделям, в каждой оставляем первый.
        """
        if granularity == "hour":
            # Keep the last max_count by mtime, delete older
            kept = candidates[:max_count]
            deleted = candidates[max_count:]
            if not dry_run:
                for p in kept:
                    if p.parent != target_dir:
                        shutil.copy2(p, target_dir / p.name)
                for p in deleted:
                    if p.exists():
                        p.unlink()
            return len(kept)

        # Daily / Weekly: group by time bucket, keep first in each
        groups: Dict[str, List[Path]] = {}
        for p in sorted(candidates, key=lambda x: x.stat().st_mtime):
            ts = datetime.fromtimestamp(p.stat().st_mtime)
            if granularity == "day":
                key = ts.strftime("%Y%m%d")
            else:  # week
                key = ts.strftime("%Y-W%W")

            if key not in groups:
                groups[key] = []
            groups[key].append(p)

        # Keep first (oldest) from each group, up to max_count
        sorted_keys = sorted(groups.keys(), reverse=True)[:max_count]
        kept = 0
        for key in sorted_keys:
            first = groups[key][0]
            if not dry_run:
                dest = target_dir / first.name
                if not dest.exists():
                    shutil.copy2(first, dest)
            kept += 1

        # Delete files in target_dir beyond max_count
        if not dry_run:
            existing = sorted(target_dir.glob("db_*.sql.gz*"))
            for p in existing[max_count:]:
                p.unlink()

        return kept


# Singleton
backup_service = BackupService()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        do_rotate = "--rotate" in sys.argv
        result = await backup_service.backup_all()
        print(f"Backup: {result['status']}")
        for f in result["files"]:
            print(f"  {f}")
        for e in result["errors"]:
            print(f"  ERROR: {e}")

        if do_rotate:
            rot = await backup_service.rotate()
            print(f"Rotation: hourly={rot['kept']['hourly']}, "
                  f"daily={rot['kept']['daily']}, weekly={rot['kept']['weekly']}")

    asyncio.run(main())
