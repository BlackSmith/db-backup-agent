"""Common remote storage provider contract and execution models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from backup_agent.providers.databases.base import CommandResult, SubprocessCommandExecutor


class CommandExecutor(Protocol):
    """Protocol for command execution wrappers."""

    def run(
        self,
        command: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> CommandResult:
        ...


@dataclass(slots=True)
class RemoteStorageError:
    """Structured error data produced by remote storage operations."""

    message: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    local_path: Path | None = None
    remote_destination: str = ""


@dataclass(slots=True)
class RemoteSyncResult:
    """Structured result returned by remote synchronization operations."""

    status: str
    local_path: Path
    remote_destination: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    error: RemoteStorageError | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


@dataclass(slots=True)
class RemoteCleanupResult:
    """Structured result returned by remote retention cleanup."""

    status: str
    local_path: Path
    remote_destination: str
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    error: RemoteStorageError | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class RemoteStorageProvider(ABC):
    """Abstract contract for remote synchronization and cleanup."""

    @abstractmethod
    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        """Synchronize a local run directory to remote storage."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        """Apply remote retention cleanup based on the current local state."""
        raise NotImplementedError
