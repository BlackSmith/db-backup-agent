# Task 19: PostgreSQL Client Version Compatibility

## Goal
Update the backup-agent runtime so it ships the newest practical packaged `pg_dump` / `pg_dumpall` version available for the chosen image strategy, eliminating the confirmed PostgreSQL client/server version mismatch and maximizing compatibility with newer PostgreSQL servers.

## User-reported failure

A real PostgreSQL backup failed with:

```text
pg_dump: error: aborting because of server version mismatch
pg_dump: detail: server version: 17.10; pg_dump version: 15.18 (Debian 15.18-0+deb12u1)
```

## Root cause

The current runtime image is based on `python:3.13-slim-bookworm` and installs Debian's default `postgresql-client` package.

On bookworm, that currently provides PostgreSQL client tools from the 15.x line. Those tools cannot reliably back up a PostgreSQL 17 server, and `pg_dump` aborts with a version mismatch.

This is a runtime packaging compatibility issue, not a metadata-resolution or orchestration issue.

## Scope

- Update the runtime packaging so the backup agent includes the newest practical PostgreSQL client toolchain available for the image strategy, with explicit support for PostgreSQL 17 and better forward compatibility than the current Debian default package.
- Keep the fix localized to packaging / runtime dependency selection plus any minimal documentation and test adjustments needed.
- Preserve existing PostgreSQL backup provider behavior and command invocation shape unless a small compatibility helper is clearly necessary.

## Desired outcome

After the change:

- PostgreSQL 17 targets can be backed up successfully.
- Existing PostgreSQL backup behavior for older supported servers remains intact.
- MariaDB behavior is not regressed.
- The runtime image documentation accurately describes the dependency strategy.

## Recommended implementation direction

Prefer one of these approaches:

### Option A: Install an explicit current PostgreSQL client package

Examples:

- `postgresql-client-17`
- or a newer packaged client version if available and operationally reasonable
- or install from the PostgreSQL upstream APT repository if Debian base packages do not provide a sufficiently recent version

### Option B: Change the base/runtime packaging strategy

If the default distro packages are too stale, switch to a packaging approach that makes a suitably new `pg_dump` available in the image while keeping the image operationally reasonable.

## Important constraints

- Do not broaden this into provider redesign unless strictly needed.
- Do not weaken secret handling.
- Do not break MariaDB or rsync tooling.
- Keep the operational story simple enough for the documented container deployment.
- Prefer deterministic runtime dependencies over ad hoc runtime downloads.

## Acceptance criteria

- The backup-agent runtime contains the newest practical packaged PostgreSQL dump client for the selected image strategy, and it is compatible with PostgreSQL 17.
- Real or reproducible validation confirms the reported version mismatch no longer occurs.
- Documentation reflects the chosen packaging/runtime dependency strategy.
- Regression tests still pass:

```bash
python -m unittest discover -s tests
```

## Likely files to inspect

- `Dockerfile`
- `README.md`
- `docker-compose.yml` (only if comments/docs need updating)
- `src/backup_agent/providers/databases/postgresql.py`
- CI or image-related workflow files if the packaging change affects build behavior

## Notes

- The current failure is specifically PostgreSQL client/server version skew.
- The user explicitly requested updating `pg_dump` to the latest practical version rather than only applying the narrowest possible compatibility fix.
- A similar class of issue could later appear for MySQL/MariaDB tooling, but this task should stay focused on the confirmed PostgreSQL problem first.
