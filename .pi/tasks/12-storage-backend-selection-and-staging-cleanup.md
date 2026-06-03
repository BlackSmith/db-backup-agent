# Task 12: Storage Backend Selection and Staging Cleanup

## Goal
Adjust the backup agent so local mounted storage and rsync become optional, independently configurable storage outputs.

## User request this task must satisfy

- `RSYNC_*` environment variables must not be required when `BACKUP_LOCAL_STORAGE` is set.
- If `RSYNC_*` is not set, the agent must not upload backups to NAS.
- If `BACKUP_LOCAL_STORAGE` is not set, nothing should remain in the local staging storage after backups complete.
- It must be possible to use both options at the same time.

## Scope
- Update configuration validation so rsync credentials are only required when rsync upload is enabled.
- Treat `BACKUP_LOCAL_STORAGE` and rsync as independent storage destinations.
- Allow one or both storage backends to be active at the same time.
- Ensure that when only rsync is configured, local staging data is cleaned up after a successful run.
- Ensure that when only `BACKUP_LOCAL_STORAGE` is configured, backups are published there and no NAS upload is attempted.
- Ensure that when both are configured, the run is published to both destinations.
- Keep failure handling explicit and safe:
  - if one backend succeeds and another fails, report a partial result
  - do not delete data needed for retry/debugging when a configured backend fails

## Deliverables
- Configuration model update for optional / combined storage backends.
- Storage backend selection logic that can return:
  - local mounted storage only
  - rsync only
  - both backends together
- Orchestrator changes so the configured storage backends are executed independently.
- Local staging cleanup logic after successful publication when no local storage backend is configured.
- Tests covering:
  - config validation with only `BACKUP_LOCAL_STORAGE`
  - config validation with only rsync credentials
  - config validation with both backends
  - no rsync upload when rsync is not configured
  - no local persistence when `BACKUP_LOCAL_STORAGE` is not configured
  - combined backend behavior

## Constraints
- Do not hardcode host paths.
- Do not change the backup discovery or database provider behavior.
- Do not remove staged data until all configured publish targets that should succeed have completed successfully.
- Preserve the existing per-run directory structure while publication is in progress.
- Keep the implementation localized; avoid a broad storage abstraction rewrite if a small extension is sufficient.

## Acceptance criteria
- A configuration with only `BACKUP_LOCAL_STORAGE` set validates successfully and does not require `RSYNC_*`.
- A configuration with only `RSYNC_*` set validates successfully and still performs NAS upload.
- A configuration with both set publishes to both destinations.
- When `BACKUP_LOCAL_STORAGE` is not set, the final local staging directory is cleaned up after a successful run.
- When `RSYNC_*` is not set, no NAS upload is attempted.
- Tests pass with:

```bash
python -m unittest discover -s tests
```

## Suggested implementation notes
- Consider making storage backend configuration explicit in `AppConfig`, for example by exposing which backends are enabled rather than a single backend flag.
- If the orchestrator currently assumes a single storage provider, introduce a small composite storage provider or a lightweight publish pipeline.
- Local staging cleanup may need a dedicated method in the staging manager.
- Keep behavior deterministic: if both backends are enabled, the run should attempt both in a well-defined order.

## Suggested verification
- Add unit tests around configuration parsing and storage selection first.
- Then add tests for single-backend and dual-backend orchestration behavior.
- Run the full test suite:

```bash
python -m unittest discover -s tests
```
