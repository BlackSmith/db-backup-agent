"""MariaDB backup provider placeholder."""

from __future__ import annotations

from pathlib import Path

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget

from .base import DatabaseBackupProvider


class MariaDBBackupProvider(DatabaseBackupProvider):
    db_type = "mariadb"

    def supports(self, target: BackupTarget) -> bool:
        return target.db_type.lower() == self.db_type

    def validate(self, target: BackupTarget) -> None:
        raise NotImplementedError("MariaDB backup validation is not implemented yet.")

    def backup(self, target: BackupTarget, output_dir: Path) -> list[BackupArtifact]:
        raise NotImplementedError("MariaDB backup execution is not implemented yet.")
