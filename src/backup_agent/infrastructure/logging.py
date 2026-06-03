"""Logging configuration and structured event helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backup_agent.app.config import AppConfig


_SECRET_KEYS = {
    "password",
    "rsync_remote_password",
    "pgpassword",
    "mariadbpassword",
    "secret",
}


def configure_logging(level: str = "INFO") -> None:
    """Configure a simple console logger."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured log message with stable key=value pairs."""

    payload = {"event": event}
    for key, value in fields.items():
        payload[key] = "***" if _looks_secret(str(key)) else _sanitize_value(value)
    logger.info(_format_payload(payload))


def log_config_validation(logger: logging.Logger, config: AppConfig) -> None:
    """Log configuration validation without exposing secrets."""

    log_event(
        logger,
        "config_validated",
        rsync_remote_host=config.rsync_remote_host,
        rsync_remote_user=config.rsync_remote_user,
        backup_time=config.backup_time.strftime("%H:%M"),
        backup_retention_days=config.backup_retention_days,
        rsync_remote_path=config.rsync_remote_path,
        local_backup_dir=str(config.local_backup_dir),
        timezone=str(config.timezone),
        log_level=config.log_level,
        docker_socket_path=config.docker_socket_path,
    )


def _sanitize_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _sanitize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {
            str(key): "***" if _looks_secret(str(key)) else _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return value


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in _SECRET_KEYS)


def _format_payload(payload: dict[str, Any]) -> str:
    parts = []
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)
