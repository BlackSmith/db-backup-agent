"""Retention boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class RetentionManager(ABC):
    """Abstract contract for retention cleanup."""

    @abstractmethod
    def cleanup(self, completed_runs_dir: Path, retention_days: int) -> None:
        """Remove expired completed backup runs."""
        raise NotImplementedError
