"""Common remote storage provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class RemoteStorageProvider(ABC):
    """Abstract contract for remote synchronization and cleanup."""

    @abstractmethod
    def sync(self, local_path: Path, remote_path: str) -> None:
        """Synchronize a local run directory to remote storage."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self, retention_days: int) -> None:
        """Apply remote retention cleanup."""
        raise NotImplementedError
