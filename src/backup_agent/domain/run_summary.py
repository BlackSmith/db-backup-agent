"""High-level summary of one backup run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .backup_run import BackupRun


@dataclass(slots=True)
class RunSummary:
    run_id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    target_count: int
    artifact_count: int
    error_count: int

    @classmethod
    def from_backup_run(cls, run: BackupRun) -> "RunSummary":
        return cls(
            run_id=run.run_id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            target_count=len(run.targets),
            artifact_count=len(run.artifacts),
            error_count=len(run.errors),
        )
