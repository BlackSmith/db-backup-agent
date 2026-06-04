# Coder Handoff for Task 15

## Objective
Make the real application runtime capable of performing an actual backup run against the live PostgreSQL and MariaDB containers reachable via `/var/run/docker.sock`, and verify successful publication into `/workspaces/backup_agent/storage` using the local storage backend.

If the first live run fails, fix the application in the same coder session and rerun until it succeeds.

## Highest-priority blocker already identified

The first thing to inspect is `src/backup_agent/app/main.py`.

Current behavior:

- `run_once(...)` performs a no-op when no orchestrator is injected.
- `main(...)` calls `run_once(config)` without constructing a real orchestrator.

This almost certainly prevents any live backup from running through the real CLI path.

## Recommended execution order

1. Inspect and fix runtime bootstrap / composition
   - `src/backup_agent/app/main.py`
   - any small supporting bootstrap code needed nearby
2. Verify live container discovery through `/var/run/docker.sock`
3. Run a real one-shot backup targeting local mounted storage
4. If failures occur, fix the smallest blocking issue and rerun
5. Add or update focused tests for the runtime bootstrap changes
6. Run the full test suite
7. Write `.pi/done/15-live-local-storage-validation-and-runtime-fix.md`

## Runtime design intent

Use the existing architecture rather than creating a second execution path.

The real CLI should compose the already-implemented pieces:

- `AppConfig`
- Docker API client / container discovery
- metadata resolver
- `BackupOrchestratorService`
- configured storage provider(s)

The preferred outcome is that `backup-agent --run-once` can execute a real backup with no test-only injection.

## Live verification target

### Required publish destination

- `BACKUP_LOCAL_STORAGE=/workspaces/backup_agent/storage`

### Required separation of staging vs. published output

Use a distinct staging directory, for example:

- `LOCAL_BACKUP_DIR=/workspaces/backup_agent/.temporary_storage`

Do not use the same path for both.

### Docker access

- `DOCKER_SOCKET_PATH=/var/run/docker.sock`

### Database targets

Use the real running containers discovered from the live Docker socket.

The repo strongly suggests one PostgreSQL and one MariaDB container, but confirm the actual runtime state instead of trusting static assumptions.

## Practical note about tooling

The architect session observed that the shell environment may not include the `docker` CLI.

So during implementation and verification:

- prefer the existing Docker socket client already present in the codebase, or
- use a very small Python helper against `/var/run/docker.sock`

Do not spend the task adding Docker tooling if the existing API client is enough.

## Minimum expected code outcomes

- Real runtime bootstrap exists and is used by the CLI path.
- A one-shot CLI invocation performs a real backup run.
- Published output lands in `/workspaces/backup_agent/storage/runs/<run-id>/...`.
- The run manifest is present.
- PostgreSQL and MariaDB artifacts are both present.
- Existing tests still pass.

## Minimum expected verification evidence

Capture in the done note:

1. how the live environment was inspected
2. the exact command used to run the backup
3. the final published directory tree under `/workspaces/backup_agent/storage`
4. confirmation that both DB engines produced artifacts
5. the result of `python -m unittest discover -s tests`

## Acceptance checklist

- [ ] Real CLI/runtime path no longer performs a no-op
- [ ] Live Docker socket discovery works
- [ ] PostgreSQL backup artifact exists in published output
- [ ] MariaDB backup artifact exists in published output
- [ ] Manifest exists in published output
- [ ] Any discovered runtime bug was fixed and verified by rerun
- [ ] Full test suite passes
- [ ] Done note includes reproducible verification steps

## Notes for minimal-change execution

- Keep fixes localized to runtime composition and any directly exposed defects.
- Avoid broad refactors unless a narrowly scoped bug fix is impossible otherwise.
- Do not weaken secret handling for the sake of easier live verification.
- Prefer fixing the real path over adding special-case test hooks.
