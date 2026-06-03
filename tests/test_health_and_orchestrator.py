"""Tests for health checks, logging helpers, and orchestrator summaries."""

from __future__ import annotations

import io
import logging
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backup_agent.app.config import AppConfig
from backup_agent.domain.backup_run import BackupRun
from backup_agent.domain.run_summary import RunSummary
from backup_agent.infrastructure.logging import configure_logging, log_event
from backup_agent.interfaces.health import check_liveness, check_readiness
from backup_agent.services.orchestrator import BackupOrchestratorService


class FakeDiscovery:
    def discover(self):
        return [
            {
                "id": "abc123",
                "name": "postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql",
                    "backup_agent.pguser": "app",
                    "backup_agent.pghost": "db",
                    "backup_agent.pgpassword": "secret",
                    "backup_agent.pgport": "5432",
                    "backup_agent.pgdatabase": "appdb",
                },
                "env": [],
            }
        ]


class FakeResolver:
    def resolve(self, container):
        from backup_agent.domain.backup_target import BackupTarget

        return BackupTarget(
            container_id=container["id"],
            container_name=container["name"],
            db_type="postgresql",
            host="db",
            port=5432,
            user="app",
            password="secret",
            password_ref="label:backup_agent.pgpassword",
            databases=["appdb"],
            all_databases=False,
            labels=container["labels"],
        )


@dataclass
class FakeProviderResult:
    status: str = "success"


class FakeProvider:
    db_type = "postgresql"

    def supports(self, target):
        return target.db_type == self.db_type

    def backup(self, target, output_dir):
        from backup_agent.domain.artifact import BackupArtifact
        from backup_agent.providers.databases.base import BackupProviderError, BackupProviderResult

        artifact_path = output_dir / "postgresql" / "postgres-app" / "appdb.dump"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("backup", encoding="utf-8")
        artifact = BackupArtifact(target=target, database="appdb", path=artifact_path, size=6, format="postgresql-custom")
        return BackupProviderResult(provider="postgresql", target=target, status="success", artifacts=[artifact], errors=[])


class FakeStorage:
    def __init__(self) -> None:
        self.synced = False
        self.cleaned = False

    def sync(self, local_path: Path, remote_path: str | None = None):
        from backup_agent.providers.storage.base import RemoteSyncResult

        self.synced = True
        return RemoteSyncResult(status="success", local_path=local_path, remote_destination="backup@nas::backups/runs/test")

    def cleanup(self, local_path: Path, retention_days: int):
        from backup_agent.providers.storage.base import RemoteCleanupResult

        self.cleaned = True
        return RemoteCleanupResult(status="success", local_path=local_path, remote_destination="backup@nas::backups")


class FakeRetention:
    def cleanup(self, completed_runs_dir: Path, retention_days: int):
        from backup_agent.services.retention import RetentionCleanupResult

        return RetentionCleanupResult(
            status="success",
            completed_runs_dir=completed_runs_dir,
            retention_days=retention_days,
            cutoff_at=datetime.now(timezone.utc),
            removed_run_dirs=[],
            retained_run_dirs=list(completed_runs_dir.iterdir()) if completed_runs_dir.exists() else [],
            errors=[],
        )


class HealthAndOrchestratorTests(unittest.TestCase):
    def test_liveness_is_healthy(self) -> None:
        result = check_liveness()
        self.assertTrue(result.healthy)
        self.assertEqual(result.name, "liveness")

    def test_readiness_checks_config_directory_and_docker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig(
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                local_backup_dir=Path(temp_dir),
            )

            class FakeDocker:
                def ping(self):
                    return True

            report = check_readiness(config, FakeDocker())
            self.assertTrue(report.healthy)
            self.assertEqual(len(report.checks), 4)

    def test_log_event_masks_secrets(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("backup-agent-test")
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        configure_logging("INFO")
        log_event(logger, "config_validated", rsync_remote_password="secret", rsync_remote_host="nas.local")
        handler.flush()
        output = stream.getvalue()
        self.assertIn("event=config_validated", output)
        self.assertIn("rsync_remote_password=***", output)
        self.assertNotIn("secret", output)

    def test_orchestrator_returns_summary_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig(
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                local_backup_dir=Path(temp_dir),
            )
            orchestrator = BackupOrchestratorService(
                config=config,
                discovery=FakeDiscovery(),
                resolver=FakeResolver(),
                database_providers=[FakeProvider()],
                remote_storage=FakeStorage(),
                retention=FakeRetention(),
            )
            run = orchestrator.run_once()

            self.assertEqual(run.status, "success")
            summary = RunSummary.from_backup_run(run)
            self.assertEqual(summary.artifact_count, 1)
            self.assertEqual(summary.error_count, 0)
            manifest = Path(temp_dir) / "runs" / run.run_id / "manifest.json"
            self.assertTrue(manifest.exists())


if __name__ == "__main__":
    unittest.main()
