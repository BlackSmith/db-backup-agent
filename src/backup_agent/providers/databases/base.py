"""Common database backup provider contract and execution models."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget


@dataclass(slots=True)
class CommandResult:
    """Result of a command execution."""

    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandExecutor(Protocol):
    """Protocol for command execution wrappers."""

    def run(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> CommandResult:
        ...


@dataclass(slots=True)
class SubprocessCommandExecutor:
    """Concrete executor based on `subprocess.run`."""

    def run(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            list(command),
            env=dict(env) if env is not None else None,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(
            command=list(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(slots=True)
class BackupProviderError:
    """Structured error data produced by backup providers."""

    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    output_path: Path | None = None
    database: str | None = None


@dataclass(slots=True)
class BackupProviderResult:
    """Structured provider result returned to the orchestrator."""

    provider: str
    target: BackupTarget
    status: str
    artifacts: list[BackupArtifact] = field(default_factory=list)
    errors: list[BackupProviderError] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @property
    def has_failures(self) -> bool:
        return bool(self.errors)


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
    def backup(self, target: BackupTarget, output_dir: Path) -> BackupProviderResult:
        """Create backup artifacts for the supplied target."""
        raise NotImplementedError
