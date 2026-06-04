# Task 22: PostgreSQL Selectable Output Formats via Label

## Goal
Allow PostgreSQL targets to choose the backup output format through a label, with support for:

- PostgreSQL binary custom dump
- gzip-compressed plain SQL export
- both formats together

If the format is not explicitly specified, PostgreSQL exports should produce both formats by default.

## User-requested behavior

The user wants PostgreSQL targets to be configurable via label so they can choose whether to export as:

- binary dump
- gzip-compressed plaintext SQL file
- both

If no label is present, the system should export both formats.

## Proposed label

Use a generic label name consistent with the current metadata model:

- `backup_agent.dump_format=binary|sql_gzip|both`

Recommended semantics:

- `binary`
  - create only PostgreSQL custom-format dump artifacts
- `sql_gzip`
  - create only gzip-compressed SQL artifacts
- `both`
  - create both artifact variants
- missing label
  - default to `both`

## Scope

- Extend PostgreSQL backup provider behavior to honor `backup_agent.dump_format`.
- Preserve current PostgreSQL credential handling and execution strategy semantics from Task 20.
- Keep the implementation localized to PostgreSQL backup behavior, related tests, and any necessary documentation.
- Do not change MariaDB behavior in this task.

## Format definitions

### Binary format

Use PostgreSQL custom format, equivalent to current per-database `pg_dump -Fc` behavior.

Recommended artifact naming:

- per database: `*.dump`

### SQL gzip format

Produce gzip-compressed plain SQL.

Recommended artifact naming:

- per database: `*.sql.gz`

For PostgreSQL custom-format dumps, do not apply additional gzip compression in this task.

## Important design caveat: `all_databases`

PostgreSQL cluster-wide backup uses `pg_dumpall`, which produces plain SQL and does not have a direct equivalent to a single PostgreSQL custom-format binary dump.

That means the format-selection behavior must define an explicit rule for `all_databases=True`.

### Recommended rule

- For single database or explicit database lists:
  - support `binary`, `sql_gzip`, and `both`
- For `all_databases=True`:
  - support only `sql_gzip`
  - if `binary` or `both` is explicitly requested, fail with an actionable provider/configuration error explaining that PostgreSQL cluster-wide backup cannot be emitted as a single binary custom dump

Reason:

- avoids silent degradation
- keeps user intent explicit
- matches PostgreSQL tool semantics accurately

## Execution-strategy interaction

This task should work with the current Task 20 execution model:

- `backup_agent.dump_method=auto|exec|local`

Recommended combination behavior:

- format selection decides what artifacts must be produced
- execution strategy decides whether each artifact is attempted through remote exec first or local execution first according to the current mode

Do not redesign Task 20 behavior here; integrate with it.

## Acceptance criteria

- PostgreSQL supports `backup_agent.dump_format=binary|sql_gzip|both`
- Missing label defaults to `both`
- Single-database exports can produce:
  - binary only
  - SQL gzip only
  - both
- Multi-database explicit lists can produce both requested formats per database or per command as defined by the provider design
- `all_databases=True` enforces the documented caveat and does not silently pretend binary output exists
- Artifact naming and manifest metadata remain correct
- Tests cover format selection behavior and `all_databases` caveat
- Full suite passes:

```bash
python -m unittest discover -s tests
```

## Likely files to inspect

- `src/backup_agent/providers/databases/postgresql.py`
- `src/backup_agent/providers/databases/base.py`
- `tests/test_database_backup_providers.py`
- `tests/test_health_and_orchestrator.py`
- `README.md` if PostgreSQL output formats are documented there

## Suggested verification

- Focused PostgreSQL provider tests for format selection
- Full regression suite
- If environment permits, a real PostgreSQL run covering at least one explicit database and verifying the expected artifacts are written
