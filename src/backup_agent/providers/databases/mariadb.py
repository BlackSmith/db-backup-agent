"""MariaDB backup provider."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

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


logger = logging.getLogger(__name__)


class MariaDBBackupProvider(DatabaseBackupProvider):
    db_type = "mariadb"

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

        dump_method = resolve_dump_method(target.labels)
        artifacts: list[BackupArtifact] = []
        errors: list[BackupProviderError] = []

        logger.debug(
            "mariadb backup start container=%s databases=%s all_databases=%s dump_method=%s output_dir=%s",
            target.container_name,
            target.databases,
            target.all_databases,
            dump_method,
            provider_dir,
        )

        with NamedTemporaryFile("w", delete=False, prefix="mariadb-", suffix="cnf") as defaults_file:
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
                logger.debug(
                    "mariadb all-databases backup container=%s output_path=%s",
                    target.container_name,
                    output_path,
                )
                artifact, command_errors = self._backup_all_databases(
                    target,
                    output_path,
                    dump_method,
                    defaults_path,
                )
                if artifact is not None:
                    artifacts.append(artifact)
                errors.extend(command_errors)
            else:
                logger.debug(
                    "mariadb database backup container=%s databases=%s",
                    target.container_name,
                    target.databases,
                )
                artifact, command_errors = self._backup_databases(
                    target,
                    provider_dir,
                    dump_method,
                    defaults_path,
                )
                if artifact is not None:
                    artifacts.append(artifact)
                errors.extend(command_errors)
        finally:
            with contextlib.suppress(FileNotFoundError):
                defaults_path.unlink()

        logger.debug(
            "mariadb backup finish container=%s status=%s artifacts=%s errors=%s",
            target.container_name,
            _result_status(artifacts, errors),
            [artifact.path.name for artifact in artifacts],
            [error.message for error in errors],
        )
        return BackupProviderResult(
            provider=self.db_type,
            target=target,
            status=_result_status(artifacts, errors),
            artifacts=artifacts,
            errors=errors,
        )

    def _backup_databases(
        self,
        target: BackupTarget,
        provider_dir: Path,
        dump_method: str,
        defaults_path: Path,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        if len(target.databases) == 1:
            database = target.databases[0]
            output_path = provider_dir / f"{_safe_name(database)}.sql"
            local_command = [
                "mariadb-dump",
                f"--defaults-extra-file={defaults_path}",
                "--result-file",
                str(output_path),
                database,
            ]
            remote_command = [
                "mariadb-dump",
                "--user",
                target.user or "",
                "--host",
                target.host,
                "--port",
                str(target.port),
                database,
            ]
            logger.debug(
                "mariadb single-database command container=%s database=%s local_command=%s remote_command=%s",
                target.container_name,
                database,
                " ".join(local_command),
                " ".join(remote_command),
            )
            return self._backup_with_strategy(
                target=target,
                output_path=output_path,
                database=database,
                dump_method=dump_method,
                local_command=local_command,
                remote_command=remote_command,
                local_env={},
                remote_env={"MYSQL_PWD": target.password or ""},
                format_name="mariadb-sql",
            )

        output_path = provider_dir / f"{_safe_name(target.container_name)}-databases.sql"
        local_command = [
            "mariadb-dump",
            f"--defaults-extra-file={defaults_path}",
            "--result-file",
            str(output_path),
            "--databases",
            *target.databases,
        ]
        remote_command = [
            "mariadb-dump",
            "--user",
            target.user or "",
            "--host",
            target.host,
            "--port",
            str(target.port),
            "--databases",
            *target.databases,
        ]
        logger.debug(
            "mariadb multi-database command container=%s databases=%s local_command=%s remote_command=%s",
            target.container_name,
            target.databases,
            " ".join(local_command),
            " ".join(remote_command),
        )
        return self._backup_with_strategy(
            target=target,
            output_path=output_path,
            database=None,
            dump_method=dump_method,
            local_command=local_command,
            remote_command=remote_command,
            local_env={},
            remote_env={"MYSQL_PWD": target.password or ""},
            format_name="mariadb-sql",
        )

    def _backup_all_databases(
        self,
        target: BackupTarget,
        output_path: Path,
        dump_method: str,
        defaults_path: Path,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        local_command = [
            "mariadb-dump",
            f"--defaults-extra-file={defaults_path}",
            "--all-databases",
            "--result-file",
            str(output_path),
        ]
        remote_command = [
            "mariadb-dump",
            "--user",
            target.user or "",
            "--host",
            target.host,
            "--port",
            str(target.port),
            "--all-databases",
        ]
        logger.debug(
            "mariadb all-databases command container=%s local_command=%s remote_command=%s",
            target.container_name,
            " ".join(local_command),
            " ".join(remote_command),
        )
        return self._backup_with_strategy(
            target=target,
            output_path=output_path,
            database=None,
            dump_method=dump_method,
            local_command=local_command,
            remote_command=remote_command,
            local_env={},
            remote_env={"MYSQL_PWD": target.password or ""},
            format_name="mariadb-sql",
        )

    def _backup_with_strategy(
        self,
        *,
        target: BackupTarget,
        output_path: Path,
        database: str | None,
        dump_method: str,
        local_command: list[str],
        remote_command: list[str],
        local_env: dict[str, str],
        remote_env: dict[str, str],
        format_name: str,
    ) -> tuple[BackupArtifact | None, list[BackupProviderError]]:
        errors: list[BackupProviderError] = []

        if dump_method in {"auto", "exec"}:
            logger.debug(
                "mariadb remote execution attempt command=%s database=%s",
                " ".join(remote_command),
                database,
            )
            remote_result, remote_error = self._run_remote_dump(
                target=target,
                command=remote_command,
                env=remote_env,
                output_path=output_path,
                database=database,
                command_name=remote_command[0],
            )
            if remote_result is not None and remote_result.returncode == 0:
                logger.debug(
                    "mariadb remote execution succeeded command=%s database=%s returncode=%s",
                    remote_command[0],
                    database,
                    remote_result.returncode,
                )
                return _artifact_for(target, output_path, database, format_name), errors
            if remote_error is not None:
                errors.append(remote_error)
            if dump_method == "exec":
                logger.debug(
                    "mariadb remote execution required but failed command=%s database=%s",
                    remote_command[0],
                    database,
                )
                return None, errors

        logger.debug(
            "mariadb local execution attempt command=%s database=%s",
            " ".join(local_command),
            database,
        )
        local_result = self._run_local_dump(local_command, local_env)
        if local_result.returncode == 0:
            logger.debug(
                "mariadb local execution succeeded command=%s database=%s returncode=%s",
                local_command[0],
                database,
                local_result.returncode,
            )
            return _artifact_for(target, output_path, database, format_name), errors
        logger.debug(
            "mariadb local execution failed command=%s database=%s returncode=%s stderr=%s",
            local_command[0],
            database,
            local_result.returncode,
            local_result.stderr,
        )
        errors.append(_error_for(local_result, f"local {local_command[0]}", output_path, database))
        return None, errors

    def _run_local_dump(self, command: list[str], env: dict[str, str]) -> CommandResult:
        logger.debug("mariadb local dump command=%s env_keys=%s", " ".join(command), sorted(env))
        result = self.executor.run(command, env=env)
        logger.debug(
            "mariadb local dump finished command=%s returncode=%s stdout=%s stderr=%s",
            " ".join(command),
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return result

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
            logger.debug(
                "mariadb remote dump unavailable command=%s database=%s",
                " ".join(command),
                database,
            )
            return None, BackupProviderError(
                message=f"remote {command_name} failed: remote exec is unavailable",
                command=command,
                output_path=output_path,
                database=database,
            )

        temp_path = _temporary_output_path(output_path)
        stderr_chunks: list[bytes] = []
        logger.debug(
            "mariadb remote exec starting container_id=%s command=%s output_path=%s",
            target.container_id,
            " ".join(command),
            output_path,
        )
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
                logger.debug(
                    "mariadb remote exec succeeded container_id=%s command=%s returncode=%s",
                    target.container_id,
                    command_name,
                    result.returncode,
                )
                return result, None
            decoded_stderr = _decode_bytes(stderr_chunks) or _decode_bytes([result.stderr])
            logger.debug(
                "mariadb remote exec failed container_id=%s command=%s returncode=%s stderr=%s",
                target.container_id,
                command_name,
                result.returncode,
                decoded_stderr,
            )
            return None, BackupProviderError(
                message=f"remote {command_name} failed with exit code {result.returncode}",
                command=command,
                returncode=result.returncode,
                stderr=decoded_stderr,
                output_path=output_path,
                database=database,
            )
        except DockerSocketError as exc:
            logger.debug(
                "mariadb remote exec socket error container_id=%s command=%s error=%s",
                target.container_id,
                command_name,
                exc,
            )
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


def _decode_bytes(chunks: list[bytes]) -> str:
    return b"".join(chunks).decode("utf-8", errors="replace")


def _target_output_dir(output_dir: Path, provider_name: str, container_name: str) -> Path:
    return output_dir / provider_name / _safe_name(container_name)
