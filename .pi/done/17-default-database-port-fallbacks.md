# Task 17 - Default Database Port Fallbacks: implementation record

## Implemented

- Added engine-specific default port fallback handling in metadata resolution.
- PostgreSQL now defaults to port `5432` when no explicit port is provided.
- MariaDB now defaults to port `3306` when no explicit port is provided.
- Preserved explicit port precedence and invalid explicit-port validation.
- Added tests covering default fallback and invalid explicit port behavior.

## Changed files

- `src/backup_agent/services/metadata_resolver.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`

## Verification

- Ran the focused metadata-resolution tests successfully.
- Ran the full regression suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- This change only affects metadata normalization and does not alter provider execution or discovery behavior.
