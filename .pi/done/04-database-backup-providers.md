# Task 04 - Database Backup Providers: implementation record

## Implemented

- Defined a shared database provider contract that returns structured results.
- Added provider execution result models:
  - `BackupProviderResult`
  - `BackupProviderError`
  - `CommandResult`
- Added a small command execution abstraction to keep process invocation testable.
- Implemented `PostgreSQLBackupProvider`:
  - single database backups with `pg_dump -Fc`
  - multiple databases with one `pg_dump -Fc` per database
  - all-databases mode with `pg_dumpall`
- Implemented `MariaDBBackupProvider`:
  - single database backups with `mariadb-dump`
  - multiple databases with one `mariadb-dump --databases ...` call
  - all-databases mode with `mariadb-dump --all-databases`
- Added secret-safe handling for credentials:
  - PostgreSQL password via `PGPASSWORD`
  - MariaDB password via temporary defaults file
- Added artifact metadata creation for successful outputs.
- Extended `BackupTarget` to carry resolved secret values needed by providers.
- Added provider tests for:
  - single-database backup
  - multi-database backup
  - all-databases mode
  - failure reporting

## Changed files

- `src/backup_agent/domain/backup_target.py`
- `src/backup_agent/providers/databases/base.py`
- `src/backup_agent/providers/databases/postgresql.py`
- `src/backup_agent/providers/databases/mariadb.py`
- `src/backup_agent/providers/databases/__init__.py`
- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_database_backup_providers.py`

## Verification

- Installed the project in editable mode:
  - `python -m pip install -e .`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Open issues / follow-ups

- The current MariaDB multiple-database path performs one `mariadb-dump --databases ...` call and records one combined artifact; if later tasks require per-database artifact splitting, this can be adjusted.
- Providers currently rely on external binaries being present in the runtime image/container.
- Full orchestration and manifest writing are still pending later tasks.
