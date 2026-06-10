"""Tests for rsync synchronization and retention cleanup."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backup_agent.providers.databases.base import CommandResult
from backup_agent.providers.storage import RsyncStorageProvider
from backup_agent.services.retention import FileSystemRetentionManager, build_retention_plan


class SimulatedRsyncExecutor:
    def __init__(self, remote_root: Path, results: list[CommandResult] | None = None) -> None:
        self.remote_root = remote_root
        self.results = results or []
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def run(self, command, *, env=None, cwd=None):
        index = len(self.commands)
        self.commands.append(list(command))
        self.envs.append(dict(env) if env is not None else None)
        if index < len(self.results):
            result = self.results[index]
        else:
            result = CommandResult(command=list(command), returncode=0, stdout="", stderr="")
        if result.returncode == 0:
            self._simulate_success(command)
        return result

    def _simulate_success(self, command: list[str]) -> None:
        if "--include=*/" in command and "--include=manifest.json" in command:
            self._copy_remote_inventory(command)
            return
        if "--delete" in command:
            protected_run_ids = [
                part.split(" ", 1)[1] for part in command if part.startswith("--filter=P ")
            ]
            self._delete_remote_runs(protected_run_ids)
            return
        self._copy_uploaded_run(command)

    def _copy_remote_inventory(self, command: list[str]) -> None:
        destination = Path(command[-1])
        destination.mkdir(parents=True, exist_ok=True)
        for run_dir in sorted(path for path in self.remote_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
            manifest = run_dir / "manifest.json"
            if not manifest.exists():
                continue
            target_run_dir = destination / run_dir.name
            target_run_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, target_run_dir / "manifest.json")

    def _delete_remote_runs(self, protected_run_ids: list[str]) -> None:
        protected = {run_id.strip().rstrip("/").replace("/***", "") for run_id in protected_run_ids}
        for run_dir in list(self.remote_root.iterdir()):
            if not run_dir.is_dir() or run_dir.name in protected:
                continue
            shutil.rmtree(run_dir, ignore_errors=True)

    def _copy_uploaded_run(self, command: list[str]) -> None:
        if len(command) < 2:
            return
        source = Path(command[-2])
        destination = command[-1]
        if not destination.startswith("rsync://"):
            return
        run_id = destination.rstrip("/").rsplit("/", 1)[-1]
        target_run_dir = self.remote_root / run_id
        if target_run_dir.exists():
            shutil.rmtree(target_run_dir)
        shutil.copytree(source, target_run_dir)


class RsyncSyncAndRetentionTests(unittest.TestCase):
    def test_sync_builds_secret_safe_rsync_command(self) -> None:
        with tempfile.TemporaryDirectory() as remote_dir:
            executor = SimulatedRsyncExecutor(Path(remote_dir))
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
        self.assertNotIn("secret", " ".join(executor.commands[0]))
        self.assertEqual(result.remote_destination, "rsync://backup@nas.local/backups/20260603T090000Z-abcdef12")
        self.assertEqual(executor.envs[0]["RSYNC_PASSWORD"], "secret")

    def test_fetch_remote_manifests_downloads_only_manifest_files(self) -> None:
        with tempfile.TemporaryDirectory() as remote_dir:
            remote_root = Path(remote_dir)
            old_run = remote_root / "20260601T020000Z-aaa11111"
            old_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T02:00:00+00:00"}), encoding="utf-8"
            )
            (old_run / "app.dump").write_text("payload", encoding="utf-8")
            executor = SimulatedRsyncExecutor(remote_root)
            provider = RsyncStorageProvider(
                remote_host="nas.local",
                remote_user="backup",
                remote_password="secret",
                remote_path="backups",
                executor=executor,
            )

            result = provider.fetch_remote_manifests()

        self.assertEqual(result.status, "success")
        self.assertEqual([manifest.run_id for manifest in result.manifests], ["20260601T020000Z-aaa11111"])
        self.assertTrue(result.manifests[0].manifest_local_path is not None)
        self.assertEqual(result.manifests[0].manifest_local_path.name, "manifest.json")
        self.assertEqual(executor.commands[0][0], "rsync")
        self.assertIn("--include=*/", executor.commands[0])
        self.assertIn("--include=manifest.json", executor.commands[0])
        self.assertIn("--exclude=*", executor.commands[0])

    def test_plan_remote_retention_uses_remote_manifest_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as remote_dir:
            remote_root = Path(remote_dir)
            old_run = remote_root / "20260601T090000Z-aaa11111"
            new_run = remote_root / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T09:00:00+00:00"}), encoding="utf-8"
            )
            (new_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-09T09:00:00+00:00"}), encoding="utf-8"
            )
            executor = SimulatedRsyncExecutor(remote_root)
            provider = RsyncStorageProvider(
                remote_host="nas.local",
                remote_user="backup",
                remote_password="secret",
                remote_path="backups",
                executor=executor,
            )

            result = provider.plan_remote_retention(
                retention_days=5,
                now=lambda: datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            )

        self.assertTrue(result.succeeded)
        self.assertEqual([manifest.run_id for manifest in result.expired_manifests], ["20260601T090000Z-aaa11111"])
        self.assertEqual([manifest.run_id for manifest in result.retained_manifests], ["20260609T090000Z-bbb22222"])
        self.assertEqual([call[0] for call in executor.commands[:1]], ["rsync"])

    def test_delete_remote_runs_removes_only_expired_remote_run_directories(self) -> None:
        with tempfile.TemporaryDirectory() as remote_dir:
            remote_root = Path(remote_dir)
            old_run = remote_root / "20260601T090000Z-aaa11111"
            new_run = remote_root / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text("{}", encoding="utf-8")
            (new_run / "manifest.json").write_text("{}", encoding="utf-8")
            executor = SimulatedRsyncExecutor(remote_root)
            provider = RsyncStorageProvider(
                remote_host="nas.local",
                remote_user="backup",
                remote_password="secret",
                remote_path="backups",
                executor=executor,
            )

            result = provider.delete_remote_runs(
                ["20260601T090000Z-aaa11111"],
                protected_run_ids=["20260609T090000Z-bbb22222"],
            )

            self.assertEqual(result.status, "success")
            self.assertFalse(old_run.exists())
            self.assertTrue(new_run.exists())
            self.assertEqual(executor.commands[0][0], "rsync")
            self.assertIn("--delete", executor.commands[0])
            self.assertIn("--delete-excluded", executor.commands[0])
            self.assertIn("--exclude=*", executor.commands[0])
            self.assertIn("--force", executor.commands[0])
            self.assertIn("--filter=P 20260609T090000Z-bbb22222/", executor.commands[0])

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
        with tempfile.TemporaryDirectory() as remote_dir:
            remote_root = Path(remote_dir)
            old_run = remote_root / "20260601T090000Z-aaa11111"
            new_run = remote_root / "20260609T090000Z-bbb22222"
            old_run.mkdir(parents=True)
            new_run.mkdir(parents=True)
            (old_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-01T09:00:00+00:00"}), encoding="utf-8"
            )
            (new_run / "manifest.json").write_text(
                json.dumps({"started_at": "2026-06-09T09:00:00+00:00"}), encoding="utf-8"
            )
            executor = SimulatedRsyncExecutor(remote_root)
            provider = RsyncStorageProvider(
                remote_host="nas.local",
                remote_user="backup",
                remote_password="secret",
                remote_path="backups",
                executor=executor,
            )

            result = provider.cleanup(remote_root, retention_days=5)

            self.assertEqual(result.status, "success")
            self.assertFalse(old_run.exists())
            self.assertTrue(new_run.exists())
            self.assertEqual(executor.commands[0][0], "rsync")
            self.assertIn("--include=*/", executor.commands[0])
            self.assertIn("--delete", executor.commands[1])
            self.assertIn("--delete-excluded", executor.commands[1])
            self.assertIn("--exclude=*", executor.commands[1])
            self.assertIn("--filter=P 20260609T090000Z-bbb22222/", executor.commands[1])
            self.assertEqual(result.remote_destination, "rsync://backup@nas.local/backups")


if __name__ == "__main__":
    unittest.main()
