"""Health-check interface and deterministic checks."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from backup_agent.app.config import AppConfig
from backup_agent.infrastructure.docker import DockerApiClient
from backup_agent.infrastructure.filesystem import ensure_directory


@dataclass(slots=True)
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    healthy: bool
    message: str = ""
    details: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class HealthReport:
    """Aggregate health report."""

    checks: list[HealthCheckResult] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(check.healthy for check in self.checks)


class SupportsPing(Protocol):
    def ping(self) -> bool:
        ...


def check_liveness() -> HealthCheckResult:
    """Liveness is intentionally simple: the process is alive if it can answer this call."""

    return HealthCheckResult(
        name="liveness",
        healthy=True,
        message="process is running",
        details={"pid": str(os.getpid())},
    )


def check_readiness(config: AppConfig, docker_client: SupportsPing | None = None) -> HealthReport:
    """Check config, local storage, and Docker API reachability without side effects."""

    checks = [HealthCheckResult(name="configuration", healthy=True, message="validated")]

    storage_path = config.backup_local_storage or config.local_backup_dir
    directory_check = _check_local_directory(storage_path, "backup_storage")
    checks.append(directory_check)

    staging_check = _check_local_directory(config.local_backup_dir, "local_backup_dir")
    checks.append(staging_check)

    docker_check = _check_docker_client(config, docker_client)
    checks.append(docker_check)

    return HealthReport(checks=checks)


def _check_local_directory(path: Path, name: str) -> HealthCheckResult:
    try:
        directory = ensure_directory(path)
        with NamedTemporaryFile("w", delete=True, dir=directory, prefix=".health-") as temp_file:
            temp_file.write("ok")
            temp_file.flush()
        return HealthCheckResult(
            name=name,
            healthy=True,
            message="directory is writable",
            details={"path": str(directory)},
        )
    except OSError as exc:
        return HealthCheckResult(
            name=name,
            healthy=False,
            message=f"directory is not writable: {exc}",
            details={"path": str(path)},
        )


def _check_docker_client(config: AppConfig, docker_client: SupportsPing | None) -> HealthCheckResult:
    client: SupportsPing
    if docker_client is None:
        client = DockerApiClient(config.docker_socket_path)
    else:
        client = docker_client

    try:
        healthy = bool(client.ping())
    except Exception as exc:  # pragma: no cover - defensive
        return HealthCheckResult(
            name="docker_api",
            healthy=False,
            message=f"docker API unavailable: {exc}",
            details={"socket_path": config.docker_socket_path},
        )

    if healthy:
        return HealthCheckResult(
            name="docker_api",
            healthy=True,
            message="docker API reachable",
            details={"socket_path": config.docker_socket_path},
        )
    return HealthCheckResult(
        name="docker_api",
        healthy=False,
        message="docker API is not reachable",
        details={"socket_path": config.docker_socket_path},
    )
