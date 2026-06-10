# Coder Handoff for Task 27

## Objective
Make `backup_agent.type` a required explicit selector and allow it to contain multiple values so a single container can request multiple backup flows in the same run.

## Primary target
Refactor the metadata resolution path so it no longer relies on implicit type inference or default type selection.

Before implementation, read:
- `.pi/tasks/27-backup-agent-type-required-multi-value-selection.md`
- `.pi/tasks/25-container-directory-archive-backups.md`
- `.pi/tasks/26-fix-combined-database-and-directory-backup-behavior.md`
- `.pi/context.md`
- `.pi/architecture.md`

## Recommended implementation order
1. Inspect the current type-resolution and target-expansion path.
2. Require `backup_agent.type` during metadata resolution for enabled containers.
3. Parse the label as a comma-separated list of requested target kinds.
4. Normalize and validate the selected values.
5. Update orchestrator / target expansion so multiple requested kinds can run in one backup cycle.
6. Make sure filesystem/archive selection only happens when `filesystem` is explicitly listed and directories are present.
7. Add regression tests for missing type, single type, and multi-type combinations.
8. Update docs/examples to show the explicit type requirement.
9. Run focused tests and then the full suite.
10. Write `.pi/done/27-backup-agent-type-required-multi-value-selection.md`.

## Expected behavior
Given a container with `backup_agent.enabled=true`:
- `backup_agent.type` must always be present
- a missing or blank type is invalid metadata
- one value should work for a single backup mode
- multiple values should be allowed when they are compatible
- a combined case such as `postgresql,filesystem` should produce both flows in the same run
- filesystem/archive backups should not be inferred from `backup_agent.directories` alone anymore
- conflicting engine combinations should fail clearly

## Constraints
- Keep changes localized.
- Preserve existing provider implementations unless the type-selection contract requires a small wiring change.
- Do not reintroduce implicit engine inference as a fallback.
- Do not broaden the scope into a full metadata model redesign.
- Update user-facing docs and tests so the new contract is obvious.

## Acceptance checklist
- [ ] `backup_agent.type` is mandatory
- [ ] no default type is inferred when the label is missing
- [ ] the label supports multiple comma-separated values
- [ ] combined backup flows can be selected explicitly
- [ ] filesystem/archive selection requires explicit `filesystem`
- [ ] invalid or conflicting type combinations are rejected clearly
- [ ] focused tests pass
- [ ] full suite passes

## Suggested verification
```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_health_and_orchestrator tests.test_database_backup_providers
python -m unittest discover -s tests
```

## Design caveat
This is a contract-breaking change for deployments that currently rely on implicit type inference. Keep the implementation small, but make the new explicit contract consistent across resolver behavior, orchestration, docs, and tests.