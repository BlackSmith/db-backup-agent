"""Backup orchestration service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from backup_agent.app.config import AppConfig
from backup_agent.domain.backup_run import BackupRun, BackupRunError
from backup_agent.domain.manifest import RunManifest
from backup_agent.domain.run_summary import RunSummary
from backup_agent.domain.status import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_SYNC_FAILED,
)
from backup_agent.infrastructure.logging import log_event
from backup_agent.providers.databases import (
    DatabaseBackupProvider,
    FilesystemArchiveBackupProvider,
    MariaDBBackupProvider,
    PostgreSQLBackupProvider,
)
from backup_agent.providers.storage import CompositeStorageProvider, RemoteStorageProvider, RsyncStorageProvider, build_storage_provider
from backup_agent.services.discovery import ContainerDiscovery, DiscoveryError
from backup_agent.services.manifest import ManifestWriter
from backup_agent.services.metadata_resolver import MetadataResolutionError, MetadataResolver
from backup_agent.services.retention import FileSystemRetentionManager, RetentionManager
from backup_agent.services.staging import LocalStagingManager, RunLayout, generate_run_id


@dataclass(slots=True)
class BackupOrchestratorService:
    """Default single-process backup workflow implementation."""

    config: AppConfig
    discovery: ContainerDiscovery
    resolver: MetadataResolver
    database_providers: list[DatabaseBackupProvider] = field(default_factory=list)
    staging: LocalStagingManager | None = None
    manifest_writer: ManifestWriter | None = None
    remote_storage: RemoteStorageProvider | None = None
    retention: RetentionManager | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def __post_init__(self) -> None:
        if not self.database_providers:
            self.database_providers = [PostgreSQLBackupProvider(), MariaDBBackupProvider()]
        if self.staging is None:
            self.staging = LocalStagingManager(self.config.local_backup_dir)
        if self.manifest_writer is None:
            from backup_agent.services.manifest import JsonManifestWriter

            self.manifest_writer = JsonManifestWriter()
        if self.remote_storage is None:
            self.remote_storage = build_storage_provider(self.config)
        if self.retention is None:
            self.retention = FileSystemRetentionManager()

    def run_once(self) -> BackupRun:
        run = BackupRun(run_id=generate_run_id(), started_at=datetime.now(timezone.utc), status=STATUS_RUNNING)
        layout = self.staging.create_run(run.run_id)
        log_event(
            self.logger,
            "run_start",
            run_id=run.run_id,
            run_dir=str(layout.run_dir),
            storage_backend=self.config.storage_backend,
        )

        try:
            discovered = self.discovery.discover()
            run.targets = []
            log_event(self.logger, "discovery_complete", run_id=run.run_id, discovered_count=len(discovered))
            targets = self._resolve_targets(run, discovered)
            if not targets:
                run.status = STATUS_FAILED
                run.errors.append(
                    BackupRunError(source="discovery", message="No eligible backup targets discovered")
                )
                self._finish_run(run, layout)
                return run

            self._backup_targets(run, layout, targets)
            if not run.artifacts:
                run.status = STATUS_FAILED if not run.errors else run.status
                self._finish_run(run, layout)
                return run

            self._finish_run(run, layout)
            rsync_provider = self._rsync_provider()
            if rsync_provider is not None:
                rsync_result = self._sync_with_rsync_retention(run, layout, rsync_provider)
                if rsync_result is not None:
                    return rsync_result
                return run

            sync_result = self.remote_storage.sync(layout.run_dir)
            log_event(
                self.logger,
                "sync_finish",
                run_id=run.run_id,
                status=sync_result.status,
                remote_destination=sync_result.remote_destination,
            )
            if not sync_result.succeeded:
                run.status = STATUS_PARTIAL if sync_result.status == "partial" else STATUS_SYNC_FAILED
                run.errors.append(
                    BackupRunError(
                        source="sync",
                        message=sync_result.error.message if sync_result.error else "Remote sync failed",
                        command=list(sync_result.command),
                        returncode=sync_result.returncode,
                        stderr=sync_result.stderr,
                    )
                )
                self._finish_run(run, layout)
                return run

            log_event(self.logger, "retention_start", run_id=run.run_id, retention_days=self.config.backup_retention_days)
            remote_cleanup = self.remote_storage.cleanup(layout.runs_root, self.config.backup_retention_days)
            local_status = "skipped"
            removed_local_runs = 0
            if remote_cleanup.succeeded and not run.errors:
                if self.config.uses_local_storage:
                    local_cleanup = self.retention.cleanup(layout.runs_root, self.config.backup_retention_days)
                    local_status = local_cleanup.status
                    removed_local_runs = len(local_cleanup.removed_run_dirs)
                    if local_cleanup.errors:
                        run.errors.append(
                            BackupRunError(
                                source="local_retention",
                                message="; ".join(local_cleanup.errors),
                            )
                        )
                else:
                    local_status = "success"
            log_event(
                self.logger,
                "retention_finish",
                run_id=run.run_id,
                remote_status=remote_cleanup.status,
                local_status=local_status,
                removed_local_runs=removed_local_runs,
            )
            if remote_cleanup.error:
                run.errors.append(
                    BackupRunError(
                        source="remote_retention",
                        message=remote_cleanup.error.message,
                        command=list(remote_cleanup.command),
                        returncode=remote_cleanup.returncode,
                        stderr=remote_cleanup.stderr,
                    )
                )

            if remote_cleanup.succeeded and not run.errors and local_status == "success":
                run.status = STATUS_SUCCESS
            else:
                run.status = STATUS_PARTIAL

            self._finish_run(run, layout)
            if run.status == STATUS_SUCCESS:
                try:
                    self.staging.cleanup_run_tree(layout)
                except OSError as exc:
                    self.logger.warning("Failed to clean up local staging for run_id=%s: %s", run.run_id, exc)
            return run
        except DiscoveryError as exc:
            run.status = STATUS_FAILED
            run.errors.append(BackupRunError(source="discovery", message=str(exc)))
            self._finish_run(run, layout)
            return run

    def _sync_with_rsync_retention(
        self,
        run: BackupRun,
        layout: RunLayout,
        rsync_provider: RsyncStorageProvider,
    ) -> BackupRun | None:
        log_event(
            self.logger,
            "retention_start",
            run_id=run.run_id,
            retention_days=self.config.backup_retention_days,
        )
        plan = rsync_provider.plan_remote_retention(self.config.backup_retention_days)
        if not plan.succeeded:
            self._append_rsync_retention_errors(
                run,
                plan.errors,
                plan.inventory.command if plan.inventory else [],
                plan.inventory.returncode if plan.inventory else None,
                plan.inventory.stderr if plan.inventory else "",
            )
            log_event(
                self.logger,
                "retention_finish",
                run_id=run.run_id,
                remote_status=plan.status,
                local_status="skipped",
                removed_local_runs=0,
            )
            run.status = STATUS_PARTIAL if run.artifacts else STATUS_FAILED
            self._finish_run(run, layout)
            return run

        delete_result = rsync_provider.delete_remote_runs([manifest.run_id for manifest in plan.expired_manifests])
        if not delete_result.succeeded:
            self._append_rsync_delete_error(run, delete_result)
            log_event(
                self.logger,
                "retention_finish",
                run_id=run.run_id,
                remote_status=delete_result.status,
                local_status="skipped",
                removed_local_runs=0,
            )
            run.status = STATUS_PARTIAL if run.artifacts else STATUS_FAILED
            self._finish_run(run, layout)
            return run

        sync_result = self.remote_storage.sync(layout.run_dir)
        log_event(
            self.logger,
            "sync_finish",
            run_id=run.run_id,
            status=sync_result.status,
            remote_destination=sync_result.remote_destination,
        )
        if not sync_result.succeeded:
            run.status = STATUS_PARTIAL if sync_result.status == "partial" else STATUS_SYNC_FAILED
            run.errors.append(
                BackupRunError(
                    source="sync",
                    message=sync_result.error.message if sync_result.error else "Remote sync failed",
                    command=list(sync_result.command),
                    returncode=sync_result.returncode,
                    stderr=sync_result.stderr,
                )
            )
            log_event(
                self.logger,
                "retention_finish",
                run_id=run.run_id,
                remote_status="success",
                local_status="skipped",
                removed_local_runs=0,
            )
            self._finish_run(run, layout)
            return run

        if self.config.uses_local_storage:
            local_cleanup = self.retention.cleanup(layout.runs_root, self.config.backup_retention_days)
            local_status = local_cleanup.status
            removed_local_runs = len(local_cleanup.removed_run_dirs)
            if local_cleanup.errors:
                run.errors.append(
                    BackupRunError(
                        source="local_retention",
                        message="; ".join(local_cleanup.errors),
                    )
                )
        else:
            local_status = "success"
            removed_local_runs = 0

        log_event(
            self.logger,
            "retention_finish",
            run_id=run.run_id,
            remote_status="success",
            local_status=local_status,
            removed_local_runs=removed_local_runs,
        )

        if run.errors:
            run.status = STATUS_PARTIAL
        else:
            run.status = STATUS_SUCCESS

        self._finish_run(run, layout)
        if run.status == STATUS_SUCCESS:
            try:
                self.staging.cleanup_run_tree(layout)
            except OSError as exc:
                self.logger.warning("Failed to clean up local staging for run_id=%s: %s", run.run_id, exc)
        return run

    def _append_rsync_retention_errors(
        self,
        run: BackupRun,
        errors: list[str],
        command: list[str],
        returncode: int | None,
        stderr: str,
    ) -> None:
        message = "; ".join(errors) if errors else "rsync manifest inventory failed"
        run.errors.append(
            BackupRunError(
                source="remote_retention",
                message=message,
                command=list(command),
                returncode=returncode,
                stderr=stderr,
            )
        )

    def _append_rsync_delete_error(self, run: BackupRun, delete_result) -> None:
        run.errors.append(
            BackupRunError(
                source="remote_retention",
                message=delete_result.error.message if delete_result.error else "rsync delete failed",
                command=list(delete_result.command),
                returncode=delete_result.returncode,
                stderr=delete_result.stderr,
            )
        )

    def _rsync_provider(self) -> RsyncStorageProvider | None:
        if isinstance(self.remote_storage, RsyncStorageProvider):
            return self.remote_storage
        if isinstance(self.remote_storage, CompositeStorageProvider):
            for provider in self.remote_storage.providers:
                if isinstance(provider, RsyncStorageProvider):
                    return provider
        return None

    def _resolve_targets(self, run: BackupRun, discovered: Iterable[dict[str, object]]) -> list:
        targets = []
        for container in discovered:
            try:
                target = self.resolver.resolve(container)
            except MetadataResolutionError as exc:
                run.errors.append(
                    BackupRunError(
                        source="metadata",
                        message=str(exc),
                        target_container_id=_container_id(container),
                        target_container_name=_container_name(container),
                    )
                )
                continue
            if target is None:
                continue
            run.targets.append(target)
            targets.append(target)
        return targets

    def _backup_targets(self, run: BackupRun, layout: RunLayout, targets: list) -> None:
        for target in targets:
            provider = self._provider_for_target(target)
            if provider is None:
                run.errors.append(
                    BackupRunError(
                        source="provider",
                        message=f"No provider available for {target.db_type!r}",
                        target_container_id=target.container_id,
                        target_container_name=target.container_name,
                    )
                )
                continue

            log_event(
                self.logger,
                "target_backup_start",
                run_id=run.run_id,
                container_name=target.container_name,
                db_type=target.db_type,
            )
            result = provider.backup(target, layout.run_dir)
            run.artifacts.extend(result.artifacts)
            run.errors.extend(_provider_errors_to_run_errors(result.errors))
            log_event(
                self.logger,
                "target_backup_finish",
                run_id=run.run_id,
                container_name=target.container_name,
                db_type=target.db_type,
                status=result.status,
                artifact_count=len(result.artifacts),
                error_count=len(result.errors),
            )

        if run.errors and run.artifacts:
            run.status = STATUS_PARTIAL
        elif run.errors and not run.artifacts:
            run.status = STATUS_FAILED
        elif run.artifacts:
            run.status = STATUS_RUNNING

    def _provider_for_target(self, target) -> DatabaseBackupProvider | None:
        for provider in self.database_providers:
            if provider.supports(target):
                return provider
        return None

    def _finish_run(self, run: BackupRun, layout: RunLayout) -> None:
        run.finished_at = datetime.now(timezone.utc)
        manifest = RunManifest.from_backup_run(run, layout.run_dir)
        manifest_path = self.manifest_writer.write_run_manifest(manifest, layout.run_dir)
        summary = RunSummary.from_backup_run(run)
        log_event(
            self.logger,
            "run_summary",
            run_id=summary.run_id,
            status=summary.status,
            target_count=summary.target_count,
            artifact_count=summary.artifact_count,
            error_count=summary.error_count,
            manifest_path=str(manifest_path),
        )


def _provider_errors_to_run_errors(errors) -> list[BackupRunError]:
    run_errors: list[BackupRunError] = []
    for error in errors:
        run_errors.append(
            BackupRunError(
                source="provider",
                message=error.message,
                command=list(error.command),
                returncode=error.returncode,
                stderr=error.stderr,
                target_container_id=error.database,
                target_container_name=error.database,
                database=error.database,
                output_path=error.output_path,
            )
        )
    return run_errors


def _container_id(container) -> str:
    return str(container.get("id") or container.get("Id") or "")


def _container_name(container) -> str:
    return str(container.get("name") or container.get("Name") or "")
