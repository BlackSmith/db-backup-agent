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
- composite storage backend selection for local-only, rsync-only, or combined publishing
- real CLI/runtime bootstrap for live backup execution
- post-success staging cleanup for successful publish flows
- default PostgreSQL and MariaDB port fallback behavior in metadata resolution
- structured logging, health checks, run summaries, and console-visible run error reporting
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
- `.pi/done/15-live-local-storage-validation-and-runtime-fix.md`
- `.pi/done/16-cleanup-temporary-staging-after-successful-publish.md`
- `.pi/done/17-default-database-port-fallbacks.md`
- `.pi/done/18-console-error-reporting-for-export-and-upload-failures.md`

## Known trade-offs / follow-up candidates

- The rsync transport is implemented for password-file/daemon-style handling; future deployment hardening may prefer SSH keys or secrets management.
- Mounted local storage is now supported but the storage abstraction is still named `RemoteStorageProvider`; a future cleanup may rename it to `StorageProvider`.
- The orchestrator currently integrates discovery, backup, sync, retention, manifest writing, and logging in a single service; this is acceptable for MVP but could be split later if complexity grows.
- Health checks are minimal by design and currently only verify process status, local writeability, and Docker API reachability.
- `BACKUP_TIME` is still a required config value in the current implementation. Task 14 remains intentionally pending and would make scheduled time optional, add immediate-run fallback semantics, switch the default staging path to `/temporary_storage`, and inherit `TZ` from the process environment when available.
- Console-visible run error reporting is currently emitted as structured `run_error` events after the run completes. If operators later need richer console diagnostics, a follow-up could reintroduce sanitized `stderr` excerpts or add dedicated debug-mode error expansion.
- Metrics endpoints are not yet implemented.
- PostgreSQL runtime packaging currently needs a compatibility follow-up for newer PostgreSQL server versions. A real PostgreSQL 17 backup failed because the image contains `pg_dump` 15.x from Debian bookworm; Task 19 tracks upgrading the packaged `pg_dump` / `pg_dumpall` toolchain to the newest practical version.
- A further database execution follow-up is planned in Task 20: support shared label-selected dump method control via `backup_agent.dump_method`, applying to PostgreSQL and MariaDB with default `auto` behavior that tries Docker exec inside the target database container first and falls back to local execution if exec fails.
- Metadata simplification is planned in Task 21: migrate from engine-specific `backup_agent.pg*` / `backup_agent.mariadb*` labels to generic `backup_agent.*` labels, infer engine type from env-variable families, and accept both `MARIADB_*` and `MYSQL_*` variables for MySQL-family targets.
- Restore workflows, encryption, notifications, and additional storage backends remain future work.

## Recommended next steps

If the project moves into phase 2, the most valuable follow-up areas are:

1. decide whether Task 14 should remain deferred or be implemented as a product behavior change
2. upgrade packaged PostgreSQL dump tools to the newest practical version (Task 19)
3. add database remote-exec dump strategy for PostgreSQL and MariaDB with shared label-selected method and exec-to-local fallback (Task 20)
4. simplify metadata labels and add MySQL/MariaDB env alias support (Task 21)
5. hardening secret handling and deployment security
6. improving retry and failure recovery behavior
7. adding an HTTP health/metrics endpoint if operationally useful
8. validating the Docker image build in CI
9. preparing restore workflows and checksum support
