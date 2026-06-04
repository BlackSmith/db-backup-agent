# Backup Agent Architecture

## 1. System Goal

The system will run as a standalone container and will:

- periodically discover database containers in a Docker network
- identify containers labeled `backup_agent.enabled=true`
- obtain connection metadata from labels or environment variables of target containers
- execute PostgreSQL and MariaDB backups
- store backups locally in a staging area
- synchronize backups to remote storage via `rsync` or publish them to a mounted local storage directory
- delete old backups according to a retention policy
- remain ready for future support of additional database engines and storage backends

---

## 2. Recommended Architectural Style

### Modular monolith with plugin-like adapters

This use case is best served by a modular monolith because:

- the current scope is small
- the system runs as a single service / single container
- there is no need for distributed transactions or microservices
- clear boundaries are still useful between:
  - Docker container discovery
  - database adapters
  - storage adapters
  - scheduling
  - retention
  - backup orchestration

This approach provides:

- fast MVP delivery
- low operational complexity
- straightforward future extension

---

## 3. High-Level Architecture

```text
+--------------------------------------------------------------+
|                     Backup Agent Container                   |
|--------------------------------------------------------------|
| Config Loader (ENV)                                          |
| Scheduler                                                    |
| Container Discovery (Docker API)                             |
| Metadata Resolver (labels/env)                               |
| Backup Orchestrator                                          |
|  ├─ PostgreSQL Adapter                                       |
|  ├─ MariaDB Adapter                                          |
|  ├─ Local Staging Manager                                    |
|  ├─ Manifest/Status Writer                                   |
|  ├─ Retention Manager                                        |
|  └─ Storage Adapter (rsync or mounted local directory)        |
| Logging / Metrics / Health                                   |
+--------------------------------------------------------------+

             | Docker API / mounted docker.sock
             v

+----------------------+        +----------------------+
| PostgreSQL container |        | MariaDB container    |
| labels/env metadata  |        | labels/env metadata  |
+----------------------+        +----------------------+

             |
             | network access
             v

+----------------------+
| Local backup staging |
| /backup or /data     |
+----------------------+

             |
             | rsync or mounted local directory publish
             v

+-------------------------------+
| Remote storage / NAS / volume |
+-------------------------------+
```

---

## 4. Key Architectural Decisions

### Prefer Docker API over Docker-in-Docker

Although the project description mentions Docker-in-Docker, the recommended approach is:

- mount `/var/run/docker.sock` into the backup agent container
- use Docker API or Docker CLI only for discovery and metadata reads

Benefits:

- simpler runtime model
- lower overhead
- less complexity than full DinD
- sufficient for reading metadata and connecting over the network

Risk:

- mounting the Docker socket is security-sensitive
- this deployment must be treated as trusted

If stricter isolation is required later, discovery can be replaced by:

- a restricted sidecar
- a custom discovery service
- an external inventory source

---

## 5. Core Modules

### 5.1 Config Loader

Loads and validates global configuration from environment variables:

