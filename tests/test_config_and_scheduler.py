"""Configuration and scheduler tests."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from datetime import datetime, time
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backup_agent.app.config import AppConfig, ConfigError
from backup_agent.app.main import run_once
from backup_agent.services.scheduler import DailyScheduler


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self) -> str:
        self.calls += 1
        return "ok"


class ConfigAndSchedulerTests(unittest.TestCase):
    def test_load_config_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "RSYNC_REMOTE_HOST": "nas.local",
                "RSYNC_REMOTE_USER": "backup",
                "RSYNC_REMOTE_PASSWORD": "secret",
                "BACKUP_TIME": "02:30",
                "BACKUP_RETENTION_DAYS": "14",
                "RSYNC_REMOTE_PATH": "/backups",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "Europe/Prague",
                "LOG_LEVEL": "debug",
                "DOCKER_SOCKET_PATH": "/var/run/docker.sock",
            }

            config = AppConfig.from_env(env)

            self.assertEqual(config.rsync_remote_host, "nas.local")
            self.assertEqual(config.rsync_remote_user, "backup")
            self.assertEqual(config.rsync_remote_password, "secret")
            self.assertEqual(config.backup_time, time(2, 30))
            self.assertEqual(config.backup_retention_days, 14)
            self.assertEqual(config.rsync_remote_path, "/backups")
            self.assertEqual(config.local_backup_dir, Path(temp_dir))
            self.assertEqual(config.timezone.key, "Europe/Prague")
            self.assertEqual(config.log_level, "debug")
            self.assertFalse(config.uses_local_storage)
            self.assertEqual(config.storage_backend, "rsync")
            self.assertEqual(config.enabled_storage_backends, ("rsync",))
            self.assertTrue(Path(temp_dir).exists())

    def test_load_config_allows_local_storage_without_rsync_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            env = {
                "BACKUP_LOCAL_STORAGE": mounted_dir,
                "BACKUP_TIME": "02:30",
                "BACKUP_RETENTION_DAYS": "14",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "UTC",
            }

            config = AppConfig.from_env(env)

            self.assertEqual(config.backup_local_storage, Path(mounted_dir))
            self.assertTrue(config.uses_local_storage)
            self.assertFalse(config.has_rsync_storage)
            self.assertEqual(config.storage_backend, "local")
            self.assertEqual(config.enabled_storage_backends, ("local",))
            self.assertEqual(config.rsync_remote_host, "")
            self.assertEqual(config.rsync_remote_user, "")
            self.assertEqual(config.rsync_remote_password, "")

    def test_load_config_allows_both_storage_backends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            env = {
                "BACKUP_LOCAL_STORAGE": mounted_dir,
                "RSYNC_REMOTE_HOST": "nas.local",
                "RSYNC_REMOTE_USER": "backup",
                "RSYNC_REMOTE_PASSWORD": "secret",
                "BACKUP_TIME": "02:30",
                "BACKUP_RETENTION_DAYS": "14",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "UTC",
            }

            config = AppConfig.from_env(env)

            self.assertTrue(config.uses_local_storage)
            self.assertTrue(config.has_rsync_storage)
            self.assertEqual(config.enabled_storage_backends, ("local", "rsync"))
            self.assertEqual(config.storage_backend, "local+rsync")

    def test_load_config_rejects_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "BACKUP_TIME": "25:99",
                "BACKUP_RETENTION_DAYS": "0",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "Not/A_Timezone",
            }

            with self.assertRaises(ConfigError) as cm:
                AppConfig.from_env(env)

        message = str(cm.exception)
        self.assertIn("At least one storage backend must be configured", message)
        self.assertIn("BACKUP_TIME", message)
        self.assertIn("BACKUP_RETENTION_DAYS", message)
        self.assertIn("TZ", message)

    def test_load_config_rejects_partial_rsync_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            env = {
                "BACKUP_LOCAL_STORAGE": mounted_dir,
                "RSYNC_REMOTE_HOST": "nas.local",
                "BACKUP_TIME": "02:30",
                "BACKUP_RETENTION_DAYS": "14",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "UTC",
            }

            with self.assertRaises(ConfigError) as cm:
                AppConfig.from_env(env)

        self.assertIn("RSYNC_* configuration is incomplete", str(cm.exception))

    def test_scheduler_computes_next_run(self) -> None:
        scheduler = DailyScheduler(
            backup_time=time(2, 0),
            timezone=ZoneInfo("UTC"),
        )

        reference = datetime(2026, 6, 3, 1, 0, tzinfo=ZoneInfo("UTC"))
        next_run = scheduler.next_run_after(reference)

        self.assertEqual(next_run, datetime(2026, 6, 3, 2, 0, tzinfo=ZoneInfo("UTC")))
        self.assertGreater(scheduler.seconds_until_next_run(reference), 0)

    def test_scheduler_moves_to_next_day_after_cutoff(self) -> None:
        scheduler = DailyScheduler(
            backup_time=time(2, 0),
            timezone=ZoneInfo("UTC"),
        )

        reference = datetime(2026, 6, 3, 3, 0, tzinfo=ZoneInfo("UTC"))
        next_run = scheduler.next_run_after(reference)

        self.assertEqual(next_run, datetime(2026, 6, 4, 2, 0, tzinfo=ZoneInfo("UTC")))

    def test_run_once_calls_orchestrator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "RSYNC_REMOTE_HOST": "nas.local",
                "RSYNC_REMOTE_USER": "backup",
                "RSYNC_REMOTE_PASSWORD": "secret",
                "BACKUP_TIME": "02:00",
                "BACKUP_RETENTION_DAYS": "7",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "UTC",
            }
            config = AppConfig.from_env(env)

        orchestrator = FakeOrchestrator()
        self.assertEqual(run_once(config, orchestrator), 0)
        self.assertEqual(orchestrator.calls, 1)


if __name__ == "__main__":
    unittest.main()
