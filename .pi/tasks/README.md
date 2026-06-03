# Backup Agent Task Breakdown

This directory contains implementation tasks for coder agents.

## Recommended execution order

1. `01-project-bootstrap.md`
2. `02-config-and-scheduler.md`
3. `03-docker-discovery-and-metadata-resolution.md`
4. `04-database-backup-providers.md`
5. `05-local-staging-and-manifest.md`
6. `06-rsync-sync-and-retention.md`
7. `07-health-logging-and-run-summary.md`
8. `08-containerization-and-example-deployment.md`

## Notes

- Tasks are designed for a modular monolith implementation.
- Prefer minimal, localized changes.
- Preserve the architecture described in `.pi/architecture.md`.
- If implementation details require a stack decision, make the smallest reasonable choice and document it in the task result.
