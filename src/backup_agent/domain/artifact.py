"""Domain model for produced backup artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .backup_target import BackupTarget


@dataclass(slots=True)
class BackupArtifact:
    target: BackupTarget
    database: str | None
    path: Path
    size: int | None = None
    checksum: str | None = None
    format: str | None = None
