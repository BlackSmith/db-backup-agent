# Task 25: Label-Driven Archive Backups for Arbitrary Container Directories

## Goal
Extend the backup agent so it can back up arbitrary directories from a discovered container, not only database data.

The selected directories must be declared through container labels, copied into local temporary staging, archived, and then published through the existing storage backend pipeline.

## Scope
- Add a new label-driven backup target type for filesystem/archive backups.
- Let operators declare one or more container directories via labels.
- Copy the selected directories out of the target container into temporary local staging.
- Archive the copied content into a single backup artifact per target run.
- Publish that archive through the existing local / rsync / FTP storage backends.
- Keep the current database backup behavior unchanged.
- Update tests and operator-facing docs for the new target type.

## Out of scope
- Restore workflow implementation.
- Incremental or differential backups.
- Encryption at rest.
- SFTP support.
- Broad redesign of the current storage abstraction.

## Recommended label model
Add a label that lists the directories to back up inside the container:

- `backup_agent.directories=/app/data,/var/lib/app/uploads`

### Recommended semantics
- values are comma-separated absolute paths inside the container
- whitespace should be trimmed
- empty entries should be ignored
- the label should be sufficient to express multiple directories
- `backup_agent.directories` alone should be enough to activate filesystem/archive backup behavior
- when `backup_agent.directories` is combined with database metadata, the container should produce both database artifacts and directory archive artifacts in the same run
- explicit `backup_agent.type=filesystem` may remain supported as a filesystem-only override, but it should not be required for normal directory backup use

## Recommended archive model
- copy the selected container directories into a temporary local workspace first
- archive the copied tree into a single artifact
- default archive format should be `tar.gz`
- preserve the selected directory structure inside the archive so the backup is meaningful to operators

## Recommended implementation direction
Prefer a small, dedicated filesystem/archive backup provider rather than forcing the new behavior into the existing PostgreSQL or MariaDB providers.

Likely changes will include:
- metadata resolution for the new label set
- a new provider module for filesystem/archive backups
- a small Docker API helper for fetching container paths if the current client cannot already copy directories out of a container
- orchestrator wiring so the new provider participates in the same run lifecycle as the database providers

## Constraints
- Keep changes localized.
- Do not break existing PostgreSQL / MariaDB backup behavior.
- Do not log secrets or sensitive file contents.
- Preserve the current publish and retention model for storage backends.
- Keep temporary source copies confined to local staging and clean them up on success.

## Acceptance criteria
- A container can opt into filesystem/archive backups through `backup_agent.directories`.
- One or more directories can be specified through labels.
- The selected directories are copied into temporary staging and archived successfully.
- The resulting archive is published through the configured storage backend(s).
- When database metadata and `backup_agent.directories` are both present on the same container, both backup flows run successfully in the same run.
- Database-only flows remain unchanged when `backup_agent.directories` is absent.
- Focused tests pass.
- Full suite passes.

## Suggested verification
```bash
python -m unittest tests.test_config_and_scheduler tests.test_storage_backend_selection
python -m unittest discover -s tests
```

## Design caveat
If the most reliable container-to-local copy mechanism requires a small Docker API helper, add the smallest helper possible rather than shelling out broadly or redesigning the backup pipeline.
