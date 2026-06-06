# Task 23 - Rsync Remote-Manifest-Driven Retention and Safe Upload Ordering: implementation record

## Implemented

- Replaced the rsync cleanup flow with a remote-manifest-driven retention path.
- Added rsync-side remote inventory support that downloads only remote `manifest.json` files for retention planning.
- Added rsync-side retention planning based on the remote manifest inventory, using the existing timestamp precedence:
  - `finished_at`
  - `started_at`
  - run-id timestamp fallback
- Added targeted rsync remote deletion support for expired run directories using rsync-native deletion arguments.
- Changed orchestrator sequencing so rsync cleanup runs before rsync upload.
- Preserved mounted local storage behavior for non-rsync paths.
- Ensured retained remote manifests are not re-uploaded during cleanup.

## Changed files

- `src/backup_agent/providers/storage/base.py`
- `src/backup_agent/providers/storage/rsync.py`
- `src/backup_agent/services/orchestrator.py`
- `tests/test_rsync_sync_and_retention.py`
- `.pi/tasks/23-rsync-remote-manifest-driven-retention.md`
- `.pi/tasks/23-coder-handoff.md`
- `.pi/tasks/23-implementation-notes.md`
- `.pi/context.md`
- `.pi/architecture.md`

## Verification

- Ran targeted tests successfully:
  - `python -m unittest tests.test_rsync_sync_and_retention tests.test_health_and_orchestrator -v`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`
- Also validated the container rsync feature set against `rsync.doc` and the local `rsync` binary.

## Notes

- The implementation uses rsync CLI features available in the container version, including `--include`, `--exclude`, `--files-from`, `--ignore-missing-args`, `--delete-missing-args`, and `--force`.
- The real NAS rsync daemon permissions and module configuration still need operational validation in a live environment.
