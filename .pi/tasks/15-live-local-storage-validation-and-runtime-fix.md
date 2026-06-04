# Task 15: Live Local-Storage Validation and Runtime Fix

## Goal
Perform a real end-to-end backup run against the currently available PostgreSQL and MariaDB containers reachable through `/var/run/docker.sock`, publishing completed backups into `/workspaces/backup_agent/storage` using the local mounted storage backend.

If the real run exposes application defects or missing runtime wiring, fix the application in the same task and rerun until the live backup succeeds.

## User request this task must satisfy

- Use the real Docker socket at `/var/run/docker.sock`.
- Back up the two real database containers currently available in the environment.
- Publish the completed backup output into `/workspaces/backup_agent/storage`.
- If the application fails during the real run, fix it immediately rather than stopping at diagnosis.

## Important discovery from architect analysis

The current runtime entrypoint is not yet fully wired for production execution:

- `src/backup_agent/app/main.py` still treats the orchestrator as an optional injected dependency.
- When no orchestrator is provided, `run_once(...)` logs a placeholder message and skips backup execution.

This means a real invocation of the current application is expected to fail the user goal until the runtime bootstrap is completed.

## Scope

- Wire the real application bootstrap so the CLI can execute an actual backup run without test-only dependency injection.
- Use the real Docker socket to discover the currently running PostgreSQL and MariaDB containers.
- Configure the run to use local mounted storage only:
  - `BACKUP_LOCAL_STORAGE=/workspaces/backup_agent/storage`
  - a separate local staging directory that is not equal to the mounted storage path
- Execute a real backup run.
- Verify that the resulting published output contains successful artifacts and a manifest for both databases.
- If any runtime, discovery, metadata, provider, staging, manifest, or local-storage publish issue appears, fix it in the same task and rerun.
- Keep the final implementation and verification notes focused and reproducible.

## Expected live-test setup

The coder session should validate the actual environment first, but the repository context strongly suggests:

- one PostgreSQL container
- one MariaDB container
- credentials and labels provided by the running compose-style environment

Do not hardcode assumptions if the live environment differs; inspect the actual containers first.

## Deliverables

- Runtime bootstrap changes needed for a real CLI-driven backup run.
- Any minimal bug fixes required to make the live local-storage backup succeed.
- Verification that `/workspaces/backup_agent/storage` contains a published run directory with:
  - `manifest.json`
  - PostgreSQL backup artifact(s)
  - MariaDB backup artifact(s)
  - a valid `latest` marker or equivalent pointer maintained by the local storage backend
- A completion note under:
  - `.pi/done/15-live-local-storage-validation-and-runtime-fix.md`

## Constraints

- Prefer minimal, localized code changes.
- Do not change unrelated architecture or broad abstractions.
- Do not switch this task to rsync; the required target is mounted local storage.
- Do not set `BACKUP_LOCAL_STORAGE` equal to the staging directory.
- Do not expose database passwords or other secrets in logs, docs, or task notes.
- Preserve the existing discovery and provider architecture unless a small runtime wiring fix is required.
- If Docker CLI is unavailable in the shell, use the existing Docker socket integration or a small Python helper instead of adding unnecessary tooling.

## Acceptance criteria

- Running the application through its real CLI/runtime path performs an actual backup instead of the current placeholder no-op.
- The application discovers the two real database containers from `/var/run/docker.sock`.
- A successful run publishes backup data to `/workspaces/backup_agent/storage`.
- The published run contains a manifest and backup artifacts for both PostgreSQL and MariaDB.
- If defects were found, they are fixed in the application and the live run is re-executed successfully.
- Automated regression tests still pass after the fix:

```bash
python -m unittest discover -s tests
```

- The done note includes the exact live verification commands used and a short summary of the produced artifacts.

## Suggested implementation notes

- Start by inspecting the current runtime bootstrap path in:
  - `src/backup_agent/app/main.py`
  - any related application wiring modules
- Reuse existing building blocks instead of inventing a parallel runtime path:
  - Docker API client
  - discovery service
  - metadata resolver
  - backup orchestrator
  - local storage provider factory
- Prefer a direct one-shot invocation for the live validation step.
- Use an explicit staging directory for the live run, for example under the workspace, so the mounted destination remains the published output only.
- Capture the final artifact tree with a non-secret directory listing in the completion note.

## Likely files to inspect

- `src/backup_agent/app/main.py`
- `src/backup_agent/app/config.py`
- `src/backup_agent/infrastructure/docker.py`
- `src/backup_agent/services/discovery.py`
- `src/backup_agent/services/metadata_resolver.py`
- `src/backup_agent/services/orchestrator.py`
- `src/backup_agent/providers/storage/local_directory.py`
- `README.md`
- `tests/test_bootstrap.py`
- `tests/test_health_and_orchestrator.py`
- any bootstrap / integration-oriented tests that need adjustment

## Suggested live verification flow

1. Inspect the live containers reachable through `/var/run/docker.sock`.
2. Clear or archive old contents under `/workspaces/backup_agent/storage` if needed for deterministic verification.
3. Run the application with local-storage-focused configuration.
4. If the run fails, fix the application and rerun.
5. Inspect the resulting published run tree.
6. Run the automated test suite.

## Suggested live configuration shape

Use real credentials from the running environment, but the storage-related configuration should look like:

```bash
BACKUP_LOCAL_STORAGE=/workspaces/backup_agent/storage
LOCAL_BACKUP_DIR=/workspaces/backup_agent/.temporary_storage
DOCKER_SOCKET_PATH=/var/run/docker.sock
BACKUP_RETENTION_DAYS=7
```

If `BACKUP_TIME` remains required at implementation time, set a safe explicit value only for the live verification command. If Task 14 has already been implemented, omission is acceptable according to the new semantics.
