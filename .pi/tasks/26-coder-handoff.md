# Coder Handoff for Task 26

## Objective
Fix the current regression where a container configured for both database backup and directory archive backup does not produce the correct filesystem archive artifact.

## Primary target
Repair the combined database + `backup_agent.directories` path so the application produces:
- normal database artifacts under the database provider directory
- one directory archive artifact under the filesystem/archive provider directory

Before implementation, read:
- `.pi/tasks/26-fix-combined-database-and-directory-backup-behavior.md`
- `.pi/tasks/25-container-directory-archive-backups.md`
- `.pi/context.md`
- `.pi/architecture.md`

## Recommended implementation order
1. Reproduce the combined-case failure with focused tests.
2. Inspect metadata resolution and combined-target expansion behavior.
3. Fix provider selection or synthetic target construction so the filesystem/archive provider receives the correct target.
4. Verify artifact output paths for the combined case.
5. Add regression coverage for PostgreSQL + directories and MariaDB + directories.
6. Run focused tests and then the full suite.
7. Write `.pi/done/26-fix-combined-database-and-directory-backup-behavior.md`.

## Expected behavior
Given one container with both:
- database metadata
- `backup_agent.directories`

one run should produce:
- database artifacts under `postgresql/...` or `mariadb/...`
- one directory archive artifact under `filesystem/...`

The combined case must not:
- produce a duplicate database export instead of the archive
- place the directory archive under the database provider directory

## Constraints
- Keep changes localized.
- Preserve standalone filesystem-only behavior.
- Preserve standalone database-only behavior.
- Do not redesign storage behavior.
- Do not broaden this into a full target-model rewrite unless truly necessary.

## Acceptance checklist
- [ ] PostgreSQL + directories works correctly
- [ ] MariaDB + directories works correctly
- [ ] The directory archive is placed under `filesystem/<container>/...`
- [ ] No duplicate database export appears in place of the archive
- [ ] Filesystem-only behavior still works
- [ ] Database-only behavior still works
- [ ] Focused tests pass
- [ ] Full suite passes

## Suggested verification
```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_database_backup_providers tests.test_health_and_orchestrator
python -m unittest discover -s tests
```

## Design caveat
Prefer a minimal regression fix over a broad abstraction rewrite. If the combined-case bug reveals a real architectural conflict, document that conflict clearly before expanding the scope.
