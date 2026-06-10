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

        requested_types = self._resolve_requested_types(labels, container_id, container_name)
        directories = parse_directory_list(labels.get("backup_agent.directories"))
        database_types = [requested_type for requested_type in requested_types if requested_type in {"postgresql", "mariadb"}]
        filesystem_requested = "filesystem" in requested_types

        if len(database_types) > 1:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has conflicting backup_agent.type values {requested_types!r}."
            )
        if filesystem_requested and not directories:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has invalid metadata: missing directories"
            )
        if directories and not filesystem_requested:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has invalid metadata: backup_agent.directories requires backup_agent.type to include filesystem"
            )

        if database_types:
            db_type = database_types[0]
            if db_type == "postgresql":
                return self._resolve_postgresql(
                    container_id,
                    container_name,
                    labels,
                    env,
                    directories=directories if filesystem_requested else [],
                )
            return self._resolve_mariadb(
                container_id,
                container_name,
                labels,
                env,
                directories=directories if filesystem_requested else [],
            )

        return self._resolve_filesystem(container_id, container_name, labels, directories)

    def _resolve_requested_types(
        self,
        labels: Mapping[str, str],
        container_id: str,
        container_name: str,
    ) -> list[str]:
        raw_type = labels.get("backup_agent.type")
        if raw_type is None or not raw_type.strip():
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) is missing required backup_agent.type label."
            )

        requested_types: list[str] = []
        for raw_value in raw_type.split(","):
            value = raw_value.strip().lower()
            if not value:
                continue
            normalized = _normalize_backup_type(value)
            if normalized is None:
                raise MetadataResolutionError(
                    f"Container {container_name!r} ({container_id}) has unsupported backup_agent.type value {raw_value.strip()!r}."
                )
            if normalized not in requested_types:
                requested_types.append(normalized)

        if not requested_types:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) is missing required backup_agent.type label."
            )

        return requested_types

    def _resolve_postgresql(
        self,
        container_id: str,
        container_name: str,
        labels: Mapping[str, str],
        env: Mapping[str, str],
        *,
        directories: list[str],
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
            directories=directories,
        )

    def _resolve_mariadb(
        self,
        container_id: str,
        container_name: str,
        labels: Mapping[str, str],
        env: Mapping[str, str],
        *,
        directories: list[str],
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
            directories=directories,
        )

    def _resolve_filesystem(
        self,
        container_id: str,
        container_name: str,
        labels: Mapping[str, str],
        directories: list[str],
    ) -> BackupTarget:
        if not directories:
            raise MetadataResolutionError(
                f"Container {container_name!r} ({container_id}) has invalid metadata: missing directories"
            )
        return BackupTarget(
            container_id=container_id,
            container_name=container_name,
            db_type="filesystem",
            host=container_name,
            port=0,
            directories=directories,
            labels=dict(labels),
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
        directories: list[str],
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
            directories=directories,
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


def parse_directory_list(value: str | None) -> list[str]:
    """Parse a comma-separated directory list."""

    if value is None:
        return []
    directories = [part.strip() for part in value.split(",")]
    return [directory for directory in directories if directory]


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


def _normalize_backup_type(value: str) -> str | None:
    if value in {"postgresql", "postgres", "pg"}:
        return "postgresql"
    if value in {"mariadb", "mysql"}:
        return "mariadb"
    if value in {"filesystem", "files", "directories", "archive"}:
        return "filesystem"
    return None


def _container_id(container: Mapping[str, Any]) -> str:
    return str(container.get("id") or container.get("Id") or "").strip()


def _container_name(container: Mapping[str, Any]) -> str:
    name = str(container.get("name") or container.get("Name") or "").strip()
    return name.lstrip("/")
