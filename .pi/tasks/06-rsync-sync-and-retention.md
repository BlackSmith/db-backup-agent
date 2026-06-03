# Task 06: Rsync Sync and Retention

## Goal
Implement remote synchronization via rsync and retention cleanup after successful upload.

## Scope
- Define the `RemoteStorageProvider` contract
- Implement `RsyncStorageProvider`
- Sync completed local run directories to remote storage
- Apply retention policy after successful sync
- Preserve local data when sync fails

## Required configuration usage
- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `BACKUP_RETENTION_DAYS`
- use optional `RSYNC_REMOTE_PATH` if available

## Deliverables
- Remote storage provider interface
- rsync implementation
- retention cleanup logic
- structured sync result model

## Constraints
- Retention must not run before successful sync
- Sync failure must not remove local backups
- Never log secrets
- Prefer deleting complete run directories rather than individual files

## Acceptance criteria
- A completed run directory can be uploaded to remote storage
- Sync result is explicit: success / failure with details
- Retention executes only after successful sync
- Old remote backups are removed according to retention policy
- Local run data remains available when remote sync fails

## Suggested notes for implementer
- If safe remote atomic publish is practical, use temp directory + rename
- If password-based rsync is awkward in the chosen runtime, document the implementation choice clearly
