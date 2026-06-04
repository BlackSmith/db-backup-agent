"""Application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from backup_agent.app.config import AppConfig, ConfigError
from backup_agent.domain.run_summary import RunSummary
from backup_agent.domain.status import STATUS_SUCCESS
from backup_agent.infrastructure.docker import DockerApiClient
from backup_agent.infrastructure.logging import configure_logging, log_config_validation, log_event
from backup_agent.interfaces.cli import build_parser
from backup_agent.providers.storage import build_storage_provider
from backup_agent.services.discovery import DockerContainerDiscovery
from backup_agent.services.metadata_resolver import ContainerMetadataResolver
from backup_agent.services.orchestrator import BackupOrchestratorService
from backup_agent.services.scheduler import DailyScheduler


logger = logging.getLogger(__name__)


def run_once(config: AppConfig | None = None, orchestrator: object | None = None) -> int:
    """Execute a single backup cycle or a bootstrap placeholder run."""

    effective_config = config or AppConfig.from_env()
    configure_logging(effective_config.log_level)
    log_config_validation(logger, effective_config)
    log_event(logger, "application_start", mode="run_once")

    active_orchestrator = orchestrator or build_orchestrator(effective_config)
    result = active_orchestrator.run_once()
    summary = _coerce_summary(result)
    log_event(
        logger,
        "run_summary",
        run_id=summary.run_id,
        status=summary.status,
        target_count=summary.target_count,
        artifact_count=summary.artifact_count,
        error_count=summary.error_count,
    )
    _log_run_errors(result)
    return 0


def run_scheduler(config: AppConfig | None = None, orchestrator: object | None = None) -> int:
    """Start the internal daily scheduler."""

    effective_config = config or AppConfig.from_env()
    configure_logging(effective_config.log_level)
    log_config_validation(logger, effective_config)
    log_event(logger, "application_start", mode="scheduler")
    active_orchestrator = orchestrator or build_orchestrator(effective_config)
    scheduler = DailyScheduler(
        backup_time=effective_config.backup_time,
        timezone=effective_config.timezone,
    )
    log_event(
        logger,
        "scheduler_started",
        next_run=scheduler.next_run_after().isoformat(),
    )
    scheduler.schedule(lambda: run_once(effective_config, active_orchestrator))
    return 0


def build_orchestrator(config: AppConfig) -> BackupOrchestratorService:
    """Build the real orchestrator used by the CLI runtime."""

    docker_client = DockerApiClient(config.docker_socket_path)
    discovery = DockerContainerDiscovery(docker_client)
    resolver = ContainerMetadataResolver()
    remote_storage = build_storage_provider(config)
    return BackupOrchestratorService(
        config=config,
        discovery=discovery,
        resolver=resolver,
        remote_storage=remote_storage,
    )


def _log_run_errors(result: object) -> None:
    errors = getattr(result, "errors", None)
    run_id = getattr(result, "run_id", "")
    if not errors:
        return

    for error in errors:
        log_event(
            logger,
            "run_error",
            run_id=run_id,
            source=getattr(error, "source", "unknown"),
            message=getattr(error, "message", ""),
            target_container_name=getattr(error, "target_container_name", ""),
            target_container_id=getattr(error, "target_container_id", ""),
            database=getattr(error, "database", ""),
            output_path=getattr(error, "output_path", ""),
        )


def _coerce_summary(result: object) -> RunSummary:
    if isinstance(result, RunSummary):
        return result
    if hasattr(result, "run_id") and hasattr(result, "targets") and hasattr(result, "artifacts") and hasattr(result, "errors"):
        try:
            return RunSummary.from_backup_run(result)  # type: ignore[arg-type]
        except Exception:
            pass
    if isinstance(result, str) and result in {"success", "partial", "failed", "sync_failed"}:
        status = result
    else:
        status = STATUS_SUCCESS
    return RunSummary(run_id="", status=status, started_at=None, finished_at=None, target_count=0, artifact_count=0, error_count=0)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by the console script and `python -m backup_agent`."""

    configure_logging("INFO")
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = AppConfig.from_env()
    except ConfigError as exc:
        logger.error(str(exc))
        return 2

    if args.schedule:
        return run_scheduler(config)
    return run_once(config)
