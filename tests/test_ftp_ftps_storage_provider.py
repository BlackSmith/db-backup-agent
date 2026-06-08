"""Tests for the FTP / FTPS storage provider."""

from __future__ import annotations

import ftplib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backup_agent.providers.storage.ftp import FtpStorageProvider


class FakeFTPBase:
    def __init__(self, *args, **kwargs) -> None:
        self.host = None
        self.port = None
        self.timeout = None
        self.user = None
        self.password = None
        self.passive = True
        self.protected = False
        self.connected = False
        self.files: dict[str, bytes] = {}
        self.directories: set[str] = {"/backups", "/backups/runs"}
        self.deleted: list[str] = []
        self.mkd_calls: list[str] = []
        self.storbinary_calls: list[str] = []
        self.retrbinary_calls: list[str] = []
        self.rmd_calls: list[str] = []
        self.rename_calls: list[tuple[str, str]] = []

    def connect(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.connected = True

    def login(self, user, password):
        self.user = user
        self.password = password

    def set_pasv(self, passive):
        self.passive = passive

    def mlsd(self, path="", facts=None):
        path = path.rstrip("/") or "/"
        if path == "/backups/runs":
            return iter([
                ("20260601T020000Z-aaa11111", {"type": "dir"}),
                ("20260609T020000Z-bbb22222", {"type": "dir"}),
            ])
        if path.startswith("/backups/runs/"):
            prefix = path.rstrip("/") + "/"
            entries: list[tuple[str, dict[str, str]]] = []
            seen: set[str] = set()
            for remote_path in sorted(self.files):
                if not remote_path.startswith(prefix):
                    continue
                remainder = remote_path[len(prefix):]
                if not remainder:
                    continue
                name = remainder.split("/", 1)[0]
                if name not in seen:
                    seen.add(name)
                    entries.append((name, {"type": "dir" if "/" in remainder else "file"}))
            if entries:
                return iter(entries)
            if path in self.directories:
                return iter([])
            if path in self.files:
                return iter([(path.rsplit("/", 1)[-1], {"type": "file"})])
            raise ftplib.error_perm("550 path not found")
        if path in self.directories:
            return iter([])
        raise ftplib.error_perm("550 path not found")

    def nlst(self, path=""):
        path = path.rstrip("/") or "/"
        if path == "/backups/runs":
            return [
                "/backups/runs/20260601T020000Z-aaa11111",
                "/backups/runs/20260609T020000Z-bbb22222",
            ]
        prefix = path + "/"
        names: list[str] = []
        seen: set[str] = set()
        for remote_path in sorted(self.files):
            if not remote_path.startswith(prefix):
                continue
            remainder = remote_path[len(prefix):]
            if not remainder:
                continue
            name = remainder.split("/", 1)[0]
            if name not in seen:
                seen.add(name)
                names.append(f"{path}/{name}" if path != "/" else f"/{name}")
        if names:
            return names
        if path in self.directories:
            return []
        raise ftplib.error_perm("550 path not found")

    def mkd(self, path):
        self.directories.add(path.rstrip("/"))
        self.mkd_calls.append(path.rstrip("/"))

    def storbinary(self, cmd, fileobj):
        data = fileobj.read()
        remote_path = cmd.split(" ", 1)[1]
        self.files[remote_path] = data
        self.storbinary_calls.append(remote_path)

    def retrbinary(self, cmd, callback):
        remote_path = cmd.split(" ", 1)[1]
        self.retrbinary_calls.append(remote_path)
        data = self.files.get(remote_path)
        if data is None:
            raise ftplib.error_perm("550 missing")
        callback(data)

    def delete(self, path):
        self.deleted.append(path)
        self.files.pop(path, None)

    def rmd(self, path):
        path = path.rstrip("/")
        self.rmd_calls.append(path)
        self.directories.discard(path)

    def rename(self, fromname, toname):
        self.rename_calls.append((fromname, toname))
        if fromname in self.files:
            self.files[toname] = self.files.pop(fromname)
        self.directories.discard(fromname.rstrip("/"))
        self.directories.add(toname.rstrip("/"))

    def quit(self):
        return None

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FTPStorageProviderTests(unittest.TestCase):
    def _provider(self, fake_ftp: FakeFTPBase, **overrides) -> FtpStorageProvider:
        params = dict(
            host="ftp.example",
            port=21,
            user="backup",
            password="secret",
            remote_path="/backups",
            use_tls=False,
            passive=True,
            timeout=30.0,
        )
        params.update(overrides)
        provider = FtpStorageProvider(**params)
        provider._connect = lambda: fake_ftp  # type: ignore[method-assign]
        return provider

    def _run_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        run_dir = Path(temp_dir.name) / "runs" / "20260603T090000Z-abcdef12"
        artifact_dir = run_dir / "postgresql" / "postgres-app"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "appdb.dump").write_text("backup", encoding="utf-8")
        (run_dir / "manifest.json").write_text(json.dumps({"started_at": "2026-06-03T09:00:00+00:00"}), encoding="utf-8")
        return run_dir

    def test_sync_uploads_run_tree_and_updates_latest(self) -> None:
        fake = FakeFTPBase()
        provider = self._provider(fake)
        run_dir = self._run_dir()

        result = provider.sync(run_dir)

        self.assertEqual(result.status, "success")
        self.assertIn("/backups/runs/20260603T090000Z-abcdef12/manifest.json", fake.files)
        self.assertIn("/backups/latest", fake.files)
        self.assertEqual(fake.files["/backups/latest"].decode("utf-8"), "runs/20260603T090000Z-abcdef12")
        self.assertTrue(fake.passive)

    def test_sync_failure_does_not_overwrite_existing_run(self) -> None:
        fake = FakeFTPBase()
        fake.files["/backups/runs/20260603T090000Z-abcdef12"] = b"existing"
        provider = self._provider(fake)
        run_dir = self._run_dir()

        result = provider.sync(run_dir)

        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(result.error)
        self.assertIn("already exists", result.error.message)

    def test_cleanup_deletes_only_expired_runs_and_updates_latest(self) -> None:
        fake = FakeFTPBase()
        fake.files["/backups/runs/20260601T020000Z-aaa11111/manifest.json"] = json.dumps(
            {"started_at": "2026-06-01T02:00:00+00:00"}
        ).encode("utf-8")
        fake.files["/backups/runs/20260609T020000Z-bbb22222/manifest.json"] = json.dumps(
            {"started_at": "2026-06-09T02:00:00+00:00"}
        ).encode("utf-8")
        provider = self._provider(fake)

        result = provider.cleanup(Path("/tmp/run"), retention_days=5)

        self.assertEqual(result.status, "success")
        self.assertIn("/backups/runs/20260601T020000Z-aaa11111/manifest.json", fake.deleted)
        self.assertEqual(fake.files["/backups/latest"].decode("utf-8"), "runs/20260609T020000Z-bbb22222")

    def test_cleanup_retains_runs_with_missing_manifest(self) -> None:
        fake = FakeFTPBase()
        fake.files["/backups/runs/20260601T020000Z-aaa11111/manifest.json"] = b"not-json"
        provider = self._provider(fake)

        result = provider.cleanup(Path("/tmp/run"), retention_days=5)

        self.assertEqual(result.status, "failed")
        self.assertIn("manifest", result.error.message if result.error else "")

    def test_plan_remote_retention_uses_remote_inventory(self) -> None:
        fake = FakeFTPBase()
        fake.files["/backups/runs/20260601T020000Z-aaa11111/manifest.json"] = json.dumps(
            {"started_at": "2026-06-01T02:00:00+00:00"}
        ).encode("utf-8")
        fake.files["/backups/runs/20260609T020000Z-bbb22222/manifest.json"] = json.dumps(
            {"started_at": "2026-06-09T02:00:00+00:00"}
        ).encode("utf-8")
        provider = self._provider(fake)

        result = provider.plan_remote_retention(5, now=lambda: datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc))

        self.assertTrue(result.succeeded)
        self.assertEqual([record.run_id for record in result.expired_manifests], ["20260601T020000Z-aaa11111"])
        self.assertEqual([record.run_id for record in result.retained_manifests], ["20260609T020000Z-bbb22222"])


if __name__ == "__main__":
    unittest.main()
