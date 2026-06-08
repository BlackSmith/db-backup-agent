"""Docker API helpers used by discovery and health checks."""

from __future__ import annotations

import http.client
import json
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


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
class DockerExecResult:
    """Result of executing a command inside a Docker container."""

    command: list[str]
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    exec_id: str = ""


@dataclass(slots=True)
class DockerApiClient:
    """Small Docker API client backed by the mounted Docker socket."""

    socket_path: str = "/var/run/docker.sock"

    def list_running_containers(self) -> list[dict[str, Any]]:
        return self._request_json("GET", "/containers/json?all=0")

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/containers/{container_id}/json")

    def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        env: Mapping[str, str] | None = None,
        user: str | None = None,
        workdir: str | None = None,
        tty: bool = False,
        stdout_handler: Callable[[bytes], None] | None = None,
        stderr_handler: Callable[[bytes], None] | None = None,
    ) -> DockerExecResult:
        exec_payload: dict[str, Any] = {
            "Cmd": list(command),
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": tty,
            "Detach": False,
        }
        if env:
            exec_payload["Env"] = [f"{key}={value}" for key, value in env.items()]
        if user:
            exec_payload["User"] = user
        if workdir:
            exec_payload["WorkingDir"] = workdir

        exec_info = self._request_json("POST", f"/containers/{container_id}/exec", body=exec_payload)
        exec_id = str((exec_info or {}).get("Id") or "").strip()
        if not exec_id:
            raise DockerSocketError(f"Docker API did not return an exec id for container {container_id!r}")

        response, connection = self._request_response(
            "POST",
            f"/exec/{exec_id}/start",
            body={"Detach": False, "Tty": tty},
        )
        try:
            raw_output = response.read()
        finally:
            connection.close()

        stdout_bytes, stderr_bytes = self._decode_exec_stream(raw_output, tty=tty)
        if stdout_handler is not None and stdout_bytes:
            stdout_handler(stdout_bytes)
        if stderr_handler is not None and stderr_bytes:
            stderr_handler(stderr_bytes)

        inspect = self._request_json("GET", f"/exec/{exec_id}/json") or {}
        return DockerExecResult(
            command=list(command),
            returncode=int(inspect.get("ExitCode") or 0),
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            exec_id=exec_id,
        )

    def get_archive(self, container_id: str, path: str) -> bytes:
        encoded_path = quote(path, safe="/")
        response, connection = self._request_response(
            "GET",
            f"/containers/{container_id}/archive?path={encoded_path}",
        )
        try:
            return response.read()
        finally:
            connection.close()

    def ping(self) -> bool:
        try:
            self._request_json("GET", "/_ping")
        except DockerSocketError:
            return False
        return True

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        connection = _UnixSocketHTTPConnection(self.socket_path)
        try:
            request_body, request_headers = self._prepare_body(body, headers)
            connection.request(method, path, body=request_body, headers=request_headers)
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

    def _request_response(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[http.client.HTTPResponse, _UnixSocketHTTPConnection]:
        connection = _UnixSocketHTTPConnection(self.socket_path)
        try:
            request_body, request_headers = self._prepare_body(body, headers)
            connection.request(method, path, body=request_body, headers=request_headers)
            response = connection.getresponse()
            if response.status >= 400:
                payload = response.read().decode("utf-8", errors="replace")
                raise DockerSocketError(
                    f"Docker API request failed: {method} {path} returned {response.status} {response.reason}: {payload}"
                )
            return response, connection
        except OSError as exc:
            connection.close()
            raise DockerSocketError(f"Docker socket {self.socket_path!r} is not reachable: {exc}") from exc
        except Exception:
            connection.close()
            raise

    def _prepare_body(
        self,
        body: Any | None,
        headers: Mapping[str, str] | None,
    ) -> tuple[bytes | bytearray | None, dict[str, str]]:
        request_headers = dict(headers or {})
        request_body = body
        if body is not None and not isinstance(body, (bytes, bytearray)):
            request_body = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        return request_body, request_headers

    def _decode_exec_stream(self, payload: bytes, *, tty: bool) -> tuple[bytes, bytes]:
        if tty:
            return payload, b""

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        offset = 0
        while offset < len(payload):
            remaining = len(payload) - offset
            if remaining < 8:
                raise DockerSocketError("Docker exec stream ended unexpectedly while parsing output")
            stream_id = payload[offset]
            payload_size = int.from_bytes(payload[offset + 4 : offset + 8], byteorder="big")
            offset += 8
            if len(payload) - offset < payload_size:
                raise DockerSocketError("Docker exec stream ended unexpectedly while parsing output")
            chunk = payload[offset : offset + payload_size]
            offset += payload_size
            if stream_id == 1:
                stdout_chunks.append(chunk)
            elif stream_id == 2:
                stderr_chunks.append(chunk)
            else:
                raise DockerSocketError(f"Docker exec stream used unsupported stream id {stream_id}")
        return b"".join(stdout_chunks), b"".join(stderr_chunks)
