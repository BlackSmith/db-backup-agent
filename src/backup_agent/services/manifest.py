"""Manifest writing boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backup_agent.domain.backup_run import BackupRun


class ManifestWriter(ABC):
    """Abstract contract for writing run manifests."""

    @abstractmethod
    def write_run_manifest(self, run: BackupRun, output_dir: Path) -> Path:
        """Persist the manifest for a completed run."""
        raise NotImplementedError
