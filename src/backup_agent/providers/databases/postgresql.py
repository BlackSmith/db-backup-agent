"""PostgreSQL backup provider."""

from __future__ import annotations

import contextlib
import gzip
import shutil
from pathlib import Path

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget
from backup_agent.infrastructure.docker import DockerApiClient, DockerSocketError

from .base import (
    BackupProviderError,
    BackupProviderResult,
    CommandExecutor,
    CommandResult,
    DatabaseBackupProvider,
    SubprocessCommandExecutor,
    resolve_dump_method,
)


_POSTGRESQL_BINARY_FORMAT = {
    "artifact_format": "postgresql-custom",
    "dump_flag": "-Fc",
    "extension": ".dump",
}
_POSTGRESQL_SQL_GZIP_FORMAT = {
    "artifact_format": "postgresql-sql-gzip",
    "dump_flag": "-Fp",
    "extension": ".sql.gz",
}


class PostgreSQLBackupProvider(DatabaseBackupProvider):
    db_type = "postgresql"

    def __init__(
        self,
        executor: CommandExecutor | None = None,
        docker_client: DockerApiClient | None = None,
    ) -> None:
        self.executor = executor or SubprocessCommandExecutor()
        self.docker_client = docker_client

    def supports(self, target: BackupTarget) -> bool:
        return target.db_type.lower() == self.db_type

    def validate(self, target: BackupTarget) -> None:
        if not self.supports(target):
            raise ValueError(f"Unsupported target database type {target.db_type!r}")
        if not target.host:
            raise ValueError("PostgreSQL target host is required")
        if not target.user:
            raise ValueError("PostgreSQL target user is required")
        if not target.password:
            raise ValueError("PostgreSQL target password is required")
        if target.port <= 0:
            raise ValueError("PostgreSQL target port must be a positive integer")
        if not target.all_databases and not target.databases:
            raise ValueError("PostgreSQL target must define databases or all_databases=True")

    def backup(self, target: BackupTarget, output_dir: Path) -> BackupProviderResult:
        self.validate(target)
        provider_dir = _target_output_dir(output_dir, self.db_type, target.container_name)
        provider_dir.mkdir(parents=True, exist_ok=True)

        dump_method = resolve_dump_method(target.labels)
        requested_formats, format_errors = self._resolve_dump_formats(target)
        artifacts: list[BackupArtifact] = []
        errors: list[BackupProviderError] = list(format_errors)

        if format_errors:
            return BackupProviderResult(
                provider=self.db_type,
                target=target,
                status=_result_status(artifacts, errors),
                artifacts=artifacts,
                errors=errors,
            )

        if target.all_databases:
            for dump_format in requested_formats:
                artifact, command_errors = self._backup_all_databases(
                    target,
                    provider_dir,
                    dump_method,
                    dump_format,
                )
                if artifact is not None:
                    artifacts.append(artifact)
                errors.extend(command_errors)
        else:
            for database in target.databases:
                for dump_format in requested_formats:
                    if dump_format == "binary":
                        artifact, command_errors = self._backup_database_binary(
                            target,
                            database,
                            provider_dir,
                            dump_method,
                        )
                    else:
                        artifact, command_errors = self._backup_database_sql_gzip(
                            target,
                            database,
                            provider_dir,
                            dump_method,
                        )
                    if artifact is not None:
                        artifacts.append(artifact)
                    errors.extend(command_errors)

        return BackupProviderResult(
            provider=self.db_type,
            target=target,
            status=_result_status(artifacts, errors),
            artifacts=artifacts,
            errors=errors,
        )

    def _backup_database_binary(
        self,
        target: BackupTarget,
        database: str,
        provider_dir: Path,
        dump_method: str,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        output_path = provider_dir / f"{_safe_name(database)}.dump"
        remote_command = self._build_pg_dump_command(target, database, _POSTGRESQL_BINARY_FORMAT["dump_flag"])
        local_command = remote_command + ["-f", str(output_path)]
        local_env = {"PGPASSWORD": target.password or ""}
        remote_env = {"PGPASSWORD": target.password or ""}
        return self._run_with_strategy(
            target=target,
            command_name="pg_dump",
            output_path=output_path,
            database=database,
            dump_method=dump_method,
            local_command=local_command,
            local_env=local_env,
            remote_command=remote_command,
            remote_env=remote_env,
            format_name=_POSTGRESQL_BINARY_FORMAT["artifact_format"],
        )

    def _backup_database_sql_gzip(
        self,
        target: BackupTarget,
        database: str,
        provider_dir: Path,
        dump_method: str,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        final_output_path = provider_dir / f"{_safe_name(database)}.sql.gz"
        plain_output_path = final_output_path.with_suffix("")
        remote_command = self._build_pg_dump_command(target, database, _POSTGRESQL_SQL_GZIP_FORMAT["dump_flag"])
        local_command = remote_command + ["-f", str(plain_output_path)]
        local_env = {"PGPASSWORD": target.password or ""}
        remote_env = {"PGPASSWORD": target.password or ""}
        artifact, errors = self._run_with_strategy(
            target=target,
            command_name="pg_dump",
            output_path=plain_output_path,
            database=database,
            dump_method=dump_method,
            local_command=local_command,
            local_env=local_env,
            remote_command=remote_command,
            remote_env=remote_env,
            format_name="postgresql-sql",
        )
        if artifact is None:
            with contextlib.suppress(FileNotFoundError):
                plain_output_path.unlink()
            return None, errors

        try:
            _gzip_file(plain_output_path, final_output_path)
        except OSError as exc:
            errors.append(
                BackupProviderError(
                    message=f"gzip compression failed for PostgreSQL database {database!r}: {exc}",
                    output_path=final_output_path,
                    database=database,
                )
            )
            return None, errors
        finally:
            with contextlib.suppress(FileNotFoundError):
                plain_output_path.unlink()

        return _artifact_for(target, final_output_path, database, _POSTGRESQL_SQL_GZIP_FORMAT["artifact_format"]), errors

    def _backup_all_databases(
        self,
        target: BackupTarget,
        provider_dir: Path,
        dump_method: str,
        dump_format: str,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        if dump_format != "sql_gzip":
            return None, [
                BackupProviderError(
                    message=(
                        "PostgreSQL cluster-wide backups only support backup_agent.dump_format=sql_gzip; "
                        "binary custom format is not available for all_databases=True"
                    ),
                )
            ]

        final_output_path = provider_dir / "all-databases.sql.gz"
        plain_output_path = final_output_path.with_suffix("")
        remote_command = self._build_pg_dumpall_command(target)
        local_command = remote_command + ["-f", str(plain_output_path)]
        local_env = {"PGPASSWORD": target.password or ""}
        remote_env = {"PGPASSWORD": target.password or ""}
        artifact, errors = self._run_with_strategy(
            target=target,
            command_name="pg_dumpall",
            output_path=plain_output_path,
            database=None,
            dump_method=dump_method,
            local_command=local_command,
            local_env=local_env,
            remote_command=remote_command,
            remote_env=remote_env,
            format_name="postgresql-sql",
        )
        if artifact is None:
            with contextlib.suppress(FileNotFoundError):
                plain_output_path.unlink()
            return None, errors

        try:
            _gzip_file(plain_output_path, final_output_path)
        except OSError as exc:
            errors.append(
                BackupProviderError(
                    message=f"gzip compression failed for PostgreSQL all-databases backup: {exc}",
                    output_path=final_output_path,
                )
            )
            return None, errors
        finally:
            with contextlib.suppress(FileNotFoundError):
                plain_output_path.unlink()

        return _artifact_for(target, final_output_path, None, _POSTGRESQL_SQL_GZIP_FORMAT["artifact_format"]), errors

    def _build_pg_dump_command(
        self,
        target: BackupTarget,
        database: str,
        dump_flag: str,
    ) -> list[str]:
        return [
            "pg_dump",
            dump_flag,
            "-U",
            target.user or "",
            "-h",
            target.host,
            "-p",
            str(target.port),
            "-d",
            database,
        ]

    def _build_pg_dumpall_command(self, target: BackupTarget) -> list[str]:
        return [
            "pg_dumpall",
            "-U",
            target.user or "",
            "-h",
            target.host,
            "-p",
            str(target.port),
        ]

    def _resolve_dump_formats(self, target: BackupTarget) -> tuple[list[str], list[BackupProviderError]]:
        raw_value = str(target.labels.get("backup_agent.dump_format", "")).strip().lower()

        if target.all_databases:
            if not raw_value or raw_value == "sql_gzip":
                return ["sql_gzip"], []
            if raw_value in {"binary", "both"}:
                return [], [
                    BackupProviderError(
                        message=(
                            "PostgreSQL cluster-wide backups only support backup_agent.dump_format=sql_gzip; "
                            "binary custom format is not available for all_databases=True"
                        ),
                    )
                ]
            return [], [
                BackupProviderError(
                    message=(
                        f"Unsupported PostgreSQL dump format {raw_value!r}; expected binary, sql_gzip, or both"
                    ),
                )
            ]

        if not raw_value or raw_value == "both":
            return ["binary", "sql_gzip"], []
        if raw_value in {"binary", "sql_gzip"}:
            return [raw_value], []
        return [], [
            BackupProviderError(
                message=f"Unsupported PostgreSQL dump format {raw_value!r}; expected binary, sql_gzip, or both",
            )
        ]

    def _run_with_strategy(
        self,
        *,
        target: BackupTarget,
        command_name: str,
        output_path: Path,
        database: str | None,
        dump_method: str,
        local_command: list[str],
        local_env: dict[str, str],
        remote_command: list[str],
        remote_env: dict[str, str],
        format_name: str,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        errors: list[BackupProviderError] = []

        if dump_method in {"auto", "exec"}:
            remote_result, remote_error = self._run_remote_dump(
                target=target,
                command=remote_command,
                env=remote_env,
                output_path=output_path,
                database=database,
                command_name=command_name,
            )
            if remote_result is not None and remote_result.returncode == 0:
                return _artifact_for(target, output_path, database, format_name), errors
            if remote_error is not None:
                errors.append(remote_error)
            if dump_method == "exec":
                return None, errors

        local_result = self._run_local_dump(local_command, local_env)
        if local_result.returncode == 0:
            return _artifact_for(target, output_path, database, format_name), errors
        errors.append(_error_for(local_result, f"local {command_name}", output_path, database))
        return None, errors

    def _run_local_dump(self, command: list[str], env: dict[str, str]) -> CommandResult:
        return self.executor.run(command, env=env)

    def _run_remote_dump(
        self,
        *,
        target: BackupTarget,
        command: list[str],
        env: dict[str, str],
        output_path: Path,
        database: str | None,
        command_name: str,
    ) -> tuple[CommandResult | None, BackupProviderError | None]:
        if self.docker_client is None:
            return None, BackupProviderError(
                message=f"remote {command_name} failed: remote exec is unavailable",
                command=command,
                output_path=output_path,
                database=database,
            )

        temp_path = _temporary_output_path(output_path)
        stderr_chunks: list[bytes] = []
        try:
            with temp_path.open("wb") as handle:
                result = self.docker_client.exec_in_container(
                    target.container_id,
                    command,
                    env=env,
                    stdout_handler=handle.write,
                    stderr_handler=stderr_chunks.append,
                )
            if result.returncode == 0:
                temp_path.replace(output_path)
                return result, None
            return None, BackupProviderError(
                message=f"remote {command_name} failed with exit code {result.returncode}",
                command=command,
                returncode=result.returncode,
                stderr=_decode_bytes(stderr_chunks) or _decode_bytes([result.stderr]),
                output_path=output_path,
                database=database,
            )
        except DockerSocketError as exc:
            return None, BackupProviderError(
                message=f"remote {command_name} failed: {exc}",
                command=command,
                stderr=str(exc),
                output_path=output_path,
                database=database,
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                temp_path.unlink()


def _artifact_for(
    target: BackupTarget, output_path: Path, database: str | None, format_name: str
) -> BackupArtifact:
    size = output_path.stat().st_size if output_path.exists() else None
    return BackupArtifact(
        target=target,
        database=database,
        path=output_path,
        size=size,
        format=format_name,
    )


def _error_for(
    result: CommandResult,
    command_name: str,
    output_path: Path,
    database: str | None,
) -> BackupProviderError:
    return BackupProviderError(
        message=f"{command_name} failed with exit code {result.returncode}",
        command=result.command,
        returncode=result.returncode,
        stderr=result.stderr,
        output_path=output_path,
        database=database,
    )


def _result_status(artifacts: list[BackupArtifact], errors: list[BackupProviderError]) -> str:
    if artifacts and errors:
        return "partial"
    if artifacts:
        return "success"
    return "failed"


def _safe_name(value: str) -> str:
    cleaned = [char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip()]
    return "".join(cleaned).strip("-") or "database"


def _temporary_output_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.name}.tmp")


def _gzip_file(source_path: Path, output_path: Path) -> None:
    temp_output_path = _temporary_output_path(output_path)
    try:
        with source_path.open("rb") as source, gzip.open(temp_output_path, "wb") as destination:
            shutil.copyfileobj(source, destination)
        temp_output_path.replace(output_path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_output_path.unlink()


def _decode_bytes(chunks: list[bytes]) -> str:
    return b"".join(chunks).decode("utf-8", errors="replace")


def _target_output_dir(output_dir: Path, provider_name: str, container_name: str) -> Path:
    return output_dir / provider_name / _safe_name(container_name)
