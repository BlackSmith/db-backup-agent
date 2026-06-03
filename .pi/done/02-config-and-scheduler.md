# Task 02 - Configuration and Scheduler: implementation record

## Implemented

- Added validated environment-based configuration loading in `AppConfig.from_env()`.
- Added `ConfigError` with aggregated, actionable validation errors.
- Validated required settings:
  - `RSYNC_REMOTE_HOST`
  - `RSYNC_REMOTE_USER`
  - `RSYNC_REMOTE_PASSWORD`
  - `BACKUP_TIME`
  - `BACKUP_RETENTION_DAYS`
- Added optional configuration support:
  - `RSYNC_REMOTE_PATH`
  - `LOCAL_BACKUP_DIR`
  - `TZ`
  - `LOG_LEVEL`
  - `DOCKER_SOCKET_PATH`
- Implemented explicit timezone handling using `zoneinfo`.
- Implemented `DailyScheduler` with deterministic next-run calculation from `BACKUP_TIME`.
- Added a single-run execution path via `run_once()`.
- Added scheduler mode via `run_scheduler()` for the internal daily loop.
- Extended the CLI with `--run-once` and `--schedule` flags.
- Updated logging configuration to allow repeated test runs with `force=True`.
- Added tests for configuration loading, validation, scheduler timing, and single-run execution.

## Changed files

- `src/backup_agent/app/config.py`
- `src/backup_agent/app/main.py`
- `src/backup_agent/interfaces/cli.py`
- `src/backup_agent/infrastructure/logging.py`
- `src/backup_agent/services/scheduler.py`
- `tests/test_bootstrap.py`
- `tests/test_config_and_scheduler.py`

## Verification

- Installed the project in editable mode:
  - `python -m pip install -e .`
- Ran the test suite successfully:
  - `python -m unittest discover -s tests`

## Open issues / follow-ups

- The scheduler currently calls a placeholder orchestrator object when one is provided; real orchestration will be wired in later tasks.
- Configuration validation is focused on the Task 02 scope and will likely grow as discovery and provider requirements are implemented.
- The internal scheduler is implemented as a blocking loop; later tasks may refine shutdown and integration behavior.
