"""Rsync storage provider."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

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
        command, password_file = self._build_sync_command(local_path, destination)
        try:
            result = self._run(command)
        finally:
            self._cleanup_password_file(password_file)
        return self._to_sync_result(local_path, destination, command, result)

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        plan = build_retention_plan(local_path, retention_days)
        destination = self._build_remote_root_destination()

        with TemporaryDirectory(prefix="rsync-retention-") as temp_dir:
            temp_root = Path(temp_dir)
            self._populate_retention_view(temp_root, plan.retained_run_dirs)
            command, password_file = self._build_cleanup_command(temp_root, destination)
            try:
                result = self._run(command)
            finally:
                self._cleanup_password_file(password_file)

        return self._to_cleanup_result(local_path, destination, command, result, plan.errors)

    def _build_run_destination(self, local_path: Path, remote_path: str | None) -> str:
        if remote_path:
            return remote_path.rstrip("/")
        run_id = safe_name(local_path.name, local_path.name)
        return f"{self.remote_user}@{self.remote_host}::{self._remote_root().rstrip('/')}/runs/{run_id}"

    def _build_remote_root_destination(self) -> str:
        return f"{self.remote_user}@{self.remote_host}::{self._remote_root().rstrip('/')}"

    def _remote_root(self) -> str:
        return self.remote_path.rstrip("/") or "/"

    def _build_sync_command(self, local_path: Path, destination: str) -> tuple[list[str], Path]:
        password_file = self._create_password_file()
        command = [
            "rsync",
            "-a",
            "--delete-delay",
            "--delay-updates",
            "--mkpath",
            f"--password-file={password_file}",
            f"{str(local_path).rstrip('/')}/",
            destination,
        ]
        return command, password_file

    def _build_cleanup_command(self, local_path: Path, destination: str) -> tuple[list[str], Path]:
        password_file = self._create_password_file()
        command = [
            "rsync",
            "-aL",
            "--delete-delay",
            "--delay-updates",
            f"--password-file={password_file}",
            f"{str(local_path).rstrip('/')}/",
            destination,
        ]
        return command, password_file

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

    def _create_password_file(self) -> Path:
        with NamedTemporaryFile("w", delete=False, prefix="rsync-password-", suffix=".txt") as temp_file:
            temp_file.write(self.remote_password)
            password_file = Path(temp_file.name)
        os.chmod(password_file, 0o600)
        return password_file

    def _cleanup_password_file(self, password_file: Path) -> None:
        try:
            password_file.unlink()
        except FileNotFoundError:
            pass

    def _run(self, command: list[str]) -> CommandResult:
        env = {"RSYNC_PASSWORD": self.remote_password}
        return self.executor.run(command, env=env)

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
