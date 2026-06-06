# Task 23 Implementation Notes

## Purpose
This note recommends a concrete API shape for implementing Task 23 with minimal disruption to the current codebase.

The goal is to keep mounted local storage behavior stable while introducing a safer rsync-specific retention flow based on remote manifests.

## Recommended design approach

### Keep the public storage abstraction stable where possible
The current `RemoteStorageProvider` contract is:

- `sync(local_path, remote_path=None)`
- `cleanup(local_path, retention_days)`

That API is too small for the new rsync-specific sequence because Task 23 needs distinct steps:

1. inventory remote manifests
2. compute remote expiration plan
3. delete expired remote runs
4. upload the new run

Trying to squeeze all of that into the existing `cleanup()` method would make orchestration opaque and difficult to test.

## Recommended API shape

### Option A: add rsync-specific helper methods and branch in orchestrator
Recommended minimal-change approach.

Keep `RemoteStorageProvider` unchanged for compatibility, but add rsync-specific helper methods on `RsyncStorageProvider` only.

Suggested methods:

```python
@dataclass(slots=True)
class RemoteManifestRecord:
    run_id: str
    remote_run_path: str
    manifest_local_path: Path | None = None
    finished_at: datetime | None = None
    started_at: datetime | None = None
```

```python
@dataclass(slots=True)
class RemoteManifestInventoryResult:
    status: str
    remote_root: str
    manifests: list[RemoteManifestRecord] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    error: RemoteStorageError | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
```

```python
@dataclass(slots=True)
class RemoteDeleteResult:
    status: str
    remote_destination: str
    deleted_run_ids: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stderr: str = ""
    error: RemoteStorageError | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
```

Suggested `RsyncStorageProvider` methods:

```python
def fetch_remote_manifests(self) -> RemoteManifestInventoryResult:
    ...

def delete_remote_runs(self, run_ids: list[str]) -> RemoteDeleteResult:
    ...

def plan_remote_retention(self, retention_days: int) -> tuple[list[RemoteManifestRecord], list[RemoteManifestRecord], list[str]]:
    ...
```

### Why Option A is preferred
- avoids broad changes to `LocalDirectoryStorageProvider`
- avoids broad changes to `CompositeStorageProvider`
- keeps the rsync redesign isolated to the rsync path
- makes tests much easier to write and reason about

## Orchestrator sequencing recommendation

### Current problem
The current orchestrator sequence is roughly:
- backup locally
- `remote_storage.sync(run_dir)`
- `remote_storage.cleanup(runs_root, retention_days)`

Task 23 needs the rsync path to become:
- backup locally
- remote manifest inventory
- remote deletion of expired runs
- upload new run

### Recommended implementation
Add a small rsync-specific branch in `BackupOrchestratorService.run_once()`.

Pseudo-flow:

```python
if isinstance(self.remote_storage, RsyncStorageProvider):
    inventory = self.remote_storage.fetch_remote_manifests()
    if not inventory.succeeded:
        fail run

    retained, expired, plan_errors = self.remote_storage.plan_remote_retention(...)
    delete_result = self.remote_storage.delete_remote_runs([record.run_id for record in expired])
    if not delete_result.succeeded:
        fail run before upload

    sync_result = self.remote_storage.sync(layout.run_dir)
    ...
else:
    # existing flow for local storage
```
```

### Composite backend case
Do not try to push this new sequence through `CompositeStorageProvider` generically.

Recommended behavior:
- keep composite provider as-is for now
- in orchestrator, detect when rsync is part of the configured backend set and sequence the rsync path explicitly
- keep local mounted storage publish behavior independent

If that becomes awkward, an acceptable small refactor is:
- keep `CompositeStorageProvider` only for simple publish aggregation
- let orchestrator handle rsync and local backends separately

This is preferable to forcing a large abstraction redesign inside Task 23.

## Manifest inventory recommendation

### Fetch only metadata
The provider should fetch only what is needed for retention planning.

Recommended rsync command shape:
- include directories
- include `manifest.json`
- exclude everything else

Recommended command example:

```bash
rsync -a \
  --include='*/' \
  --include='manifest.json' \
  --exclude='*' \
  rsync://backup@nas.local/backups/ /tmp/backup-agent-remote-inventory/
```

Expected local result shape:

```text
/tmp/backup-agent-remote-inventory/
  20260601T020000Z-aaa11111/
    manifest.json
  20260602T020000Z-bbb22222/
    manifest.json
