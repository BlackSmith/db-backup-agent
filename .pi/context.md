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
- optional mounted local storage publishing through `BACKUP_LOCAL_STORAGE`, with `BACKUP_RETENTION_DAYS` applied to the published local storage but not to transient staging
- FTP/FTPS remote storage via `FTP_*`
- composite storage backend selection for local-only, rsync-only, FTP-only, or combined publishing
- real CLI/runtime bootstrap for live backup execution
- post-success staging cleanup for successful publish flows
- default PostgreSQL and MariaDB port fallback behavior in metadata resolution
- runtime PostgreSQL client packaging refreshed via the PostgreSQL APT repository for newer server compatibility
- shared label-selected dump execution strategy with remote-exec-first auto mode and local fallback for PostgreSQL and MariaDB
- PostgreSQL output-format selection through `backup_agent.dump_format` with `binary`, `sql_gzip`, and `both` variants, defaulting to `both` for explicit databases and constraining `all_databases=True` to `sql_gzip`
- generic `backup_agent.*` metadata labels with backward-compatible legacy label support
- MariaDB/MySQL-family env alias support via both `MARIADB_*` and `MYSQL_*`
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
  - MariaDB via a temporary defaults file locally or `MYSQL_PWD` for remote exec inside the target container
- Local backups are written into isolated run directories under `/backup/runs/<run-id>/`.
- Manifests are JSON and intentionally omit secrets.
- Logs use stable `key=value` event formatting with secret masking.
- Health checks are deterministic and do not trigger backup side effects.
- The container image installs the external tools needed by the providers: `pg_dump`, `pg_dumpall`, `mariadb-dump`, and `rsync`.
- PostgreSQL client tooling is now sourced from the PostgreSQL APT repository so the runtime can back up newer PostgreSQL servers such as PostgreSQL 17.
- Storage backend selection is configuration-driven: mounted local directory publishing and rsync are independent backends that can be enabled separately or together.
- Database dump execution strategy is label-driven through `backup_agent.dump_method` with `auto`, `exec`, and `local` modes; `auto` prefers Docker exec inside the target container and falls back to local execution.
- Metadata resolution now prefers generic `backup_agent.*` labels while temporarily retaining compatibility with legacy engine-specific labels.
- MySQL-family metadata is accepted from both `MARIADB_*` and `MYSQL_*` environment variable families and routes through the MariaDB provider path.

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
- `.pi/done/19-postgresql-client-version-compatibility.md`
- `.pi/done/20-database-remote-exec-with-label-selected-strategy.md`
- `.pi/done/21-generic-backup-agent-labels-and-mysql-mariadb-env-aliases.md`
- `.pi/done/24-ftp-ftps-storage-provider.md`

## Known trade-offs / follow-up candidates

- The rsync transport is implemented for password-file/daemon-style handling; future deployment hardening may prefer SSH keys or secrets management.
- Mounted local storage is now supported but the storage abstraction is still named `RemoteStorageProvider`; a future cleanup may rename it to `StorageProvider`.
- The orchestrator currently integrates discovery, backup, sync, retention, manifest writing, and logging in a single service; this is acceptable for MVP but could be split later if complexity grows.
- Health checks are minimal by design and currently only verify process status, local writeability, and Docker API reachability.
- `BACKUP_TIME` is still a required config value in the current implementation. Task 14 remains intentionally pending and would make scheduled time optional, add immediate-run fallback semantics, switch the default staging path to `/temporary_storage`, and inherit `TZ` from the process environment when available.
- Console-visible run error reporting is currently emitted as structured `run_error` events after the run completes. If operators later need richer console diagnostics, a follow-up could reintroduce sanitized `stderr` excerpts or add dedicated debug-mode error expansion.
- Remote gzip for container-exec dump paths remains unimplemented; the current remote-exec strategy streams raw dump output and relies on existing artifact formats.
- Generic labels are now preferred, but the implementation intentionally still accepts legacy engine-specific labels during the migration window.
- PostgreSQL cluster-wide backups intentionally restrict `backup_agent.dump_format` to `sql_gzip` because `pg_dumpall` does not produce a single custom-format binary equivalent.
- Metrics endpoints are not yet implemented.
- Current rsync retention still derives the remote deletion set from transient local staging state; this is unsafe for ransomware or staging-loss scenarios and should be replaced by remote-manifest-based retention.
- Restore workflows, encryption, notifications, and additional storage backends remain future work.
- FTP/FTPS storage support is implemented; future work should validate it against real server deployments and harden any protocol-specific edge cases.
- A new follow-up task has been shaped for label-driven container directory archive backups.

## Recommended next steps

If the project moves into phase 2, the most valuable follow-up areas are:

1. decide whether Task 14 should remain deferred or be implemented as a product behavior change
2. decide whether remote gzip should be added to the container-exec dump path
3. surface PostgreSQL format-selection details in operator-facing docs and examples
4. clean up README and compose examples so they advertise only the generic `backup_agent.*` label model
5. hardening secret handling and deployment security
6. improving retry and failure recovery behavior
7. adding an HTTP health/metrics endpoint if operationally useful
8. redesign rsync retention so it inventories remote manifests, deletes only expired remote runs, and never re-uploads retained manifests during cleanup
9. validate FTP/FTPS storage publishing against real-world server behavior and refine any protocol trade-offs
10. implement label-driven container directory archive backups for arbitrary paths inside a target container
11. validating the Docker image build in CI
12. preparing restore workflows and checksum support
