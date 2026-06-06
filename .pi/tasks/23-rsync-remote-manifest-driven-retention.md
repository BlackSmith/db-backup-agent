# Task 23: Rsync Remote-Manifest-Driven Retention and Safe Upload Ordering

## Goal
Redesign rsync-backed retention so the application no longer derives the remote deletion set from transient local staging directories.

When rsync publishing is enabled, the application should:

1. create the new backup run in local temporary storage
2. fetch the existing remote backup manifests from the NAS
3. determine which remote runs are expired from that remote inventory
4. delete only those expired remote runs from the NAS
5. upload the newly created run

The design must explicitly avoid re-uploading retained remote manifest files back to the NAS during cleanup.

## User-requested behavior
The user wants rsync retention to be driven by the current state on the NAS, not by the current state of local transient storage.

Important constraint:

- manifest files for remote runs that remain on the NAS must not be uploaded again during cleanup, because that could overwrite retained metadata unexpectedly

## Background / problem statement
The current rsync retention implementation builds a retained-runs view from local transient staging and mirrors that view back to the rsync remote root with delete semantics.

That is unsafe because:

- local staging is intentionally transient and may be cleaned up after successful publication
- local staging can be lost independently of the NAS
- ransomware or accidental local deletion could shrink the local retained set and cause unintended remote deletion on the next successful run

This task should replace that retention source of truth with a remote-manifest-based inventory.

## Scope

### In scope
- redesign rsync retention logic only
- add a remote inventory path that fetches existing remote manifests from the NAS
- compute expired vs retained runs from the remote inventory
- delete only expired remote runs from the NAS
- perform the new rsync upload after cleanup
- preserve the mounted local storage backend behavior unless a very small shared abstraction is needed
- update tests and docs that describe rsync retention ordering or rsync remote layout

### Out of scope
- redesigning mounted local storage retention
- adding SSH transport
- changing backup provider behavior
- introducing encryption, notifications, or restore flows
- broad renames of the storage abstraction

## Recommended architecture

### High-level flow for rsync-backed runs
When the configured storage backend includes rsync, the orchestrator flow should become:

1. produce the local run in staging
2. write the local manifest for the new run
3. ask the rsync provider to inventory remote manifests from the NAS
4. compute which remote runs are expired from the remote inventory
5. delete only the expired remote run directories on the NAS
6. upload the new run directory to the NAS
7. if all configured backends succeed, continue with existing post-success cleanup behavior

### Remote inventory approach
Assume rsync daemon-style transport only.

Preferred minimal approach:
- use rsync include/exclude rules to download only:
  - top-level run directories
  - `manifest.json` files
- do not download database dump artifacts during retention planning

Acceptable inventory source shapes:
- top-level run directory names only, if the run-id timestamp is sufficient
- top-level run directory names plus `manifest.json`, if manifest timestamps remain the chosen source of truth

Recommended preference:
- continue using the existing retention timestamp rules:
  1. `finished_at`
  2. `started_at`
  3. run-id timestamp fallback
- therefore fetch remote `manifest.json` files during rsync retention planning

### Remote deletion strategy
Because rsync daemon mode is not a remote shell, avoid designs that require arbitrary remote commands.

Recommended deletion mechanism:
- issue targeted rsync delete operations per expired run directory
- keep deletion scoped to the specific expired run path, not to the entire remote root

If the implementation instead needs a small provider helper that mirrors a deletion sentinel directory or uses another rsync-native pattern, that is acceptable only if:
- deletion remains scoped to expired run directories
- retained remote manifests are not re-uploaded
- the implementation does not require re-syncing the full retained set back to the NAS

## Key constraints
- Do not use transient local staging as the source of truth for remote retention.
- Do not re-upload retained remote manifests during cleanup.
- Do not download full remote backup payloads just to compute retention.
- Keep rsync credentials secret-safe.
- Keep the change localized to rsync storage handling, orchestrator ordering, targeted tests, and docs.
- Preserve existing local mounted storage behavior.
- Preserve current run status semantics (`success`, `partial`, `sync_failed`, etc.) unless a very small clarification is required.

## Expected behavior details

### Ordering
For rsync-backed publication:
- remote cleanup runs before the new upload
- if remote cleanup fails, the new rsync upload should not proceed
- local staging must remain intact when remote cleanup fails

Reason:
- the user explicitly requested: inspect NAS manifests, decide deletions, perform NAS deletion, then upload the new run

### Manifest handling
- retained remote runs stay untouched on the NAS
- their `manifest.json` files must not be re-uploaded during cleanup
- only the new run's manifest is uploaded as part of the new run publish step

### Composite backend behavior
If both local mounted storage and rsync are enabled:
- local mounted storage may keep its current publish behavior unless the orchestrator needs small sequencing changes
- rsync-specific retention/deletion logic should remain isolated to the rsync provider path
- be explicit in tests about the ordering when rsync is part of a composite backend

## Acceptance criteria
- rsync retention no longer uses local staging contents to decide which remote runs survive
- the application fetches remote manifest inventory from the NAS before rsync retention
- expired remote runs are determined from the remote inventory
- only expired remote run directories are deleted from the NAS
- retained remote manifests are not re-uploaded during cleanup
- the new run is uploaded after successful remote cleanup
- rsync cleanup failure prevents the new rsync upload and preserves local staging
- mounted local storage behavior remains unchanged unless explicitly documented
- focused rsync/orchestrator tests pass
- full test suite passes

## Likely files to inspect
- `src/backup_agent/providers/storage/rsync.py`
- `src/backup_agent/providers/storage/base.py`
- `src/backup_agent/providers/storage/composite.py`
- `src/backup_agent/services/orchestrator.py`
- `src/backup_agent/services/retention.py`
- `tests/test_rsync_sync_and_retention.py`
- `tests/test_storage_backend_selection.py`
- `tests/test_health_and_orchestrator.py`
- docs describing rsync retention behavior

## Suggested verification
```bash
python -m unittest tests.test_rsync_sync_and_retention tests.test_storage_backend_selection tests.test_health_and_orchestrator
python -m unittest discover -s tests
```

## Design caveats
- Rsync daemon transport is inventory-capable but not a general remote shell. Favor rsync-native manifest download and targeted delete operations.
- If explicit remote deletion for a single run directory proves awkward with pure rsync daemon semantics, stop and document the exact transport constraint before broadening the design.
- Keep retained remote manifests authoritative on the NAS; do not regenerate or overwrite them during cleanup.
