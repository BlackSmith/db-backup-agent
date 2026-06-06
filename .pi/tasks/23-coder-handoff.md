# Coder Handoff for Task 23

## Objective
Replace the current rsync retention model with a remote-manifest-driven flow.

When rsync publishing is enabled, the system must:

1. create the new backup in local staging
2. fetch existing remote manifests from the NAS
3. determine which remote runs are expired from that remote inventory
4. delete expired remote runs from the NAS
5. upload the new run

Do not re-upload retained remote manifest files during cleanup.

## Primary target
Refactor rsync storage behavior and the orchestrator sequencing with minimal impact outside the rsync path.

Before implementation, read:
- `.pi/tasks/23-rsync-remote-manifest-driven-retention.md`
- `.pi/tasks/23-implementation-notes.md`

## Recommended implementation order
1. Update `src/backup_agent/providers/storage/rsync.py`
2. Add any minimal supporting models/helpers in `src/backup_agent/providers/storage/base.py` only if needed
3. Adjust `src/backup_agent/services/orchestrator.py` so rsync cleanup occurs before rsync upload
4. Update focused rsync/provider/orchestrator tests
5. Update docs that describe rsync retention ordering or behavior
6. Run focused tests and then the full suite
7. Write `.pi/done/23-rsync-remote-manifest-driven-retention.md`

## Expected behavior

### Remote manifest inventory
The rsync provider should fetch only the remote metadata needed for retention planning.

Preferred minimum:
- run directory names
- `manifest.json` files

Do not download full dump artifacts for retention planning.

Preferred command shape:

```bash
rsync -a \
  --include='*/' \
  --include='manifest.json' \
  --exclude='*' \
  rsync://backup@nas.local/backups/ /tmp/backup-agent-remote-inventory/
```

### Retention planning
Compute expired runs from the remote inventory using the existing retention semantics:
1. `finished_at`
2. `started_at`
3. run-id timestamp fallback

### Remote deletion
Delete only expired remote run directories.

Do not:
- mirror the retained set back to the NAS from local staging
- rebuild the NAS tree from transient local directories
- upload retained manifests again during cleanup

Preferred command shape:

```bash
rsync -r \
  --files-from=/tmp/backup-agent-expired-runs.txt \
  --ignore-missing-args \
  --delete-missing-args \
  --force \
  /tmp/backup-agent-delete-root/ \
  rsync://backup@nas.local/backups/
```

This command shape is preferred specifically because it deletes only expired run directories without re-uploading retained manifests.

Compatibility note:
- the repository's `rsync.doc` confirms that the container rsync help includes `--ignore-missing-args`, `--delete-missing-args`, `--files-from`, `--list-only`, and `--force`
- the strategy is therefore realistic for the container rsync version from a feature-availability perspective
- still validate the real NAS daemon permissions before relying on it in production

### Upload ordering
For rsync-backed publication:
- cleanup first
- upload second

Preferred upload command shape:

```bash
rsync -a \
  --delete-delay \
  --delay-updates \
  /local/staging/runs/<run-id>/ \
  rsync://backup@nas.local/backups/<run-id>
```

If cleanup fails:
- do not upload the new run through rsync
- preserve local staging
- return an actionable failure/partial result through the existing run status model

## Constraints
- Keep changes localized.
- Preserve secret-safe rsync auth handling.
- Preserve mounted local storage behavior.
- Do not redesign unrelated provider or backup behavior.
- Do not add SSH transport.
- Do not change the on-NAS run layout except as required by the existing recent rsync path behavior.

## Acceptance checklist
- [ ] rsync retention fetches remote manifests before deciding deletions
- [ ] retention no longer depends on transient local staging contents
- [ ] only expired remote runs are deleted
- [ ] retained remote manifests are not re-uploaded during cleanup
- [ ] new rsync upload occurs after successful cleanup
- [ ] cleanup failure blocks new rsync upload
- [ ] local staging remains intact on cleanup failure
- [ ] focused tests pass
- [ ] full suite passes

## Suggested verification
```bash
python -m unittest tests.test_rsync_sync_and_retention tests.test_storage_backend_selection tests.test_health_and_orchestrator
python -m unittest discover -s tests
```

## Design caveat
If you discover that deleting a specific expired run directory is impractical with pure rsync daemon semantics alone, stop and document the exact limitation rather than silently falling back to re-uploading retained manifests.
