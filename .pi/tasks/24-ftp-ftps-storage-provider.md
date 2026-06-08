# Task 24: FTP / FTPS Storage Provider and Retention Support

## Goal
Extend the backup agent so completed backup runs can be published to an FTP or FTPS server and old remote runs can be removed according to the existing retention policy.

## User-requested behavior
The user wants a new storage backend that supports:

- FTP upload of completed backup runs
- FTPS upload of completed backup runs
- retention cleanup on the FTP / FTPS server
- configuration-driven backend selection consistent with the existing rsync and mounted-local backends

## Scope

### In scope
- add configuration support for an FTP-family storage backend
- support both plain FTP and FTPS through the same backend family
- publish a completed run directory to the remote FTP / FTPS server
- support retention cleanup of complete remote run directories
- preserve the current storage backend composition model so FTP / FTPS can be enabled alone or together with existing backends
- update tests and operator-facing docs for the new backend

### Out of scope
- SSH/SFTP support
- encryption of backup payloads at rest
- restore workflow implementation
- retry/reconnect policy beyond a minimal reasonable implementation
- checksum support
- broad renaming of the existing storage abstraction

## Recommended configuration model
Add a new environment variable family, for example:

- `FTP_HOST`
- `FTP_PORT`
- `FTP_USER`
- `FTP_PASSWORD`
- `FTP_REMOTE_PATH`
- `FTP_TLS`
- optional `FTP_PASSIVE`
- optional `FTP_TIMEOUT`

### Recommended semantics
- `FTP_HOST` = FTP / FTPS server host
- `FTP_PORT` = optional explicit port; default according to TLS mode
- `FTP_USER` = login username
- `FTP_PASSWORD` = login password
- `FTP_REMOTE_PATH` = remote root directory where runs are stored
- `FTP_TLS=true|false` = whether to use FTPS
- `FTP_PASSIVE=true|false` = passive mode toggle, default true
- `FTP_TIMEOUT=<seconds>` = connection / operation timeout if implemented

### Default port recommendation
- FTP: `21`
- FTPS explicit TLS: `21`
- do not introduce implicit FTPS (`990`) unless there is a clear requirement; explicit TLS is simpler and easier to document

## Recommended architecture

### New provider
Add a new storage provider, conceptually:

- `FtpStorageProvider`

Recommended location:
- `src/backup_agent/providers/storage/ftp.py`

### Standard library preference
Prefer using Python standard library support if it keeps the implementation small and avoids unnecessary dependencies.

Recommended baseline:
- `ftplib.FTP`
- `ftplib.FTP_TLS`

Reason:
- keeps the image and dependency set small
- avoids broad packaging changes for a first implementation

## Remote layout recommendation
Use the same logical run-oriented model as the existing durable backends.

Recommended remote layout:

```text
<FTP_REMOTE_PATH>/
  runs/
    <run-id>/
      manifest.json
      postgresql/
      mariadb/
  latest
```

### Important note about parity with rsync
The current rsync implementation recently moved to storing run directories directly under its remote root without an additional remote `runs/` path in the publish URL.

For FTP / FTPS, favor the durable-storage-style directory model that mirrors mounted local storage:
- remote root contains `runs/`
- each run lives under `runs/<run-id>/`
- `latest` points to or records the newest retained run

If exact cross-backend path parity becomes important later, document that follow-up separately instead of blocking this task.

## Upload behavior
Publish a fully completed local run directory to FTP / FTPS storage.

Recommended safety model:
1. create a temporary remote directory for the run if practical
2. upload all files for the new run
3. rename or finalize to the final run directory name if the server supports it reliably
4. update the remote `latest` marker after success

If a safe temp-then-rename flow is too awkward across FTP servers, an acceptable first implementation is:
- upload directly into the final run directory
- surface partial failures clearly
- do not delete local staging on upload failure

## Retention behavior
Retention for FTP / FTPS should be remote-state-driven.

Recommended approach:
1. list remote run directories under `runs/`
2. inspect remote `manifest.json` files for those runs, or fall back to run-id parsing if manifest retrieval is impractical
3. compute expired vs retained runs using the existing retention timestamp precedence:
   - `finished_at`
   - `started_at`
   - run-id timestamp fallback
4. delete only expired remote run directories
5. update `latest` to the newest retained run

### Important safety rules
- do not derive FTP / FTPS retention from transient local staging contents
- do not delete individual files from a retained run directory as a retention strategy
- delete only whole expired run directories
- retain remote runs with unreadable or missing metadata unless there is a clearly safer rule

## Recommended orchestrator behavior
FTP / FTPS can follow the general post-backup durable-publish pattern already used by non-rsync storage backends:

1. create local run
2. write local manifest
3. upload to configured backend(s)
4. after successful upload, run FTP / FTPS retention cleanup
5. if all configured backends succeed, remove transient local staging

This differs from the rsync-specific remote-manifest-first cleanup sequence and should remain isolated to the FTP backend unless a future architectural unification is desired.

## Constraints
- Keep changes localized to configuration, storage providers, tests, and docs.
- Preserve existing rsync and mounted local storage behavior.
- Do not require rsync settings when only FTP / FTPS is configured.
- Keep secret handling safe; do not log FTP passwords.
- Prefer standard library support over adding third-party dependencies unless a concrete blocker appears.

## Acceptance criteria
- FTP / FTPS can be configured as a storage backend
- completed runs can be uploaded to an FTP server
- completed runs can be uploaded to an FTPS server
- retention cleanup removes expired remote run directories
- remote retention is based on remote state, not transient local staging
- `latest` is maintained on the FTP / FTPS destination
- storage backend selection supports FTP / FTPS alone or together with existing backends
- focused tests pass
- full suite passes

## Likely files to inspect
- `src/backup_agent/app/config.py`
- `src/backup_agent/providers/storage/base.py`
- `src/backup_agent/providers/storage/factory.py`
- `src/backup_agent/providers/storage/__init__.py`
- `src/backup_agent/providers/storage/composite.py`
- `src/backup_agent/services/orchestrator.py`
- tests for config, storage selection, and storage providers
- docs covering configuration and operations

## Suggested verification
```bash
python -m unittest tests.test_config_and_scheduler tests.test_storage_backend_selection
python -m unittest discover -s tests
```

## Design caveats
- FTP server capabilities vary more than rsync or local filesystems; prefer the smallest reliable baseline.
- Explicit FTPS via `FTP_TLS` is the recommended first target. Avoid implicit FTPS unless a real requirement appears.
- If directory rename semantics or recursive delete semantics vary across target servers, document the exact trade-off instead of hiding it.
