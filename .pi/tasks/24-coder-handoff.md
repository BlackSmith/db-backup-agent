# Coder Handoff for Task 24

## Objective
Add a new FTP / FTPS storage backend that can upload completed runs and apply remote retention cleanup.

## Primary target
Implement a focused `FtpStorageProvider` path with minimal impact outside storage configuration, provider selection, and storage tests/docs.

Before implementation, read:
- `.pi/tasks/24-ftp-ftps-storage-provider.md`
- `.pi/tasks/24-implementation-notes.md`
- `.pi/tasks/24-config-notes.md`
- `.pi/tasks/24-retention-notes.md`

## Recommended implementation order
1. Update `src/backup_agent/app/config.py`
2. Add `src/backup_agent/providers/storage/ftp.py`
3. Update `src/backup_agent/providers/storage/factory.py`
4. Update `src/backup_agent/providers/storage/__init__.py`
5. Add or adjust focused tests for config parsing, storage selection, and the FTP / FTPS provider
6. Update targeted docs for configuration and operations
7. Run focused tests and then the full suite
8. Write `.pi/done/24-ftp-ftps-storage-provider.md`

## Expected behavior

### Configuration
Support an FTP-family environment variable set, for example:
- `FTP_HOST`
- `FTP_PORT`
- `FTP_USER`
- `FTP_PASSWORD`
- `FTP_REMOTE_PATH`
- `FTP_TLS`
- optional `FTP_PASSIVE`
- optional `FTP_TIMEOUT`

Recommended defaults:
- `FTP_PORT=21`
- `FTP_REMOTE_PATH=/backups`
- `FTP_TLS=false`
- `FTP_PASSIVE=true`
- `FTP_TIMEOUT=30`

### Upload
- upload a completed run directory to the remote FTP / FTPS destination
- preserve the run directory structure and manifest
- return structured success / failure results via the existing storage result model

### Retention
- determine retention from the remote FTP / FTPS destination, not from local staging
- delete only expired remote run directories
- keep unreadable or ambiguous runs rather than deleting them blindly
- update `latest` after successful cleanup

### FTPS recommendation
Prefer explicit FTPS using Python standard library `ftplib.FTP_TLS`.

Recommended connection behavior:
1. connect
2. login
3. enable protected data channel with `prot_p()`
4. set passive mode according to config

## Constraints
- Keep changes localized.
- Preserve existing rsync and local mounted storage behavior.
- Do not add SFTP in this task.
- Prefer standard library support over third-party dependencies.
- Do not log FTP credentials.

## Acceptance checklist
- [ ] FTP backend configuration is supported
- [ ] FTPS backend configuration is supported
- [ ] FTP / FTPS upload works through the storage provider abstraction
- [ ] FTP / FTPS retention cleanup removes expired remote run directories
- [ ] `latest` is maintained remotely
- [ ] backend selection works with FTP / FTPS alone or combined with existing backends
- [ ] focused tests pass
- [ ] full suite passes

## Suggested verification
```bash
python -m unittest tests.test_config_and_scheduler tests.test_storage_backend_selection
python -m unittest discover -s tests
```

## Design caveat
If reliable temp-directory publish or recursive delete semantics differ too much across FTP servers, choose the smallest explicit trade-off, document it, and avoid pretending stronger guarantees than the protocol/server behavior can provide.

Also keep the implementation inside the existing `RemoteStorageProvider` contract; do not broaden Task 24 into a full storage abstraction rewrite.
