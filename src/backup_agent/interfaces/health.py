"""Health-check interface placeholders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HealthCheckResult:
    """Simple health-check result placeholder."""

    name: str
    healthy: bool
    message: str = ""
