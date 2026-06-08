"""Tests for database backup providers."""

from __future__ import annotations

import gzip
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from backup_agent.domain.backup_target import BackupTarget
from backup_agent.providers.databases import FilesystemArchiveBackupProvider, MariaDBBackupProvider, PostgreSQLBackupProvider


class FakeExecutor:
    def __init__(self, results: list[tuple[int, str, str]] | None = None) -> None:
        self.results = results or []
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def run(self, command, *, env=None, cwd=None):
        from backup_agent.providers.databases.base import CommandResult

        self.commands.append(list(command))
        self.envs.append(dict(env) if env is not None else None)
        index = len(self.commands) - 1
        if index < len(self.results):
            returncode, stdout, stderr = self.results[index]
        else:
            returncode, stdout, stderr = (0, "", "")
        if returncode == 0:
            self._write_output_file(command)
        return CommandResult(command=list(command), returncode=returncode, stdout=stdout, stderr=stderr)

    def _write_output_file(self, command: list[str]) -> None:
        output_path = None
        if "-f" in command:
            index = command.index("-f")
            if index + 1 < len(command):
                output_path = Path(command[index + 1])
        elif "--result-file" in command:
            index = command.index("--result-file")
            if index + 1 < len(command):
                output_path = Path(command[index + 1])

        if output_path is None:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = "backup\n"
        output_path.write_text(content, encoding="utf-8")


