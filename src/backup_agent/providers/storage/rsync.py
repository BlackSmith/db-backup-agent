"""Rsync storage provider."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from backup_agent.infrastructure.filesystem import safe_name
from backup_agent.providers.databases.base import CommandResult, SubprocessCommandExecutor
from backup_agent.services.retention import build_retention_plan

from .base import (
    CommandExecutor,
    RemoteCleanupResult,
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
        plan = build_retention_plan(local_path, retention_days)
        destination = self._build_remote_root_destination()

        with TemporaryDirectory(prefix="rsync-retention-") as temp_dir:
            temp_root = Path(temp_dir)
            self._populate_retention_view(temp_root, plan.retained_run_dirs)
            command = self._build_cleanup_command(temp_root, destination)
            logger.debug(
                "rsync cleanup start local_path=%s destination=%s retention_days=%s command=%s",
                local_path,
                destination,
                retention_days,
                " ".join(command),
            )
            result = self._run(command)

        logger.debug(
            "rsync cleanup finish local_path=%s destination=%s returncode=%s retained=%s expired=%s",
            local_path,
            destination,
            result.returncode,
            [str(path) for path in plan.retained_run_dirs],
            [str(path) for path in plan.expired_run_dirs],
        )
        return self._to_cleanup_result(local_path, destination, command, result, plan.errors)

    def _build_run_destination(self, local_path: Path, remote_path: str | None) -> str:
        remote_root = self._normalize_remote_path(remote_path)
        run_id = safe_name(local_path.name, local_path.name)
        return f"rsync://{self.remote_user}@{self.remote_host}/{remote_root}/runs/{run_id}"

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

    def _build_cleanup_command(self, local_path: Path, destination: str) -> list[str]:
        command = [
            "rsync",
            "-aL",
            "--delete-delay",
            "--delay-updates",
            f"{str(local_path).rstrip('/')}/",
            destination,
        ]
        logger.debug(
            "rsync cleanup command built local_path=%s destination=%s command=%s",
            local_path,
            destination,
            " ".join(command),
        )
        return command

    def _populate_retention_view(self, temp_root: Path, retained_run_dirs: list[Path]) -> None:
        runs_view = temp_root / "runs"
        runs_view.mkdir(parents=True, exist_ok=True)
        for run_dir in retained_run_dirs:
            link_path = runs_view / run_dir.name
            try:
                link_path.symlink_to(run_dir)
            except OSError:
                if run_dir.is_dir():
                    shutil.copytree(run_dir, link_path)
                else:
                    link_path.write_text(run_dir.read_text(encoding="utf-8"), encoding="utf-8")

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

    def _to_cleanup_result(
        self,
        local_path: Path,
        destination: str,
        command: list[str],
        result: CommandResult,
        plan_errors: list[str],
    ) -> RemoteCleanupResult:
        if result.returncode == 0:
            status = "success" if not plan_errors else "partial"
            error = None
        else:
            status = "failed"
            error = RemoteStorageError(
                message=f"rsync cleanup failed with exit code {result.returncode}",
                command=command,
                returncode=result.returncode,
                stderr=result.stderr,
                local_path=local_path,
                remote_destination=destination,
            )
        return RemoteCleanupResult(
            status=status,
            local_path=local_path,
            remote_destination=destination,
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
            error=error,
        )
