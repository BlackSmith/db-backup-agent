# Coder Handoff for Task 17

## Objective
Implement default database port fallbacks in metadata resolution:

- PostgreSQL -> `5432`
- MariaDB -> `3306`

This should apply only when no explicit port is provided.

## Primary target

Update:

- `src/backup_agent/services/metadata_resolver.py`

## Expected behavior

### PostgreSQL

If neither of these is present:

- `backup_agent.pgport`
- `POSTGRES_PORT`

then resolved PostgreSQL targets should use port `5432`.

### MariaDB

If neither of these is present:

- `backup_agent.mariadbport`
- `MARIADB_PORT`

then resolved MariaDB targets should use port `3306`.

## Important constraints

- Do not change discovery behavior.
- Do not change backup provider behavior.
- Keep explicit ports taking precedence.
- Keep invalid explicit ports failing with `MetadataResolutionError`.
- Keep the change localized to resolver logic and tests.

## Recommended implementation approach

The smallest safe change is to introduce engine-specific fallback for the port before `_require_value(...)` turns missing port metadata into a validation error.

A reasonable shape is:

- keep `_select_value(...)` for explicit port lookup
- if it returns `None`, inject an engine-specific default value for the port field
- continue using the existing `_parse_port(...)` validation path

That preserves current behavior for explicit invalid values while allowing missing ports to resolve cleanly.

## Tests to update

Most likely file:

- `tests/test_docker_discovery_and_metadata_resolution.py`

Add or update tests for:

1. PostgreSQL target without explicit port -> resolves to `5432`
2. MariaDB target without explicit port -> resolves to `3306`
3. Explicit port still overrides the default
4. Invalid explicit port still fails

## Acceptance checklist

- [ ] PostgreSQL default port fallback works
- [ ] MariaDB default port fallback works
- [ ] Explicit ports still win
- [ ] Invalid explicit ports still fail
- [ ] Full test suite passes with `python -m unittest discover -s tests`

## Suggested verification

Run focused resolver tests first, then the full suite:

```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution
python -m unittest discover -s tests
```
