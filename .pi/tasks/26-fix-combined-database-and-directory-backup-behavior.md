# Task 26: Fix Combined Database + Directory Backup Behavior

## Goal
Correct the runtime behavior for containers that define both database backup metadata and `backup_agent.directories`.

The intended behavior is:
- the database backup runs normally
- the selected container directories are archived exactly once
- the directory archive is written under the filesystem/archive artifact path, not under the database provider path

## Problem statement
A regression has been reported in the current application behavior:

- when a container declares both database backup metadata and `backup_agent.directories`
- the directory backup is not produced correctly
- instead, the output may contain another database export
- and the artifact may appear under the `postgresql/` path instead of a dedicated filesystem/archive path such as `filesystem/`

This violates the intended separation between:
- database artifacts
- directory archive artifacts

## Scope
- inspect the current combined-target execution path
- fix target expansion or provider selection so combined database + directory backups work correctly
- ensure the directory archive is created by the filesystem/archive provider, not by the database provider
- ensure the filesystem/archive artifact is written under a dedicated provider directory
- add regression tests for the combined case
- update operator-facing docs if behavior wording needs clarification

## Out of scope
- broad redesign of backup target abstractions
- restore workflows
- archive format selection beyond the current default
- renaming all user-facing terminology from `filesystem` to `volume`

## Intended behavior
For a container such as:

```text
backup_agent.enabled=true
backup_agent.type=postgresql
backup_agent.user=app
backup_agent.password=secret
backup_agent.host=postgres
backup_agent.port=5432
backup_agent.database=appdb
backup_agent.directories=/app/data,/var/lib/app/uploads
```

one run should produce:
- the PostgreSQL dump artifact(s) under `postgresql/<container>/...`
- one directory archive artifact under `filesystem/<container>/directories.tar.gz`

The combined case must not:
- produce a duplicate database export instead of the directory archive
- place the directory archive under `postgresql/` or `mariadb/`

## Recommended implementation focus
Inspect these areas first:
- metadata resolution for targets carrying both database metadata and directory lists
- orchestrator target expansion logic for combined targets
- provider selection for synthetic filesystem/archive targets
- filesystem/archive provider output path construction
- manifest serialization for combined runs

## Acceptance criteria
- A PostgreSQL target with `backup_agent.directories` produces both a PostgreSQL artifact and one filesystem archive artifact.
- A MariaDB target with `backup_agent.directories` produces both a MariaDB artifact and one filesystem archive artifact.
- The filesystem archive is written under `filesystem/<container>/...` rather than the database provider directory.
- The combined case does not produce an extra database export in place of the directory archive.
- Filesystem-only targets continue to work.
- Database-only targets continue to work.
- Focused regression tests pass.
- Full suite passes.

## Suggested verification
```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_database_backup_providers tests.test_health_and_orchestrator
python -m unittest discover -s tests
```

## Design caveat
Prefer the smallest correction that restores correct combined behavior. Do not broaden this task into a full redesign of the backup target model unless the bug cannot be fixed safely without that redesign.
