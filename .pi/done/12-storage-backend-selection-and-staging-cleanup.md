# Task 12 - Storage Backend Selection and Staging Cleanup: implementation record

## Implemented

- Updated configuration validation so `BACKUP_LOCAL_STORAGE` can be used without requiring `RSYNC_*`.
- Kept partial rsync configuration invalid when only some rsync fields are provided.
- Added independent backend selection helpers on `AppConfig`:
  - `has_rsync_storage`
  - `uses_local_storage`
  - `enabled_storage_backends`
  - `storage_backend`
- Updated the storage factory to return:
  - local mounted storage only
  - rsync only
  - a composite provider when both are configured
- Wired the orchestrator to execute the configured storage backends independently and preserve partial results when one backend fails.
- Added cleanup of local staging after successful runs when no mounted local storage backend is configured.
- Added tests covering:
  - rsync-only config validation
  - local-only config validation
  - combined backend config validation
  - storage backend selection
  - composite publishing behavior
  - staging cleanup when no local storage backend is configured
- Updated README configuration notes to describe optional and combinable storage backends.

## Changed files

- `README.md`
- `.pi/architecture.md`
- `.pi/context.md`
- `src/backup_agent/app/config.py`
- `src/backup_agent/providers/storage/__init__.py`
- `src/backup_agent/providers/storage/composite.py`
- `src/backup_agent/providers/storage/factory.py`
- `src/backup_agent/services/orchestrator.py`
- `src/backup_agent/services/staging.py`
- `tests/test_config_and_scheduler.py`
- `tests/test_health_and_orchestrator.py`
- `tests/test_storage_backend_selection.py`

## Verification

- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Notes / follow-ups

- The combined backend flow is intentionally order-preserving: mounted local storage publishes first, then rsync.
- Local staging is now treated as ephemeral when no mounted local storage backend is configured.
- The storage abstraction still uses the `RemoteStorageProvider` name; a future cleanup could rename it to `StorageProvider` if the project continues to expand.
