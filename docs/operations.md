# Operations and Run Lifecycle

This document explains what happens during a backup run, what files are created, and how status is reported.

## CLI modes

Backup Agent supports two CLI modes.

### Run once

```bash
backup-agent --run-once
```

Executes a single backup cycle and exits.

### Schedule

```bash
backup-agent --schedule
```

Starts the internal daily scheduler and waits for the next configured `BACKUP_TIME`.

## Run lifecycle

A normal run executes these phases.

### 1. Configuration validation

The app validates environment variables and logs a `config_validated` event.

### 2. Run creation

A unique run ID is generated in UTC.

Example shape:

```text
20260605T170102Z-97ada144
```

### 3. Local staging initialization

The staging manager creates:

```text
<LOCAL_BACKUP_DIR>/runs/<run-id>/
```

and updates the `latest` pointer in the local staging root.

### 4. Discovery

The application inspects running Docker containers and filters them to enabled targets.

### 5. Metadata resolution

Each eligible container is normalized into a `BackupTarget`.

### 6. Backup execution

The correct provider is selected by `db_type`.

#### PostgreSQL artifacts

Possible artifact formats:

- `postgresql-custom` → `.dump`
- `postgresql-sql-gzip` → `.sql.gz`

#### MariaDB artifacts

Produced format:

- `mariadb-sql` → `.sql`

#### Filesystem / archive artifacts

Produced format:

- `filesystem-tar-gzip` → `.tar.gz`

For filesystem/archive targets, the selected container directories are copied into local temporary staging first and then archived into a publishable artifact.

### 7. Manifest generation

A JSON manifest is written to:

```text
<run-dir>/manifest.json
```

### 8. Publish to storage backend(s)

Depending on config, the run is published to:

- local mounted storage
- rsync remote storage
- FTP / FTPS remote storage
- any combination of the above

### 9. Retention cleanup

Retention runs against the configured published storage and, when applicable, local mounted storage.

### 10. Staging cleanup

If publication succeeds fully, the local staging run directory is removed.

If publication fails, staging remains on disk for inspection.

## Status values

The system uses these run statuses:

- `pending`
- `running`
- `success`
- `partial`
- `failed`
- `sync_failed`

## Manifest contents

`manifest.json` includes:

- `run_id`
- `started_at`
- `finished_at`
- `status`
- `targets`
- `artifacts`
- `errors`

### Target fields

Each target includes:

- `container_id`
- `container_name`
- `db_type`
- `host`
- `port`
- `user`
- `databases`
- `directories`
- `all_databases`

### Artifact fields

Each artifact includes:

- `container_id`
- `container_name`
- `db_type`
- `database`
- `path`
- `size`
- `checksum`
- `format`

### Error fields

Each error includes:

- `source`
- `message`
- `command`
- `returncode`
- `stderr`
- `container_id`
- `container_name`
- `database`
- `output_path`

## Storage behavior

### Mounted local storage backend

Successful runs are published into:

```text
<BACKUP_LOCAL_STORAGE>/runs/<run-id>/
```

and the backend updates:

```text
<BACKUP_LOCAL_STORAGE>/latest
```

### Rsync backend

The provider publishes staged content with rsync and uses:

- `--delete-delay`
- `--delay-updates`
- a temporary password file

Retention is implemented by building a temporary retained-runs view and synchronizing it back to the remote root.

The remote rsync destination is the configured `remote_root` with the run ID appended directly; completed run directories are not nested under an additional `runs/` prefix in the remote URL.

### FTP / FTPS backend

The FTP provider publishes the full run directory under:

```text
<FTP_REMOTE_PATH>/runs/<run-id>/
```

It also updates a simple `latest` marker file at:

```text
<FTP_REMOTE_PATH>/latest
```

Retention is remote-state-driven:

- the provider inventories remote run directories
- it reads each remote `manifest.json` when available
- it keeps unreadable or ambiguous runs rather than deleting them blindly
- it deletes only expired remote run directories
- it refreshes `latest` after cleanup

FTP mode uses standard FTP; FTPS mode uses explicit TLS via `ftplib.FTP_TLS`.

## Health checks

Two health interfaces are implemented in code.

### Liveness

`check_liveness()` always returns healthy if the process can execute the check.

### Readiness

`check_readiness()` verifies:

- validated configuration
- backup storage directory writeability
- local staging directory writeability
- Docker API reachability

## Logging

The application emits structured `key=value` logs.

Examples of lifecycle events:

- `config_validated`
- `application_start`
- `run_start`
- `discovery_complete`
- `target_backup_start`
- `target_backup_finish`
- `sync_finish`
- `retention_start`
- `retention_finish`
- `run_summary`
- `run_error`

Secret-like fields are masked in logs.

## Example run tree

```text
/.temporary_storage/
├── latest
└── runs/
    └── 20260605T170102Z-97ada144/
        ├── manifest.json
        ├── postgresql/
        │   └── backup_agent-postgres-1/
        │       ├── postgres.dump
        │       └── postgres.sql.gz
        └── mariadb/
            └── backup_agent-mariadb-1/
                └── mariadb.sql
```
