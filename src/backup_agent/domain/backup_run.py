"""Domain model for one scheduled backup run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .artifact import BackupArtifact
from .backup_target import BackupTarget


@dataclass(slots=True)
class BackupRun:
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "pending"
    targets: list[BackupTarget] = field(default_factory=list)
    artifacts: list[BackupArtifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
