# Task 21 - Generic `backup_agent.*` Labels and MySQL/MariaDB Environment Alias Support: implementation record

## Implemented

- Introduced generic metadata labels for shared backup fields:
  - `backup_agent.user`
  - `backup_agent.password`
  - `backup_agent.host`
  - `backup_agent.port`
  - `backup_agent.database`
- Kept `backup_agent.type` as an explicit override for ambiguous deployments.
- Preserved compatibility with the existing engine-specific legacy labels during migration.
- Updated metadata resolution so PostgreSQL inference still uses `POSTGRES_*` env variables.
- Updated MariaDB/MySQL metadata resolution so both `MARIADB_*` and `MYSQL_*` env variables are accepted.
- Preserved default-port fallback behavior and invalid-port validation.
- Kept discovery and backup provider execution behavior unchanged beyond metadata interpretation.

## Changed files

- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`

## Verification

- Ran focused metadata-resolution tests successfully:
  - `python -m unittest tests.test_docker_discovery_and_metadata_resolution`
- Ran the full regression suite successfully:
  - `python -m unittest discover -s tests`
- Ran the application against the live Docker-backed runtime using the mounted Docker socket and `sudo -E`:
  - `sudo -E env PYTHONPATH=src BACKUP_LOCAL_STORAGE=/tmp/backup-agent-validate-storage LOCAL_BACKUP_DIR=/tmp/backup-agent-validate-staging DOCKER_SOCKET_PATH=/var/run/docker.sock BACKUP_TIME=02:00 BACKUP_RETENTION_DAYS=7 TZ=UTC LOG_LEVEL=INFO python -m backup_agent --run-once`
- Verified the live runtime backup succeeded against both available containers:
  - `backup_agent-postgres-1`
  - `backup_agent-mariadb-1`

## Notes

- Generic labels are now the preferred metadata surface, while legacy engine-specific labels remain accepted for compatibility.
- The MariaDB provider path now accepts both `MARIADB_*` and `MYSQL_*` environment variable families.
