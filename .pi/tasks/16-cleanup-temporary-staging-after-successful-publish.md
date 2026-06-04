# Task 16: Cleanup Temporary Staging After Successful Publish

## Goal
Ensure that the temporary local staging directory is cleaned up after a successful backup run once the data has been safely published to its configured durable destination(s).

## User request this task must satisfy

- After a successful database export and successful copy to local mounted storage and/or upload to NAS, the temporary directory must be cleaned up.

## Background

The current system uses a local staging directory to assemble one complete backup run before publication.

Recent live validation showed that successful publication can still leave temporary staging data behind. This is undesirable because the staging area is intended to be transient working space, not durable backup storage.

The cleanup behavior now needs to be made explicit and deterministic for all successful publish flows.

## Scope

- Define and implement post-success cleanup of the temporary staging run directory.
- Ensure cleanup works for these cases:
  - local mounted storage only
  - rsync / NAS only
  - both backends enabled together
- Only clean staging after all configured publish targets for the run have completed successfully.
- Keep staging data intact when publication fails or is partial, so retry/debugging remains possible.
- Ensure cleanup logic does not delete the durable published copy.
- Add or update tests for the cleanup behavior.

## Required behavior

### Successful publish

If the run finishes with successful artifact creation and all configured publish targets succeed:

- the temporary run directory under `LOCAL_BACKUP_DIR` must be removed
- any empty temporary parent directories or staging pointers created only for staging should be cleaned up when appropriate
- the published durable copy must remain intact

### Failed or partial publish

If any configured publish target fails:

- do not remove the temporary staging run directory for that run
- keep the staged data available for debugging or retry

## Deliverables

- Orchestrator and/or staging cleanup changes that remove temporary staging after successful publish.
- Tests covering:
  - cleanup after successful local-storage publish
  - cleanup after successful rsync-only publish
  - cleanup after successful combined publish
  - preservation of staging after failed publish
- A completion note under:
  - `.pi/done/16-cleanup-temporary-staging-after-successful-publish.md`

## Constraints

- Keep implementation localized.
- Do not change backup discovery or database backup behavior.
- Do not delete durable storage outputs.
- Do not delete staging data before all configured publish targets for the run succeed.
- Preserve data needed for retry/debugging on failed or partial runs.

## Acceptance criteria

- After a successful local-storage publish, the temporary staging run directory is removed.
- After a successful rsync / NAS publish, the temporary staging run directory is removed.
- After a successful combined local+rsync publish, the temporary staging run directory is removed.
- If publication fails or is partial, the temporary staging run directory is preserved.
- Published backups remain available in the durable target location(s).
- Tests pass with:

```bash
python -m unittest discover -s tests
```

## Suggested implementation notes

- The cleanup decision likely belongs in the orchestrator because it already knows the final run outcome and whether all configured publish targets succeeded.
- The filesystem deletion itself may belong in `LocalStagingManager` so staging path rules remain centralized.
- Review the current sequence of:
  - artifact creation
  - manifest writing
  - publish
  - retention
  - staging cleanup

  and make sure the manifest needed by durable outputs exists before the staging tree is removed.
- Be careful with the distinction between:
  - cleaning only the current run staging directory
  - cleaning the entire staging root

  Prefer the smallest safe deletion that satisfies the request.

## Likely files to inspect

- `src/backup_agent/services/orchestrator.py`
- `src/backup_agent/services/staging.py`
- `src/backup_agent/services/retention.py`
- `tests/test_health_and_orchestrator.py`
- `tests/test_local_staging_and_manifest.py`
- any live-validation related tests that cover storage publishing

## Suggested verification

- Add focused unit tests for successful and failed publish cleanup behavior.
- Run the full suite:

```bash
python -m unittest discover -s tests
```
