"""Composite storage provider for multiple storage backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .base import RemoteCleanupResult, RemoteStorageError, RemoteStorageProvider, RemoteSyncResult


@dataclass(slots=True)
class CompositeStorageProvider(RemoteStorageProvider):
    """Execute sync/cleanup across multiple configured storage backends."""

    providers: list[RemoteStorageProvider] = field(default_factory=list)

    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        results = [provider.sync(local_path) for provider in self.providers]
        return self._compose_sync_result(local_path, results)

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        results = [provider.cleanup(local_path, retention_days) for provider in self.providers]
        return self._compose_cleanup_result(local_path, results)

    def _compose_sync_result(
        self, local_path: Path, results: list[RemoteSyncResult]
    ) -> RemoteSyncResult:
        if not results:
            return RemoteSyncResult(status="success", local_path=local_path, remote_destination="")

        if all(result.succeeded for result in results):
            return RemoteSyncResult(
                status="success",
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
            )

        if any(result.succeeded for result in results):
            return RemoteSyncResult(
                status="partial",
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
                error=RemoteStorageError(
                    message=self._join_messages(
                        result.error.message if result.error else result.status for result in results if not result.succeeded
                    ),
                    local_path=local_path,
                    remote_destination=self._join_destinations(result.remote_destination for result in results),
                ),
            )

        return RemoteSyncResult(
            status="failed",
            local_path=local_path,
            remote_destination=self._join_destinations(result.remote_destination for result in results),
            error=RemoteStorageError(
                message=self._join_messages(
                    result.error.message if result.error else result.status for result in results
                ),
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
            ),
        )

    def _compose_cleanup_result(
        self, local_path: Path, results: list[RemoteCleanupResult]
    ) -> RemoteCleanupResult:
        if not results:
            return RemoteCleanupResult(status="success", local_path=local_path, remote_destination="")

        if all(result.succeeded for result in results):
            return RemoteCleanupResult(
                status="success",
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
            )

        if any(result.succeeded for result in results):
            return RemoteCleanupResult(
                status="partial",
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
                error=RemoteStorageError(
                    message=self._join_messages(
                        result.error.message if result.error else result.status for result in results if not result.succeeded
                    ),
                    local_path=local_path,
                    remote_destination=self._join_destinations(result.remote_destination for result in results),
                ),
            )

        return RemoteCleanupResult(
            status="failed",
            local_path=local_path,
            remote_destination=self._join_destinations(result.remote_destination for result in results),
            error=RemoteStorageError(
                message=self._join_messages(
                    result.error.message if result.error else result.status for result in results
                ),
                local_path=local_path,
                remote_destination=self._join_destinations(result.remote_destination for result in results),
            ),
        )

    @staticmethod
    def _join_destinations(destinations) -> str:
        values = [destination for destination in destinations if destination]
        return " | ".join(values)

    @staticmethod
    def _join_messages(messages) -> str:
        values = [message for message in messages if message]
        return "; ".join(values) if values else "one or more storage backends failed"