- `BACKUP_LOCAL_STORAGE`
- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`

Storage backends may be configured independently or together.

Recommended extensions:

- `RSYNC_REMOTE_PATH`
- `LOCAL_BACKUP_DIR=/temporary_storage`
- `TZ` inherited from the process environment when available, otherwise `UTC`
- `LOG_LEVEL=info`
- `DOCKER_SOCKET_PATH=/var/run/docker.sock`

Validation rules:

- `BACKUP_TIME` is optional; when provided it must be in `HH:MM`
- when `BACKUP_TIME` is omitted, the application should use immediate-run mode instead of failing config validation
- `BACKUP_RETENTION_DAYS >= 1`
- remote sync credentials must be present when rsync publishing is enabled
- local backup directory must exist or be creatable

### 5.2 Scheduler

Responsible for triggering one backup run per day when `BACKUP_TIME` is configured, or an immediate run when it is omitted.

Recommended approach:

- use an internal scheduler inside the application
- do not rely on OS cron as the primary scheduling mechanism inside the container

Benefits:

- unified application lifecycle
- centralized logging
- easier health reporting
- simpler container operation

Scheduler behavior:

1. if `BACKUP_TIME` is configured, compute the next execution time from it
2. if `BACKUP_TIME` is omitted, trigger the backup orchestrator immediately and return without entering the daily wait loop
3. if `BACKUP_TIME` is configured, continue with the next daily execution

### 5.3 Container Discovery

Before each run:

- query Docker for running containers
- filter containers with `backup_agent.enabled=true`

Recommendation:

- avoid long-lived metadata cache
- perform discovery immediately before each run
- this naturally captures newly started or updated containers

### 5.4 Metadata Resolver

For each discovered container, resolve normalized backup metadata.

Sources:

- container labels
- container environment variables
- optional image metadata if needed later

Recommended precedence:

1. explicit `backup_agent.*` labels
2. environment variables in the target container
3. default values

Normalized output example:

```json
{
  "container_name": "postgres-app",
  "db_type": "postgresql",
  "host": "postgres",
  "port": 5432,
  "user": "app",
  "password": "***",
  "databases": ["db1", "db2"],
  "backup_all_databases": false
}
```

Recommended addition:

- `backup_agent.type=postgresql|mariadb`

While database type can be inferred from labels or image names, an explicit type is more robust.

### 5.5 Backup Orchestrator

Central coordinator for a single backup run.

Responsibilities:

- create a run ID
- trigger discovery
- resolve target metadata
- execute backups sequentially or with limited parallelism
- write a run manifest
- execute remote sync
- execute retention cleanup
- return final run status

Recommendation:

- for MVP, execute backups sequentially
- later, introduce limited parallelism such as `MAX_PARALLEL_BACKUPS=2..4`

Reason:

- reduces the risk of overloading databases or NAS storage

### 5.6 Database Adapters

#### PostgreSQL Adapter

Must support:

- single database backup
- multiple explicit databases
- all databases backup

Important clarification:

- `pg_dump` is appropriate for one database
- `pg_dumpall` is the correct tool for cluster-wide "all databases" backup

Recommended formats:

- per-database backup in PostgreSQL custom format: `*.dump`
- optional plain SQL export only if explicitly required later

For MVP, standardize on a single primary format:

- PostgreSQL: `pg_dump -Fc`
- MariaDB: compressed SQL dump

Credential handling:

- avoid exposing passwords in command-line arguments when possible
- use `PGPASSWORD` or another protected mechanism

#### MariaDB Adapter

Must support:

- single database backup
- multiple explicit databases
- all databases backup

Recommended mapping:

- one DB: `mariadb-dump dbname`
- multiple DBs: `mariadb-dump --databases db1 db2`
- all DBs: `mariadb-dump --all-databases`

Credential handling:

- do not leak passwords in logs
- prefer environment variables or temporary defaults file over direct visible CLI output where possible

### 5.7 Local Staging Manager

Responsible for local directory layout and atomic write operations.

Recommended layout:

```text
/backup/
  runs/
    2026-06-03T02-00-00Z/
      manifest.json
      postgresql/
        postgres-app/
          db1.dump
          db2.dump
      mariadb/
        mariadb-app/
          appdb.sql.gz
  latest -> /backup/runs/2026-06-03T02-00-00Z
