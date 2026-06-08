"""Storage provider factory helpers."""

from __future__ import annotations

from backup_agent.app.config import AppConfig

from .base import RemoteStorageProvider
from .composite import CompositeStorageProvider
from .ftp import FtpStorageProvider
from .local_directory import LocalDirectoryStorageProvider
from .rsync import RsyncStorageProvider


def build_storage_provider(config: AppConfig) -> RemoteStorageProvider:
    """Build the active storage provider for the current configuration."""

    providers: list[RemoteStorageProvider] = []
    if config.uses_local_storage:
        providers.append(LocalDirectoryStorageProvider(storage_root=config.backup_local_storage))
    if config.has_rsync_storage:
        providers.append(
            RsyncStorageProvider(
                remote_host=config.rsync_remote_host,
                remote_user=config.rsync_remote_user,
                remote_password=config.rsync_remote_password,
                remote_path=config.rsync_remote_path,
            )
        )
    if config.has_ftp_storage:
        providers.append(
            FtpStorageProvider(
                host=config.ftp_host,
                port=config.ftp_port,
                user=config.ftp_user,
                password=config.ftp_password,
                remote_path=config.ftp_remote_path,
                use_tls=config.ftp_tls,
                passive=config.ftp_passive,
                timeout=config.ftp_timeout,
            )
        )

    if not providers:
        raise ValueError("At least one storage backend must be configured")
    if len(providers) == 1:
        return providers[0]
    return CompositeStorageProvider(providers=providers)
