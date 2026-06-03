"""Retention service for local run directory cleanup and retention planning."""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backup_agent.infrastructure.filesystem import ensure_directory


@dataclass(slots=True)
class RetentionPlan:
    """A retention decision for a run directory tree."""

    completed_runs_dir: Path
    retention_days: int
    cutoff_at: datetime
    retained_run_dirs: list[Path] = field(default_factory=list)
    expired_run_dirs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetentionCleanupResult:
    """Structured result for retention cleanup operations."""

    status: str
    completed_runs_dir: Path
    retention_days: int
    cutoff_at: datetime
    removed_run_dirs: list[Path] = field(default_factory=list)
    retained_run_dirs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class RetentionManager(ABC):
    """Abstract contract for retention cleanup."""

    @abstractmethod
    def plan(self, completed_runs_dir: Path, retention_days: int) -> RetentionPlan:
        """Decide which run directories should be retained or expired."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self, completed_runs_dir: Path, retention_days: int) -> RetentionCleanupResult:
        """Remove expired backup run directories."""
        raise NotImplementedError


@dataclass(slots=True)
class FileSystemRetentionManager(RetentionManager):
    """Delete complete run directories older than the configured retention window."""

    now: Callable[[], datetime] = field(default_factory=lambda: (lambda: datetime.now(timezone.utc)))

    def plan(self, completed_runs_dir: Path, retention_days: int) -> RetentionPlan:
        return build_retention_plan(completed_runs_dir, retention_days, now=self.now)

    def cleanup(self, completed_runs_dir: Path, retention_days: int) -> RetentionCleanupResult:
        plan = self.plan(completed_runs_dir, retention_days)
        removed: list[Path] = []
        errors = list(plan.errors)

        for run_dir in plan.expired_run_dirs:
            try:
                shutil.rmtree(run_dir)
                removed.append(run_dir)
            except OSError as exc:
                errors.append(f"Failed to remove {run_dir.name}: {exc}")

        retained = [run_dir for run_dir in plan.retained_run_dirs if run_dir.exists()]
        if removed or errors:
            self._update_latest_pointer(plan.completed_runs_dir, retained)

        status = "success" if not errors else ("partial" if removed else "failed")
        return RetentionCleanupResult(
            status=status,
            completed_runs_dir=plan.completed_runs_dir,
            retention_days=plan.retention_days,
            cutoff_at=plan.cutoff_at,
            removed_run_dirs=removed,
            retained_run_dirs=retained,
            errors=errors,
        )

    def _update_latest_pointer(self, completed_runs_dir: Path, retained_run_dirs: list[Path]) -> None:
        latest = completed_runs_dir.parent / "latest"
        if not retained_run_dirs:
            if latest.exists() or latest.is_symlink():
                try:
                    latest.unlink()
                except OSError:
                    pass
            return

        newest = max(
            retained_run_dirs,
            key=lambda path: _run_timestamp(path) or datetime.min.replace(tzinfo=timezone.utc),
        )
        relative_target = Path("runs") / newest.name
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(relative_target)
        except OSError:
            latest.write_text(str(relative_target), encoding="utf-8")


def build_retention_plan(
    completed_runs_dir: Path,
    retention_days: int,
    *,
    now: Callable[[], datetime] | None = None,
) -> RetentionPlan:
    """Build a retention plan without mutating the filesystem."""

    completed_runs_dir = ensure_directory(completed_runs_dir)
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")

    current = _now_utc(now)
    cutoff_at = current - timedelta(days=retention_days)
    retained: list[Path] = []
    expired: list[Path] = []
    errors: list[str] = []

    for run_dir in sorted(path for path in completed_runs_dir.iterdir() if path.is_dir() and not path.name.startswith(".")):
        run_at = _run_timestamp(run_dir)
        if run_at is None:
            errors.append(f"Unable to determine timestamp for {run_dir.name}")
            retained.append(run_dir)
            continue
        if run_at < cutoff_at:
            expired.append(run_dir)
        else:
            retained.append(run_dir)

    return RetentionPlan(
        completed_runs_dir=completed_runs_dir,
        retention_days=retention_days,
        cutoff_at=cutoff_at,
        retained_run_dirs=retained,
        expired_run_dirs=expired,
        errors=errors,
    )


def _now_utc(now: Callable[[], datetime] | None = None) -> datetime:
    current = now() if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _run_timestamp(run_dir: Path) -> datetime | None:
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for key in ("finished_at", "started_at"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                parsed = _parse_datetime(value)
                if parsed is not None:
                    return parsed
    return _parse_run_id(run_dir.name)


def _parse_datetime(value: str) -> datetime | None:
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