```

Benefits:

- each run is isolated
- easier debugging
- easy synchronization to NAS
- easier restore by run ID

Recommended `manifest.json` fields:

- run ID
- start time
- end time
- list of containers
- list of databases
- file sizes
- final status: `success`, `partial`, `failed`, `sync_failed`
- error details

### 5.8 Storage Adapters

Initial implementations:

- `rsync` remote storage via `RSYNC_*`
- mounted local directory storage via `BACKUP_LOCAL_STORAGE`

The backends can be enabled independently or together.

Responsibilities:

- transfer or publish a completed run to durable storage
- return detailed status and error data
- log transfer progress and summary
- optionally retry failed upload attempts in future versions

Recommendation:

- synchronize or copy the full run directory as a unit
- do not treat individual files as separate remote transactions
- if the storage supports it, upload/copy into a temporary directory and rename after success

Recommended config extensions:

- `RSYNC_REMOTE_PATH=/backups`
- `BACKUP_LOCAL_STORAGE=/mnt/backups`
- `RSYNC_SSH_PORT=22`
- `RSYNC_OPTIONS=...`

Security note:

- `RSYNC_REMOTE_PASSWORD` is acceptable for MVP
- long term, SSH key authentication or mounted storage with external secret handling is preferred

### 5.9 Retention Manager

Retention must be separated from the backup process itself.

Recommendation:

- perform retention only after successful remote sync
- apply retention on remote storage
- optionally apply local retention as a separate policy

Policy:

- preserve backups for the last `N` days
- delete complete run directories only
- calculate retention using run timestamps rather than only filename patterns

### 5.10 Logging, Metrics, and Health

#### Logging

Provide structured logs for:

- run start
- discovered containers
- resolved metadata without secrets
- backup start and finish per target
- remote sync start and finish
- retention start and finish
- final run summary

#### Health

- liveness: process is running
- readiness: configuration valid, backup directory writable, Docker API reachable

#### Future Metrics

- `backup_runs_total`
- `backup_run_duration_seconds`
- `backup_targets_total`
- `backup_failures_total`
- `backup_last_success_timestamp`

---

## 6. Domain Model

### BackupTarget

Represents one database source derived from a container.

Fields:

- `containerId`
- `containerName`
- `dbType`
- `host`
- `port`
- `user`
- `passwordRef`
- `databases[]`
- `allDatabases`
- `labels`

### BackupRun

Represents one scheduled run.

Fields:

- `runId`
- `startedAt`
- `finishedAt`
- `status`
- `targets[]`
- `artifacts[]`
- `errors[]`

### BackupArtifact

Represents one output file.

Fields:

- `target`
- `database`
- `path`
- `size`
- `checksum`
- `format`

---

## 7. Processing Flow

### Daily Run Flow

1. Scheduler starts a run at `BACKUP_TIME`
2. Container Discovery loads containers with `backup_agent.enabled=true`
3. Metadata Resolver builds `BackupTarget` objects
4. Orchestrator validates and processes each target:
   - validate resolved metadata
   - choose the correct database adapter
   - produce backup artifacts in the staging directory
   - write results into the manifest
5. After target processing:
   - if at least one backup artifact exists, run remote sync
6. After successful remote sync:
   - execute retention cleanup
7. Write final summary and status

---

## 8. Error Handling Model

The architecture should distinguish the following scenarios.

### A. Partial Failure

Example:

- 3 containers succeed
- 1 container fails

Result:

- run status = `partial`
- remote sync still transfers successful artifacts
- errors are recorded in the manifest

### B. Fatal Failure

Examples:

- Docker API unavailable
- invalid global configuration
- staging directory cannot be created

Result:

- run status = `failed`
- remote sync is not started

### C. Remote Sync Failure

Result:

- local backup remains intact
- run status = `sync_failed`
- retention is not executed

This prevents deletion of older remote data before the new backup is safely uploaded.

---

## 9. Security Architecture

### Main Risks

1. mounting Docker socket provides high privileges
2. database passwords may leak into logs or process listings
3. rsync password in environment variables is sensitive
4. backups contain production data and may require strict protection

### Recommendations

- never log secrets
- mask sensitive values in all outputs
- move toward file-based secrets or Docker secrets when possible
- restrict access to the local backup volume
- prefer SSH key authentication for rsync transport
- consider backup encryption in a future version

---

## 10. Deployment Model

Recommended deployment:

- one `backup-agent` container
- connected to the same Docker network as database containers
- mounted Docker socket for discovery
- persistent volume for `/backup`

Topology example:

```text
Docker host
├─ backup-agent
│  ├─ /var/run/docker.sock
│  └─ /backup (volume)
├─ postgres-1
├─ mariadb-1
└─ other application containers
```

---

## 11. Extension Interfaces

To support additional database engines and storage backends later, define two internal contracts.

### DatabaseBackupProvider

Suggested methods:

- `supports(target)`
- `validate(target)`
- `backup(target, outputDir)`

Initial implementations:

- `PostgreSQLBackupProvider`
- `MariaDBBackupProvider`

### Storage Provider Interface

The current implementation still uses the historical name `RemoteStorageProvider`, but architecturally this is now a generic storage provider abstraction.

Suggested methods:

- `sync(localPath, remotePath)`
- `cleanup(retentionPolicy)`

Initial implementations:

- `RsyncStorageProvider`
- `LocalDirectoryStorageProvider`

Possible future implementations:

- `S3StorageProvider`
- `WebDAVStorageProvider`
- `SMBStorageProvider`

---

## 12. Suggested Project Structure

```text
src/
  app/
    main
    config
    scheduler
  domain/
    backup_target
    backup_run
    artifact
  services/
    orchestrator
    discovery
    metadata_resolver
    retention
    manifest
  providers/
    databases/
      postgresql
      mariadb
    storage/
      rsync
  infrastructure/
    docker
    filesystem
    logging
  interfaces/
    cli
    health
