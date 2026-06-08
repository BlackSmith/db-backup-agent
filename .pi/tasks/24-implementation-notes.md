# Task 24 Implementation Notes

## Purpose
This note recommends a concrete implementation shape for adding FTP / FTPS storage support while minimizing disruption to the current storage architecture.

The goal is to add a focused FTP-family provider that:
- uploads completed backup runs
- manages remote retention from remote state
- composes cleanly with the existing local and rsync backends

## Recommended design approach

### Keep the current storage abstraction stable
The current storage abstraction already models the two operations FTP / FTPS needs:

- `sync(local_path, remote_path=None)`
- `cleanup(local_path, retention_days)`

Unlike the rsync redesign, FTP / FTPS does not need a special pre-upload cleanup sequence.

Recommended implementation:
- keep `RemoteStorageProvider` unchanged
- add a new `FtpStorageProvider`
- integrate it through existing provider selection and composite behavior

This is preferable to a broad storage abstraction redesign.

## Recommended provider API shape

### New provider
Suggested file:
- `src/backup_agent/providers/storage/ftp.py`

Suggested class:

```python
@dataclass(slots=True)
class FtpStorageProvider(RemoteStorageProvider):
    host: str
    port: int
    user: str
    password: str
    remote_path: str
    use_tls: bool = False
    passive: bool = True
    timeout: float = 30.0
```

### Internal helper methods
Recommended internal methods:

```python
def _connect(self) -> FTP | FTP_TLS:
    ...

def _ensure_remote_dir(self, client, remote_dir: str) -> None:
    ...

def _upload_tree(self, client, local_root: Path, remote_root: str) -> None:
    ...

def _list_remote_runs(self, client) -> list[str]:
    ...

def _fetch_remote_manifest(self, client, run_id: str) -> dict[str, object] | None:
    ...

def _delete_remote_tree(self, client, remote_dir: str) -> None:
    ...

def _update_latest(self, client, latest_value: str | None) -> None:
    ...
```

Reason:
- keeps the public abstraction small
- keeps FTP protocol details isolated inside the provider
- makes tests easier to target by mocking or faking small units of FTP behavior

## Library recommendation

### Prefer standard library
Recommended baseline:
- `ftplib.FTP`
- `ftplib.FTP_TLS`

This is the preferred first implementation because:
- the repository currently has no runtime dependencies
- it avoids image expansion and packaging complexity
- explicit FTPS is supported by `FTP_TLS`

### TLS behavior recommendation
For FTPS:
1. connect via `FTP_TLS`
2. login
3. call `prot_p()` so the data channel is protected
4. set passive mode according to config

Do not add implicit FTPS (`990`) in the first implementation unless explicitly requested.

## Remote layout recommendation
Use a stable remote root with a `runs/` subtree.

Recommended shape:

```text
<FTP_REMOTE_PATH>/
  runs/
    <run-id>/
      manifest.json
      postgresql/
      mariadb/
  latest
```

### Why this shape is recommended
- mirrors mounted local storage behavior
- makes retention logic easier to understand
- avoids mixing run directories with helper files in one flat namespace
- allows `latest` to remain a simple marker file

## Upload behavior recommendation

### Safe baseline
Recommended sync behavior:
1. connect
2. ensure `<FTP_REMOTE_PATH>/runs/` exists
3. if `<run-id>` already exists, fail explicitly instead of overwriting silently
4. upload the full local run tree to `<FTP_REMOTE_PATH>/runs/<run-id>/`
5. update `<FTP_REMOTE_PATH>/latest`

### Temp-directory option
If the implementation remains small and reliable across test scenarios, an acceptable enhancement is:
- upload to `<run-id>.tmp-<suffix>`
- rename to `<run-id>` after success

However, this should not block the first implementation.

### Recommended first trade-off
For the first implementation, direct upload to the final run directory is acceptable if:
- directory existence is checked first
- partial upload failures are surfaced clearly
- local staging is preserved on failure

## Retention behavior recommendation

### Source of truth
FTP / FTPS retention must be based on the remote server state, not on transient local staging.

### Recommended algorithm
1. connect
2. list remote run directories under `<FTP_REMOTE_PATH>/runs/`
3. for each run, retrieve `manifest.json` if available
4. compute the retention plan using timestamp precedence:
   - `finished_at`
   - `started_at`
   - run-id timestamp fallback
5. delete only expired run directories
6. recompute and update `latest`

### Missing or unreadable manifest rule
Recommended safe rule:
- keep the run
- record an error in the cleanup result
- do not delete ambiguous runs

This matches the project’s bias toward safe retention behavior.

## `latest` marker recommendation

### Representation
Prefer a simple text file named `latest` containing:

```text
runs/<run-id>
```

Reason:
- FTP servers do not provide a reliable symlink model across deployments
- a plain text marker is simple and portable

### Update rule
- after successful upload: point `latest` to the uploaded run
- after cleanup: point `latest` to the newest retained run
- if no runs remain: delete `latest` if possible, otherwise overwrite it with an empty value only if deletion proves awkward

## Command / protocol semantics note
Unlike rsync, FTP / FTPS is not shell-like and does not support a single sync command for recursive delete.

That means:
- recursive upload must be implemented explicitly
- recursive deletion must be implemented explicitly
- retention logic is best kept inside the provider, not delegated to the orchestrator

This is acceptable because the current abstraction already allows provider-specific cleanup behavior.

## Recommended orchestrator impact
Minimal.

Recommended approach:
- do not add a special orchestrator branch for FTP / FTPS
- let the provider participate in the existing flow:
  - backup
  - sync
  - cleanup
- this should behave like mounted local storage, not like the rsync-specific pre-cleanup sequence

## Composite backend behavior

### Recommended behavior
Allow FTP / FTPS to compose with:
- local mounted storage
- rsync

The existing `CompositeStorageProvider` should remain usable.

### Important interaction note
If FTP / FTPS is combined with rsync, the coder should preserve the current semantics of the composite provider and the current rsync-specific sequencing. Do not redesign the full multi-backend orchestration model in Task 24.

If the combined sequencing becomes awkward:
- prefer a small localized orchestrator clarification
- avoid broad storage abstraction redesign

## Testing recommendation

### Unit/focused tests
Add focused tests for:
- config parsing of `FTP_*`
- backend selection including FTP / FTPS only and combined cases
- successful FTP upload of a run tree
- FTPS connection mode selection
- retention cleanup deleting only expired remote run directories
- `latest` marker updates
- failure behavior preserving local staging

### Test strategy suggestion
Because real FTP servers are heavy for unit tests, prefer one of:
- a small fake FTP client injected into `FtpStorageProvider`
- monkeypatching `ftplib.FTP` / `FTP_TLS`
- thin internal wrappers around `nlst`, `retrbinary`, `storbinary`, `mkd`, `delete`, `rmd`, `rename`

Keep tests deterministic and local.

## What not to do in Task 24
- do not add SFTP under the same task
- do not add third-party FTP libraries unless the standard library proves insufficient
- do not derive retention from local staging
- do not silently overwrite an existing remote run directory
- do not broaden the task into a full storage abstraction rewrite

## Recommended minimal file impact
Most likely files:
- `src/backup_agent/app/config.py`
- `src/backup_agent/providers/storage/ftp.py`
- `src/backup_agent/providers/storage/factory.py`
- `src/backup_agent/providers/storage/__init__.py`
- `tests/test_config_and_scheduler.py`
- `tests/test_storage_backend_selection.py`
- a new focused FTP provider test file
- targeted docs for configuration and operations
