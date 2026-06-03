"""Local mounted directory storage provider."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from backup_agent.infrastructure.filesystem import ensure_directory, safe_name, write_text_atomic
from backup_agent.services.retention import build_retention_plan

from .base import RemoteCleanupResult, RemoteStorageError, RemoteStorageProvider, RemoteSyncResult


@dataclass(slots=True)
class LocalDirectoryStorageProvider(RemoteStorageProvider):
    """Publish completed runs into a mounted local directory."""

    storage_root: Path

    def sync(self, local_path: Path, remote_path: str | None = None) -> RemoteSyncResult:
        destination_root = ensure_directory(self.storage_root)
        runs_root = ensure_directory(destination_root / "runs")
        destination = self._run_destination(local_path, remote_path)
        final_dir = runs_root / destination

        try:
            if final_dir.exists():
                raise FileExistsError(f"Destination run directory already exists: {final_dir}")
            temp_parent = ensure_directory(runs_root / ".tmp")
            with TemporaryDirectory(dir=temp_parent, prefix=f"{safe_name(local_path.name)}-") as temp_dir:
                temp_root = Path(temp_dir)
                temp_run_dir = temp_root / local_path.name
                shutil.copytree(local_path, temp_run_dir, dirs_exist_ok=False)
                shutil.move(str(temp_run_dir), final_dir)
        except Exception as exc:
            error = RemoteStorageError(
                message=f"local storage publish failed: {exc}",
                local_path=local_path,
                remote_destination=str(final_dir),
            )
            return RemoteSyncResult(
                status="failed",
                local_path=local_path,
                remote_destination=str(final_dir),
                error=error,
            )

        self._update_latest(destination_root, final_dir.relative_to(destination_root))
        return RemoteSyncResult(
            status="success",
            local_path=local_path,
            remote_destination=str(final_dir),
        )

    def cleanup(self, local_path: Path, retention_days: int) -> RemoteCleanupResult:
        destination_root = ensure_directory(self.storage_root)
        runs_root = ensure_directory(destination_root / "runs")
        plan = build_retention_plan(runs_root, retention_days)
        temp_root = runs_root / ".tmp"
        if temp_root.exists():
            for child in temp_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        pass
        removed: list[Path] = []
        errors: list[str] = list(plan.errors)
        for run_dir in plan.expired_run_dirs:
            try:
                shutil.rmtree(run_dir)
                removed.append(run_dir)
            except OSError as exc:
                errors.append(f"Failed to remove {run_dir.name}: {exc}")
        retained = [run_dir for run_dir in plan.retained_run_dirs if run_dir.exists()]
        self._update_latest(destination_root, self._newest_run_name(retained))
        status = "success" if not errors else ("partial" if removed else "failed")
        error = None
        if errors:
            error = RemoteStorageError(
                message="; ".join(errors),
                local_path=local_path,
                remote_destination=str(runs_root),
            )
        return RemoteCleanupResult(
            status=status,
            local_path=local_path,
            remote_destination=str(runs_root),
            error=error,
        )

    def _run_destination(self, local_path: Path, remote_path: str | None) -> str:
        if remote_path:
            return remote_path.rstrip("/")
        return local_path.name

    def _update_latest(self, destination_root: Path, target: Path | None) -> None:
        latest = destination_root / "latest"
        if target is None:
            if latest.exists() or latest.is_symlink():
                try:
                    latest.unlink()
                except OSError:
                    pass
            return
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(target)
        except OSError:
            write_text_atomic(latest, str(target))

    def _newest_run_name(self, retained_run_dirs: list[Path]) -> Path | None:
        if not retained_run_dirs:
            return None
        newest = max(retained_run_dirs, key=lambda path: path.name)
        return Path("runs") / newest.name
