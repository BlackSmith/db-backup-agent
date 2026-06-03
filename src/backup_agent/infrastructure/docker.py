"""Docker API helpers used by discovery and health checks."""

from __future__ import annotations

import http.client
import json
import socket
from dataclasses import dataclass
from typing import Any


class DockerSocketError(RuntimeError):
    """Raised when the Docker socket cannot be queried successfully."""


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    """HTTP connection over a Unix domain socket."""

    def __init__(self, socket_path: str) -> None:
        super().__init__(host="localhost")
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socket_path)
        self.sock = sock


@dataclass(slots=True)
class DockerApiClient:
    """Small Docker API client backed by the mounted Docker socket."""

    socket_path: str = "/var/run/docker.sock"

    def list_running_containers(self) -> list[dict[str, Any]]:
        return self._request_json("GET", "/containers/json?all=0")

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/containers/{container_id}/json")

    def ping(self) -> bool:
        try:
            self._request_json("GET", "/_ping")
        except DockerSocketError:
            return False
        return True

    def _request_json(self, method: str, path: str) -> Any:
        connection = _UnixSocketHTTPConnection(self.socket_path)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            payload = response.read().decode("utf-8", errors="replace")
            if response.status >= 400:
                raise DockerSocketError(
                    f"Docker API request failed: {method} {path} returned {response.status} {response.reason}: {payload}"
                )
            if not payload:
                return None
            if path == "/_ping":
                return payload
            return json.loads(payload)
        except OSError as exc:
            raise DockerSocketError(f"Docker socket {self.socket_path!r} is not reachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DockerSocketError(
                f"Docker API returned invalid JSON for {method} {path}: {exc}"
            ) from exc
        finally:
            connection.close()
