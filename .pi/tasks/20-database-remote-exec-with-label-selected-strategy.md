# Task 20: Database Remote Exec Strategy with Label-Selected Method and Local Fallback

## Goal
Add a database backup execution strategy that can run dump commands inside the target database container through the Docker API, stream the resulting backup into the backup-agent staging directory, and support explicit per-container method selection via label.

This task applies to both supported engines:

- PostgreSQL
- MariaDB

## User-requested behavior

- Allow using the dump utility from the remote database container instead of always using the local runtime tool.
- Make the execution method selectable explicitly by label.
- Default behavior should first try remote container exec and then fall back to local execution if remote exec fails.
- If possible, perform gzip compression directly inside the remote container before streaming the result back.

## Motivation

The project already hit a real PostgreSQL client/server version mismatch when local `pg_dump` was older than the target PostgreSQL server.

Running the dump tool inside the database container can:

- align tool and server versions more naturally
- reduce packaging sensitivity in the backup-agent image
- provide a resilient execution path even when the local runtime toolchain lags behind

The same architectural approach should be available for MariaDB as well, using the engine-appropriate dump utility from the target container.

## Scope

- Introduce a database dump execution strategy abstraction that supports at least:
  - remote container exec
  - local command execution
  - default auto mode: remote exec first, local fallback second
- Add explicit label-based strategy selection for supported database targets.
- Extend the Docker integration layer so the agent can execute commands in a target container and capture:
  - stdout stream
  - stderr stream
  - exit code
- Stream remote command stdout into the local staging artifact file.
- Keep failures secret-safe and preserve actionable error reporting.
- If available in the remote container, support gzip compression in the remote execution path.

## Required behavior

### Strategy label

Add an explicit label for dump execution strategy:

- `backup_agent.dump_method=auto|exec|local`

Semantics:

- `auto`:
  - try container exec first
  - if exec path cannot be used or fails, fall back to local execution
- `exec`:
  - require remote container exec path
  - do not silently fall back to local
- `local`:
  - use the current local execution behavior only

### Default behavior

If the label is not present, default to:

- `auto`

### Remote exec implementation

For supported targets, the agent should be able to use Docker exec to run inside the target container.

Representative commands:

#### PostgreSQL

- single database:
  - `pg_dump -Fc ...`
- all databases:
  - `pg_dumpall ...`

#### MariaDB

- single database:
  - `mariadb-dump dbname`
- multiple databases:
  - `mariadb-dump --databases db1 db2`
- all databases:
  - `mariadb-dump --all-databases`

The resulting stdout should be streamed into a file under the local staging run directory.

### Remote gzip preference

If possible, support remote compression, for example by invoking a shell pipeline inside the target container.

Examples of acceptable intent:

- PostgreSQL custom or SQL dump piped through `gzip -c`
- MariaDB SQL dump piped through `gzip -c`

However:

- do not assume every container has `gzip`
- if gzip is unavailable, the exec path should still be able to proceed without remote compression unless the chosen implementation explicitly documents another fallback
- output naming and manifest format metadata must remain correct

### Error handling

- In `auto` mode, remote exec failure should be captured and then local execution should be attempted.
- The final run errors should make it clear which path failed.
- Secret-safe logging must be preserved.
- Partial or corrupt artifact files from failed exec attempts must be removed before fallback or final failure return.

## Architectural constraints

- Keep the current metadata resolution and orchestrator architecture intact unless a small extension is necessary.
- Support PostgreSQL and MariaDB only; do not broaden this task beyond the currently supported engines.
- Keep the local execution path working for both engines.
- The Docker API client is currently discovery-only; this task will require extending it to support exec operations.
- Avoid coupling the implementation to a shell-only approach unless needed for gzip support.

## Design recommendations

### 1. Add a small database dump execution strategy layer

Instead of embedding all branching directly inside each provider, introduce a small internal strategy concept for dump execution.

Reason:

- isolates exec-vs-local complexity
- keeps provider orchestration readable
- makes fallback logic testable
- allows the same policy model for PostgreSQL and MariaDB

### 2. Keep strategy selection close to provider execution

Metadata may carry the explicit method label, but the actual decision and fallback behavior should stay near provider execution.

### 3. Extend Docker API carefully

Add only the minimum exec support required:

- create exec instance
- start exec session
- capture output stream
- inspect exec result / exit code if needed

### 4. Treat gzip as opportunistic, not mandatory

Remote gzip is useful, but the backup must still work if the target database container does not include `gzip`.

## Acceptance criteria

- PostgreSQL and MariaDB targets support an explicit label-based dump method override.
- The shared label is `backup_agent.dump_method`.
- Default behavior is `auto`, meaning remote exec first and local fallback second.
- `exec` mode uses remote container execution only.
- `local` mode preserves current behavior.
- Remote exec stdout is written into the local staging artifact path.
- Failed remote exec attempts do not leave corrupt artifact files behind.
- Secret-safe logging remains intact.
- Tests cover strategy selection and fallback behavior for PostgreSQL and MariaDB.
- Full test suite passes:

```bash
python -m unittest discover -s tests
```

## Likely files to inspect

- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/services/discovery.py`
- `src/backup_agent/services/metadata_resolver.py`
- `src/backup_agent/domain/backup_target.py`
- `src/backup_agent/providers/databases/postgresql.py`
- `src/backup_agent/providers/databases/mariadb.py`
- `src/backup_agent/providers/databases/base.py`
- `tests/test_database_backup_providers.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`
- `tests/test_health_and_orchestrator.py`

## Suggested verification

- Focused unit tests for PostgreSQL and MariaDB strategy selection and fallback
- Focused Docker exec client tests if introduced
- Full regression suite
- If environment permits, real validation against PostgreSQL and MariaDB containers where remote exec can be exercised
