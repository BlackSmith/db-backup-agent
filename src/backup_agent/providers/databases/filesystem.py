"""Filesystem archive backup provider for labeled container directories."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

from backup_agent.domain.artifact import BackupArtifact
from backup_agent.domain.backup_target import BackupTarget
from backup_agent.infrastructure.docker import DockerApiClient, DockerSocketError
from backup_agent.infrastructure.filesystem import safe_name

from .base import BackupProviderError, BackupProviderResult, DatabaseBackupProvider


class FilesystemArchiveBackupProvider(DatabaseBackupProvider):
    db_type = "filesystem"

    def __init__(self, docker_client: DockerApiClient) -> None:
        self.docker_client = docker_client

    def supports(self, target: BackupTarget) -> bool:
        return target.db_type.lower() == self.db_type

    def validate(self, target: BackupTarget) -> None:
        if not self.supports(target):
            raise ValueError(f"Unsupported target database type {target.db_type!r}")
        if not target.directories:
            raise ValueError("Filesystem target must define at least one directory")
        for directory in target.directories:
            if not directory.startswith("/"):
                raise ValueError("Filesystem target directories must use absolute container paths")

    def backup(self, target: BackupTarget, output_dir: Path) -> BackupProviderResult:
        self.validate(target)
        provider_dir = _target_output_dir(output_dir, self.db_type, target.container_name)
        provider_dir.mkdir(parents=True, exist_ok=True)
        archive_path = provider_dir / "directories.tar.gz"
        errors: list[BackupProviderError] = []

        with TemporaryDirectory(prefix="filesystem-backup-") as temp_dir:
            temp_root = Path(temp_dir)
            extracted_root = temp_root / "copied"
            extracted_root.mkdir(parents=True, exist_ok=True)

            for directory in target.directories:
                try:
                    archive_bytes = self.docker_client.get_archive(target.container_id, directory)
                except DockerSocketError as exc:
                    errors.append(
                        BackupProviderError(
                            message=f"Failed to copy container directory {directory}: {exc}",
                            output_path=archive_path,
                            database=directory,
                        )
                    )
                    continue
                try:
                    self._extract_container_archive(archive_bytes, extracted_root, directory)
                except (tarfile.TarError, OSError) as exc:
                    errors.append(
                        BackupProviderError(
                            message=f"Failed to unpack container directory {directory}: {exc}",
                            output_path=archive_path,
                            database=directory,
                        )
                    )

            copied_entries = list(extracted_root.iterdir())
            if errors and not copied_entries:
                return BackupProviderResult(
                    provider=self.db_type,
                    target=target,
                    status="failed",
                    artifacts=[],
                    errors=errors,
                )
            if not copied_entries:
                errors.append(
                    BackupProviderError(
                        message="No filesystem data was copied from the target container",
                        output_path=archive_path,
                    )
                )
                return BackupProviderResult(
                    provider=self.db_type,
                    target=target,
                    status="failed",
                    artifacts=[],
                    errors=errors,
                )

            try:
                self._write_archive(extracted_root, archive_path)
            except OSError as exc:
                errors.append(
                    BackupProviderError(
                        message=f"Failed to create filesystem archive: {exc}",
                        output_path=archive_path,
                    )
                )
                return BackupProviderResult(
                    provider=self.db_type,
                    target=target,
                    status="failed" if not errors[:-1] else "partial",
                    artifacts=[],
                    errors=errors,
                )

        artifact = BackupArtifact(
            target=target,
            database=None,
            path=archive_path,
            size=archive_path.stat().st_size if archive_path.exists() else None,
            format="filesystem-tar-gzip",
        )
        return BackupProviderResult(
            provider=self.db_type,
            target=target,
            status="partial" if errors else "success",
            artifacts=[artifact],
            errors=errors,
        )

    def _extract_container_archive(self, payload: bytes, destination_root: Path, directory: str) -> None:
        destination_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            archive.extractall(destination_root, filter="data")

    def _write_archive(self, source_root: Path, archive_path: Path) -> None:
        with tarfile.open(archive_path, mode="w:gz") as archive:
            for path in sorted(source_root.rglob("*")):
                archive.add(path, arcname=path.relative_to(source_root))


def _target_output_dir(output_dir: Path, provider_name: str, container_name: str) -> Path:
    return output_dir / provider_name / safe_name(container_name)
