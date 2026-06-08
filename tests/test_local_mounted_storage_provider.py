"""Tests for the local mounted storage provider."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backup_agent.domain.backup_target import BackupTarget
from backup_agent.providers.storage import LocalDirectoryStorageProvider


class LocalMountedStorageProviderTests(unittest.TestCase):
    def _target(self) -> BackupTarget:
        return BackupTarget(
            container_id="abc123",
            container_name="postgres-app",
            db_type="postgresql",
            host="db",
            port=5432,
            user="app",
            password="secret",
            password_ref="env:POSTGRES_PASSWORD",
            databases=["appdb"],
            all_databases=False,
            labels={"backup_agent.enabled": "true"},
        )

    def test_sync_copies_completed_run_into_mounted_directory(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as storage_dir:
            run_dir = Path(source_dir) / "runs" / "20260603T090000Z-abcdef12"
            artifact_dir = run_dir / "postgresql" / "postgres-app"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "appdb.dump").write_text("backup", encoding="utf-8")
            (run_dir / "manifest.json").write_text("{}", encoding="utf-8")

            provider = LocalDirectoryStorageProvider(storage_root=Path(storage_dir))
            result = provider.sync(run_dir)

            published_dir = Path(storage_dir) / "runs" / run_dir.name
            self.assertEqual(result.status, "success")
            self.assertTrue(published_dir.exists())
            self.assertTrue((published_dir / "manifest.json").exists())
            self.assertTrue((published_dir / "postgresql" / "postgres-app" / "appdb.dump").exists())
            latest = Path(storage_dir) / "latest"
            self.assertTrue(latest.exists())
            if latest.is_symlink():
                self.assertEqual(latest.readlink(), Path("runs") / run_dir.name)
            else:
                self.assertEqual(latest.read_text(encoding="utf-8"), f"runs/{run_dir.name}")

    def test_sync_failure_preserves_source_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as storage_dir:
            run_dir = Path(source_dir) / "runs" / "20260603T090000Z-abcdef12"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text("{}", encoding="utf-8")

            provider = LocalDirectoryStorageProvider(storage_root=Path(storage_dir))
            with patch("backup_agent.providers.storage.local_directory.shutil.copytree", side_effect=OSError("copy failed")):
                result = provider.sync(run_dir)

            self.assertEqual(result.status, "failed")
            self.assertTrue(run_dir.exists())
            self.assertFalse((Path(storage_dir) / "runs" / run_dir.name).exists())
            self.assertIsNotNone(result.error)
            self.assertIn("copy failed", result.error.message)

    def test_cleanup_removes_expired_runs_and_updates_latest(self) -> None:
        with tempfile.TemporaryDirectory() as storage_dir:
            root = Path(storage_dir)
            runs_root = root / "runs"
            old_run = runs_root / "20260601T090000Z-aaa11111"
            new_run = runs_root / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text('{"finished_at": "2026-06-01T09:05:00+00:00"}', encoding="utf-8")
            (new_run / "manifest.json").write_text('{"finished_at": "2026-06-09T09:05:00+00:00"}', encoding="utf-8")

            provider = LocalDirectoryStorageProvider(storage_root=root)
            result = provider.cleanup(runs_root, 5)

            self.assertEqual(result.status, "success")
            self.assertFalse(old_run.exists())
            self.assertTrue(new_run.exists())
            latest = root / "latest"
            if latest.is_symlink():
                self.assertEqual(latest.readlink(), Path("runs") / new_run.name)
            else:
                self.assertEqual(latest.read_text(encoding="utf-8"), f"runs/{new_run.name}")


if __name__ == "__main__":
    unittest.main()
