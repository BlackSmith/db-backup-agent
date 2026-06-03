"""Tests for database backup providers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backup_agent.domain.backup_target import BackupTarget
from backup_agent.providers.databases import MariaDBBackupProvider, PostgreSQLBackupProvider


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
        return CommandResult(command=list(command), returncode=returncode, stdout=stdout, stderr=stderr)


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
            labels={"backup_agent.enabled": "true"},
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
            labels={"backup_agent.enabled": "true"},
        )
        data.update(overrides)
        return BackupTarget(**data)

    def test_postgresql_single_database_creates_dump_artifact(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(self._postgres_target(), Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].database, "db1")
        self.assertTrue(result.artifacts[0].path.name.endswith(".dump"))
        self.assertEqual(executor.commands[0][0], "pg_dump")
        self.assertIn("-Fc", executor.commands[0])
        self.assertEqual(executor.envs[0]["PGPASSWORD"], "secret")

    def test_postgresql_all_databases_uses_pg_dumpall(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(
                self._postgres_target(databases=[], all_databases=True), Path(temp_dir)
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(executor.commands[0][0], "pg_dumpall")
        self.assertEqual(executor.commands[0][0], "pg_dumpall")
        self.assertEqual(result.artifacts[0].format, "postgresql-sql")
        self.assertIsNone(result.artifacts[0].database)

    def test_postgresql_multiple_databases_runs_one_command_per_database(self) -> None:
        executor = FakeExecutor()
        provider = PostgreSQLBackupProvider(executor)
        target = self._postgres_target(databases=["db1", "db2"])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(target, Path(temp_dir))

        self.assertEqual(result.status, "success")
        self.assertEqual([command[0] for command in executor.commands], ["pg_dump", "pg_dump"])
        self.assertEqual([artifact.database for artifact in result.artifacts], ["db1", "db2"])

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

    def test_failed_command_is_reported_in_result(self) -> None:
        executor = FakeExecutor([(1, "", "boom")])
        provider = PostgreSQLBackupProvider(executor)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = provider.backup(self._postgres_target(), Path(temp_dir))

        self.assertEqual(result.status, "failed")
        self.assertFalse(result.artifacts)
        self.assertTrue(result.errors)
        self.assertIn("boom", result.errors[0].stderr)


if __name__ == "__main__":
    unittest.main()
