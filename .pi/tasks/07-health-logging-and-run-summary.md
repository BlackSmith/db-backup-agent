# Task 07: Health, Logging, and Run Summary

## Goal
Add operational visibility: structured logs, health checks, and final run summary handling.

## Scope
- Introduce structured logging across the main workflow
- Add liveness and readiness checks
- Ensure the orchestrator emits a clear final summary per run
- Standardize status values across success and failure paths

## Deliverables
- Logging utility or configured logger
- Liveness check
- Readiness check
- Run summary output integrated with orchestrator results

## Minimum logging events
- application start
- configuration validation result
- run start
- discovered container count
- per-target backup start/finish
- sync start/finish
- retention start/finish
- run summary

## Constraints
- Never log passwords or secret material
- Logs must remain useful for manual troubleshooting
- Health checks should not trigger backup side effects

## Acceptance criteria
- Logs are emitted for the main run lifecycle
- Readiness fails when configuration or required dependencies are unavailable
- Liveness indicates the process is alive
- Final run status is clearly represented as one of:
  - `success`
  - `partial`
  - `failed`
  - `sync_failed`

## Suggested notes for implementer
- Keep health checks minimal and deterministic
- Use the same status vocabulary in logs and manifest data
