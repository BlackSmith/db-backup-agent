"""Container discovery boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

ContainerRecord = Mapping[str, Any]


class ContainerDiscovery(ABC):
    """Abstract discovery contract for Docker container enumeration."""

    @abstractmethod
    def discover(self) -> list[ContainerRecord]:
        """Return raw container records for later metadata resolution."""
        raise NotImplementedError
