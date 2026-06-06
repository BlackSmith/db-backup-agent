"""Rsync storage provider."""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from backup_agent.providers.databases.base import CommandResult, SubprocessCommandExecutor

from .base import (
    CommandExecutor,
    RemoteCleanupResult,
    RemoteDeleteResult,
    RemoteManifestInventoryResult,
    RemoteManifestRecord,
    RemoteRetentionPlanResult,
    RemoteStorageError,
    RemoteStorageProvider,
    RemoteSyncResult,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RsyncStorageProvider(RemoteStorageProvider):
    remote_host: str
    remote_user: str
    remote_password: str
    remote_path: str
    executor: CommandExecutor | None = None

    def __post_init__(self) -> None:
        if self.executor is None:
            self.executor = SubprocessCommandExecutor()

    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        destination = self._build_run_destination(local_path, remote_path)
        command = self._build_sync_command(local_path, destination)
        logger.debug(
            "rsync sync start local_path=%s destination=%s command=%s",
            local_path,
            destination,
            " ".join(command),
        )
        result = self._run(command)
        logger.debug(
            "rsync sync finish local_path=%s destination=%s returncode=%s",
            local_path,
            destination,
            result.returncode,
        )
        return self._to_sync_result(local_path, destination, command, result)

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        plan = self.plan_remote_retention(retention_days)
        destination = self._build_remote_root_destination()
        if not plan.succeeded:
            error_message = "; ".join(plan.errors) if plan.errors else "rsync remote retention planning failed"
            error = RemoteStorageError(
                message=error_message,
                local_path=local_path,
                remote_destination=destination,
            )
            return RemoteCleanupResult(
                status="failed",
                local_path=local_path,
                remote_destination=destination,
                command=plan.inventory.command if plan.inventory is not None else [],
                returncode=plan.inventory.returncode if plan.inventory is not None else None,
                stderr=plan.inventory.stderr if plan.inventory is not None else "",
                error=error,
            )

        expired_run_ids = [manifest.run_id for manifest in plan.expired_manifests]
        if not expired_run_ids:
            return RemoteCleanupResult(
                status="success",
                local_path=local_path,
                remote_destination=destination,
                command=plan.inventory.command if plan.inventory is not None else [],
                returncode=plan.inventory.returncode if plan.inventory is not None else None,
                stderr=plan.inventory.stderr if plan.inventory is not None else "",
            )

        delete_result = self.delete_remote_runs(expired_run_ids)
        return self._to_cleanup_result(local_path, destination, delete_result)

    def fetch_remote_manifests(self) -> RemoteManifestInventoryResult:
        remote_destination = self._build_remote_root_destination()
        with TemporaryDirectory(prefix="rsync-manifest-inventory-") as temp_dir:
            inventory_root = Path(temp_dir)
            command = self._build_inventory_command(inventory_root)
            logger.debug(
                "rsync inventory start destination=%s command=%s",
                remote_destination,
                " ".join(command),
            )
            result = self._run(command)
            if result.returncode != 0:
                error = RemoteStorageError(
                    message=f"rsync manifest inventory failed with exit code {result.returncode}",
                    command=command,
                    returncode=result.returncode,
                    stderr=result.stderr,
                    local_path=inventory_root,
                    remote_destination=remote_destination,
                )
                return RemoteManifestInventoryResult(
                    status="failed",
                    remote_destination=remote_destination,
                    command=command,
                    returncode=result.returncode,
                    stderr=result.stderr,
                    error=error,
                )

            manifests, errors = self._read_remote_manifests(inventory_root, remote_destination)
            status = "success" if not errors else "failed"
            error = None
            if errors:
                error = RemoteStorageError(
                    message="; ".join(errors),
                    command=command,
                    returncode=result.returncode,
                    stderr=result.stderr,
                    local_path=inventory_root,
                    remote_destination=remote_destination,
                )
            logger.debug(
                "rsync inventory finish destination=%s manifest_count=%s error_count=%s",
                remote_destination,
                len(manifests),
                len(errors),
            )
            return RemoteManifestInventoryResult(
                status=status,
                remote_destination=remote_destination,
                manifests=manifests,
                command=command,
                returncode=result.returncode,
                stderr=result.stderr,
                errors=errors,
                error=error,
            )

    def plan_remote_retention(
        self,
        retention_days: int,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> RemoteRetentionPlanResult:
        inventory = self.fetch_remote_manifests()
        remote_destination = inventory.remote_destination
        cutoff_at = _now_utc(now) - timedelta(days=retention_days)

        if not inventory.succeeded:
            return RemoteRetentionPlanResult(
                status="failed",
                remote_destination=remote_destination,
                retention_days=retention_days,
                cutoff_at=cutoff_at,
                retained_manifests=list(inventory.manifests),
                expired_manifests=[],
                errors=list(inventory.errors) if inventory.errors else [inventory.error.message if inventory.error else "remote manifest inventory failed"],
                inventory=inventory,
            )

        retained: list[RemoteManifestRecord] = []
        expired: list[RemoteManifestRecord] = []
        errors: list[str] = []
        for manifest in inventory.manifests:
            run_at = _record_timestamp(manifest)
            if run_at is None:
                errors.append(f"Unable to determine timestamp for remote run {manifest.run_id}")
                retained.append(manifest)
                continue
            if run_at < cutoff_at:
                expired.append(manifest)
            else:
                retained.append(manifest)

        status = "success" if not errors else "failed"
        return RemoteRetentionPlanResult(
            status=status,
            remote_destination=remote_destination,
            retention_days=retention_days,
            cutoff_at=cutoff_at,
            retained_manifests=retained,
            expired_manifests=expired,
            errors=errors,
            inventory=inventory,
        )

    def delete_remote_runs(self, run_ids: list[str]) -> RemoteDeleteResult:
        remote_destination = self._build_remote_root_destination()
        if not run_ids:
            return RemoteDeleteResult(status="success", remote_destination=remote_destination)

        with TemporaryDirectory(prefix="rsync-delete-") as temp_dir:
            delete_root = Path(temp_dir) / "delete-root"
            delete_root.mkdir(parents=True, exist_ok=True)
            files_from = Path(temp_dir) / "expired-runs.txt"
            files_from.write_text("\n".join(run_ids) + "\n", encoding="utf-8")
            command = self._build_delete_command(delete_root, files_from)
            logger.debug(
                "rsync delete start destination=%s run_ids=%s command=%s",
                remote_destination,
                run_ids,
                " ".join(command),
            )
            result = self._run(command)
            logger.debug(
                "rsync delete finish destination=%s returncode=%s deleted_run_ids=%s",
                remote_destination,
                result.returncode,
                run_ids,
            )
            return self._to_delete_result(remote_destination, command, result, run_ids)

    def _build_run_destination(self, local_path: Path, remote_path: str | None) -> str:
        remote_root = self._normalize_remote_path(remote_path)
        return f"rsync://{self.remote_user}@{self.remote_host}/{remote_root}/{local_path.name}"

    def _build_remote_root_destination(self) -> str:
        return f"rsync://{self.remote_user}@{self.remote_host}/{self._normalize_remote_path(None)}"

    def _remote_root(self) -> str:
        return self.remote_path.rstrip("/") or "/"

    def _normalize_remote_path(self, remote_path: str | None) -> str:
        path = (remote_path if remote_path is not None else self._remote_root()).strip()
        if path.startswith("rsync://"):
            return path.removeprefix("rsync://").rstrip("/")
        return path.lstrip("/").rstrip("/") or ""

    def _build_sync_command(self, local_path: Path, destination: str) -> list[str]:
        command = [
            "rsync",
            "-a",
            "--delete-delay",
            "--delay-updates",
            f"{str(local_path).rstrip('/')}/",
            destination,
        ]
        logger.debug(
            "rsync sync command built local_path=%s destination=%s command=%s",
            local_path,
            destination,
            " ".join(command),
        )
        return command

    def _build_inventory_command(self, inventory_root: Path) -> list[str]:
        command = [
            "rsync",
            "-a",
            "--include=*/",
            "--include=manifest.json",
            "--exclude=*",
            f"{self._build_remote_root_destination().rstrip('/')}/",
            f"{str(inventory_root).rstrip('/')}/",
        ]
        logger.debug(
            "rsync inventory command built inventory_root=%s command=%s",
            inventory_root,
            " ".join(command),
        )
        return command

    def _build_delete_command(self, delete_root: Path, files_from: Path) -> list[str]:
        command = [
            "rsync",
            "-r",
            f"--files-from={files_from}",
            "--ignore-missing-args",
            "--delete-missing-args",
            "--force",
            f"{str(delete_root).rstrip('/')}/",
            self._build_remote_root_destination(),
        ]
        logger.debug(
            "rsync delete command built delete_root=%s files_from=%s command=%s",
            delete_root,
            files_from,
            " ".join(command),
        )
        return command

    def _read_remote_manifests(
        self,
        inventory_root: Path,
        remote_destination: str,
    ) -> tuple[list[RemoteManifestRecord], list[str]]:
        manifests: list[RemoteManifestRecord] = []
        errors: list[str] = []

        if not inventory_root.exists():
            return manifests, [f"Remote manifest inventory root {inventory_root} does not exist"]

        for run_dir in sorted(path for path in inventory_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                errors.append(f"Missing manifest.json for remote run {run_dir.name}")
                continue
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid manifest.json for remote run {run_dir.name}: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"Invalid manifest payload for remote run {run_dir.name}: expected JSON object")
                continue
            manifests.append(
                RemoteManifestRecord(
                    run_id=run_dir.name,
                    remote_run_path=f"{remote_destination.rstrip('/')}/{run_dir.name}",
                    manifest_local_path=manifest_path,
                    finished_at=_parse_datetime(str(payload.get("finished_at") or "")),
                    started_at=_parse_datetime(str(payload.get("started_at") or "")),
                )
            )

        return manifests, errors

    def _run(self, command: list[str]) -> CommandResult:
        env = {"RSYNC_PASSWORD": self.remote_password}
        logger.debug("rsync execution starting command=%s env_keys=%s", " ".join(command), sorted(env))
        result = self.executor.run(command, env=env)
        logger.debug(
            "rsync execution finished command=%s returncode=%s stdout=%s stderr=%s",
            " ".join(command),
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return result

    def _to_sync_result(
        self,
        local_path: Path,
        destination: str,
        command: list[str],
        result: CommandResult,
    ) -> RemoteSyncResult:
        if result.returncode == 0:
            return RemoteSyncResult(
                status="success",
                local_path=local_path,
                remote_destination=destination,
                command=command,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        error = RemoteStorageError(
            message=f"rsync failed with exit code {result.returncode}",
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
            local_path=local_path,
            remote_destination=destination,
        )
        return RemoteSyncResult(
            status="failed",
            local_path=local_path,
            remote_destination=destination,
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
            error=error,
        )

    def _to_delete_result(
        self,
        destination: str,
        command: list[str],
        result: CommandResult,
        run_ids: list[str],
    ) -> RemoteDeleteResult:
        if result.returncode == 0:
            return RemoteDeleteResult(
                status="success",
                remote_destination=destination,
                deleted_run_ids=run_ids,
                command=command,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        error = RemoteStorageError(
            message=f"rsync delete failed with exit code {result.returncode}",
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
            remote_destination=destination,
        )
        return RemoteDeleteResult(
            status="failed",
            remote_destination=destination,
            deleted_run_ids=run_ids,
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
            error=error,
        )

    def _to_cleanup_result(
        self,
        local_path: Path,
        destination: str,
        delete_result: RemoteDeleteResult,
    ) -> RemoteCleanupResult:
        if delete_result.succeeded:
            return RemoteCleanupResult(
                status="success",
                local_path=local_path,
                remote_destination=destination,
                command=delete_result.command,
                returncode=delete_result.returncode,
                stderr=delete_result.stderr,
            )
        return RemoteCleanupResult(
            status="failed",
            local_path=local_path,
            remote_destination=destination,
            command=delete_result.command,
            returncode=delete_result.returncode,
            stderr=delete_result.stderr,
            error=delete_result.error,
        )


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_run_id(run_id: str) -> datetime | None:
    prefix = run_id.split("-", 1)[0]
    if len(prefix) != 16 or not prefix.endswith("Z"):
        return None
    try:
        parsed = datetime.strptime(prefix, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _record_timestamp(record: RemoteManifestRecord) -> datetime | None:
    return record.finished_at or record.started_at or _parse_run_id(record.run_id)


def _now_utc(now: Callable[[], datetime] | None = None) -> datetime:
    current = now() if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
