# Task 18: Console Error Reporting for Export and Upload Failures

## Goal
Make the application print the actual failure reason to the console when a database export fails or when backup publication/upload fails.

## User request this task must satisfy

- If database export fails, the reason must be printed to the console.
- If upload / publish fails, the reason must be printed to the console.

## Background

The current runtime already collects structured errors in `BackupRun.errors`, but the console output is still too summary-oriented in failure cases.

At the moment, operators can see that a run failed or was partial, but they may not see the concrete reason directly in the console output without inspecting deeper internal state or artifacts.

This task should make operational failures easier to diagnose from standard application logs alone.

## Scope

- Surface database export failure reasons in normal console logging.
- Surface storage publish / upload failure reasons in normal console logging.
- Keep the output secret-safe.
- Reuse existing structured logging conventions where possible.
- Add or update tests for failure logging behavior.

## Required behavior

### Database export failure

If a PostgreSQL or MariaDB backup provider fails, console output should include at least:

- failure source
- human-readable reason / message
- target container name when available
- database name when available

When useful and safe, stderr may also be included in a sanitized form.

### Upload / publish failure

If local-storage publish or rsync / NAS upload fails, console output should include at least:

- failure source
- human-readable reason / message
- run ID when available
- destination context when available

### Secret safety

Failure logging must not expose passwords or other sensitive values.

## Deliverables

- Runtime logging changes that print actionable failure reasons to the console.
- Tests covering:
  - database export failure logging
  - upload / publish failure logging
  - secret masking in failure output
- A completion note under:
  - `.pi/done/18-console-error-reporting-for-export-and-upload-failures.md`

## Constraints

- Keep implementation localized.
- Do not redesign the full logging system.
- Do not weaken existing secret masking behavior.
- Prefer using already-collected structured error data from `BackupRun.errors` rather than inventing a second error model.
- Avoid duplicating the same failure message excessively if a single concise log event is enough.

## Acceptance criteria

- When a DB export fails, the console output clearly states the reason.
- When upload / publish fails, the console output clearly states the reason.
- Console output remains secret-safe.
- Existing success-path logging remains concise.
- Tests pass with:

```bash
python -m unittest discover -s tests
```

## Suggested implementation notes

- The smallest change may be in the runtime / orchestration logging path:
  - emit one structured log event per run error after `run_once()` completes, or
  - emit targeted failure events at the point the orchestrator records the error
- Likely candidates:
  - `src/backup_agent/services/orchestrator.py`
  - `src/backup_agent/app/main.py`
  - `src/backup_agent/infrastructure/logging.py`
- Prefer stable event names such as:
  - `run_error`
  - `provider_error`
  - `publish_error`

## Likely files to inspect

- `src/backup_agent/app/main.py`
- `src/backup_agent/services/orchestrator.py`
- `src/backup_agent/infrastructure/logging.py`
- `src/backup_agent/domain/backup_run.py`
- `tests/test_health_and_orchestrator.py`
- `tests/test_database_backup_providers.py`
- any runtime logging tests already covering secret masking

## Suggested verification

- Add focused tests for export and publish failure logging first.
- Then run the full suite:

```bash
python -m unittest discover -s tests
```
