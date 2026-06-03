"""Metadata resolution boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from backup_agent.domain.backup_target import BackupTarget


class MetadataResolver(ABC):
    """Abstract contract for resolving container metadata into backup targets."""

    @abstractmethod
    def resolve(self, container: Mapping[str, Any]) -> BackupTarget | None:
        """Convert a raw container record into a normalized backup target."""
        raise NotImplementedError
