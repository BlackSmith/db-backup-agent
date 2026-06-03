"""Domain model for one scheduled backup run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .artifact import BackupArtifact
from .backup_target import BackupTarget


@dataclass(slots=True)
class BackupRunError:
    """Structured error captured during a backup run."""

    source: str
    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    target_container_id: str | None = None
    target_container_name: str | None = None
    database: str | None = None
    output_path: Path | None = None


@dataclass(slots=True)
class BackupRun:
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "pending"
    targets: list[BackupTarget] = field(default_factory=list)
    artifacts: list[BackupArtifact] = field(default_factory=list)
    errors: list[BackupRunError] = field(default_factory=list)
