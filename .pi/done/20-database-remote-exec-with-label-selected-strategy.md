# Task 20 - Database Remote Exec Strategy with Label-Selected Method and Local Fallback: implementation record

## Implemented

- Added a shared dump execution strategy label: `backup_agent.dump_method`.
- Implemented database dump execution strategy support for both supported engines:
  - PostgreSQL
  - MariaDB
- Added Docker exec support to the Docker API client so the app can execute commands inside a target container.
- Implemented remote-first execution with local fallback when `backup_agent.dump_method=auto`.
- Implemented `exec` mode that requires remote execution.
- Preserved `local` mode behavior.
- Added remote command streaming into the local staging artifact path.
- Preserved secret-safe error reporting and cleanup of temporary partial files.
- Wired the runtime bootstrap to pass the Docker client into the database providers.

## Changed files

- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/providers/databases/base.py`
- `src/backup_agent/providers/databases/postgresql.py`
- `src/backup_agent/providers/databases/mariadb.py`
- `src/backup_agent/app/main.py`
- `tests/test_database_backup_providers.py`

## Verification

- Ran focused provider tests successfully:
  - `python -m unittest tests.test_database_backup_providers`
- Ran the full regression suite successfully:
  - `python -m unittest discover -s tests`
- Ran the application against the live Docker-backed runtime using the mounted Docker socket and `sudo -E`:
  - `sudo -E env PYTHONPATH=src BACKUP_LOCAL_STORAGE=/tmp/backup-agent-validate-storage LOCAL_BACKUP_DIR=/tmp/backup-agent-validate-staging DOCKER_SOCKET_PATH=/var/run/docker.sock BACKUP_TIME=02:00 BACKUP_RETENTION_DAYS=7 TZ=UTC LOG_LEVEL=INFO python -m backup_agent --run-once`
- Verified the live runtime backup succeeded against both available containers:
  - `backup_agent-postgres-1`
  - `backup_agent-mariadb-1`

## Notes

- The implementation prefers remote exec when `backup_agent.dump_method=auto`, but falls back to the local runtime execution path if the remote exec path fails.
- Remote gzip was left as a future follow-up; the current implementation streams raw dump output and keeps the artifact path clean.
