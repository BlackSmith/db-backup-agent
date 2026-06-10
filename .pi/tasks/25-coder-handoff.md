# Coder Handoff for Task 25

## Objective
Add support for label-driven backups of arbitrary directories from a discovered container.

The new feature should let an operator specify one or more container directories through labels, copy those directories into temporary local staging, archive them, and then publish the resulting archive through the existing storage backend pipeline.

## Primary target
Implement a focused filesystem/archive backup path with minimal impact outside metadata resolution, provider selection, backup providers, staging, tests, and docs.

Before implementation, read:
- `.pi/tasks/25-container-directory-archive-backups.md`
- `.pi/context.md`
- `.pi/architecture.md`

## Recommended implementation order
1. Update metadata resolution so a new filesystem/archive target type can be discovered from labels.
2. Add a new backup provider for container directory archive backups.
3. Wire the new provider into orchestrator provider selection.
4. Add or adjust staging helpers if needed for temporary local copies and archive creation.
5. Add focused tests for label parsing, provider behavior, and orchestration.
6. Update operator-facing docs for the new label model.
7. Run focused tests and then the full suite.
8. Write `.pi/done/25-container-directory-archive-backups.md`.

## Expected behavior

### Configuration / labels
Support directory archive backups selected by labels, for example:
- `backup_agent.directories=/app/data,/var/lib/app/uploads`

Recommended semantics:
- `backup_agent.directories` contains a comma-separated list of absolute container paths
- whitespace should be trimmed
- empty entries should be ignored
- the label should support multiple directories
- `backup_agent.directories` alone should be enough to activate directory archive backup behavior
- when combined with PostgreSQL or MariaDB metadata on the same container, both the database backup and directory archive backup should run in the same run
- explicit `backup_agent.type=filesystem` may remain supported as a filesystem-only override, but it should not be required for the normal combined case

### Backup behavior
- copy the selected directories from the target container into temporary local staging
- archive the copied content into a single artifact, preferably `tar.gz`
- preserve the selected directory structure inside the archive
- publish the archive through the existing storage backend flow
- keep database backup behavior unchanged when `backup_agent.directories` is absent
- allow one container to produce both database artifacts and a directory archive artifact when both label sets are present

### Retention / publish flow
- the new archive backup should follow the same durable publish pattern as other non-rsync backends
- do not invent a new retention model for this task
- let the existing storage backend retention and cleanup behavior remain in control

## Constraints
- Keep changes localized.
- Preserve existing PostgreSQL, MariaDB, rsync, local mounted storage, and FTP/FTPS behavior.
- Do not add SFTP.
- Prefer standard library support where possible.
- Do not log file contents or secrets.

## Acceptance checklist
- [ ] Container directory archive backups can be selected via `backup_agent.directories`
- [ ] Multiple container directories can be specified
- [ ] Selected directories are copied into temporary staging
- [ ] An archive artifact is produced
- [ ] The archive is published through the existing storage pipeline
- [ ] One container can produce both database and directory archive artifacts in the same run
- [ ] Existing database-only behavior remains intact when directory labels are absent
- [ ] Focused tests pass
- [ ] Full suite passes

## Suggested verification
```bash
python -m unittest tests.test_config_and_scheduler tests.test_storage_backend_selection
python -m unittest discover -s tests
```

## Design caveat
If the most reliable implementation requires a very small Docker API helper for copying directories out of a container, add that helper rather than broadening the task into a larger orchestration refactor.
