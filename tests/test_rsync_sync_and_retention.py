"""Tests for rsync synchronization and retention cleanup."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backup_agent.providers.databases.base import CommandResult
from backup_agent.providers.storage import RsyncStorageProvider
from backup_agent.services.retention import FileSystemRetentionManager, build_retention_plan


class FakeExecutor:
    def __init__(self, results: list[CommandResult] | None = None) -> None:
        self.results = results or []
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def run(self, command, *, env=None, cwd=None):
        index = len(self.commands)
        self.commands.append(list(command))
        self.envs.append(dict(env) if env is not None else None)
        if index < len(self.results):
            return self.results[index]
        return CommandResult(command=list(command), returncode=0, stdout="", stderr="")


class RsyncSyncAndRetentionTests(unittest.TestCase):
    def test_sync_builds_secret_safe_rsync_command(self) -> None:
        executor = FakeExecutor()
        provider = RsyncStorageProvider(
            remote_host="nas.local",
            remote_user="backup",
            remote_password="secret",
            remote_path="backups",
            executor=executor,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            local_run = Path(temp_dir) / "runs" / "20260603T090000Z-abcdef12"
            local_run.mkdir(parents=True)
            result = provider.sync(local_run)

        self.assertEqual(result.status, "success")
        self.assertEqual(executor.commands[0][0], "rsync")
        self.assertIn("--mkpath", executor.commands[0])
        self.assertNotIn("secret", " ".join(executor.commands[0]))
        self.assertEqual(result.remote_destination, "rsync://backup@nas.local/backups/runs/20260603T090000Z-abcdef12")
        self.assertEqual(executor.envs[0]["RSYNC_PASSWORD"], "secret")

    def test_sync_failure_is_reported_and_local_path_is_preserved(self) -> None:
        executor = FakeExecutor([CommandResult(command=["rsync"], returncode=1, stdout="", stderr="boom")])
        provider = RsyncStorageProvider(
            remote_host="nas.local",
            remote_user="backup",
            remote_password="secret",
            remote_path="backups",
            executor=executor,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            local_run = Path(temp_dir) / "runs" / "20260603T090000Z-abcdef12"
            local_run.mkdir(parents=True)
            result = provider.sync(local_run)

            self.assertEqual(result.status, "failed")
            self.assertTrue(local_run.exists())
            self.assertIsNotNone(result.error)
            self.assertIn("boom", result.stderr)

    def test_retention_plan_marks_expired_and_retained_runs(self) -> None:
        fixed_now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            old_run = runs_dir / "20260601T090000Z-aaa11111"
            new_run = runs_dir / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T09:00:00+00:00"}), encoding="utf-8"
            )
            (new_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-09T09:00:00+00:00"}), encoding="utf-8"
            )

            plan = build_retention_plan(runs_dir, retention_days=5, now=lambda: fixed_now)

            self.assertIn(old_run, plan.expired_run_dirs)
            self.assertIn(new_run, plan.retained_run_dirs)

    def test_local_retention_manager_deletes_expired_runs_and_updates_latest(self) -> None:
        fixed_now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        manager = FileSystemRetentionManager(now=lambda: fixed_now)

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_root = Path(temp_dir)
            runs_dir = backup_root / "runs"
            old_run = runs_dir / "20260601T090000Z-aaa11111"
            new_run = runs_dir / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T09:00:00+00:00"}), encoding="utf-8"
            )
            (new_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-09T09:00:00+00:00"}), encoding="utf-8"
            )
            (backup_root / "latest").write_text("runs/old", encoding="utf-8")

            result = manager.cleanup(runs_dir, retention_days=5)

            self.assertEqual(result.status, "success")
            self.assertFalse(old_run.exists())
            self.assertTrue(new_run.exists())
            latest = backup_root / "latest"
            if latest.is_symlink():
                self.assertEqual(latest.readlink(), Path("runs") / new_run.name)
            else:
                self.assertEqual(latest.read_text(encoding="utf-8"), f"runs/{new_run.name}")

    def test_remote_cleanup_builds_delete_command_and_keeps_local_runs(self) -> None:
        fixed_now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        executor = FakeExecutor()
        provider = RsyncStorageProvider(
            remote_host="nas.local",
            remote_user="backup",
            remote_password="secret",
            remote_path="backups",
            executor=executor,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            backup_root = Path(temp_dir)
            runs_dir = backup_root / "runs"
            old_run = runs_dir / "20260601T090000Z-aaa11111"
            new_run = runs_dir / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T09:00:00+00:00"}), encoding="utf-8"
            )
            (new_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-09T09:00:00+00:00"}), encoding="utf-8"
            )

            result = provider.cleanup(runs_dir, retention_days=5)

            self.assertEqual(result.status, "success")
            self.assertTrue(old_run.exists())
            self.assertTrue(new_run.exists())
            self.assertEqual(executor.commands[0][0], "rsync")
            self.assertIn("--delete-delay", executor.commands[0])
            self.assertEqual(result.remote_destination, "rsync://backup@nas.local/backups")


if __name__ == "__main__":
    unittest.main()
