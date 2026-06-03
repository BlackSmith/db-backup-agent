"""MariaDB backup provider."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

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


class MariaDBBackupProvider(DatabaseBackupProvider):
    db_type = "mariadb"

    def __init__(self, executor: CommandExecutor | None = None) -> None:
        self.executor = executor or SubprocessCommandExecutor()

    def supports(self, target: BackupTarget) -> bool:
        return target.db_type.lower() == self.db_type

    def validate(self, target: BackupTarget) -> None:
        if not self.supports(target):
            raise ValueError(f"Unsupported target database type {target.db_type!r}")
        if not target.host:
            raise ValueError("MariaDB target host is required")
        if not target.user:
            raise ValueError("MariaDB target user is required")
        if not target.password:
            raise ValueError("MariaDB target password is required")
        if target.port <= 0:
            raise ValueError("MariaDB target port must be a positive integer")
        if not target.all_databases and not target.databases:
            raise ValueError("MariaDB target must define databases or all_databases=True")

    def backup(self, target: BackupTarget, output_dir: Path) -> BackupProviderResult:
        self.validate(target)
        provider_dir = _target_output_dir(output_dir, self.db_type, target.container_name)
        provider_dir.mkdir(parents=True, exist_ok=True)

        artifacts: list[BackupArtifact] = []
        errors: list[BackupProviderError] = []

        with NamedTemporaryFile("w", delete=False, prefix="mariadb-", suffix=".cnf") as defaults_file:
            defaults_path = Path(defaults_file.name)
            defaults_file.write(
                "[client]\n"
                f"user={target.user}\n"
                f"password={target.password}\n"
                f"host={target.host}\n"
                f"port={target.port}\n"
            )

        try:
            if target.all_databases:
                output_path = provider_dir / "all-databases.sql"
                result = self._run_command(
                    [
                        "mariadb-dump",
                        f"--defaults-extra-file={defaults_path}",
                        "--all-databases",
                        "--result-file",
                        str(output_path),
                    ]
                )
                if result.returncode == 0:
                    artifacts.append(_artifact_for(target, output_path, None, "mariadb-sql"))
                else:
                    errors.append(_error_for(result, "mariadb-dump", output_path, None))
            else:
                for database in target.databases:
                    output_path = provider_dir / f"{_safe_name(database)}.sql"
                    command = [
                        "mariadb-dump",
                        f"--defaults-extra-file={defaults_path}",
                        "--result-file",
                        str(output_path),
                    ]
                    if len(target.databases) == 1:
                        command.append(database)
                    else:
                        command.extend(["--databases", *target.databases])
                        break
                    result = self._run_command(command)
                    if result.returncode == 0:
                        artifacts.append(_artifact_for(target, output_path, database, "mariadb-sql"))
                    else:
                        errors.append(_error_for(result, "mariadb-dump", output_path, database))
                if len(target.databases) > 1:
                    output_path = provider_dir / f"{_safe_name(target.container_name)}-databases.sql"
                    command = [
                        "mariadb-dump",
                        f"--defaults-extra-file={defaults_path}",
                        "--result-file",
                        str(output_path),
                        "--databases",
                        *target.databases,
                    ]
                    result = self._run_command(command)
                    if result.returncode == 0:
                        artifacts.append(
                            _artifact_for(target, output_path, None, "mariadb-sql")
                        )
                    else:
                        errors.append(_error_for(result, "mariadb-dump", output_path, None))
        finally:
            with suppress(FileNotFoundError):
                defaults_path.unlink()

        status = _result_status(artifacts, errors)
        return BackupProviderResult(
            provider=self.db_type,
            target=target,
            status=status,
            artifacts=artifacts,
            errors=errors,
        )

    def _run_command(self, command: list[str]) -> CommandResult:
        return self.executor.run(command)


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