class FakeDockerExecResult:
    def __init__(self, command: list[str], returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.exec_id = "exec-123"


class FakeDockerClient:
    def __init__(self, results: list[FakeDockerExecResult] | None = None, archives: dict[str, bytes] | None = None) -> None:
        self.results = results or []
        self.archives = archives or {}
        self.calls: list[dict[str, object]] = []
        self.archive_calls: list[dict[str, object]] = []

    def exec_in_container(self, container_id, command, *, env=None, user=None, workdir=None, tty=False, stdout_handler=None, stderr_handler=None):
        self.calls.append({"container_id": container_id, "command": list(command), "env": dict(env or {})})
        index = len(self.calls) - 1
        result = self.results[index] if index < len(self.results) else FakeDockerExecResult(list(command))
        if stdout_handler is not None and result.stdout:
            stdout_handler(result.stdout)
        if stderr_handler is not None and result.stderr:
            stderr_handler(result.stderr)
        return result

    def get_archive(self, container_id: str, path: str) -> bytes:
        self.archive_calls.append({"container_id": container_id, "path": path})
        key = f"{container_id}:{path}"
        if key not in self.archives:
            from backup_agent.infrastructure.docker import DockerSocketError

            raise DockerSocketError(f"missing archive for {key}")
        return self.archives[key]


class DatabaseBackupProviderTests(unittest.TestCase):
    def _postgres_target(self, **overrides) -> BackupTarget:
        data = dict(
            container_id="abc123",
            container_name="postgres-app",
            db_type="postgresql",
            host="postgres",
            port=5432,
            user="app",
            password="secret",
            password_ref="env:POSTGRES_PASSWORD",
            databases=["db1"],
            all_databases=False,
            labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local"},
        )
        data.update(overrides)
        return BackupTarget(**data)

    def _mariadb_target(self, **overrides) -> BackupTarget:
        data = dict(
            container_id="def456",
            container_name="mariadb-app",
            db_type="mariadb",
            host="mariadb",
            port=3306,
            user="root",
            password="secret",
            password_ref="env:MARIADB_PASSWORD",
            databases=["appdb"],
            all_databases=False,
            labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local"},
        )
        data.update(overrides)
        return BackupTarget(**data)

    def _filesystem_target(self, **overrides) -> BackupTarget:
        data = dict(
            container_id="fs123",
            container_name="files-app",
            db_type="filesystem",
            host="files-app",
            port=0,
            user=None,
            password=None,
            password_ref=None,
            databases=[],
            directories=["/app/data", "/var/lib/app/uploads"],
            all_databases=False,
            labels={"backup_agent.enabled": "true", "backup_agent.type": "filesystem", "backup_agent.directories": "/app/data,/var/lib/app/uploads"},
        )
        data.update(overrides)
        return BackupTarget(**data)

    def _build_tar_archive(self, entries: dict[str, bytes]) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, content in entries.items():
                data = content if isinstance(content, bytes) else bytes(content)
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def test_postgresql_single_database_defaults_to_both_formats(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.artifacts), 2)
        self.assertEqual([artifact.format for artifact in result.artifacts], ["postgresql-custom", "postgresql-sql-gzip"])
        self.assertEqual([artifact.path.name for artifact in result.artifacts], ["db1.dump", "db1.sql.gz"])
        self.assertEqual([command[0] for command in executor.commands], ["pg_dump", "pg_dump"])
        self.assertIn("-Fc", executor.commands[0])
        self.assertIn("-Fp", executor.commands[1])
        self.assertEqual(executor.envs[0]["PGPASSWORD"], "secret")

    def test_postgresql_single_database_can_limit_to_binary_format(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "binary"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].format, "postgresql-custom")
        self.assertEqual(result.artifacts[0].path.name, "db1.dump")
        self.assertEqual(len(executor.commands), 1)
        self.assertIn("-Fc", executor.commands[0])

    def test_postgresql_single_database_can_limit_to_sql_gzip_format(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "sql_gzip"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))
            self.assertEqual(result.status, "success")
            self.assertEqual(len(result.artifacts), 1)
            self.assertEqual(result.artifacts[0].format, "postgresql-sql-gzip")
            self.assertEqual(result.artifacts[0].path.name, "db1.sql.gz")
            self.assertEqual(len(executor.commands), 1)
            self.assertIn("-Fp", executor.commands[0])
            with gzip.open(result.artifacts[0].path, "rt", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "backup\n")

    def test_postgresql_all_databases_uses_pg_dumpall_and_sql_gzip(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(databases=[], all_databases=True, labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "sql_gzip"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(executor.commands[0][0], "pg_dumpall")
        self.assertEqual(result.artifacts[0].format, "postgresql-sql-gzip")
        self.assertEqual(result.artifacts[0].path.name, "all-databases.sql.gz")

    def test_postgresql_all_databases_rejects_binary_format(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(databases=[], all_databases=True, labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "binary"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.artifacts)
        self.assertTrue(result.errors)
        self.assertIn("all_databases=True", result.errors[0].message)

    def test_postgresql_multiple_databases_runs_one_command_per_database(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(databases=["db1", "db2"], labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "binary"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual([command[0] for command in executor.commands], ["pg_dump", "pg_dump"])
        self.assertEqual([artifact.database for artifact in result.artifacts], ["db1", "db2"])
        self.assertEqual([artifact.path.name for artifact in result.artifacts], ["db1.dump", "db2.dump"])

    def test_postgresql_remote_exec_with_local_fallback_succeeds(self) -> None:
        docker_client = FakeDockerClient([
            FakeDockerExecResult(["pg_dump", "-Fc"], returncode=1, stdout=b"", stderr=b"remote boom")
        ])
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor, docker_client=docker_client)
        target = self._postgres_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "auto", "backup_agent.dump_format": "binary"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "partial")
        self.assertEqual(len(docker_client.calls), 1)
        self.assertEqual(len(executor.commands), 1)
        self.assertEqual(executor.commands[0][0], "pg_dump")
        self.assertTrue(result.artifacts)
        self.assertTrue(result.errors)
        self.assertIn("remote pg_dump failed", result.errors[0].message)

    def test_mariadb_single_database_uses_defaults_file_and_result_file(self) -> None:
        executor = FakeExecutor()
        provider = MariaDBBackupProvider(executor)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(self._mariadb_target(), Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(executor.commands[0][0], "mariadb-dump")
        self.assertTrue(any(part.startswith("--defaults-extra-file=") for part in executor.commands[0]))
        self.assertIn("--result-file", executor.commands[0])
        self.assertEqual(result.artifacts[0].database, "appdb")

    def test_mariadb_all_databases_uses_all_databases_mode(self) -> None:
        executor = FakeExecutor()
        provider = MariaDBBackupProvider(executor)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(
                self._mariadb_target(databases=[], all_databases=True), Path(temp_dir)
            )

        self.assertEqual(result.status, "success")
        self.assertIn("--all-databases", executor.commands[0])
        self.assertEqual(result.artifacts[0].format, "mariadb-sql")

    def test_mariadb_multiple_databases_runs_single_dump_command(self) -> None:
        executor = FakeExecutor()
        provider = MariaDBBackupProvider(executor)
        target = self._mariadb_target(databases=["db1", "db2"])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(executor.commands), 1)
        self.assertIn("--databases", executor.commands[0])
        self.assertIn("db1", executor.commands[0])
        self.assertIn("db2", executor.commands[0])
        self.assertEqual(result.artifacts[0].database, None)

    def test_mariadb_remote_exec_with_local_fallback_succeeds(self) -> None:
        docker_client = FakeDockerClient([
            FakeDockerExecResult(["mariadb-dump"], returncode=1, stdout=b"", stderr=b"remote boom")
        ])
        executor = FakeExecutor()
        provider = MariaDBBackupProvider(executor, docker_client=docker_client)
        target = self._mariadb_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "auto"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "partial")
        self.assertEqual(len(docker_client.calls), 1)
        self.assertEqual(len(executor.commands), 1)
        self.assertEqual(executor.commands[0][0], "mariadb-dump")
        self.assertTrue(result.artifacts)
        self.assertTrue(result.errors)
        self.assertIn("remote mariadb-dump failed", result.errors[0].message)

    def test_filesystem_provider_archives_selected_directories(self) -> None:
        docker_client = FakeDockerClient(
            archives={
                "fs123:/app/data": self._build_tar_archive({"data/file.txt": b"alpha"}),
                "fs123:/var/lib/app/uploads": self._build_tar_archive({"uploads/image.png": b"beta"}),
            }
        )
        provider = FilesystemArchiveBackupProvider(docker_client=docker_client)
        target = self._filesystem_target()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))
            self.assertEqual(result.status, "success")
            self.assertEqual(len(result.artifacts), 1)
            artifact = result.artifacts[0]
            self.assertEqual(artifact.format, "filesystem-tar-gzip")
            self.assertTrue(artifact.path.exists())
            self.assertEqual(len(docker_client.archive_calls), 2)
            with tarfile.open(artifact.path, mode="r:gz") as archive:
                names = sorted({member.name for member in archive.getmembers() if member.isfile()})
            self.assertEqual(names, ["data/file.txt", "uploads/image.png"])

    def test_failed_command_is_reported_in_result(self) -> None:
        executor = FakeExecutor([(1, "", "boom"), (1, "", "boom")])
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(labels={"backup_agent.enabled": "true", "backup_agent.dump_method": "local", "backup_agent.dump_format": "binary"})
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.artifacts)
        self.assertTrue(result.errors)
        self.assertIn("boom", result.errors[0].stderr)


if __name__ == "__main__":
    unittest.main()
