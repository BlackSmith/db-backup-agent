"""Backup orchestration boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backup_agent.domain.backup_run import BackupRun


class BackupOrchestrator(ABC):
    """Abstract contract for the daily backup flow."""

    @abstractmethod
    def run_once(self) -> BackupRun:
        """Execute a single backup run."""
        raise NotImplementedError
