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
from backup_agent.providers.storage import LocalDirectoryStorageProvider
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


class FakeFilesystemDiscovery:
    def discover(self):
        return [
            {
                "id": "fs123",
                "name": "files-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "filesystem",
                    "backup_agent.directories": "/app/data,/var/lib/app/uploads",
                },
                "env": [],
            }
        ]


class FakeFilesystemResolver:
    def resolve(self, container):
        from backup_agent.domain.backup_target import BackupTarget

        return BackupTarget(
            container_id=container["id"],
            container_name=container["name"],
            db_type="filesystem",
            host=container["name"],
            port=0,
            directories=["/app/data", "/var/lib/app/uploads"],
            labels=container["labels"],
        )


class FakeFilesystemProvider:
    db_type = "filesystem"

    def supports(self, target):
        return target.db_type == self.db_type

    def backup(self, target, output_dir):
        from backup_agent.domain.artifact import BackupArtifact
        from backup_agent.providers.databases.base import BackupProviderResult

        artifact_path = output_dir / "filesystem" / "files-app" / "directories.tar.gz"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"archive")
        artifact = BackupArtifact(target=target, database=None, path=artifact_path, size=7, format="filesystem-tar-gzip")
        return BackupProviderResult(provider="filesystem", target=target, status="success", artifacts=[artifact], errors=[])


