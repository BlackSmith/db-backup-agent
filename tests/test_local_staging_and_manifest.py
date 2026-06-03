"""Tests for local staging and manifest generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_run import BackupRun, BackupRunError
from backup_agent.domain.backup_target import BackupTarget
from backup_agent.domain.manifest import RunManifest
from backup_agent.services.manifest import JsonManifestWriter
from backup_agent.services.staging import LocalStagingManager, generate_run_id


class LocalStagingAndManifestTests(unittest.TestCase):
    def _target(self, db_type: str = "postgresql", container_name: str = "postgres-app") -> BackupTarget:
        return BackupTarget(
            container_id="abc123",
            container_name=container_name,
            db_type=db_type,
            host="db",
            port=5432,
            user="app",
            password="secret",
            password_ref="env:POSTGRES_PASSWORD",
            databases=["appdb"],
            all_databases=False,
            labels={"backup_agent.enabled": "true"},
        )

    def test_create_run_directory_creates_unique_layout_and_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = LocalStagingManager(Path(temp_dir))
            layout = staging.create_run("20260603T090000Z-abcdef12")

            self.assertTrue(layout.run_dir.exists())
            self.assertEqual(layout.run_dir.name, "20260603T090000Z-abcdef12")
            self.assertTrue(layout.manifest_path.parent.exists())
            self.assertTrue(layout.latest_path.exists())
            if layout.latest_path.is_symlink():
                self.assertEqual(layout.latest_path.readlink(), Path("runs") / layout.run_id)
            else:
                self.assertEqual(layout.latest_path.read_text(encoding="utf-8"), "runs/20260603T090000Z-abcdef12")

            artifact_dir = staging.artifact_directory_for(layout.run_dir, self._target())
            self.assertEqual(artifact_dir, layout.run_dir / "postgresql" / "postgres-app")

    def test_generate_run_id_is_time_ordered_and_safe(self) -> None:
        run_id = generate_run_id(datetime(2026, 6, 3, 9, 15, tzinfo=timezone.utc))
        self.assertTrue(run_id.startswith("20260603T091500Z-"))
        self.assertNotIn(":", run_id)

    def test_manifest_writer_serializes_run_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_root = Path(temp_dir) / "runs" / "20260603T091500Z-abcdef12"
            run_root.mkdir(parents=True)
            target = self._target()
            artifact_path = run_root / "postgresql" / "postgres-app" / "appdb.dump"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text("backup", encoding="utf-8")

            run = BackupRun(
                run_id="20260603T091500Z-abcdef12",
                started_at=datetime(2026, 6, 3, 9, 15, tzinfo=timezone.utc),
                finished_at=datetime(2026, 6, 3, 9, 16, tzinfo=timezone.utc),
                status="success",
                targets=[target],
                artifacts=[
                    BackupArtifact(
                        target=target,
                        database="appdb",
                        path=artifact_path,
                        size=6,
                        checksum="abc123",
                        format="postgresql-custom",
                    )
                ],
                errors=[
                    BackupRunError(
                        source="postgresql",
                        message="sample error",
                        command=["pg_dump"],
                        returncode=1,
                        stderr="boom",
                        target_container_id=target.container_id,
                        target_container_name=target.container_name,
                        database="appdb",
                        output_path=artifact_path,
                    )
                ],
            )

            manifest = RunManifest.from_backup_run(run, run_root)
            writer = JsonManifestWriter()
            manifest_path = writer.write_run_manifest(manifest, run_root)

            self.assertEqual(manifest_path, run_root / "manifest.json")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], run.run_id)
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["targets"][0]["container_name"], "postgres-app")
            self.assertEqual(payload["artifacts"][0]["path"], "postgresql/postgres-app/appdb.dump")
            self.assertNotIn("secret", json.dumps(payload))
            self.assertEqual(payload["errors"][0]["output_path"], "postgresql/postgres-app/appdb.dump")


if __name__ == "__main__":
    unittest.main()
