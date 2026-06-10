"""Tests for Docker discovery and metadata resolution."""

from __future__ import annotations

import unittest

from backup_agent.services.discovery import DockerContainerDiscovery
from backup_agent.services.metadata_resolver import (
    ContainerMetadataResolver,
    MetadataResolutionError,
    parse_database_list,
    parse_directory_list,
)


class FakeDockerClient:
    def __init__(self, summaries: list[dict[str, object]], details: dict[str, dict[str, object]]) -> None:
        self.summaries = summaries
        self.details = details
        self.inspected_ids: list[str] = []

    def list_running_containers(self) -> list[dict[str, object]]:
        return self.summaries

    def inspect_container(self, container_id: str) -> dict[str, object]:
        self.inspected_ids.append(container_id)
        return self.details[container_id]


class DockerDiscoveryAndMetadataResolutionTests(unittest.TestCase):
    def test_discovery_filters_to_enabled_containers_only(self) -> None:
        client = FakeDockerClient(
            summaries=[
                {
                    "Id": "abc123",
                    "Image": "postgres:16",
                    "Labels": {"backup_agent.enabled": "true"},
                    "Names": ["/postgres-app"],
                },
                {
                    "Id": "def456",
                    "Image": "mariadb:11",
                    "Labels": {"backup_agent.enabled": "false"},
                    "Names": ["/mariadb-app"],
                },
            ],
            details={
                "abc123": {
                    "Id": "abc123",
                    "Name": "/postgres-app",
                    "Config": {
                        "Labels": {
                            "backup_agent.enabled": "true",
                            "backup_agent.type": "postgresql",
                        },
                        "Env": ["POSTGRES_USER=app", "POSTGRES_HOST=db", "POSTGRES_PASSWORD=secret", "POSTGRES_PORT=5432"],
                        "Image": "postgres:16",
                    },
                }
            },
        )

        discovery = DockerContainerDiscovery(client)
        discovered = discovery.discover()

        self.assertEqual([container["id"] for container in discovered], ["abc123"])
        self.assertEqual(client.inspected_ids, ["abc123"])
        self.assertEqual(discovered[0]["name"], "postgres-app")
        self.assertEqual(discovered[0]["labels"]["backup_agent.type"], "postgresql")

    def test_postgresql_labels_override_env_and_blank_database_list_means_all_databases(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "abc123",
                "name": "/postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql,filesystem",
                    "backup_agent.pguser": "label_user",
                    "backup_agent.pghost": "label_host",
                    "backup_agent.pgpassword": "label_secret",
                    "backup_agent.pgport": "5433",
                    "backup_agent.pgdatabase": "db1, db2",
                    "backup_agent.directories": "/var/lib/postgresql/data",
                },
                "env": [
                    "POSTGRES_USER=env_user",
                    "POSTGRES_HOST=env_host",
                    "POSTGRES_PASSWORD=env_secret",
                    "POSTGRES_PORT=5432",
                    "POSTGRES_DATABASE=otherdb",
                ],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.db_type, "postgresql")
        self.assertEqual(target.user, "label_user")
        self.assertEqual(target.host, "label_host")
        self.assertEqual(target.port, 5433)
        self.assertEqual(target.password_ref, "label:backup_agent.pgpassword")
        self.assertEqual(target.databases, ["db1", "db2"])
        self.assertEqual(target.directories, ["/var/lib/postgresql/data"])
        self.assertFalse(target.all_databases)

    def test_generic_labels_are_supported(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "abc123",
                "name": "/postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql",
                    "backup_agent.user": "generic_user",
                    "backup_agent.host": "generic_host",
                    "backup_agent.password": "generic_secret",
                    "backup_agent.port": "5432",
                    "backup_agent.database": "db1,db2",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.user, "generic_user")
        self.assertEqual(target.host, "generic_host")
        self.assertEqual(target.password_ref, "label:backup_agent.password")
        self.assertEqual(target.port, 5432)
        self.assertEqual(target.databases, ["db1", "db2"])

    def test_generic_labels_override_legacy_labels(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "abc123",
                "name": "/postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql",
                    "backup_agent.user": "generic_user",
                    "backup_agent.host": "generic_host",
                    "backup_agent.password": "generic_secret",
                    "backup_agent.port": "5432",
                    "backup_agent.database": "db1",
                    "backup_agent.pguser": "legacy_user",
                    "backup_agent.pghost": "legacy_host",
                    "backup_agent.pgpassword": "legacy_secret",
                    "backup_agent.pgport": "5433",
                    "backup_agent.pgdatabase": "legacydb",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.user, "generic_user")
        self.assertEqual(target.host, "generic_host")
        self.assertEqual(target.password_ref, "label:backup_agent.password")
        self.assertEqual(target.port, 5432)
        self.assertEqual(target.databases, ["db1"])

    def test_mariadb_missing_database_list_is_treated_as_all_databases(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "def456",
                "name": "/mariadb-app",
                "labels": {"backup_agent.enabled": "true", "backup_agent.type": "mariadb"},
                "env": [
                    "MARIADB_USER=root",
                    "MARIADB_HOST=db",
                    "MARIADB_PASSWORD=env_secret",
                    "MARIADB_PORT=3306",
                ],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.db_type, "mariadb")
        self.assertEqual(target.password_ref, "env:MARIADB_PASSWORD")
        self.assertEqual(target.databases, [])
        self.assertTrue(target.all_databases)

    def test_mysql_env_aliases_are_accepted_for_mariadb(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "def456",
                "name": "/mysql-app",
                "labels": {"backup_agent.enabled": "true", "backup_agent.type": "mariadb"},
                "env": [
                    "MYSQL_USER=root",
                    "MYSQL_HOST=db",
                    "MYSQL_PASSWORD=env_secret",
                    "MYSQL_PORT=3306",
                    "MYSQL_DATABASE=appdb",
                ],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.db_type, "mariadb")
        self.assertEqual(target.user, "root")
        self.assertEqual(target.host, "db")
        self.assertEqual(target.password_ref, "env:MYSQL_PASSWORD")
        self.assertEqual(target.port, 3306)
        self.assertEqual(target.databases, ["appdb"])

    def test_postgresql_defaults_to_standard_port_when_missing(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "abc123",
                "name": "/postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql",
                    "backup_agent.user": "app",
                    "backup_agent.host": "db",
                    "backup_agent.password": "secret",
                    "backup_agent.database": "appdb",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.port, 5432)

    def test_mariadb_defaults_to_standard_port_when_missing(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "def456",
                "name": "/mariadb-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "mariadb",
                    "backup_agent.user": "root",
                    "backup_agent.host": "db",
                    "backup_agent.password": "secret",
                    "backup_agent.database": "appdb",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.port, 3306)

    def test_invalid_explicit_port_values_still_fail_validation(self) -> None:
        resolver = ContainerMetadataResolver()
        cases = [
            (
                "postgresql",
                {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "postgresql",
                    "backup_agent.user": "app",
                    "backup_agent.host": "db",
                    "backup_agent.password": "secret",
                    "backup_agent.port": "not-a-number",
                },
                "POSTGRES_PORT=5432",
            ),
            (
                "mariadb",
                {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "mariadb",
                    "backup_agent.user": "root",
                    "backup_agent.host": "db",
                    "backup_agent.password": "secret",
                    "backup_agent.port": "",
                },
                "MYSQL_PORT=not-a-number",
            ),
        ]

        for db_type, labels, env_entry in cases:
            with self.subTest(db_type=db_type):
                with self.assertRaises(MetadataResolutionError) as cm:
                    resolver.resolve(
                        {
                            "id": f"{db_type}-1",
                            "name": f"/{db_type}-app",
                            "labels": labels,
                            "env": [env_entry],
                        }
                    )
                self.assertIn("invalid metadata", str(cm.exception))
                self.assertIn("port", str(cm.exception))

    def test_resolver_requires_explicit_type_label(self) -> None:
        resolver = ContainerMetadataResolver()
        with self.assertRaises(MetadataResolutionError) as cm:
            resolver.resolve(
                {
                    "id": "xyz999",
                    "name": "ambiguous-app",
                    "labels": {"backup_agent.enabled": "true"},
                    "env": [
                        "POSTGRES_USER=app",
                        "POSTGRES_HOST=db",
                        "POSTGRES_PASSWORD=secret",
                        "POSTGRES_PORT=5432",
                        "MYSQL_USER=root",
                        "MYSQL_HOST=db2",
                        "MYSQL_PASSWORD=secret2",
                        "MYSQL_PORT=3306",
                    ],
                }
            )

        self.assertIn("missing required backup_agent.type", str(cm.exception))

    def test_filesystem_target_resolves_from_explicit_type_and_directories_label(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "fs123",
                "name": "/files-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": "filesystem",
                    "backup_agent.directories": "/app/data, /var/lib/app/uploads",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.db_type, "filesystem")
        self.assertEqual(target.directories, ["/app/data", "/var/lib/app/uploads"])
        self.assertEqual(target.container_name, "files-app")

    def test_multi_value_type_keeps_database_target_and_directories_for_expansion(self) -> None:
        resolver = ContainerMetadataResolver()
        target = resolver.resolve(
            {
                "id": "abc123",
                "name": "/postgres-app",
                "labels": {
                    "backup_agent.enabled": "true",
                    "backup_agent.type": " postgres , filesystem , postgres ",
                    "backup_agent.user": "app",
                    "backup_agent.host": "db",
                    "backup_agent.password": "secret",
                    "backup_agent.database": "appdb",
                    "backup_agent.directories": "/app/data",
                },
                "env": [],
            }
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.db_type, "postgresql")
        self.assertEqual(target.port, 5432)
        self.assertEqual(target.directories, ["/app/data"])

    def test_conflicting_multi_value_database_types_are_rejected(self) -> None:
        resolver = ContainerMetadataResolver()
        with self.assertRaises(MetadataResolutionError) as cm:
            resolver.resolve(
                {
                    "id": "abc123",
                    "name": "/db-app",
                    "labels": {
                        "backup_agent.enabled": "true",
                        "backup_agent.type": "postgresql,mariadb",
                        "backup_agent.user": "app",
                        "backup_agent.host": "db",
                        "backup_agent.password": "secret",
                    },
                    "env": [],
                }
            )

        self.assertIn("conflicting backup_agent.type", str(cm.exception))

    def test_directories_require_filesystem_type(self) -> None:
        resolver = ContainerMetadataResolver()
        with self.assertRaises(MetadataResolutionError) as cm:
            resolver.resolve(
                {
                    "id": "abc123",
                    "name": "/postgres-app",
                    "labels": {
                        "backup_agent.enabled": "true",
                        "backup_agent.type": "postgresql",
                        "backup_agent.user": "app",
                        "backup_agent.host": "db",
                        "backup_agent.password": "secret",
                        "backup_agent.database": "appdb",
                        "backup_agent.directories": "/app/data",
                    },
                    "env": [],
                }
            )

        self.assertIn("requires backup_agent.type to include filesystem", str(cm.exception))

    def test_blank_type_is_rejected(self) -> None:
        resolver = ContainerMetadataResolver()
        with self.assertRaises(MetadataResolutionError) as cm:
            resolver.resolve(
                {
                    "id": "abc123",
                    "name": "/postgres-app",
                    "labels": {
                        "backup_agent.enabled": "true",
                        "backup_agent.type": "   ",
                    },
                    "env": [],
                }
            )

        self.assertIn("missing required backup_agent.type", str(cm.exception))

    def test_directories_without_type_are_rejected(self) -> None:
        resolver = ContainerMetadataResolver()
        with self.assertRaises(MetadataResolutionError) as cm:
            resolver.resolve(
                {
                    "id": "fs124",
                    "name": "/files-app",
                    "labels": {
                        "backup_agent.enabled": "true",
                        "backup_agent.directories": "/srv/assets",
                    },
                    "env": [],
                }
            )

        self.assertIn("missing required backup_agent.type", str(cm.exception))

    def test_parse_database_list(self) -> None:
        self.assertEqual(parse_database_list(None), [])
        self.assertEqual(parse_database_list(""), [])
        self.assertEqual(parse_database_list("db1, db2 , ,db3"), ["db1", "db2", "db3"])

    def test_parse_directory_list(self) -> None:
        self.assertEqual(parse_directory_list(None), [])
        self.assertEqual(parse_directory_list(""), [])
        self.assertEqual(parse_directory_list("/a, /b , ,/c"), ["/a", "/b", "/c"])


if __name__ == "__main__":
    unittest.main()
