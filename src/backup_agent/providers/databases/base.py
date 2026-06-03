"""Common database backup provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget


class DatabaseBackupProvider(ABC):
    """Abstract contract for backing up a database target."""

    db_type: str = ""

    @abstractmethod
    def supports(self, target: BackupTarget) -> bool:
        """Return whether the provider can handle the target."""
        raise NotImplementedError

    @abstractmethod
    def validate(self, target: BackupTarget) -> None:
        """Validate the target before backup execution."""
        raise NotImplementedError

    @abstractmethod
    def backup(self, target: BackupTarget, output_dir: Path) -> list[BackupArtifact]:
        """Create backup artifacts for the supplied target."""
        raise NotImplementedError