class FakeStorage:
    def __init__(self, *, sync_status: str = "success", cleanup_status: str = "success") -> None:
        self.synced = False
        self.cleaned = False
        self.sync_status = sync_status
        self.cleanup_status = cleanup_status

    def sync(self, local_path: Path, remote_path: str | None = None):
        from backup_agent.providers.storage.base import RemoteStorageError, RemoteSyncResult

        self.synced = True
        error = None
        if self.sync_status != "success":
            error = RemoteStorageError(message="storage sync failed", local_path=local_path, remote_destination="backup@nas::backups/runs/test")
        return RemoteSyncResult(status=self.sync_status, local_path=local_path, remote_destination="backup@nas::backups/runs/test", error=error)

    def cleanup(self, local_path: Path, retention_days: int):
        from backup_agent.providers.storage.base import RemoteCleanupResult

        self.cleaned = True
        return RemoteCleanupResult(status=self.cleanup_status, local_path=local_path, remote_destination="backup@nas::backups")


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
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = AppConfig(
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                backup_local_storage=Path(mounted_dir),
                local_backup_dir=Path(temp_dir),
            )
            orchestrator = BackupOrchestratorService(
                config=config,
                discovery=FakeDiscovery(),
                resolver=FakeResolver(),
                database_providers=[FakeProvider()],
                remote_storage=LocalDirectoryStorageProvider(storage_root=Path(mounted_dir)),
                retention=FakeRetention(),
            )
            run = orchestrator.run_once()

            self.assertEqual(run.status, "success")
            summary = RunSummary.from_backup_run(run)
            self.assertEqual(summary.artifact_count, 1)
            self.assertEqual(summary.error_count, 0)
            self.assertFalse((Path(temp_dir) / "runs" / run.run_id).exists())
            self.assertFalse((Path(temp_dir) / "latest").exists())
            self.assertTrue((Path(mounted_dir) / "runs" / run.run_id / "manifest.json").exists())
            self.assertTrue((Path(mounted_dir) / "runs" / run.run_id / "postgresql" / "postgres-app" / "appdb.dump").exists())

    def test_orchestrator_supports_filesystem_archive_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = AppConfig(
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                backup_local_storage=Path(mounted_dir),
                local_backup_dir=Path(temp_dir),
            )
            orchestrator = BackupOrchestratorService(
                config=config,
                discovery=FakeFilesystemDiscovery(),
                resolver=FakeFilesystemResolver(),
                database_providers=[FakeFilesystemProvider()],
                remote_storage=LocalDirectoryStorageProvider(storage_root=Path(mounted_dir)),
                retention=FakeRetention(),
            )
            run = orchestrator.run_once()

            self.assertEqual(run.status, "success")
            self.assertTrue((Path(mounted_dir) / "runs" / run.run_id / "filesystem" / "files-app" / "directories.tar.gz").exists())
            self.assertEqual(run.targets[0].directories, ["/app/data", "/var/lib/app/uploads"])

    def test_orchestrator_cleans_up_staging_when_only_local_storage_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = AppConfig(
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                backup_local_storage=Path(mounted_dir),
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
            self.assertFalse((Path(temp_dir) / "runs" / run.run_id).exists())
            self.assertFalse((Path(temp_dir) / "latest").exists())

    def test_orchestrator_cleans_up_staging_when_only_rsync_is_configured(self) -> None:
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
            self.assertFalse((Path(temp_dir) / "runs" / run.run_id).exists())
            self.assertFalse((Path(temp_dir) / "latest").exists())

    def test_orchestrator_cleans_up_staging_when_both_storage_backends_are_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = AppConfig(
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
                backup_time=datetime.strptime("02:00", "%H:%M").time(),
                backup_retention_days=7,
                backup_local_storage=Path(mounted_dir),
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
            self.assertFalse((Path(temp_dir) / "runs" / run.run_id).exists())
            self.assertFalse((Path(temp_dir) / "latest").exists())

    def test_orchestrator_preserves_staging_when_publish_fails(self) -> None:
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
                remote_storage=FakeStorage(sync_status="failed"),
                retention=FakeRetention(),
            )
            run = orchestrator.run_once()

            self.assertNotEqual(run.status, "success")
            self.assertTrue((Path(temp_dir) / "runs" / run.run_id).exists())

    def test_log_event_reports_run_errors_without_secrets(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        module_logger = logging.getLogger("backup_agent.app.main")
        original_handlers = list(module_logger.handlers)
        original_level = module_logger.level
        original_propagate = module_logger.propagate
        module_logger.handlers = [handler]
        module_logger.setLevel(logging.INFO)
        module_logger.propagate = False

        from backup_agent.app.main import _log_run_errors
        from backup_agent.domain.backup_run import BackupRunError

        class FakeResult:
            run_id = "run-123"
            errors = [
                BackupRunError(
                    source="provider",
                    message="pg_dump failed with exit code 1",
                    stderr="password=secret should not appear",
                    target_container_name="postgres-app",
                    database="appdb",
                )
            ]

        try:
            _log_run_errors(FakeResult())
            handler.flush()
            output = stream.getvalue()
            self.assertIn("event=run_error", output)
            self.assertIn("source=provider", output)
            self.assertIn("message=pg_dump failed with exit code 1", output)
            self.assertIn("target_container_name=postgres-app", output)
            self.assertIn("database=appdb", output)
            self.assertIn("output_path=None", output)
            self.assertNotIn("should not appear", output)
            self.assertNotIn("stderr=", output)
        finally:
            module_logger.handlers = original_handlers
            module_logger.setLevel(original_level)
            module_logger.propagate = original_propagate

    def test_log_event_reports_publish_errors_without_secrets(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        module_logger = logging.getLogger("backup_agent.app.main")
        original_handlers = list(module_logger.handlers)
        original_level = module_logger.level
        original_propagate = module_logger.propagate
        module_logger.handlers = [handler]
        module_logger.setLevel(logging.INFO)
        module_logger.propagate = False

        from backup_agent.app.main import _log_run_errors
        from backup_agent.domain.backup_run import BackupRunError

        class FakeResult:
            run_id = "run-456"
            errors = [
                BackupRunError(
                    source="sync",
                    message="local storage publish failed",
                    stderr="--password-file=/tmp/secret.txt",
                )
            ]

        try:
            _log_run_errors(FakeResult())
            handler.flush()
            output = stream.getvalue()
            self.assertIn("event=run_error", output)
            self.assertIn("source=sync", output)
            self.assertIn("message=local storage publish failed", output)
            self.assertIn("run_id=run-456", output)
            self.assertIn("run_id=run-456", output)
            self.assertIn("message=local storage publish failed", output)
            self.assertNotIn("secret.txt", output)
            self.assertNotIn("stderr=", output)
        finally:
            module_logger.handlers = original_handlers
            module_logger.setLevel(original_level)
            module_logger.propagate = original_propagate


if __name__ == "__main__":
    unittest.main()
