# Task 26 - Fix Combined Database + Directory Backup Behavior: implementation record

## Implemented

- Preserved the combined backup execution path for containers that declare both database metadata and `backup_agent.directories`.
- Ensured the orchestrator expands one combined target into:
  - a database backup target
  - a synthetic filesystem/archive backup target
- Kept the filesystem/archive artifact on the dedicated `filesystem/` subtree instead of the database provider subtree.
- Added directory metadata support to the database target model so database and filesystem/archive flows can coexist for the same container.
- Extended metadata resolution so `backup_agent.directories` is carried on PostgreSQL and MariaDB targets, while standalone filesystem/archive targets still resolve normally.
- Added filesystem/archive backup provider support through the existing backup provider contract.
- Added regression coverage for:
  - PostgreSQL + directories
  - MariaDB + directories
  - standalone filesystem/archive targets
- Clarified the discovery docs to state that combined DB + directory metadata produces separate database and filesystem/archive targets.

## Changed files

- `src/backup_agent/domain/backup_target.py`
- `src/backup_agent/domain/manifest.py`
- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/providers/databases/__init__.py`
- `src/backup_agent/providers/databases/filesystem.py`
- `src/backup_agent/services/metadata_resolver.py`
- `src/backup_agent/services/orchestrator.py`
- `tests/test_database_backup_providers.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`
- `tests/test_health_and_orchestrator.py`
- `tests/test_local_staging_and_manifest.py`
- `docs/discovery-and-labels.md`
- `docs/operations.md`

## Verification

- Ran focused tests successfully:
  - `python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_database_backup_providers tests.test_health_and_orchestrator`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- The combined behavior is implemented as target expansion rather than a new top-level backup mode.
- Filesystem/archive backups use the `filesystem-tar-gzip` artifact format.
- The resulting manifest keeps the database and filesystem/archive artifacts distinct.
