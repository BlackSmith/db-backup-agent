# Task 11: Local Mounted Storage Provider

## Goal
Extend the backup agent so completed backup runs can be copied to a local directory mounted into the backup-agent container.

The destination path must be configured through the environment variable:

- `BACKUP_LOCAL_STORAGE`

## Background
The current MVP uses rsync as the remote storage provider. Some deployments may instead mount a NAS, host directory, or another persistent filesystem path directly into the backup-agent container. In that mode, the agent should be able to publish completed run directories into the mounted path without rsync.

## Scope
- Add configuration support for `BACKUP_LOCAL_STORAGE`.
- Implement a local-directory storage provider behind the existing storage provider abstraction.
- Copy completed run directories into the mounted destination path.
- Preserve the existing per-run directory model.
- Keep local staging data intact if publishing to the mounted storage path fails.
- Apply retention to complete run directories in the mounted destination.
- Document the new environment variable and deployment mode.

## Intended behavior

### Configuration

`BACKUP_LOCAL_STORAGE` is optional.

When set:

- it points to a writable directory inside the backup-agent container
- the directory is expected to be backed by a Docker bind mount or volume
- the application must validate that the directory exists or can be created
- the application must validate write access

Recommended default behavior:

- If `BACKUP_LOCAL_STORAGE` is set, use the local mounted storage provider.
- If `BACKUP_LOCAL_STORAGE` is not set, keep the existing rsync provider behavior.

If both rsync configuration and `BACKUP_LOCAL_STORAGE` are present, prefer the local mounted storage provider unless a future explicit storage-backend selector is added.

## Required directory model

The mounted storage should mirror the backup root model:

```text
<BACKUP_LOCAL_STORAGE>/
  runs/
    <run-id>/
      manifest.json
      postgresql/
        <container-name>/
      mariadb/
        <container-name>/
  latest -> runs/<run-id>
```

## Deliverables

- Config model update for `BACKUP_LOCAL_STORAGE`.
- Local mounted storage provider implementation, for example:
  - `LocalDirectoryStorageProvider`
- Storage-provider selection logic.
- Retention support for the mounted destination.
- Tests for:
  - config parsing and validation
  - successful local copy
  - failed local copy preserving original run data
  - retention deleting complete destination run directories only
  - `latest` pointer update in the mounted destination
- README / deployment documentation update.

## Constraints

- Do not hardcode host paths.
- Do not require rsync variables when local mounted storage is the selected storage backend, unless the existing config design makes this difficult; if so, document the transitional behavior.
- Never delete the source staging run directory as part of publishing.
- Retention must delete complete run directories only.
- Local publish should be as safe as practical:
  - copy to a temporary destination directory first
  - rename to the final run directory after successful copy
  - avoid leaving partially published final run directories

## Acceptance criteria

- Setting `BACKUP_LOCAL_STORAGE=/mnt/backups` causes completed runs to be copied to `/mnt/backups/runs/<run-id>/`.
- The mounted destination receives a `manifest.json` and all produced artifacts.
- A `latest` pointer or equivalent marker is maintained in the mounted destination.
- Publish failures return structured error data and do not delete local staging data.
- Retention runs only after successful publish.
- Retention removes only complete destination run directories older than `BACKUP_RETENTION_DAYS`.
- Existing rsync behavior remains available when `BACKUP_LOCAL_STORAGE` is not set.
- Tests pass with:
  - `python -m unittest discover -s tests`

## Suggested implementation notes

- Reuse existing filesystem helpers where possible.
- Reuse or extend the retention planner from `services/retention.py`.
- Keep the provider behind the `RemoteStorageProvider` interface even though the destination is local; it is still a publish/storage backend from the orchestrator's perspective.
- Consider renaming the abstraction in a future cleanup from `RemoteStorageProvider` to `StorageProvider`, but avoid broad renames in this task unless necessary.
- If storage-provider selection becomes more complex, introduce a small factory function rather than embedding selection logic deeply in the orchestrator.

## Suggested verification

- Unit tests for the local storage provider using `tempfile.TemporaryDirectory`.
- Unit tests for config selection behavior.
- Full test suite:

```bash
python -m unittest discover -s tests
```
