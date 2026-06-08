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
    ftp_host: str = ""
    ftp_port: int = 21
    ftp_user: str = ""
    ftp_password: str = ""
    ftp_remote_path: str = "/backups"
    ftp_tls: bool = False
    ftp_passive: bool = True
    ftp_timeout: float = 30.0
    backup_time: time = field(default_factory=lambda: time(2, 0))
    backup_retention_days: int = 7
    rsync_remote_path: str = "/backups"
    backup_local_storage: Path | None = None
    local_backup_dir: Path = field(default_factory=lambda: Path("/.temporary_storage"))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    log_level: str = "INFO"
    docker_socket_path: str = "/var/run/docker.sock"

    @property
    def has_rsync_storage(self) -> bool:
        """Return whether all rsync credentials are available."""

        return bool(
            self.rsync_remote_host and self.rsync_remote_user and self.rsync_remote_password
        )

    @property
    def uses_local_storage(self) -> bool:
        """Return whether mounted local storage is configured."""

        return self.backup_local_storage is not None

    @property
    def has_ftp_storage(self) -> bool:
        """Return whether FTP / FTPS credentials are available."""

        return bool(self.ftp_host and self.ftp_user and self.ftp_password)

    @property
    def enabled_storage_backends(self) -> tuple[str, ...]:
        """Return configured storage backends in execution order."""

        backends: list[str] = []
        if self.uses_local_storage:
            backends.append("local")
        if self.has_rsync_storage:
            backends.append("rsync")
        if self.has_ftp_storage:
            backends.append("ftp")
        return tuple(backends)

    @property
    def storage_backend(self) -> str:
        """Return a compact backend description for logs and diagnostics."""

        backends = self.enabled_storage_backends
        return "+".join(backends) if backends else "none"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppConfig":
        """Load and validate configuration from environment variables."""

        source = os.environ if env is None else env
        errors: list[str] = []

        backup_local_storage_raw = source.get("BACKUP_LOCAL_STORAGE", "").strip()
        backup_local_storage = Path(backup_local_storage_raw) if backup_local_storage_raw else None
        if backup_local_storage is not None:
            cls._ensure_directory(backup_local_storage, errors, "BACKUP_LOCAL_STORAGE")

        rsync_remote_host = source.get("RSYNC_REMOTE_HOST", "").strip()
        rsync_remote_user = source.get("RSYNC_REMOTE_USER", "").strip()
        rsync_remote_password = source.get("RSYNC_REMOTE_PASSWORD", "").strip()
        rsync_fields = {
            "RSYNC_REMOTE_HOST": rsync_remote_host,
            "RSYNC_REMOTE_USER": rsync_remote_user,
            "RSYNC_REMOTE_PASSWORD": rsync_remote_password,
        }
        provided_rsync_fields = [name for name, value in rsync_fields.items() if value]
        if provided_rsync_fields and len(provided_rsync_fields) != len(rsync_fields):
            missing = [name for name, value in rsync_fields.items() if not value]
            errors.append(
                "RSYNC_* configuration is incomplete; missing: " + ", ".join(missing)
            )

        backup_time_raw = source.get("BACKUP_TIME", "").strip()
        backup_time = cls._parse_backup_time(backup_time_raw, errors)

        backup_retention_days_raw = source.get("BACKUP_RETENTION_DAYS", "").strip()
        backup_retention_days = cls._parse_retention_days(
            backup_retention_days_raw, errors
        )

        ftp_host = source.get("FTP_HOST", "").strip()
        ftp_user = source.get("FTP_USER", "").strip()
        ftp_password = source.get("FTP_PASSWORD", "").strip()
        ftp_remote_path_raw = source.get("FTP_REMOTE_PATH", "").strip()
        ftp_port_raw = source.get("FTP_PORT", "").strip()
        ftp_tls_raw = source.get("FTP_TLS", "").strip()
        ftp_passive_raw = source.get("FTP_PASSIVE", "").strip()
        ftp_timeout_raw = source.get("FTP_TIMEOUT", "").strip()
        ftp_credentials = {
            "FTP_HOST": ftp_host,
            "FTP_USER": ftp_user,
            "FTP_PASSWORD": ftp_password,
        }
        provided_ftp_credentials = [name for name, value in ftp_credentials.items() if value]
        if provided_ftp_credentials and len(provided_ftp_credentials) != len(ftp_credentials):
            missing = [name for name, value in ftp_credentials.items() if not value]
            errors.append(
                "FTP_* configuration is incomplete; missing: " + ", ".join(missing)
            )

        ftp_port = cls._parse_port(ftp_port_raw, errors)
        ftp_remote_path = ftp_remote_path_raw or "/backups"
        ftp_tls = cls._parse_bool(ftp_tls_raw, False, errors, "FTP_TLS")
        ftp_passive = cls._parse_bool(ftp_passive_raw, True, errors, "FTP_PASSIVE")
        ftp_timeout = cls._parse_timeout(ftp_timeout_raw, 30.0, errors)

        rsync_remote_path = source.get("RSYNC_REMOTE_PATH", "/backups").strip() or "/backups"
        local_backup_dir = Path(
            source.get("LOCAL_BACKUP_DIR", "/.temporary_storage").strip() or "/.temporary_storage"
        )
        timezone = cls._parse_timezone(source.get("TZ", "UTC").strip() or "UTC", errors)
        log_level = source.get("LOG_LEVEL", "INFO").strip() or "INFO"
        docker_socket_path = (
            source.get("DOCKER_SOCKET_PATH", "/var/run/docker.sock").strip()
            or "/var/run/docker.sock"
        )

        cls._ensure_directory(local_backup_dir, errors, "LOCAL_BACKUP_DIR")

        if backup_local_storage is not None and backup_local_storage == local_backup_dir:
            errors.append("BACKUP_LOCAL_STORAGE must differ from LOCAL_BACKUP_DIR")

        if not backup_local_storage and not (
            rsync_remote_host and rsync_remote_user and rsync_remote_password
        ) and not (ftp_host and ftp_user and ftp_password):
            errors.append(
                "At least one storage backend must be configured via BACKUP_LOCAL_STORAGE, complete RSYNC_* settings, or complete FTP_* settings"
            )

        if errors:
            raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))

        return cls(
            rsync_remote_host=rsync_remote_host,
            rsync_remote_user=rsync_remote_user,
            rsync_remote_password=rsync_remote_password,
            ftp_host=ftp_host,
            ftp_port=ftp_port,
            ftp_user=ftp_user,
            ftp_password=ftp_password,
            ftp_remote_path=ftp_remote_path,
            ftp_tls=ftp_tls,
            ftp_passive=ftp_passive,
            ftp_timeout=ftp_timeout,
            backup_time=backup_time,
            backup_retention_days=backup_retention_days,
            rsync_remote_path=rsync_remote_path,
            backup_local_storage=backup_local_storage,
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
    def _parse_port(value: str, errors: list[str]) -> int:
        if not value:
            return 21
        try:
            parsed = int(value)
        except ValueError:
            errors.append(f"FTP_PORT must be an integer, got {value!r}")
            return 21
        if not 1 <= parsed <= 65535:
            errors.append("FTP_PORT must be between 1 and 65535")
            return 21
        return parsed

    @staticmethod
    def _parse_timeout(value: str, default: float, errors: list[str]) -> float:
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            errors.append(f"FTP_TIMEOUT must be a number, got {value!r}")
            return default
        if parsed <= 0:
            errors.append("FTP_TIMEOUT must be greater than 0")
            return default
        return parsed

    @staticmethod
    def _parse_bool(value: str, default: bool, errors: list[str], label: str) -> bool:
        if not value:
            return default
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        errors.append(f"{label} must be a boolean value, got {value!r}")
        return default

    @staticmethod
    def _parse_timezone(value: str, errors: list[str]) -> ZoneInfo:
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError:
            errors.append(f"TZ must reference a valid timezone, got {value!r}")
            return ZoneInfo("UTC")

    @staticmethod
    def _ensure_directory(path: Path, errors: list[str], label: str) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"{label} {str(path)!r} is not writable: {exc}")
