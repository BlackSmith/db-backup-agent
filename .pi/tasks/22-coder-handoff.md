# Coder Handoff for Task 22

## Objective
Implement PostgreSQL output-format selection through `backup_agent.dump_format`, supporting:

- `binary`
- `sql_gzip`
- `both`
- missing label => `both`

## Primary target

Extend the PostgreSQL backup provider to produce one or both artifact variants without changing MariaDB behavior.

## Recommended implementation order

1. Update `src/backup_agent/providers/databases/postgresql.py`
2. Add any minimal shared helper support only if it keeps the PostgreSQL provider cleaner
3. Update PostgreSQL provider tests in `tests/test_database_backup_providers.py`
4. Update any targeted orchestrator/log tests only if the artifact-count expectations change
5. Update docs only if they describe PostgreSQL artifact formats or defaults
6. Run focused tests and then the full suite
7. Write `.pi/done/22-postgresql-selectable-output-formats.md`

## Label behavior

Support:

- `backup_agent.dump_format=binary|sql_gzip|both`

Expected semantics:

- missing label => `both`
- `binary` => PostgreSQL custom-format dump artifacts only
- `sql_gzip` => gzip-compressed plain SQL artifacts only
- `both` => both artifact variants

## Design caveat for `all_databases`

PostgreSQL `pg_dumpall` produces plain SQL and does not provide a single equivalent custom-format binary dump.

Recommended implementation rule:

- if `target.all_databases` is true:
  - allow only `sql_gzip`
  - treat explicit `binary` or `both` as an actionable provider/configuration error

Do not silently downgrade `both` to SQL-only without surfacing that decision.

## Implementation guidance

### Binary artifacts

Continue using the current PostgreSQL custom-format dump behavior for explicit databases.

### SQL gzip artifacts

Produce gzip-compressed SQL output.

Acceptable shapes include:

- direct SQL export to a temporary file followed by gzip
- streaming gzip if that keeps the implementation small and testable

### Task 20 integration

Keep format selection orthogonal to dump method selection:

- format selection decides what artifacts to produce
- dump method selection decides whether each artifact is attempted via remote exec or local execution

Do not redesign the dump-method strategy in this task.

## Constraints

- Keep changes localized.
- Do not modify MariaDB behavior.
- Preserve secret-safe execution and logging.
- Preserve current artifact semantics unless the new format requirement explicitly changes them.
- Be explicit about `all_databases` limitations.

## Acceptance checklist

- [ ] PostgreSQL supports `backup_agent.dump_format`
- [ ] Missing label defaults to `both`
- [ ] `binary` works for explicit databases
- [ ] `sql_gzip` works for explicit databases
- [ ] `both` produces both formats for explicit databases
- [ ] `all_databases` applies the documented caveat correctly
- [ ] Tests cover format-selection behavior
- [ ] Full suite passes with `python -m unittest discover -s tests`

## Suggested verification

```bash
python -m unittest tests.test_database_backup_providers
python -m unittest discover -s tests
```

If possible, also validate against a live PostgreSQL target and verify the produced artifact set matches the chosen label.
