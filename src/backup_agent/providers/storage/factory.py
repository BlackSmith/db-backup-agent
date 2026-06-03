"""Storage provider factory helpers."""

from __future__ import annotations

from backup_agent.app.config import AppConfig

from .base import RemoteStorageProvider
from .local_directory import LocalDirectoryStorageProvider
from .rsync import RsyncStorageProvider


def build_storage_provider(config: AppConfig) -> RemoteStorageProvider:
    """Build the active storage provider for the current configuration."""

    if config.backup_local_storage is not None:
        return LocalDirectoryStorageProvider(storage_root=config.backup_local_storage)
    return RsyncStorageProvider(
        remote_host=config.rsync_remote_host,
        remote_user=config.rsync_remote_user,
        remote_password=config.rsync_remote_password,
        remote_path=config.rsync_remote_path,
    )
