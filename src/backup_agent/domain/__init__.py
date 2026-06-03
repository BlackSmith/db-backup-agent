"""Core domain models for backup runs and artifacts."""

from .artifact import BackupArtifact
from .backup_run import BackupRun, BackupRunError
from .backup_target import BackupTarget
from .manifest import ManifestArtifact, ManifestError, ManifestTarget, RunManifest
from .run_summary import RunSummary
from .status import (
    RUN_TERMINAL_STATUSES,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_SYNC_FAILED,
)

__all__ = [
    "BackupArtifact",
    "BackupRun",
    "BackupRunError",
    "BackupTarget",
    "ManifestArtifact",
    "ManifestError",
    "ManifestTarget",
    "RunManifest",
    "RunSummary",
    "RUN_TERMINAL_STATUSES",
    "STATUS_FAILED",
    "STATUS_PARTIAL",
    "STATUS_PENDING",
    "STATUS_RUNNING",
    "STATUS_SUCCESS",
    "STATUS_SYNC_FAILED",
]
