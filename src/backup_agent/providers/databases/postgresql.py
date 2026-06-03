"""PostgreSQL backup provider."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget

from .base import (
    BackupProviderError,
    BackupProviderResult,
    CommandExecutor,
    CommandResult,
    DatabaseBackupProvider,
    SubprocessCommandExecutor,
)


class PostgreSQLBackupProvider(DatabaseBackupProvider):
    db_type = "postgresql"

    def __init__(self, executor: CommandExecutor | None = None) -> None:
        self.executor = executor or SubprocessCommandExecutor()

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

        artifacts: list[BackupArtifact] = []
        errors: list[BackupProviderError] = []

        if target.all_databases:
            output_path = provider_dir / "all-databases.sql"
            result = self._run_command(
                [
                    "pg_dumpall",
                    "-U",
                    target.user or "",
                    "-h",
                    target.host,
                    "-p",
                    str(target.port),
                    "-f",
                    str(output_path),
                ],
                target.password or "",
            )
            if result.returncode == 0:
                artifacts.append(_artifact_for(target, output_path, None, "postgresql-sql"))
            else:
                errors.append(_error_for(result, "pg_dumpall", output_path, None))
        else:
            for database in target.databases:
                output_path = provider_dir / f"{_safe_name(database)}.dump"
                result = self._run_command(
                    [
                        "pg_dump",
                        "-Fc",
                        "-U",
                        target.user or "",
                        "-h",
                        target.host,
                        "-p",
                        str(target.port),
                        "-d",
                        database,
                        "-f",
                        str(output_path),
                    ],
                    target.password or "",
                )
                if result.returncode == 0:
                    artifacts.append(
                        _artifact_for(target, output_path, database, "postgresql-custom")
                    )
                else:
                    errors.append(_error_for(result, "pg_dump", output_path, database))

        status = _result_status(artifacts, errors)
        return BackupProviderResult(
            provider=self.db_type,
            target=target,
            status=status,
            artifacts=artifacts,
            errors=errors,
        )

    def _run_command(self, command: list[str], password: str) -> CommandResult:
        env = {"PGPASSWORD": password}
        return self.executor.run(command, env=env)


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


def _target_output_dir(output_dir: Path, provider_name: str, container_name: str) -> Path:
    return output_dir / provider_name / _safe_name(container_name)
