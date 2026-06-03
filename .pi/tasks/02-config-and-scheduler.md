# Task 02: Configuration and Scheduler

## Goal
Implement configuration loading, validation, and the internal daily scheduler.

## Scope
- Load global configuration from environment variables
- Validate required values and formats
- Implement internal scheduling based on `BACKUP_TIME`
- Expose a single-run execution path that can be called by the scheduler and tests

## Required configuration
- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`

## Recommended optional configuration
- `RSYNC_REMOTE_PATH`
- `LOCAL_BACKUP_DIR`
- `TZ`
- `LOG_LEVEL`
- `DOCKER_SOCKET_PATH`

## Deliverables
- Config model/object
- Validation logic with clear error messages
- Scheduler service
- A callable `runOnce()` or equivalent orchestrator trigger

## Constraints
- Do not rely on OS cron inside the container
- Invalid configuration must fail fast
- Time handling must be explicit and deterministic

## Acceptance criteria
- Invalid env values are rejected with actionable errors
- The scheduler computes the next run from `BACKUP_TIME`
- A single-run mode exists for manual execution and tests
- No backup logic is embedded directly into the scheduler

## Suggested notes for implementer
- Keep the scheduler isolated from backup details
- Favor testable time abstractions if practical
