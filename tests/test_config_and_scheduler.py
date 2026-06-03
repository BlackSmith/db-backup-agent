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
            self.assertTrue(Path(temp_dir).exists())

    def test_load_config_rejects_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "RSYNC_REMOTE_HOST": "",
                "RSYNC_REMOTE_USER": "",
                "RSYNC_REMOTE_PASSWORD": "",
                "BACKUP_TIME": "25:99",
                "BACKUP_RETENTION_DAYS": "0",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "Not/A_Timezone",
            }

            with self.assertRaises(ConfigError) as cm:
                AppConfig.from_env(env)

        message = str(cm.exception)
        self.assertIn("RSYNC_REMOTE_HOST is required", message)
        self.assertIn("RSYNC_REMOTE_USER is required", message)
        self.assertIn("RSYNC_REMOTE_PASSWORD is required", message)
        self.assertIn("BACKUP_TIME", message)
        self.assertIn("BACKUP_RETENTION_DAYS", message)
        self.assertIn("TZ", message)

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
