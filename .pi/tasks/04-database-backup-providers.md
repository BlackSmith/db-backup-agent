# Task 04: Database Backup Providers

## Goal
Implement PostgreSQL and MariaDB backup providers behind a shared provider interface.

## Scope
- Define the `DatabaseBackupProvider` contract
- Implement `PostgreSQLBackupProvider`
- Implement `MariaDBBackupProvider`
- Support single database, multiple databases, and all databases modes
- Return artifact metadata for each successful backup output

## Required behavior
### PostgreSQL
- single DB: use `pg_dump -Fc`
- multiple DBs: run one `pg_dump -Fc` per database
- all DBs: use `pg_dumpall`

### MariaDB
- single DB: use `mariadb-dump`
- multiple DBs: use `mariadb-dump --databases ...`
- all DBs: use `mariadb-dump --all-databases`

## Deliverables
- Shared provider interface
- PostgreSQL provider implementation
- MariaDB provider implementation
- Secret-safe command execution wrappers
- Provider result model with status, artifacts, and errors

## Constraints
- Do not leak passwords into logs
- Avoid exposing credentials in visible command arguments where practical
- Keep command-building logic testable

## Acceptance criteria
- Providers can back up a normalized `BackupTarget`
- Output artifacts are created in a caller-provided directory
- Failures are returned with structured error data
- PostgreSQL "all databases" uses `pg_dumpall`, not `pg_dump`
- MariaDB supports single, multiple, and all-databases scenarios

## Suggested notes for implementer
- The exact artifact naming convention should align with the staging/manifest task
- If necessary, add small abstractions around process execution for easier testing
