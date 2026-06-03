"""Docker integration placeholder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DockerSocketConfig:
    """Configuration for Docker socket access."""

    socket_path: str = "/var/run/docker.sock"
