# Task 17: Default Database Port Fallbacks

## Goal
Add default port fallback behavior for PostgreSQL and MariaDB targets so backup metadata resolution no longer requires the database port to be explicitly provided when the standard engine port should be used.

## User request this task must satisfy

- Set default database ports for PostgreSQL and MariaDB.

## Background

The current metadata resolver requires the database port to be explicitly present in labels or environment variables.

This is unnecessarily strict for common deployments because:

- PostgreSQL typically uses port `5432`
- MariaDB typically uses port `3306`

If the port is omitted but all other required metadata is present, the resolver should fall back to the standard engine-specific default instead of failing metadata validation.

## Scope

- Update metadata resolution so PostgreSQL defaults to port `5432` when no explicit port is supplied.
- Update metadata resolution so MariaDB defaults to port `3306` when no explicit port is supplied.
- Keep explicit non-empty port values taking precedence.
- Keep invalid explicit port values failing validation.
- Add or update tests covering default-port fallback behavior.

## Required behavior

### PostgreSQL

If a PostgreSQL target resolves successfully except that no explicit port is present in:

- `backup_agent.pgport`
- `POSTGRES_PORT`

then the resolver must use:

- `5432`

### MariaDB

If a MariaDB target resolves successfully except that no explicit port is present in:

- `backup_agent.mariadbport`
- `MARIADB_PORT`

then the resolver must use:

- `3306`

### Explicit values

If an explicit port is provided, it must still take precedence.

### Invalid explicit values

If an explicit port is present but invalid, resolution must still fail with a metadata validation error.

## Deliverables

- Metadata resolver update for engine-specific default ports.
- Tests covering:
  - PostgreSQL default port fallback
  - MariaDB default port fallback
  - explicit port precedence
  - invalid explicit port rejection
- A completion note under:
  - `.pi/done/17-default-database-port-fallbacks.md`

## Constraints

- Keep implementation localized.
- Do not change backup provider execution behavior.
- Do not change discovery behavior.
- Do not weaken validation for malformed explicit port values.
- Prefer small resolver-side logic rather than broad config changes.

## Acceptance criteria

- A PostgreSQL target with no explicit port resolves to `5432`.
- A MariaDB target with no explicit port resolves to `3306`.
- An explicit PostgreSQL or MariaDB port still overrides the default.
- An invalid explicit port still raises `MetadataResolutionError`.
- Tests pass with:

```bash
python -m unittest discover -s tests
```

## Suggested implementation notes

- The smallest change is likely in `ContainerMetadataResolver._build_target(...)` or a small engine-specific fallback helper invoked before `_require_value(...)` for the port field.
- Keep user/host/password requirements unchanged.
- Be explicit in tests that "missing port" is different from "invalid provided port".

## Likely files to inspect

- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`

## Suggested verification

- Add focused resolver tests first.
- Then run the full suite:

```bash
python -m unittest discover -s tests
```
