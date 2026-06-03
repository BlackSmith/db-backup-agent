"""Application configuration loading and validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    """Raised when the environment does not contain valid application config."""


_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass(slots=True)
class AppConfig:
    """Validated application configuration."""

    app_name: str = "backup-agent"
    version: str = "0.1.0"
    rsync_remote_host: str = ""
    rsync_remote_user: str = ""
    rsync_remote_password: str = ""
    backup_time: time = field(default_factory=lambda: time(2, 0))
    backup_retention_days: int = 7
    rsync_remote_path: str = "/backups"
    local_backup_dir: Path = field(default_factory=lambda: Path("/backup"))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    log_level: str = "INFO"
    docker_socket_path: str = "/var/run/docker.sock"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppConfig":
        """Load and validate configuration from environment variables."""

        source = os.environ if env is None else env
        errors: list[str] = []

        def read_required(name: str) -> str:
            value = source.get(name, "").strip()
            if not value:
                errors.append(f"{name} is required")
            return value

        rsync_remote_host = read_required("RSYNC_REMOTE_HOST")
        rsync_remote_user = read_required("RSYNC_REMOTE_USER")
        rsync_remote_password = read_required("RSYNC_REMOTE_PASSWORD")

        backup_time_raw = source.get("BACKUP_TIME", "").strip()
        backup_time = cls._parse_backup_time(backup_time_raw, errors)

        backup_retention_days_raw = source.get("BACKUP_RETENTION_DAYS", "").strip()
        backup_retention_days = cls._parse_retention_days(
            backup_retention_days_raw, errors
        )

        rsync_remote_path = source.get("RSYNC_REMOTE_PATH", "/backups").strip() or "/backups"
        local_backup_dir = Path(
            source.get("LOCAL_BACKUP_DIR", "/backup").strip() or "/backup"
        )
        timezone = cls._parse_timezone(source.get("TZ", "UTC").strip() or "UTC", errors)
        log_level = source.get("LOG_LEVEL", "INFO").strip() or "INFO"
        docker_socket_path = (
            source.get("DOCKER_SOCKET_PATH", "/var/run/docker.sock").strip()
            or "/var/run/docker.sock"
        )

        cls._ensure_directory(local_backup_dir, errors)

        if errors:
            raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))

        return cls(
            rsync_remote_host=rsync_remote_host,
            rsync_remote_user=rsync_remote_user,
            rsync_remote_password=rsync_remote_password,
            backup_time=backup_time,
            backup_retention_days=backup_retention_days,
            rsync_remote_path=rsync_remote_path,
            local_backup_dir=local_backup_dir,
            timezone=timezone,
            log_level=log_level,
            docker_socket_path=docker_socket_path,
        )

    @staticmethod
    def _parse_backup_time(value: str, errors: list[str]) -> time:
        if not value:
            errors.append("BACKUP_TIME is required and must use HH:MM format")
            return time(2, 0)
        if not _TIME_RE.match(value):
            errors.append(f"BACKUP_TIME must use HH:MM format, got {value!r}")
            return time(2, 0)
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError:
            errors.append(f"BACKUP_TIME must be a valid 24-hour time, got {value!r}")
            return time(2, 0)

    @staticmethod
    def _parse_retention_days(value: str, errors: list[str]) -> int:
        if not value:
            errors.append("BACKUP_RETENTION_DAYS is required and must be >= 1")
            return 1
        try:
            parsed = int(value)
        except ValueError:
            errors.append(f"BACKUP_RETENTION_DAYS must be an integer, got {value!r}")
            return 1
        if parsed < 1:
            errors.append("BACKUP_RETENTION_DAYS must be greater than or equal to 1")
            return 1
        return parsed

    @staticmethod
    def _parse_timezone(value: str, errors: list[str]) -> ZoneInfo:
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError:
            errors.append(f"TZ must reference a valid timezone, got {value!r}")
            return ZoneInfo("UTC")

    @staticmethod
    def _ensure_directory(path: Path, errors: list[str]) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"LOCAL_BACKUP_DIR {str(path)!r} is not writable: {exc}")
