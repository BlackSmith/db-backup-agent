"""Application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from backup_agent.app.config import AppConfig, ConfigError
from backup_agent.infrastructure.logging import configure_logging
from backup_agent.interfaces.cli import build_parser
from backup_agent.services.scheduler import DailyScheduler


logger = logging.getLogger(__name__)


def run_once(config: AppConfig | None = None, orchestrator: object | None = None) -> int:
    """Execute a single backup cycle or a bootstrap placeholder run."""

    effective_config = config or AppConfig.from_env()
    configure_logging(effective_config.log_level)
    logger.info("Backup agent single-run mode started")

    if orchestrator is None:
        logger.info("No backup orchestrator is configured yet; skipping backup execution.")
        return 0

    result = orchestrator.run_once()
    logger.info("Backup orchestrator finished with result: %s", result)
    return 0


def run_scheduler(config: AppConfig | None = None, orchestrator: object | None = None) -> int:
    """Start the internal daily scheduler."""

    effective_config = config or AppConfig.from_env()
    configure_logging(effective_config.log_level)
    scheduler = DailyScheduler(
        backup_time=effective_config.backup_time,
        timezone=effective_config.timezone,
    )
    logger.info(
        "Scheduler started; next run at %s",
        scheduler.next_run_after().isoformat(),
    )
    scheduler.schedule(lambda: run_once(effective_config, orchestrator))
    return 0


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
