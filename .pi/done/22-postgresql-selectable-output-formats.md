# Task 22 - PostgreSQL Selectable Output Formats via Label: implementation record

## Implemented

- Added PostgreSQL output-format selection through `backup_agent.dump_format`.
- Supported values:
  - `binary`
  - `sql_gzip`
  - `both`
- Preserved the default behavior for missing label values:
  - explicit PostgreSQL databases default to `both`
- Kept MariaDB behavior unchanged.
- Enforced the PostgreSQL `all_databases=True` caveat:
  - `sql_gzip` is supported
  - `binary` and `both` return an actionable provider error
- Preserved the current dump-method strategy so format selection remains orthogonal to `backup_agent.dump_method`.
- Kept secret handling and artifact cleanup intact.

## Changed files

- `src/backup_agent/providers/databases/postgresql.py`
- `tests/test_database_backup_providers.py`
- `.pi/context.md`
- `.pi/architecture.md`

## Verification

- Ran focused PostgreSQL provider tests successfully:
  - `python -m unittest tests.test_database_backup_providers -v`
- Ran the full regression suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- PostgreSQL cluster-wide backups intentionally do not pretend a single custom-format binary dump exists.
- The implementation keeps the existing PostgreSQL execution model intact while selecting artifact formats via label.
