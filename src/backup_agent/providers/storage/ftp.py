"""FTP / FTPS storage provider."""

from __future__ import annotations

import contextlib
import ftplib
import io
import json
import logging
import posixpath
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .base import (
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
class FtpStorageProvider(RemoteStorageProvider):
    """Publish completed runs to an FTP or FTPS destination."""

    host: str
    port: int
    user: str
    password: str
    remote_path: str
    use_tls: bool = False
    passive: bool = True
    timeout: float = 30.0

    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        destination = self._run_remote_destination(local_path, remote_path)
        remote_root = self._remote_root(remote_path)
        logger.debug(
            "ftp sync start local_path=%s destination=%s use_tls=%s passive=%s timeout=%s",
            local_path,
            destination,
            self.use_tls,
            self.passive,
            self.timeout,
        )
        try:
            with self._connect() as client:
                self._ensure_remote_dir(client, remote_root)
                if self._remote_path_exists(client, destination):
                    raise FileExistsError(f"Destination run directory already exists: {destination}")
                self._ensure_remote_dir(client, posixpath.dirname(destination))
                self._upload_tree(client, local_path, destination)
                self._update_latest(client, f"runs/{local_path.name}")
            return RemoteSyncResult(status="success", local_path=local_path, remote_destination=destination)
        except Exception as exc:
            logger.debug("ftp sync failed local_path=%s destination=%s error=%s", local_path, destination, exc)
            error = RemoteStorageError(
                message=f"ftp publish failed: {exc}",
                local_path=local_path,
                remote_destination=destination,
            )
            return RemoteSyncResult(
                status="failed",
                local_path=local_path,
                remote_destination=destination,
                error=error,
            )

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        remote_destination = self._remote_root(None)
        try:
            inventory = self.fetch_remote_manifests()
        except Exception as exc:
            return RemoteCleanupResult(
                status="failed",
                local_path=local_path,
                remote_destination=remote_destination,
                error=RemoteStorageError(
                    message=f"ftp retention planning failed: {exc}",
                    local_path=local_path,
                    remote_destination=remote_destination,
                ),
            )

        plan = self._build_retention_plan(inventory, retention_days)
        if not inventory.succeeded and not inventory.manifests:
            error = RemoteStorageError(
                message="; ".join(inventory.errors) if inventory.errors else "ftp manifest inventory failed",
                local_path=local_path,
                remote_destination=remote_destination,
            )
            return RemoteCleanupResult(
                status="failed",
                local_path=local_path,
                remote_destination=remote_destination,
                error=error,
            )

        deleted: list[str] = []
        errors = list(plan.errors)
        try:
            with self._connect() as client:
                runs_root = self._runs_root(None)
                for run_id in [record.run_id for record in plan.expired_manifests]:
                    run_dir = self._join_remote(runs_root, run_id)
                    try:
                        self._delete_remote_tree(client, run_dir)
                        deleted.append(run_id)
                    except Exception as exc:
                        errors.append(f"Failed to remove {run_id}: {exc}")
                self._update_latest(client, self._latest_value(plan.retained_manifests))
        except Exception as exc:
            errors.append(str(exc))

        if errors and deleted:
            status = "partial"
        elif errors:
            status = "failed"
        else:
            status = "success"
        error = None
        if errors:
            error = RemoteStorageError(
                message="; ".join(errors),
                local_path=local_path,
                remote_destination=remote_destination,
            )
        return RemoteCleanupResult(
            status=status,
            local_path=local_path,
            remote_destination=remote_destination,
            error=error,
        )

    def fetch_remote_manifests(self) -> RemoteManifestInventoryResult:
        remote_destination = self._remote_root(None)
        manifests: list[RemoteManifestRecord] = []
        errors: list[str] = []
        try:
            with self._connect() as client:
                runs_root = self._runs_root(None)
                for run_name, is_dir in self._list_remote_runs(client, runs_root):
                    if not is_dir or run_name.startswith("."):
                        continue
                    remote_run_dir = self._join_remote(runs_root, run_name)
                    manifest = self._fetch_remote_manifest(client, remote_run_dir)
                    if manifest is None:
                        errors.append(f"Missing or unreadable manifest.json for remote run {run_name}")
                        continue
                    manifests.append(
                        RemoteManifestRecord(
                            run_id=run_name,
                            remote_run_path=remote_run_dir,
                            manifest_local_path=None,
                            finished_at=manifest.get("finished_at"),
                            started_at=manifest.get("started_at"),
                        )
                    )
        except Exception as exc:
            error = RemoteStorageError(
                message=f"ftp manifest inventory failed: {exc}",
                remote_destination=remote_destination,
            )
            return RemoteManifestInventoryResult(
                status="failed",
                remote_destination=remote_destination,
                error=error,
            )

        status = "success" if not errors else "failed"
        error = None
        if errors:
            error = RemoteStorageError(
                message="; ".join(errors),
                remote_destination=remote_destination,
            )
        return RemoteManifestInventoryResult(
            status=status,
            remote_destination=remote_destination,
            manifests=manifests,
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
        cutoff_at = _now_utc(now) - timedelta(days=retention_days)

        retained: list[RemoteManifestRecord] = []
        expired: list[RemoteManifestRecord] = []
        errors: list[str] = list(inventory.errors)
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
            remote_destination=inventory.remote_destination,
            retention_days=retention_days,
            cutoff_at=cutoff_at,
            retained_manifests=retained,
            expired_manifests=expired,
            errors=errors,
            inventory=inventory,
        )

    def delete_remote_runs(self, run_ids: list[str]) -> RemoteDeleteResult:
        remote_destination = self._remote_root(None)
        deleted: list[str] = []
        errors: list[str] = []
        try:
            with self._connect() as client:
                runs_root = self._runs_root(None)
                for run_id in run_ids:
                    try:
                        self._delete_remote_tree(client, self._join_remote(runs_root, run_id))
                        deleted.append(run_id)
                    except Exception as exc:
                        errors.append(f"Failed to remove {run_id}: {exc}")
        except Exception as exc:
            errors.append(str(exc))

        status = "success" if not errors else ("partial" if deleted else "failed")
        error = None
        if errors:
            error = RemoteStorageError(
                message="; ".join(errors),
                remote_destination=remote_destination,
            )
        return RemoteDeleteResult(
            status=status,
            remote_destination=remote_destination,
            deleted_run_ids=deleted,
            error=error,
        )

    def _connect(self) -> ftplib.FTP | ftplib.FTP_TLS:
        ftp_cls: type[ftplib.FTP] | type[ftplib.FTP_TLS]
        if self.use_tls:
            ftp_cls = ftplib.FTP_TLS
        else:
            ftp_cls = ftplib.FTP
        client = ftp_cls()
        client.connect(self.host, self.port, timeout=self.timeout)
        client.login(self.user, self.password)
        if self.use_tls and isinstance(client, ftplib.FTP_TLS):
            client.prot_p()
        client.set_pasv(self.passive)
        return client

    def _ensure_remote_dir(self, client: ftplib.FTP | ftplib.FTP_TLS, remote_dir: str) -> None:
        normalized = self._normalize_remote_path(remote_dir)
        if normalized == "/":
            return
        current = ""
        for part in normalized.strip("/").split("/"):
            if not part:
                continue
            current = f"{current}/{part}" if current else f"/{part}"
            with contextlib.suppress(ftplib.all_errors, OSError):
                client.mkd(current)

    def _upload_tree(self, client: ftplib.FTP | ftplib.FTP_TLS, local_root: Path, remote_root: str) -> None:
        for path in sorted(local_root.rglob("*")):
            relative = path.relative_to(local_root).as_posix()
            remote_path = self._join_remote(remote_root, relative)
            if path.is_dir():
                self._ensure_remote_dir(client, remote_path)
                continue
            self._ensure_remote_dir(client, posixpath.dirname(remote_path))
            with path.open("rb") as handle:
                client.storbinary(f"STOR {remote_path}", handle)

    def _list_remote_runs(
        self,
        client: ftplib.FTP | ftplib.FTP_TLS,
        runs_root: str,
    ) -> list[tuple[str, bool]]:
        return [entry for entry in self._list_remote_entries(client, runs_root) if entry[0] not in {".", ".."}]

    def _fetch_remote_manifest(
        self,
        client: ftplib.FTP | ftplib.FTP_TLS,
        remote_run_dir: str,
    ) -> dict[str, datetime] | None:
        buffer = io.BytesIO()
        remote_manifest = self._join_remote(remote_run_dir, "manifest.json")
        try:
            client.retrbinary(f"RETR {remote_manifest}", buffer.write)
        except ftplib.all_errors:
            return None
        try:
            payload = json.loads(buffer.getvalue().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return {
            "finished_at": _parse_datetime(str(payload.get("finished_at") or "")),
            "started_at": _parse_datetime(str(payload.get("started_at") or "")),
        }

    def _delete_remote_tree(self, client: ftplib.FTP | ftplib.FTP_TLS, remote_dir: str) -> None:
        for name, is_dir in self._list_remote_entries(client, remote_dir):
            remote_entry = self._join_remote(remote_dir, name)
            if is_dir:
                self._delete_remote_tree(client, remote_entry)
            else:
                client.delete(remote_entry)
        with contextlib.suppress(ftplib.all_errors):
            client.rmd(remote_dir)
        with contextlib.suppress(ftplib.all_errors):
            client.delete(remote_dir)

    def _update_latest(self, client: ftplib.FTP | ftplib.FTP_TLS, latest_value: str | None) -> None:
        latest_path = self._join_remote(self._remote_root(None), "latest")
        if latest_value is None:
            with contextlib.suppress(ftplib.all_errors):
                client.delete(latest_path)
            return
        self._ensure_remote_dir(client, self._remote_root(None))
        with io.BytesIO(latest_value.encode("utf-8")) as buffer:
            client.storbinary(f"STOR {latest_path}", buffer)

    def _latest_value(self, retained: list[RemoteManifestRecord]) -> str | None:
        if not retained:
            return None
        newest = max(retained, key=_record_timestamp)
        return f"runs/{newest.run_id}"

    def _build_retention_plan(
        self,
        inventory: RemoteManifestInventoryResult,
        retention_days: int,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> RemoteRetentionPlanResult:
        cutoff_at = _now_utc(now) - timedelta(days=retention_days)
        retained: list[RemoteManifestRecord] = []
        expired: list[RemoteManifestRecord] = []
        errors: list[str] = list(inventory.errors)
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
            remote_destination=inventory.remote_destination,
            retention_days=retention_days,
            cutoff_at=cutoff_at,
            retained_manifests=retained,
            expired_manifests=expired,
            errors=errors,
            inventory=inventory,
        )

    def _remote_root(self, remote_path: str | None) -> str:
        return self._normalize_remote_path(remote_path if remote_path is not None else self.remote_path)

    def _runs_root(self, remote_path: str | None) -> str:
        return self._join_remote(self._remote_root(remote_path), "runs")

    def _run_remote_destination(self, local_path: Path, remote_path: str | None) -> str:
        return self._join_remote(self._runs_root(remote_path), local_path.name)

    def _normalize_remote_path(self, remote_path: str) -> str:
        path = remote_path.strip()
        if not path or path == "/":
            return "/"
        return "/" + path.strip("/")

    def _join_remote(self, parent: str, child: str) -> str:
        parent = self._normalize_remote_path(parent)
        child = child.strip().lstrip("/")
        if not child:
            return parent
        if parent == "/":
            return f"/{child}"
        return posixpath.join(parent, child)

    def _list_remote_entries(
        self,
        client: ftplib.FTP | ftplib.FTP_TLS,
        remote_dir: str,
    ) -> list[tuple[str, bool]]:
        try:
            entries = []
            for name, facts in client.mlsd(remote_dir, facts=["type"]):
                entries.append((name, facts.get("type") == "dir"))
            return entries
        except (AttributeError, ftplib.error_perm):
            names = client.nlst(remote_dir)
            entries: list[tuple[str, bool]] = []
            for name in names:
                base = name.rstrip("/").rsplit("/", 1)[-1]
                entries.append((base, self._is_directory(client, self._join_remote(remote_dir, base))))
            return entries

    def _is_directory(self, client: ftplib.FTP | ftplib.FTP_TLS, remote_path: str) -> bool:
        try:
            current = client.pwd()
        except Exception:
            current = None
        try:
            client.cwd(remote_path)
        except ftplib.all_errors:
            return False
        finally:
            if current is not None:
                with contextlib.suppress(ftplib.all_errors):
                    client.cwd(current)
        return True

    def _remote_path_exists(self, client: ftplib.FTP | ftplib.FTP_TLS, remote_dir: str) -> bool:
        try:
            self._list_remote_entries(client, remote_dir)
            return True
        except ftplib.all_errors:
            return False


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
