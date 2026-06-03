# Task 05: Local Staging and Manifest

## Goal
Implement local run directories, artifact placement rules, and manifest generation.

## Scope
- Create a per-run directory structure under the configured local backup root
- Support atomic or safe artifact writing where practical
- Generate a `manifest.json` describing each run
- Optionally maintain a `latest` symlink or equivalent pointer

## Required directory model
A structure equivalent to:

```text
/backup/
  runs/
    <run-id>/
      manifest.json
      postgresql/
        <container-name>/
      mariadb/
        <container-name>/
```

## Deliverables
- Run directory creation logic
- Artifact naming strategy
- Manifest writer
- Domain model or DTO for manifest content

## Required manifest fields
- run ID
- start time
- end time
- final status
- processed targets
- produced artifacts
- error list

## Constraints
- Each run must be isolated in its own directory
- Manifest output must not contain secrets
- File layout must be deterministic and easy to inspect manually

## Acceptance criteria
- A new run creates a unique run directory
- Provider outputs can be stored under the expected DB/container hierarchy
- `manifest.json` is produced for success, partial, and failed runs where applicable
- Artifact metadata includes enough data for debugging and restore planning

## Suggested notes for implementer
- Keep the manifest extensible for future checksum support
- Prefer stable, machine-readable status values
