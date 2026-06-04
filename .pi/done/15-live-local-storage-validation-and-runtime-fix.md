# Task 15 - Live Local-Storage Validation and Runtime Fix: implementation record

## Implemented

- Wired the real CLI/runtime path so `backup-agent` now constructs and uses a live `BackupOrchestratorService` instead of the previous no-op placeholder path.
- Added runtime bootstrap composition in `src/backup_agent/app/main.py` using:
  - `DockerApiClient`
  - `DockerContainerDiscovery`
  - `ContainerMetadataResolver`
  - `build_storage_provider(config)`
- Fixed `src/backup_agent/services/discovery.py` to import `DockerApiClient` from the correct package path.
- Fixed command execution environment merging in `src/backup_agent/providers/databases/base.py` so database backup providers inherit the full process environment instead of replacing it with a minimal env containing only provider-specific variables.
- Verified the live local-storage backup run against the real PostgreSQL and MariaDB containers discovered through `/var/run/docker.sock`.
- Confirmed published backup artifacts in `/workspaces/backup_agent/storage`.

## Live verification performed

### 1. Live Docker socket inspection

Used a small Python helper through the mounted Docker socket to list running containers and inspect the backup targets.

Observed backup targets:

- PostgreSQL container: `backup_agent-postgres-1`
- MariaDB container: `backup_agent-mariadb-1`

### 2. Runtime dependencies installed for the live run

The host container initially lacked the database client tools required for backup execution. I installed the needed packages with:

```bash
sudo apt-get update
sudo apt-get install -y postgresql-client mariadb-client rsync
```

### 3. Live backup command

The successful live backup was executed with:

```bash
sudo -E env PYTHONPATH=/workspaces/backup_agent/src \
  BACKUP_LOCAL_STORAGE=/workspaces/backup_agent/storage \
  LOCAL_BACKUP_DIR=/workspaces/backup_agent/.temporary_storage \
  DOCKER_SOCKET_PATH=/var/run/docker.sock \
  BACKUP_RETENTION_DAYS=7 \
  BACKUP_TIME=02:00 \
  TZ=UTC \
  LOG_LEVEL=info \
  python3 - <<'PY'
from backup_agent.app.config import AppConfig
from backup_agent.app.main import build_orchestrator
cfg = AppConfig.from_env()
orchestrator = build_orchestrator(cfg)
run = orchestrator.run_once()
print(run.status)
print(len(run.targets), len(run.artifacts), len(run.errors))
PY
```

Result:

- `RUN_STATUS success`
- `TARGETS 2`
- `ARTIFACTS 2`
- `ERRORS 0`

### 4. Published output tree

Final published tree under `/workspaces/backup_agent/storage`:

```text
/workspaces/backup_agent/storage
/workspaces/backup_agent/storage/latest
/workspaces/backup_agent/storage/runs
/workspaces/backup_agent/storage/runs/.tmp
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/mariadb
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/mariadb/backup_agent-mariadb-1
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/mariadb/backup_agent-mariadb-1/mariadb.sql
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/postgresql
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/postgresql/backup_agent-postgres-1
/workspaces/backup_agent/storage/runs/20260604T071426Z-1f4cd120/postgresql/backup_agent-postgres-1/postgres.dump
```

`latest` points to:

- `runs/20260604T071426Z-1f4cd120`

### 5. Artifact confirmation

Confirmed live artifacts:

- PostgreSQL: `postgres.dump`
- MariaDB: `mariadb.sql`

## Verification

- Ran focused unit tests successfully after the fix:
  - `python -m unittest tests.test_bootstrap tests.test_config_and_scheduler tests.test_health_and_orchestrator tests.test_storage_backend_selection`
- Ran the full regression suite successfully:
  - `python -m unittest discover -s tests`

## Notes / follow-ups

- The live run uncovered a real runtime defect in command execution environment handling; that defect has been fixed in `src/backup_agent/providers/databases/base.py`.
- The live environment required host-side installation of `postgresql-client` and `mariadb-client` to make the backup utilities available in this shell context.
- Temporary live staging data existed from the failed first attempt under `/workspaces/backup_agent/.temporary_storage`; the final successful run was verified separately.
