"""Rsync storage provider placeholder."""

from __future__ import annotations

from pathlib import Path

from .base import RemoteStorageProvider


class RsyncStorageProvider(RemoteStorageProvider):
    def sync(self, local_path: Path, remote_path: str) -> None:
        raise NotImplementedError("Rsync synchronization is not implemented yet.")

    def cleanup(self, retention_days: int) -> None:
        raise NotImplementedError("Rsync retention cleanup is not implemented yet.")
