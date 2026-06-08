# Task 24 Retention Notes: FTP / FTPS Remote Retention Algorithm

## Purpose
This note defines a concrete, safe retention algorithm for the planned FTP / FTPS storage backend.

The goal is to make retention decisions from the remote server state, not from transient local staging.

## Core rule
FTP / FTPS retention must treat the remote destination as the source of truth.

That means:
- list remote runs from the FTP / FTPS server
- inspect remote metadata for those runs
- compute expired vs retained runs from that remote inventory
- delete only expired remote run directories
- update the remote `latest` marker after cleanup

Do not:
- derive deletion from local staging contents
- delete files from a retained run directory one by one as a retention shortcut
- rebuild the remote tree from local retained runs

## Recommended remote layout assumption

```text
<FTP_REMOTE_PATH>/
  runs/
    <run-id>/
      manifest.json
      ...artifacts...
  latest
```

The retention algorithm assumes:
- all backup runs live under `runs/`
- each run has a unique run directory name
- `latest` is a simple text file containing `runs/<run-id>`

## Recommended retention algorithm

### Step 1: connect
- establish FTP or FTPS connection
- login
- enable protected data channel for FTPS via `prot_p()`
- configure passive mode according to `FTP_PASSIVE`

### Step 2: enumerate remote run directories
List entries under:

```text
<FTP_REMOTE_PATH>/runs/
```

Recommended rule:
- consider only directory-like entries that do not start with `.`
- ignore helper files and temporary directories unless the implementation explicitly recognizes them

### Step 3: fetch remote manifests
For each candidate run directory:
- attempt to read `manifest.json`
- parse JSON if available

Recommended metadata precedence for timestamp extraction:
1. `finished_at`
2. `started_at`
3. run-id timestamp fallback

### Step 4: classify each run
For each remote run:
- if timestamp is valid and older than cutoff: classify as expired
- if timestamp is valid and within retention window: classify as retained
- if metadata is missing or unreadable: classify as retained and record an error

Recommended cutoff rule:

```text
cutoff_at = now_utc - retention_days
```

### Step 5: delete expired remote run directories
Delete only whole run directories under:

```text
<FTP_REMOTE_PATH>/runs/<run-id>/
```

Recommended behavior:
- recursively delete all files first
- recursively delete nested directories
- remove the run directory itself last

If deletion of one run fails:
- record a cleanup error
- continue attempting the remaining expired runs if the implementation can do so safely
- return `partial` if some deletes succeeded and some failed

### Step 6: recompute and update `latest`
After deletion:
- determine the newest retained run
- write `latest` as:

```text
runs/<newest-run-id>
```

If no retained runs remain:
- remove `latest` if possible
- if deletion is awkward on a given server, document the fallback clearly instead of silently leaving stale data

## Timestamp extraction rules

### Preferred manifest fields
Use:
- `finished_at`
- `started_at`

Both should be parsed as ISO timestamps.

### Fallback to run-id
If the manifest is missing, unreadable, or lacks timestamps, fall back to parsing the run-id prefix.

Expected run-id shape:

```text
YYYYMMDDTHHMMSSZ-<suffix>
```

Example:

```text
20260607T020000Z-a1b2c3d4
```

### Safe failure rule
If neither manifest metadata nor run-id parsing yields a timestamp:
- do not delete the run
- record an error in the cleanup result

## Directory listing strategy
FTP servers vary in listing behavior.

### Recommended preference order
1. use `mlsd()` if available and reliable
2. otherwise use `nlst()` or `retrlines('LIST')` with the smallest parsing needed

### Why `mlsd()` is preferred
- machine-readable facts
- easier to distinguish directories from files
- less locale-dependent than `LIST`

### Fallback rule
If the server does not support `MLSD`:
- use the smallest acceptable fallback
- document the exact trade-off in the implementation note if parsing becomes imperfect

## Manifest retrieval strategy
Recommended approach:
- retrieve `manifest.json` into memory with `retrbinary()`
- parse JSON immediately
- avoid persisting temporary local manifest files unless that materially simplifies the implementation

Reason:
- manifest files are small
- in-memory parsing keeps the implementation localized
- avoids extra temporary-file lifecycle complexity

## Recursive delete strategy
FTP has no single portable "delete directory tree" primitive.

Recommended algorithm for deleting one run directory:
1. list entries inside the directory
2. for each file: `delete()`
3. for each subdirectory: recursively delete it
4. call `rmd()` on the now-empty directory

Pseudo-shape:

```python
def delete_tree(path):
    for entry in list_entries(path):
        child = join(path, entry.name)
        if entry.is_dir:
            delete_tree(child)
        else:
            ftp.delete(child)
    ftp.rmd(path)
```

### Safety note
Never point recursive delete at `FTP_REMOTE_PATH` itself.
Only delete directories already classified as expired runs under `runs/`.

## Status mapping recommendation

### Success
- inventory succeeded
- all eligible expired run directories were deleted
- `latest` was updated correctly or removed when appropriate
- no retention errors recorded

### Partial
- some expired runs were deleted successfully
- some retention steps failed
- or ambiguous runs were retained due to unreadable metadata

### Failed
- remote inventory could not be built
- or no deletion/update step could proceed safely

## Recommended result behavior
Use the existing `RemoteCleanupResult` shape for the public provider contract.

Recommended message strategy:
- aggregate cleanup errors into a concise `RemoteStorageError.message`
- preserve the remote destination path in the result
- avoid embedding secrets or raw credentials in any error output

## Upload / retention sequencing recommendation
For FTP / FTPS, keep the standard non-rsync sequence:
1. upload the new run
2. if upload succeeds, run retention cleanup
3. if all configured backends succeed, clean up local staging

Reason:
- FTP cleanup is based on remote inventory and does not need the rsync-specific pre-upload delete model
- this keeps FTP behavior aligned with mounted local storage and existing orchestrator expectations

## Edge cases to handle explicitly

### Missing `runs/` directory
Treat as:
- no retained runs
- cleanup success
- `latest` should be absent

### Existing `latest` points to a deleted run
After cleanup, overwrite `latest` with the correct newest retained run or remove it if no runs remain.

### Run directory exists without `manifest.json`
Retain it and record an error.

### Broken / invalid JSON manifest
Retain it and record an error.

### Empty server
- cleanup succeeds
- upload path remains unaffected
- `latest` should not reference stale data

## Testing recommendations
Add focused tests for:
- remote run listing from FTP metadata
- manifest-based expiration decision
- fallback to run-id parsing
- recursive delete of one expired run tree
- ambiguous runs retained on metadata parse failure
- `latest` update after cleanup
- no-run case removing or clearing stale `latest`

## What not to do
- do not make FTP retention depend on local staging contents
- do not delete the whole remote root just to enforce retention
- do not silently ignore manifest parse failures and continue deleting ambiguous runs
- do not overwrite retained manifests as part of cleanup