```

This keeps clear separation between:

- domain model
- orchestration logic
- infrastructure integrations
- external interfaces

---

## 13. Label and Environment Resolution Rules

The project description states that metadata may come from labels or environment variables. The following resolution model is recommended.

### PostgreSQL

Preferred labels:

- `backup_agent.pguser`
- `backup_agent.pghost`
- `backup_agent.pgpassword`
- `backup_agent.pgport`
- `backup_agent.pgdatabase`

Fallback environment variables:

- `POSTGRES_USER`
- `POSTGRES_HOST`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `POSTGRES_DB` or `POSTGRES_DATABASE`

### MariaDB

Preferred labels:

- `backup_agent.mariadbuser`
- `backup_agent.mariadbpassword`
- `backup_agent.mariadbhost`
- `backup_agent.mariadbport`
- `backup_agent.mariadbdatabase`

Fallback environment variables:

- `MARIADB_USER`
- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `MARIADB_HOST`
- `MARIADB_PORT`
- `MARIADB_DATABASE`

### Database List Parsing

- split by comma
- trim whitespace
- empty or missing database list means `allDatabases=true`

---

## 14. Backup Command Guidance

The project description includes example commands, but the implementation should follow the correct backup semantics.

### PostgreSQL

- single database: `pg_dump -Fc`
- all databases: `pg_dumpall`

Reason:

- `pg_dump` backs up one database
- `pg_dumpall` is the correct tool for cluster-wide backup

### MariaDB

- single / multiple databases: `mariadb-dump`
- all databases: `mariadb-dump --all-databases`

This distinction should be explicit in the implementation to avoid incorrect full-instance backup behavior.

---

## 15. Delivery Phases

### Phase 1: MVP

- single container deployment
- internal scheduler
- Docker discovery via mounted socket
- PostgreSQL and MariaDB adapters
- rsync storage provider
- local staging directory
- retention support
- structured logs
- `manifest.json`

### Phase 2: Hardening

- improved secret handling
- retry policy
- artifact checksums
- health endpoints
- metrics
- configurable parallelism
- explicit `backup_agent.type`

### Phase 3: Extensibility

- additional remote storage backends
- additional database engines
- restore workflow
- backup encryption
- notification hooks

---

## 16. Final Recommendation

The recommended target architecture is:

### Single-process modular backup agent

Characteristics:

- runs as one container
- uses Docker API for discovery
- contains an internal scheduler
- uses plugin-like adapters for databases and storage providers
- stores backups in isolated per-run directories
- synchronizes completed runs via rsync
- executes retention only after successful sync
- remains extensible without requiring a microservices transition

## 17. Implementation Status

The repository currently implements the phase-1 MVP architecture in Python 3.13.

Implemented modules include:

- configuration loading and scheduler bootstrap
- Docker discovery and metadata resolution
- PostgreSQL and MariaDB backup providers
- local staging and JSON manifest generation
- rsync synchronization and retention cleanup
- mounted local directory storage via `BACKUP_LOCAL_STORAGE`
- structured logging, health checks, and run summaries
- containerization and example Docker Compose deployment

This means the architecture document remains valid as the target design, but the codebase has now progressed from planning into a working MVP implementation.
