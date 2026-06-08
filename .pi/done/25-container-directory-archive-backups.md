# Task 25 - Container Directory Archive Backups: implementation record

## Implemented

- Added label-driven filesystem/archive backup target support through `backup_agent.type=filesystem` and `backup_agent.directories`.
- Extended metadata resolution so filesystem targets can be resolved explicitly or inferred from `backup_agent.directories`.
- Extended the backup target and manifest models to carry resolved directory lists.
- Added a `DockerApiClient.get_archive()` helper for copying paths out of a container through the Docker API archive endpoint.
- Added `FilesystemArchiveBackupProvider` that:
  - validates absolute container directories
  - copies selected directories from the target container into temporary local staging
  - creates a single `.tar.gz` artifact per target run
  - returns the artifact through the existing backup/provider pipeline
- Wired the new provider into the runtime orchestrator build path.
- Updated focused tests for metadata resolution, provider behavior, manifest serialization, and orchestrator support.
- Updated operator docs for the filesystem/archive label model and produced artifact type.

## Changed files

- `src/backup_agent/domain/backup_target.py`
- `src/backup_agent/domain/manifest.py`
- `src/backup_agent/services/metadata_resolver.py`
- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/providers/databases/filesystem.py`
- `src/backup_agent/providers/databases/__init__.py`
- `src/backup_agent/app/main.py`
- `src/backup_agent/services/orchestrator.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`
- `tests/test_database_backup_providers.py`
- `tests/test_local_staging_and_manifest.py`
- `tests/test_health_and_orchestrator.py`
- `docs/discovery-and-labels.md`
- `docs/operations.md`
- `.pi/done/25-container-directory-archive-backups.md`

## Verification

- Ran focused tests successfully:
  - `python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_database_backup_providers tests.test_local_staging_and_manifest tests.test_health_and_orchestrator`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- The initial implementation produces one `filesystem-tar-gzip` artifact per filesystem target.
- The implementation intentionally uses the Docker API archive endpoint rather than broad shelling out.
- Restore flows, archive format selection, and incremental filesystem backups remain future work.
