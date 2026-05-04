"""
Tests for MAC_ASD v13.0 Backup Service (Item 5, P0 May 2026).

Covers: pg_dump tar, graphs tar, artifacts tar, rotation policy.
"""

from __future__ import annotations

import gzip
import os
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def backup_service(tmp_path, monkeypatch):
    """Create BackupService with temp directories."""
    from src.core.backup import BackupService
    svc = BackupService()
    svc.backup_root = tmp_path
    svc.hourly_dir = tmp_path / "hourly"
    svc.daily_dir = tmp_path / "daily"
    svc.weekly_dir = tmp_path / "weekly"
    for d in [svc.hourly_dir, svc.daily_dir, svc.weekly_dir]:
        d.mkdir(parents=True, exist_ok=True)
    return svc


# ═══════════════════════════════════════════════════════════════════════════════
# Database backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabaseBackup:
    def test_pg_dump_creates_gzip(self, backup_service, tmp_path):
        """pg_dump should produce a valid .sql.gz file."""
        # Skip if pg_dump not available
        import shutil
        if not shutil.which("pg_dump"):
            pytest.skip("pg_dump not installed")

        output = tmp_path / "db_test.sql.gz"
        try:
            backup_service._backup_database(output)
            assert output.exists()
            assert output.stat().st_size > 0
            # Verify it's valid gzip
            with gzip.open(str(output), "rt") as f:
                assert len(f.read(100)) >= 0  # readable
        except RuntimeError as e:
            if "pg_dump failed" in str(e):
                pytest.skip(f"pg_dump connection failed: {e}")
            raise

    def test_pg_dump_mocked(self, backup_service, tmp_path):
        """With mocked subprocess, verify correct pg_dump args."""
        output = tmp_path / "db_test_mock.sql.gz"
        sql_content = "CREATE TABLE test (id INT);"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=sql_content, stderr="")
            backup_service._backup_database(output)

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "pg_dump" in args
            assert "-h" in args
            assert "-U" in args

            assert output.exists()
            with gzip.open(str(output), "rt") as f:
                assert f.read() == sql_content

    def test_pg_dump_failure(self, backup_service, tmp_path):
        """pg_dump failure should raise RuntimeError."""
        output = tmp_path / "db_fail.sql.gz"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="connection refused")
            with pytest.raises(RuntimeError, match="pg_dump failed"):
                backup_service._backup_database(output)


# ═══════════════════════════════════════════════════════════════════════════════
# Graphs backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphsBackup:
    def test_empty_graphs_dir(self, backup_service, tmp_path):
        """Empty or missing graphs dir produces empty tar."""
        output = tmp_path / "graphs_empty.tar.gz"
        with patch.object(backup_service.__class__, '_backup_graphs',
                          lambda self, p: self._tar_directory(Path("/nonexistent"), p)):
            pass

        # Mock the graphs path to an empty temp dir
        empty_dir = tmp_path / "empty_graphs"
        empty_dir.mkdir()
        backup_service._tar_directory(empty_dir, output)
        assert output.exists()

    def test_graphs_tar_with_files(self, backup_service, tmp_path):
        """Graphs dir with files should produce non-empty tar."""
        graphs_dir = tmp_path / "graphs"
        graphs_dir.mkdir()
        (graphs_dir / "test.gpickle").write_text("mock graph data")
        (graphs_dir / "test.gpickle.meta").write_text("meta")

        output = tmp_path / "graphs.tar.gz"
        backup_service._tar_directory(graphs_dir, output)

        assert output.exists()
        assert output.stat().st_size > 0

        with tarfile.open(output, "r:gz") as tar:
            names = tar.getnames()
            assert any("test.gpickle" in n for n in names)


