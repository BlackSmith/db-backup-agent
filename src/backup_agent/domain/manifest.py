"""Manifest DTOs for serializing backup run results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .artifact import BackupArtifact
from .backup_run import BackupRun, BackupRunError
from .backup_target import BackupTarget


@dataclass(slots=True)
class ManifestTarget:
    container_id: str
    container_name: str
    db_type: str
    host: str
    port: int
    user: str | None = None
    databases: list[str] = field(default_factory=list)
    all_databases: bool = False

    @classmethod
    def from_backup_target(cls, target: BackupTarget) -> "ManifestTarget":
        return cls(
            container_id=target.container_id,
            container_name=target.container_name,
            db_type=target.db_type,
            host=target.host,
            port=target.port,
            user=target.user,
            databases=list(target.databases),
            all_databases=target.all_databases,
        )


@dataclass(slots=True)
class ManifestArtifact:
    container_id: str
    container_name: str
    db_type: str
    database: str | None
    path: str
    size: int | None = None
    checksum: str | None = None
    format: str | None = None

    @classmethod
    def from_backup_artifact(cls, artifact: BackupArtifact, run_root: Path) -> "ManifestArtifact":
        return cls(
            container_id=artifact.target.container_id,
            container_name=artifact.target.container_name,
            db_type=artifact.target.db_type,
            database=artifact.database,
            path=_relative_path(artifact.path, run_root),
            size=artifact.size,
            checksum=artifact.checksum,
            format=artifact.format,
        )


@dataclass(slots=True)
class ManifestError:
    source: str
    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    container_id: str | None = None
    container_name: str | None = None
    database: str | None = None
    output_path: str | None = None

    @classmethod
    def from_backup_run_error(cls, error: BackupRunError, run_root: Path) -> "ManifestError":
        return cls(
            source=error.source,
            message=error.message,
            command=list(error.command),
            returncode=error.returncode,
            stderr=error.stderr,
            container_id=error.target_container_id,
            container_name=error.target_container_name,
            database=error.database,
            output_path=_relative_path(error.output_path, run_root) if error.output_path else None,
        )


@dataclass(slots=True)
class RunManifest:
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "pending"
    targets: list[ManifestTarget] = field(default_factory=list)
    artifacts: list[ManifestArtifact] = field(default_factory=list)
    errors: list[ManifestError] = field(default_factory=list)

    @classmethod
    def from_backup_run(cls, run: BackupRun, run_root: Path) -> "RunManifest":
        return cls(
            run_id=run.run_id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            targets=[ManifestTarget.from_backup_target(target) for target in run.targets],
            artifacts=[ManifestArtifact.from_backup_artifact(artifact, run_root) for artifact in run.artifacts],
            errors=[ManifestError.from_backup_run_error(error, run_root) for error in run.errors],
        )


def _relative_path(path: Path | None, run_root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(run_root))
    except ValueError:
        return str(path)
