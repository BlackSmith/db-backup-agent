# Task 03 - Docker Discovery and Metadata Resolution: implementation record

## Implemented

- Added a small Docker API client that talks to the mounted Docker socket.
- Implemented `DockerContainerDiscovery` to:
  - list running containers
  - filter only containers with `backup_agent.enabled=true`
  - inspect only enabled containers for normalized metadata
- Implemented `ContainerMetadataResolver` to normalize container metadata into `BackupTarget`.
- Added explicit resolution precedence:
  - labels first
  - environment variables as fallback
- Added support for PostgreSQL and MariaDB metadata.
- Added database type inference with explicit failure when ambiguous.
- Added comma-separated database parsing via `parse_database_list()`.
- Added `allDatabases=True` behavior when database list is missing or empty.
- Kept secrets out of logs and surfaced resolution failures with actionable error messages.
- Added tests for discovery filtering, label precedence, type inference, database parsing, and all-databases handling.

## Changed files

- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/services/discovery.py`
- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`

## Verification

- Installed the project in editable mode:
  - `python -m pip install -e .`
- Ran the test suite successfully:
  - `python -m unittest discover -s tests`

## Open issues / follow-ups

- Docker socket connectivity is implemented with a lightweight HTTP client; later tasks may replace or extend it with richer Docker integration.
- Metadata resolver currently requires explicit `backup_agent.type` only when inference is ambiguous; later tasks may tighten or expand inference rules if needed.
- The orchestrator still does not yet consume discovery/resolution results in a full backup flow.
