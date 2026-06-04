"""Metadata resolution boundary and normalization logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backup_agent.domain.backup_target import BackupTarget


class MetadataResolutionError(ValueError):
    """Raised when container metadata cannot be normalized."""


class MetadataResolver(ABC):
    """Abstract contract for resolving container metadata into backup targets."""

    @abstractmethod
    def resolve(self, container: Mapping[str, Any]) -> BackupTarget | None:
        """Convert a raw container record into a normalized backup target."""
        raise NotImplementedError


@dataclass(slots=True)
class ContainerMetadataResolver(MetadataResolver):
    """Resolve container labels and env vars into a shared backup model."""

    def resolve(self, container: Mapping[str, Any]) -> BackupTarget | None:
        labels = _normalize_mapping(container.get("labels") or container.get("Labels") or {})
        env = _normalize_env(container.get("env") or container.get("Env") or [])

        if not _is_enabled(labels):
            return None

        container_id = _container_id(container)
        container_name = _container_name(container)

        db_type = self._resolve_database_type(labels, env, container_id, container_name)
        if db_type == "postgresql":
            return self._resolve_postgresql(container_id, container_name, labels, env)
        if db_type == "mariadb":
            return self._resolve_mariadb(container_id, container_name, labels, env)

        raise MetadataResolutionError(
            f"Container {container_name!r} ({container_id}) uses unsupported backup_agent.type {db_type!r}."
        )

    def _resolve_database_type(
        self,
        labels: Mapping[str, str],
        env: Mapping[str, str],
        container_id: str,
        container_name: str,
    ) -> str:
        explicit_type = _first_non_empty(
            labels.get("backup_agent.type"),
            env.get("BACKUP_AGENT_TYPE"),
        )
        if explicit_type:
            normalized = explicit_type.strip().lower()
            if normalized in {"postgresql", "postgres", "pg"}:
                return "postgresql"
            if normalized in {"mariadb", "mysql"}:
                return "mariadb"
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has unsupported backup_agent.type {explicit_type!r}."
            )

        postgres_signal = _has_any(
            labels,
            env,
            [
                "backup_agent.pguser",
                "backup_agent.pghost",
                "backup_agent.pgpassword",
                "backup_agent.pgport",
                "backup_agent.pgdatabase",
                "POSTGRES_USER",
                "POSTGRES_HOST",
                "POSTGRES_PASSWORD",
                "POSTGRES_PORT",
                "POSTGRES_DB",
                "POSTGRES_DATABASE",
            ],
        )
        mariadb_signal = _has_any(
            labels,
            env,
            [
                "backup_agent.mariadbuser",
                "backup_agent.mariadbpassword",
                "backup_agent.mariadbhost",
                "backup_agent.mariadbport",
                "backup_agent.mariadbdatabase",
                "MARIADB_USER",
                "MARIADB_PASSWORD",
                "MARIADB_ROOT_PASSWORD",
                "MARIADB_HOST",
                "MARIADB_PORT",
                "MARIADB_DATABASE",
                "MYSQL_USER",
                "MYSQL_PASSWORD",
                "MYSQL_ROOT_PASSWORD",
                "MYSQL_HOST",
                "MYSQL_PORT",
                "MYSQL_DATABASE",
            ],
        )

        if postgres_signal and mariadb_signal:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) contains both PostgreSQL and MariaDB metadata; set backup_agent.type explicitly."
            )
        if postgres_signal:
            return "postgresql"
        if mariadb_signal:
            return "mariadb"

        raise MetadataResolutionError(
            f"Container {container_name!r} ({container_id}) does not declare enough metadata to infer a database type; set backup_agent.type explicitly."
        )

    def _resolve_postgresql(
        self,
        container_id: str,
        container_name: str,
        labels: Mapping[str, str],
        env: Mapping[str, str],
    ) -> BackupTarget:
        user = _select_value(labels, env, ["backup_agent.user", "backup_agent.pguser"], ["POSTGRES_USER"])
        host = _select_value(labels, env, ["backup_agent.host", "backup_agent.pghost"], ["POSTGRES_HOST"])
        port_value = _select_value(labels, env, ["backup_agent.port", "backup_agent.pgport"], ["POSTGRES_PORT"])
        password_value = _select_value(
            labels,
            env,
            ["backup_agent.password", "backup_agent.pgpassword"],
            ["POSTGRES_PASSWORD"],
        )
        password_ref = _select_source(
            labels,
            env,
            ["backup_agent.password", "backup_agent.pgpassword"],
            ["POSTGRES_PASSWORD"],
        )
        database_value = _select_value(
            labels,
            env,
            ["backup_agent.database", "backup_agent.pgdatabase"],
            ["POSTGRES_DB", "POSTGRES_DATABASE"],
        )
        databases = parse_database_list(database_value[0] if database_value else None)
        return self._build_target(
            container_id=container_id,
            container_name=container_name,
            db_type="postgresql",
            labels=labels,
            user=user,
            host=host,
            port_value=port_value,
            default_port=5432,
            password_value=password_value,
            password_ref=password_ref,
            databases=databases,
        )

    def _resolve_mariadb(
        self,
        container_id: str,
        container_name: str,
        labels: Mapping[str, str],
        env: Mapping[str, str],
    ) -> BackupTarget:
        user = _select_value(
            labels,
            env,
            ["backup_agent.user", "backup_agent.mariadbuser"],
            ["MARIADB_USER", "MYSQL_USER"],
        )
        host = _select_value(
            labels,
            env,
            ["backup_agent.host", "backup_agent.mariadbhost"],
            ["MARIADB_HOST", "MYSQL_HOST"],
        )
        port_value = _select_value(
            labels,
            env,
            ["backup_agent.port", "backup_agent.mariadbport"],
            ["MARIADB_PORT", "MYSQL_PORT"],
        )
        password_value = _select_value(
            labels,
            env,
            ["backup_agent.password", "backup_agent.mariadbpassword"],
            ["MARIADB_PASSWORD", "MARIADB_ROOT_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"],
        )
        password_ref = _select_source(
            labels,
            env,
            ["backup_agent.password", "backup_agent.mariadbpassword"],
            ["MARIADB_PASSWORD", "MARIADB_ROOT_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"],
        )
        database_value = _select_value(
            labels,
            env,
            ["backup_agent.database", "backup_agent.mariadbdatabase"],
            ["MARIADB_DATABASE", "MYSQL_DATABASE"],
        )
        databases = parse_database_list(database_value[0] if database_value else None)
        return self._build_target(
            container_id=container_id,
            container_name=container_name,
            db_type="mariadb",
            labels=labels,
            user=user,
            host=host,
            port_value=port_value,
            default_port=3306,
            password_value=password_value,
            password_ref=password_ref,
            databases=databases,
        )

    def _build_target(
        self,
        *,
        container_id: str,
        container_name: str,
        db_type: str,
        labels: Mapping[str, str],
        user: tuple[str, str] | None,
        host: tuple[str, str] | None,
        port_value: tuple[str, str] | None,
        default_port: int | None,
        password_value: tuple[str, str] | None,
        password_ref: tuple[str, str] | None,
        databases: list[str],
    ) -> BackupTarget:
        missing: list[str] = []
        resolved_user = _require_value(user, "user", container_name, container_id, missing)
        resolved_host = _require_value(host, "host", container_name, container_id, missing)
        resolved_password = _require_value(
            password_value, "password", container_name, container_id, missing
        )
        resolved_password_ref = _require_source(
            password_ref, "password", container_name, container_id, missing
        )

        if port_value is None:
            if default_port is None:
                missing.append("missing port")
                resolved_port = 0
            else:
                resolved_port = default_port
        else:
            resolved_port = _parse_port(
                _require_value(port_value, "port", container_name, container_id, missing),
                container_name,
                container_id,
                missing,
            )
        if missing:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has invalid metadata: "
                + "; ".join(missing)
            )

        return BackupTarget(
            container_id=container_id,
            container_name=container_name,
            db_type=db_type,
            host=resolved_host,
            port=resolved_port,
            user=resolved_user,
            password=resolved_password,
            password_ref=resolved_password_ref,
            databases=databases,
            all_databases=not databases,
            labels=dict(labels),
        )


def parse_database_list(value: str | None) -> list[str]:
    """Parse a comma-separated database list.

    Empty or missing values mean the caller should back up all databases.
    """

    if value is None:
        return []
    databases = [part.strip() for part in value.split(",")]
    return [database for database in databases if database]


def _is_enabled(labels: Mapping[str, str]) -> bool:
    return str(labels.get("backup_agent.enabled", "")).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_mapping(values: Mapping[str, Any] | Any) -> dict[str, str]:
    if isinstance(values, Mapping):
        return {str(key): str(value).strip() for key, value in values.items()}
    return {}


def _normalize_env(values: Any) -> dict[str, str]:
    if isinstance(values, Mapping):
        return {str(key): str(value).strip() for key, value in values.items()}

    env_map: dict[str, str] = {}
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, value = item.split("=", 1)
            env_map[key.strip()] = value.strip()
    return env_map


def _has_any(labels: Mapping[str, str], env: Mapping[str, str], keys: list[str]) -> bool:
    return any(_first_non_empty(labels.get(key), env.get(key)) for key in keys)


def _select_value(
    labels: Mapping[str, str], env: Mapping[str, str], label_keys: list[str], env_keys: list[str]
) -> tuple[str, str] | None:
    source = _select_source(labels, env, label_keys, env_keys)
    if source is None:
        return None
    return source


def _select_source(
    labels: Mapping[str, str], env: Mapping[str, str], label_keys: list[str], env_keys: list[str]
) -> tuple[str, str] | None:
    for label_key in label_keys:
        value = labels.get(label_key, "").strip()
        if value:
            return value, f"label:{label_key}"
    for env_key in env_keys:
        value = env.get(env_key, "").strip()
        if value:
            return value, f"env:{env_key}"
    return None


def _require_value(
    source: tuple[str, str] | None,
    field_name: str,
    container_name: str,
    container_id: str,
    missing: list[str],
) -> str:
    if source is None:
        missing.append(f"missing {field_name}")
        return ""
    return source[0]


def _require_source(
    source: tuple[str, str] | None,
    field_name: str,
    container_name: str,
    container_id: str,
    missing: list[str],
) -> str:
    if source is None:
        missing.append(f"missing {field_name}")
        return ""
    return source[1]


def _parse_port(
    value: str,
    container_name: str,
    container_id: str,
    missing: list[str],
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        missing.append(f"invalid port {value!r}")
        return 0


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _container_id(container: Mapping[str, Any]) -> str:
    return str(container.get("id") or container.get("Id") or "").strip()


def _container_name(container: Mapping[str, Any]) -> str:
    name = str(container.get("name") or container.get("Name") or "").strip()
    return name.lstrip("/")
