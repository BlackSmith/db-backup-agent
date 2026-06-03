"""Tests for Docker discovery and metadata resolution."""

from __future__ import annotations

import unittest

from backup_agent.services.discovery import DockerContainerDiscovery
from backup_agent.services.metadata_resolver import (
    ContainerMetadataResolver,
    MetadataResolutionError,
    parse_database_list,
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
                    "backup_agent.type": "postgresql",
                    "backup_agent.pguser": "label_user",
                    "backup_agent.pghost": "label_host",
                    "backup_agent.pgpassword": "label_secret",
                    "backup_agent.pgport": "5433",
                    "backup_agent.pgdatabase": "db1, db2",
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
        self.assertFalse(target.all_databases)

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

    def test_resolver_requires_explicit_type_when_metadata_is_ambiguous(self) -> None:
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
                        "MARIADB_USER=root",
                        "MARIADB_HOST=db2",
                        "MARIADB_PASSWORD=secret2",
                        "MARIADB_PORT=3306",
                    ],
                }
            )

        self.assertIn("backup_agent.type", str(cm.exception))

    def test_parse_database_list(self) -> None:
        self.assertEqual(parse_database_list(None), [])
        self.assertEqual(parse_database_list(""), [])
        self.assertEqual(parse_database_list("db1, db2 , ,db3"), ["db1", "db2", "db3"])


if __name__ == "__main__":
    unittest.main()