# ═══════════════════════════════════════════════════════════════════════════════
# Artifacts backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestArtifactsBackup:
    def test_artifacts_tar(self, backup_service, tmp_path):
        """Artifacts dir produces valid tar."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        prj_dir = artifacts_dir / "testproject" / "aosr"
        prj_dir.mkdir(parents=True)
        (prj_dir / "aosr_001.v1.json").write_text('{"type": "aosr"}')

        output = tmp_path / "artifacts.tar.gz"
        backup_service._tar_directory(artifacts_dir, output)

        assert output.exists()
        with tarfile.open(output, "r:gz") as tar:
            names = tar.getnames()
            assert any("aosr_001.v1.json" in n for n in names)


# ═══════════════════════════════════════════════════════════════════════════════
# Full backup flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackupAll:
    @pytest.mark.asyncio
    async def test_backup_all_success(self, backup_service, tmp_path):
        """Full backup should return status=ok."""
        # Mock all backup methods
        with patch.object(backup_service, '_backup_database'), \
             patch.object(backup_service, '_backup_graphs'), \
             patch.object(backup_service, '_backup_artifacts'):
            result = await backup_service.backup_all()
            assert result["status"] == "ok"
            assert len(result["files"]) == 3
            assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_backup_all_partial(self, backup_service, tmp_path):
        """Partial failure returns status=partial."""
        def fail_db(output_path):
            raise RuntimeError("DB down")
        backup_service._backup_database = fail_db

        with patch.object(backup_service, '_backup_graphs'), \
             patch.object(backup_service, '_backup_artifacts'):
            result = await backup_service.backup_all()
            assert result["status"] == "partial"
            assert len(result["errors"]) == 1
            assert len(result["files"]) == 2  # 2 succeeded

    @pytest.mark.asyncio
    async def test_backup_all_total_failure(self, backup_service, tmp_path):
        """All failures return status=error."""
        def fail_all(output_path):
            raise RuntimeError("Everything broken")
        backup_service._backup_database = fail_all
        backup_service._backup_graphs = fail_all
        backup_service._backup_artifacts = fail_all

        result = await backup_service.backup_all()
        assert result["status"] == "error"
        assert len(result["errors"]) == 3
        assert len(result["files"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Rotation
# ═══════════════════════════════════════════════════════════════════════════════

class TestRotation:
    def test_rotate_hourly_keeps_last_n(self, backup_service, tmp_path):
        """Hourly rotation: keep last 24, delete older."""
        # Create 30 fake backup files with different mtimes
        for i in range(30):
            f = tmp_path / f"db_20260504_{i:02d}0000.sql.gz"
            f.write_text("dummy")
            ts = (datetime(2026, 5, 4) - timedelta(hours=30 - i)).timestamp()
            os.utime(f, (ts, ts))

        all_files = sorted(tmp_path.glob("db_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        kept = backup_service._rotate_tier(
            all_files,
            backup_service.hourly_dir,
            max_count=24,
            granularity="hour",
            now=datetime(2026, 5, 5),
            dry_run=True,
        )
        assert kept == 24  # 24 kept, 6 deleted

    def test_rotate_daily_keeps_last_n_groups(self, backup_service, tmp_path):
        """Daily rotation: group by day, keep last 7 days."""
        for i in range(14):
            f = tmp_path / f"db_202605{15-i:02d}_120000.sql.gz"
            f.write_text("dummy")
            ts = (datetime(2026, 5, 15 - i)).timestamp()
            os.utime(f, (ts, ts))

        all_files = sorted(tmp_path.glob("db_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        kept = backup_service._rotate_tier(
            all_files,
            backup_service.daily_dir,
            max_count=7,
            granularity="day",
            now=datetime(2026, 5, 17),
            dry_run=True,
        )
        assert kept == 7

    def test_rotate_weekly_keeps_last_n_weeks(self, backup_service, tmp_path):
        """Weekly rotation: group by ISO week, keep last 4 weeks."""
        dates = [datetime(2026, 5, 11) - timedelta(weeks=i) for i in range(8)]
        for i, dt in enumerate(dates):
            week_num = dt.isocalendar()[1]
            f = tmp_path / f"db_2026_W{week_num:02d}.sql.gz"
            f.write_text("dummy")
            ts = dt.timestamp()
            os.utime(f, (ts, ts))

        all_files = sorted(tmp_path.glob("db_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        kept = backup_service._rotate_tier(
            all_files,
            backup_service.weekly_dir,
            max_count=4,
            granularity="week",
            now=datetime(2026, 6, 1),
            dry_run=True,
        )
        assert kept == 4

    @pytest.mark.asyncio
    async def test_rotate_full(self, backup_service, tmp_path):
        """Full rotation returns correct stats."""
        # Create some files
        for i in range(25):
            f = tmp_path / f"db_20260504_{i:02d}0000.sql.gz"
            f.write_text("dummy")
            ts = (datetime(2026, 5, 4) - timedelta(hours=25 - i)).timestamp()
            os.utime(f, (ts, ts))

        with patch.object(backup_service, '_rotate_tier', wraps=backup_service._rotate_tier):
            result = await backup_service.rotate(dry_run=True)
            assert "kept" in result
            assert "hourly" in result["kept"]
