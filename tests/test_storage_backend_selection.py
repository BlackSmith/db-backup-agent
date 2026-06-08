"""Tests for storage backend selection and composite publishing."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backup_agent.app.config import AppConfig
from backup_agent.providers.storage import (
    CompositeStorageProvider,
    FtpStorageProvider,
    LocalDirectoryStorageProvider,
    RsyncStorageProvider,
    build_storage_provider,
)
from backup_agent.providers.storage.base import RemoteCleanupResult, RemoteSyncResult


class RecordingStorageProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sync_calls: list[tuple[Path, str | None]] = []
        self.cleanup_calls: list[tuple[Path, int]] = []

    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        self.sync_calls.append((local_path, remote_path))
        return RemoteSyncResult(status="success", local_path=local_path, remote_destination=self.name)

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        self.cleanup_calls.append((local_path, retention_days))
        return RemoteCleanupResult(status="success", local_path=local_path, remote_destination=self.name)


class StorageBackendSelectionTests(unittest.TestCase):
    def _base_config(self, temp_dir: str, **kwargs) -> AppConfig:
        return AppConfig(
            backup_time=datetime.strptime("02:00", "%H:%M").time(),
            backup_retention_days=7,
            local_backup_dir=Path(temp_dir),
            **kwargs,
        )

    def test_build_storage_provider_returns_local_backend_when_only_mounted_storage_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = self._base_config(temp_dir, backup_local_storage=Path(mounted_dir))

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, LocalDirectoryStorageProvider)

    def test_build_storage_provider_returns_rsync_backend_when_only_rsync_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._base_config(
                temp_dir,
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
            )

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, RsyncStorageProvider)

    def test_build_storage_provider_returns_ftp_backend_when_only_ftp_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._base_config(
                temp_dir,
                ftp_host="ftp.example",
                ftp_user="backup",
                ftp_password="secret",
            )

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, FtpStorageProvider)

    def test_build_storage_provider_returns_composite_backend_when_both_are_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = self._base_config(
                temp_dir,
                backup_local_storage=Path(mounted_dir),
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
            )

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, CompositeStorageProvider)

    def test_build_storage_provider_returns_composite_backend_with_ftp_and_local(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as mounted_dir:
            config = self._base_config(
                temp_dir,
                backup_local_storage=Path(mounted_dir),
                ftp_host="ftp.example",
                ftp_user="backup",
                ftp_password="secret",
            )

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, CompositeStorageProvider)

    def test_build_storage_provider_returns_composite_backend_with_rsync_and_ftp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._base_config(
                temp_dir,
                rsync_remote_host="nas.local",
                rsync_remote_user="backup",
                rsync_remote_password="secret",
                ftp_host="ftp.example",
                ftp_user="backup",
                ftp_password="secret",
            )

            provider = build_storage_provider(config)

            self.assertIsInstance(provider, CompositeStorageProvider)

    def test_composite_storage_provider_runs_all_backends_in_order(self) -> None:
        first = RecordingStorageProvider("local")
        second = RecordingStorageProvider("rsync")
        third = RecordingStorageProvider("ftp")
        provider = CompositeStorageProvider(providers=[first, second, third])

        local_path = Path("/tmp/run")
        sync_result = provider.sync(local_path, "runs/custom")
        cleanup_result = provider.cleanup(Path("/tmp/runs"), 7)

        self.assertEqual(sync_result.status, "success")
        self.assertEqual(sync_result.remote_destination, "local | rsync | ftp")
        self.assertEqual(cleanup_result.status, "success")
        self.assertEqual(cleanup_result.remote_destination, "local | rsync | ftp")
        self.assertEqual(first.sync_calls[0][1], "runs/custom")
        self.assertEqual(second.sync_calls[0][1], "runs/custom")
        self.assertEqual(third.sync_calls[0][1], "runs/custom")
        self.assertEqual(first.cleanup_calls[0][1], 7)
        self.assertEqual(second.cleanup_calls[0][1], 7)
        self.assertEqual(third.cleanup_calls[0][1], 7)


if __name__ == "__main__":
    unittest.main()
