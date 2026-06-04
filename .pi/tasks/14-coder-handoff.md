# Coder Handoff for Task 14

## Objective
Implement the behavior described in `.pi/tasks/14-immediate-run-default-staging-and-timezone-fallback.md`.

The key change is to make `BACKUP_TIME` optional and treat its absence as an immediate-run mode instead of a configuration error.

## Recommended implementation order

1. Update `src/backup_agent/app/config.py`
2. Update `src/backup_agent/app/main.py`
3. Adjust logging in `src/backup_agent/infrastructure/logging.py`
4. Only if needed, make minimal supporting changes in `src/backup_agent/services/scheduler.py`
5. Update tests:
   - `tests/test_config_and_scheduler.py`
   - `tests/test_bootstrap.py`
   - any additional focused test file if that keeps changes cleaner
6. Update documentation that now contains outdated defaults:
   - `README.md`
   - optionally `docker-compose.yml` comments if they still communicate the old default staging path or mandatory `BACKUP_TIME`
7. Write the completion note:
   - `.pi/done/14-immediate-run-default-staging-and-timezone-fallback.md`

## Design intent

### 1. `BACKUP_TIME` should become optional

Recommended approach:

- change `AppConfig.backup_time` from `time` to `time | None`
- if `BACKUP_TIME` is missing or empty, return `None` from parsing instead of adding a config error
- if `BACKUP_TIME` is non-empty but invalid, keep raising a config error

This preserves fail-fast behavior for bad explicit config while allowing deployments to omit the variable entirely.

### 2. Immediate-run behavior belongs at the entrypoint level

Recommended approach:

- keep `DailyScheduler` focused on the scheduled case
- branch in `run_scheduler(...)` before constructing `DailyScheduler`
- if `effective_config.backup_time is None`:
  - log that immediate mode is being used
  - call `run_once(effective_config, orchestrator)` exactly once
  - return its exit code

Do not introduce a fake schedule time or a repeating loop when `BACKUP_TIME` is missing.

### 3. New default staging path

Update the config default and env fallback from `/backup` to `/temporary_storage`.

Touch all places that encode the old default as behavior rather than as historical documentation.

### 4. Timezone fallback precedence

Use the following precedence during config loading:

1. explicit `TZ` in the provided mapping
2. process environment `os.environ["TZ"]` if present
3. `UTC`

Important caveat:

- when `AppConfig.from_env(env=...)` is called with a custom mapping that does not contain `TZ`, it should still be able to inherit from the real process environment
- tests should prove this explicitly with `patch.dict("os.environ", ...)`

## Concrete code expectations

### `src/backup_agent/app/config.py`

Expected changes:

- make `backup_time` optional in the dataclass
- update `_parse_backup_time(...)`
- change the fallback default for `LOCAL_BACKUP_DIR`
- update timezone resolution logic so it can consult both the supplied mapping and `os.environ`

Likely shape:

- `backup_time: time | None = None`
- `_parse_backup_time("", errors) -> None`
- `local_backup_dir = Path(source.get("LOCAL_BACKUP_DIR", "/temporary_storage").strip() or "/temporary_storage")`
- resolve `TZ` via a small helper or inline precedence logic

### `src/backup_agent/app/main.py`

Expected changes:

- branch inside `run_scheduler(...)`
- preserve current scheduler behavior when `backup_time` is configured
- keep `main(...)` semantics unchanged otherwise

### `src/backup_agent/infrastructure/logging.py`

Expected changes:

- `log_config_validation(...)` currently assumes `backup_time.strftime(...)`
- update it so `None` is logged clearly, for example as `"immediate"`

### `src/backup_agent/services/scheduler.py`

Prefer no functional change unless typing or guardrails require a small cleanup.

The scheduler should still require a real `time` value in normal scheduled mode.

## Test matrix

Minimum expected tests:

1. Config without `BACKUP_TIME` validates successfully
2. Invalid explicit `BACKUP_TIME` still fails
3. Missing `LOCAL_BACKUP_DIR` falls back to `/temporary_storage`
4. `TZ` falls back to process env when not present in the supplied mapping
5. `TZ` falls back to `UTC` when missing everywhere
6. `run_once(...)` still works with config created without `BACKUP_TIME`
7. `run_scheduler(...)` with no `BACKUP_TIME` executes one immediate run and returns
8. Existing `DailyScheduler` tests for configured times still pass unchanged

## Acceptance checklist for the coder session

- [ ] Missing `BACKUP_TIME` is no longer a config error
- [ ] Invalid explicit `BACKUP_TIME` is still a config error
- [ ] Default `LOCAL_BACKUP_DIR` is `/temporary_storage`
- [ ] `TZ` can be inherited from process env when omitted from the provided mapping
- [ ] `--schedule` with no `BACKUP_TIME` performs one immediate run and exits successfully
- [ ] Existing scheduled behavior still works when `BACKUP_TIME` is set
- [ ] Documentation reflects the new defaults and semantics
- [ ] Full test suite passes with `python -m unittest discover -s tests`

## Notes for minimal-change execution

- Avoid broad renames or scheduler redesign.
- Do not change backup orchestration behavior beyond the startup trigger semantics.
- Keep the implementation localized to config, entrypoint, logging, tests, and docs.