```

This preserves:
- remote run directory names
- remote manifest files

while avoiding full artifact download.

### Optional listing-only fallback
If the implementation needs a lightweight existence check before pulling manifests, an acceptable supplemental command is:

```bash
rsync --list-only rsync://backup@nas.local/backups/
```

Use this only as a helper; the retention decision should still come from the manifest-aware inventory so timestamp precedence stays aligned with the existing retention rules.

### Reuse existing retention timestamp logic
Do not invent a second timestamp model.

Recommended reuse:
- parse remote downloaded manifests with the same precedence already used by `services.retention`:
  1. `finished_at`
  2. `started_at`
  3. run-id fallback

A small shared helper extracted from `services.retention` is acceptable if it reduces duplication.

## Remote deletion recommendation

### Preferred behavior
Delete only expired remote run directories.

### Important implementation note
The task requirement is stronger than the current rsync retained-set mirroring model:
- do not mirror retained manifests back to the NAS
- do not rebuild the remote root from a local retained set

So the deletion helper should be explicit and targeted.

### Recommended rsync-native delete strategy
Use `--files-from` together with `--delete-missing-args` against an empty local root.

Recommended preparation:
1. create an empty local directory, for example `/tmp/backup-agent-delete-root/`
2. write a text file containing one expired run ID per line, for example:

```text
20260601T020000Z-aaa11111
20260602T020000Z-bbb22222
```

Recommended command example:

```bash
rsync -r \
  --files-from=/tmp/backup-agent-expired-runs.txt \
  --ignore-missing-args \
  --delete-missing-args \
  --force \
  /tmp/backup-agent-delete-root/ \
  rsync://backup@nas.local/backups/
```

Intended effect:
- each listed run ID is treated as a missing source arg relative to the empty local root
- rsync deletes only the matching destination path under `remote_root`
- retained run directories are not traversed or re-uploaded
- retained `manifest.json` files remain untouched on the NAS

### Practical API suggestion
Suggested helper signature:

```python
def delete_remote_runs(self, run_ids: list[str]) -> RemoteDeleteResult:
    ...
```

Internally, the implementation may use one rsync-native strategy or multiple scoped commands, as long as:
- only expired run directories are removed
- retained remote manifests are untouched
- no retained remote files are uploaded during cleanup

### Exact anti-pattern to avoid
Do not do this during cleanup:

```bash
rsync -a --delete <local-retained-view>/ rsync://backup@nas.local/backups/
```

That pattern would re-send retained manifests and risks overwriting authoritative metadata already stored on the NAS.

The repository includes `rsync.doc`, which reflects the container rsync help output. It confirms support for:
- `--ignore-missing-args`
- `--delete-missing-args`
- `--files-from`
- `--list-only`
- include/exclude filters
- `--force`

That means the proposed strategy is realistic for the container rsync version from a CLI-capability perspective.

Implementation caveat:
- because expired runs are non-empty directories, prefer including `--force` in the delete command so directory deletion is not blocked by non-empty contents
- final validation is still required against the real NAS daemon permissions and module configuration

If the recommended `--delete-missing-args` strategy proves impossible in pure rsync daemon mode against the real NAS, coder should stop and document the exact transport limitation.

## Upload command reminder

The new run upload should remain a normal run-scoped publish step after successful cleanup.

Recommended command shape:

```bash
rsync -a \
  --delete-delay \
  --delay-updates \
  /local/staging/runs/20260606T020000Z-ccc33333/ \
  rsync://backup@nas.local/backups/20260606T020000Z-ccc33333
```

This keeps the existing on-NAS layout of one run directory per run ID, directly under `remote_root`.

## Testing recommendation

### Rsync provider tests
Add focused tests for:
- manifest-only inventory command shape
- retention planning from remote manifests
- targeted delete invocation for expired runs only
- no retained manifest upload during cleanup path
- upload still publishes the new run to `remote_root/<run-id>`

### Orchestrator tests
Add focused tests for:
- rsync cleanup happens before rsync upload
- cleanup failure blocks upload
- staging remains on disk when cleanup fails
- local-only storage behavior remains unchanged
- combined backend behavior remains explicit and deterministic

## What not to do in Task 23
- do not redesign all storage abstractions into a large workflow engine
- do not force mounted local storage to adopt the same remote-inventory model
- do not silently fall back to the old retained-set mirroring behavior
- do not overwrite remote retained manifests as a side effect of cleanup

## Recommended minimal file impact
Most likely files:
- `src/backup_agent/providers/storage/rsync.py`
- `src/backup_agent/providers/storage/base.py` (small DTO additions only if needed)
- `src/backup_agent/services/orchestrator.py`
- `tests/test_rsync_sync_and_retention.py`
- `tests/test_health_and_orchestrator.py`
- `tests/test_storage_backend_selection.py`

Keep any doc changes targeted to rsync retention behavior.
