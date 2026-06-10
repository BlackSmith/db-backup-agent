# Task 27: Require explicit `backup_agent.type` and allow multi-value selection

## Goal
Change metadata resolution so `backup_agent.type` becomes a required selector for every backup-enabled container, with no implicit default.

The label must also support multiple values so a single container can explicitly request more than one backup mode in the same run.

## Problem statement
The current metadata model treats `backup_agent.type` as an optional override and still allows implicit type inference from other labels or environment variables.

That behavior is no longer desired for future deployments because it can hide configuration mistakes and makes the selected backup modes less explicit.

The new contract should be:
- `backup_agent.type` is always required on `backup_agent.enabled=true` containers
- there is no default value
- the label may contain more than one value
- each requested value must be resolved explicitly

## Scope
- update metadata resolution so `backup_agent.type` is mandatory
- support comma-separated multi-value type selection
- validate and normalize the selected values
- update target expansion / orchestrator wiring if needed so multiple requested types can run in the same backup run
- update tests for missing-type, single-type, and multi-type cases
- update operator-facing docs and examples to show the explicit type requirement

## Out of scope
- redesigning the database providers themselves
- changing archive format behavior
- changing storage backend retention logic
- introducing new backup engines beyond the currently supported ones
- broad refactors unrelated to type selection and target expansion

## Proposed type semantics
Use `backup_agent.type` as a comma-separated list, for example:

- `backup_agent.type=postgresql`
- `backup_agent.type=mariadb`
- `backup_agent.type=filesystem`
- `backup_agent.type=postgresql,filesystem`
- `backup_agent.type=mariadb,filesystem`

Recommended semantics:
- trim whitespace around values
- ignore empty entries
- deduplicate repeated values
- normalize aliases to canonical values if compatibility is kept
- reject unknown values with a clear validation error

### Compatibility rules
- do **not** synthesize a type from labels or environment variables when `backup_agent.type` is absent
- do **not** keep the current default/inference behavior
- if a type list mixes incompatible database engines in one container, treat it as invalid metadata
- filesystem archive backups should only run when `filesystem` is explicitly listed and `backup_agent.directories` is present

## Intended behavior
For a container with database metadata and directory paths:

```text
backup_agent.enabled=true
backup_agent.type=postgresql,filesystem
backup_agent.user=app
backup_agent.password=secret
backup_agent.host=postgres
backup_agent.port=5432
backup_agent.database=appdb
backup_agent.directories=/app/data,/var/lib/app/uploads
```

one run should produce:
- the PostgreSQL artifact(s) through the PostgreSQL provider
- one filesystem/archive artifact through the filesystem provider

For a container with only database metadata:
- a single explicit database type should work as before

For a container with only `backup_agent.directories` and no type:
- the container should be rejected as invalid metadata

## Recommended implementation focus
Inspect these areas first:
- metadata resolution and normalization
- target expansion logic for multi-value `backup_agent.type`
- provider selection for database vs filesystem/archive targets
- manifest / run summary output if target counts change
- docs and tests that currently describe `backup_agent.type` as optional

## Acceptance criteria
- `backup_agent.type` is required for every enabled target container
- missing or blank `backup_agent.type` produces a clear validation error
- `backup_agent.type` can contain multiple values
- multiple values can produce multiple backup flows in the same run
- filesystem/archive backups still work when `filesystem` is explicitly listed and directories are provided
- database-only containers still work with an explicit single database type
- invalid or conflicting multi-value combinations are rejected clearly
- focused tests pass
- full suite passes

## Suggested verification
```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution tests.test_health_and_orchestrator tests.test_database_backup_providers
python -m unittest discover -s tests
```

## Design caveat
This is a metadata-contract change, not just a parser tweak. Keep the implementation localized, but make sure the new explicit-type contract is reflected consistently in resolver behavior, orchestration, tests, and documentation.