# Task 27 - Require explicit `backup_agent.type` and allow multi-value selection: implementation record

## Implemented

- Made `backup_agent.type` mandatory for every `backup_agent.enabled=true` container.
- Removed implicit type inference from labels, environment variables, and `backup_agent.directories` alone.
- Added comma-separated multi-value parsing for `backup_agent.type` with:
  - whitespace trimming
  - empty-entry ignoring
  - duplicate removal
  - alias normalization to canonical values
- Rejected conflicting database-engine combinations such as `postgresql,mariadb`.
- Required `filesystem` to be explicitly present in `backup_agent.type` before `backup_agent.directories` can activate filesystem/archive backup behavior.
- Preserved combined database + filesystem behavior by carrying directory metadata on database targets when `backup_agent.type` includes both the database engine and `filesystem`.
- Added resolver and orchestrator regression coverage for:
  - missing type
  - blank type
  - multi-value type parsing
  - conflicting type combinations
  - directories without `filesystem`
  - combined PostgreSQL + filesystem and MariaDB + filesystem runs using the real resolver path
- Updated operator-facing docs to describe the explicit type requirement and multi-value behavior.

## Changed files

- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`
- `tests/test_health_and_orchestrator.py`
- `docs/discovery-and-labels.md`
- `docs/troubleshooting.md`

## Verification

- Ran focused tests successfully:
  - `python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_health_and_orchestrator tests.test_database_backup_providers`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- This is a breaking metadata-contract change for deployments that relied on implicit type inference.
- `backup_agent.directories` no longer activates filesystem backup by itself; `backup_agent.type` must explicitly include `filesystem`.
