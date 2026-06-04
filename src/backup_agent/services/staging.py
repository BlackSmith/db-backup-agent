"""Local staging helpers for run directories and artifact placement."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backup_agent.domain.backup_target import BackupTarget
from backup_agent.infrastructure.filesystem import ensure_directory, safe_name


@dataclass(slots=True)
class RunLayout:
    """Resolved local directory layout for one backup run."""

    run_id: str
    backup_root: Path
    runs_root: Path
    run_dir: Path
    manifest_path: Path
    latest_path: Path


@dataclass(slots=True)
class LocalStagingManager:
    """Create isolated run directories under the configured local backup root."""

    backup_root: Path
    runs_dir_name: str = "runs"
    latest_name: str = "latest"

    def create_run(self, run_id: str | None = None) -> RunLayout:
        run_id = run_id or generate_run_id()
        backup_root = ensure_directory(self.backup_root)
        runs_root = ensure_directory(backup_root / self.runs_dir_name)
        run_dir = ensure_directory(runs_root / run_id)
        layout = RunLayout(
            run_id=run_id,
            backup_root=backup_root,
            runs_root=runs_root,
            run_dir=run_dir,
            manifest_path=run_dir / "manifest.json",
            latest_path=backup_root / self.latest_name,
        )
        self._update_latest(layout)
        return layout

    def artifact_directory_for(self, run_dir: Path, target: BackupTarget) -> Path:
        """Return the deterministic artifact directory for a target."""

        return run_dir / safe_name(target.db_type.lower(), target.db_type.lower()) / safe_name(
            target.container_name, target.container_id
        )

    def cleanup_run_tree(self, layout: RunLayout) -> None:
        """Remove the staged run tree after a successful publish."""

        if layout.run_dir.exists():
            shutil.rmtree(layout.run_dir)

        remaining_run_dirs = self._remaining_run_dirs(layout.runs_root)
        self._update_latest_from_remaining(layout.backup_root, remaining_run_dirs)

        if not remaining_run_dirs:
            try:
                layout.runs_root.rmdir()
            except OSError:
                pass

    def _remaining_run_dirs(self, runs_root: Path) -> list[Path]:
        if not runs_root.exists():
            return []
        return sorted(
            [path for path in runs_root.iterdir() if path.is_dir() and not path.name.startswith(".")],
            key=lambda path: path.name,
        )

    def _update_latest_from_remaining(self, backup_root: Path, retained_run_dirs: list[Path]) -> None:
        latest = backup_root / self.latest_name
        if not retained_run_dirs:
            if latest.exists() or latest.is_symlink():
                try:
                    latest.unlink()
                except OSError:
                    pass
            return

        target = Path(self.runs_dir_name) / retained_run_dirs[-1].name
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(target)
        except OSError:
            latest.write_text(str(target), encoding="utf-8")

    def _update_latest(self, layout: RunLayout) -> None:
        """Maintain a latest pointer when the filesystem allows it."""

        latest = layout.latest_path
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(Path(self.runs_dir_name) / layout.run_id)
        except OSError:
            latest.write_text(str(Path(self.runs_dir_name) / layout.run_id), encoding="utf-8")


def generate_run_id(reference: datetime | None = None) -> str:
    """Generate a safe, time-ordered run identifier."""

    current = reference or datetime.now(timezone.utc)
    timestamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"
