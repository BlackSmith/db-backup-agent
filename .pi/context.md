# Project Context

## Current state

The backup agent project is now implemented as a Python 3.13 modular monolith with the full phase-1 MVP scope delivered.

Completed implementation areas:

- project bootstrap and packaging
- environment-based configuration and internal scheduler
- Docker socket discovery and metadata resolution
- PostgreSQL and MariaDB backup providers
- local staging directories and manifest generation
- rsync-based remote synchronization and retention cleanup
- optional mounted local storage publishing through `BACKUP_LOCAL_STORAGE`
- structured logging, health checks, and run summaries
- containerization and example Docker Compose deployment

## Repository shape

Primary runtime modules now live under `src/backup_agent/`:

- `app/` – entrypoints and configuration
- `domain/` – backup models, manifest DTOs, status values, run summaries
- `services/` – discovery, metadata resolution, staging, manifest writing, retention, orchestrator, scheduler
- `providers/databases/` – PostgreSQL and MariaDB providers
- `providers/storage/` – rsync and mounted local directory storage providers
- `infrastructure/` – Docker API client, filesystem helpers, logging helpers
- `interfaces/` – CLI and health-check boundaries

## Key implementation decisions

- Docker discovery uses the mounted Docker socket instead of Docker-in-Docker.
- Configuration is validated from environment variables and fails fast on invalid input.
- The scheduler is internal to the application and does not depend on OS cron.
- Backup providers use secret-safe execution patterns:
  - PostgreSQL via `PGPASSWORD`
  - MariaDB via a temporary defaults file
- Local backups are written into isolated run directories under `/backup/runs/<run-id>/`.
- Manifests are JSON and intentionally omit secrets.
- Logs use stable `key=value` event formatting with secret masking.
- Health checks are deterministic and do not trigger backup side effects.
- The container image installs the external tools needed by the providers: `pg_dump`, `pg_dumpall`, `mariadb-dump`, and `rsync`.
- Storage backend selection is configuration-driven: mounted local directory publishing and rsync are independent backends that can be enabled separately or together.

## Delivered task trail

Implementation notes for each task were written to:

- `.pi/done/01-project-bootstrap.md`
- `.pi/done/02-config-and-scheduler.md`
- `.pi/done/03-docker-discovery-and-metadata-resolution.md`
- `.pi/done/04-database-backup-providers.md`
- `.pi/done/05-local-staging-and-manifest.md`
- `.pi/done/06-rsync-sync-and-retention.md`
- `.pi/done/07-health-logging-and-run-summary.md`
- `.pi/done/08-containerization-and-example-deployment.md`
- `.pi/done/10-github-actions-ci-release.md`
- `.pi/done/11-local-mounted-storage-provider.md`
- `.pi/done/12-storage-backend-selection-and-staging-cleanup.md`

## Known trade-offs / follow-up candidates

- The rsync transport is implemented for password-file/daemon-style handling; future deployment hardening may prefer SSH keys or secrets management.
- Mounted local storage is now supported but the storage abstraction is still named `RemoteStorageProvider`; a future cleanup may rename it to `StorageProvider`.
- The orchestrator currently integrates discovery, backup, sync, retention, manifest writing, and logging in a single service; this is acceptable for MVP but could be split later if complexity grows.
- Health checks are minimal by design and currently only verify process status, local writeability, and Docker API reachability.
- `BACKUP_TIME` is still a required config value in the current implementation; Task 14 plans to make it optional with an immediate-run fallback, switch the default staging path to `/temporary_storage`, and inherit `TZ` from the process environment when available.
- The CLI/runtime bootstrap still appears to use a placeholder no-op path when no orchestrator is injected; Task 15 is intended to complete real runtime wiring and validate a live local-storage backup against the mounted Docker socket.
- Temporary staging cleanup after successful publish is still a follow-up concern; Task 16 is intended to ensure `LOCAL_BACKUP_DIR` is cleaned after successful local-storage and/or NAS publication while preserving staging on failed or partial runs.
- Metrics endpoints are not yet implemented.
- Restore workflows, encryption, notifications, and additional storage backends remain future work.

## Recommended next steps

If the project moves into phase 2, the most valuable follow-up areas are:

1. hardening secret handling and deployment security
2. improving retry and failure recovery behavior
3. adding an HTTP health/metrics endpoint if operationally useful
4. validating the Docker image build in CI
5. preparing restore workflows and checksum support
