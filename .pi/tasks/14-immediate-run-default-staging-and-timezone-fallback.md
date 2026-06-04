# Task 14: Immediate Run Fallback and Config Default Updates

## Goal
Relax the configuration and startup behavior so the agent can run immediately when `BACKUP_TIME` is not set, while also updating the default local staging path and timezone fallback behavior.

## User request this task must satisfy

- If `BACKUP_TIME` is not set, the backup should run immediately.
- Change the default `LOCAL_BACKUP_DIR` to `/temporary_storage`.
- The default timezone should be inherited from environment variables.

## Architectural decision for this task

To remove ambiguity and keep the implementation deterministic:

- In `--schedule` mode, if `BACKUP_TIME` is omitted, the application should execute one immediate backup cycle and then return successfully instead of entering the daily scheduler wait loop.
- In `--run-once` mode, omitting `BACKUP_TIME` should simply stop being a configuration error.
- A non-empty but invalid `BACKUP_TIME` must remain a configuration error.
- Timezone fallback precedence should be:
  1. explicit `TZ` value in the provided config mapping
  2. process environment `os.environ["TZ"]` if present
  3. `UTC`

## Background

Current behavior is stricter than the requested deployment model:

- `BACKUP_TIME` is currently required by config validation.
- `LOCAL_BACKUP_DIR` currently defaults to `/backup`.
- `TZ` currently falls back directly to `UTC` at config-parse time.

This task should make the startup path friendlier for container deployments that want immediate execution and ephemeral local staging.

## Scope

- Update configuration parsing so `BACKUP_TIME` becomes optional.
- Preserve format validation for non-empty `BACKUP_TIME` values.
- Update startup / scheduling behavior so missing `BACKUP_TIME` triggers an immediate run.
- Change the default local staging root from `/backup` to `/temporary_storage`.
- Update timezone fallback handling to inherit the process environment when possible.
- Update logs, tests, and documentation affected by the new defaults and optional schedule time.

## Deliverables

- `AppConfig` update for optional `BACKUP_TIME` handling or an equivalent explicit immediate-run mode.
- Entrypoint and/or scheduler changes that implement the immediate-run fallback.
- Default `LOCAL_BACKUP_DIR` updated to `/temporary_storage`.
- Timezone resolution updated to prefer the environment before falling back to `UTC`.
- Tests covering the new configuration and startup behavior.
- README / deployment documentation updates for the new defaults.

## Constraints

- Keep the implementation localized.
- Do not change backup discovery, database backup providers, or storage backend semantics.
- Do not invent a recurring schedule when `BACKUP_TIME` is missing.
- Preserve existing behavior when `BACKUP_TIME` is explicitly configured.
- Keep invalid explicit times failing fast.

## Acceptance criteria

- A configuration without `BACKUP_TIME` validates successfully when all other required settings are present.
- `main(["--run-once"])` no longer fails only because `BACKUP_TIME` is missing.
- In `--schedule` mode with no `BACKUP_TIME`, the orchestrator is executed immediately once and the process returns successfully.
- In `--schedule` mode with a valid `BACKUP_TIME`, the existing daily scheduler behavior remains unchanged.
- A non-empty invalid `BACKUP_TIME` such as `25:99` still raises a configuration error.
- If `LOCAL_BACKUP_DIR` is omitted, the config uses `/temporary_storage`.
- If `TZ` is omitted from the provided config mapping but exists in the process environment, that timezone is used.
- If `TZ` is omitted everywhere, the config still falls back to `UTC`.
- Tests pass with:

```bash
python -m unittest discover -s tests
```

## Suggested implementation notes

- The smallest change is likely to make `AppConfig.backup_time` optional (`time | None`) and branch in `run_scheduler` before constructing `DailyScheduler`.
- Keep `DailyScheduler` focused on the scheduled case; do not overload it with implicit immediate-run semantics if a simple caller-side branch is enough.
- Update configuration logging so missing `BACKUP_TIME` is represented clearly, for example as `immediate` or an empty value.
- Review any documentation and example config that still assumes `/backup` as the default staging root.
- Add tests for timezone fallback using `patch.dict("os.environ", ...)` so inherited `TZ` behavior is explicit.

## Likely files to inspect

- `src/backup_agent/app/config.py`
- `src/backup_agent/app/main.py`
- `src/backup_agent/services/scheduler.py`
- `src/backup_agent/infrastructure/logging.py`
- `tests/test_config_and_scheduler.py`
- `tests/test_bootstrap.py`
- `README.md`
- `docker-compose.yml`

## Suggested verification

- Add or update focused unit tests for config parsing and scheduler behavior first.
- Verify that missing `BACKUP_TIME` no longer blocks startup.
- Verify that invalid explicit `BACKUP_TIME` values still fail.
- Run the full test suite:

```bash
python -m unittest discover -s tests
```
