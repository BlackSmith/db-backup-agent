"""Container discovery boundary and Docker implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backup_agent.infrastructure.docker import DockerApiClient, DockerSocketError

ContainerRecord = Mapping[str, Any]


class DiscoveryError(RuntimeError):
    """Raised when container discovery cannot complete."""


class ContainerDiscovery(ABC):
    """Abstract discovery contract for Docker container enumeration."""

    @abstractmethod
    def discover(self) -> list[ContainerRecord]:
        """Return raw container records for later metadata resolution."""
        raise NotImplementedError


@dataclass(slots=True)
class DockerContainerDiscovery(ContainerDiscovery):
    """Discover only containers explicitly opted-in via backup labels."""

    docker_client: DockerApiClient
    enabled_label: str = "backup_agent.enabled"

    def discover(self) -> list[ContainerRecord]:
        try:
            summaries = self.docker_client.list_running_containers()
        except DockerSocketError as exc:
            raise DiscoveryError(str(exc)) from exc

        discovered: list[ContainerRecord] = []
        for summary in summaries:
            if not _is_enabled(_label_value(summary, self.enabled_label)):
                continue

            container_id = str(summary.get("Id", "")).strip()
            if not container_id:
                continue

            try:
                details = self.docker_client.inspect_container(container_id)
            except DockerSocketError as exc:
                raise DiscoveryError(
                    f"Failed to inspect enabled container {container_id!r}: {exc}"
                ) from exc

            discovered.append(_normalize_container(summary, details))
        return discovered


def _normalize_container(summary: Mapping[str, Any], details: Mapping[str, Any]) -> dict[str, Any]:
    config = details.get("Config") or {}
    labels = _normalize_string_mapping(config.get("Labels") or summary.get("Labels") or {})
    env = list(config.get("Env") or [])
    name = str(details.get("Name") or _first_name(summary) or summary.get("Id") or "").lstrip("/")
    return {
        "id": str(details.get("Id") or summary.get("Id") or ""),
        "name": name,
        "labels": labels,
        "env": env,
        "image": str(config.get("Image") or summary.get("Image") or ""),
        "raw": {
            "summary": dict(summary),
            "details": dict(details),
        },
    }


def _normalize_string_mapping(values: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        normalized[str(key)] = str(value)
    return normalized


def _label_value(container: Mapping[str, Any], label_name: str) -> str:
    labels = container.get("Labels") or container.get("labels") or {}
    if isinstance(labels, Mapping):
        return str(labels.get(label_name, "")).strip()
    return ""


def _is_enabled(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _first_name(container: Mapping[str, Any]) -> str:
    names = container.get("Names") or []
    if isinstance(names, list) and names:
        return str(names[0])
    return ""
