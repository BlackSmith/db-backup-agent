# Coder Handoff for Task 20

## Objective
Implement a database dump execution strategy that supports both PostgreSQL and MariaDB with:

- explicit per-container label-based method selection
- `auto` mode by default: remote container exec first, local fallback second
- `exec` mode: remote exec only
- `local` mode: current local behavior only
- streaming remote dump output into the local staging artifact file
- opportunistic remote gzip when available

## Primary target

Add database dump execution strategy support for both currently supported engines without redesigning the whole backup architecture.

## Recommended implementation order

1. Extend Docker exec support in `src/backup_agent/infrastructure/docker.py`
2. Add any minimal domain/metadata support needed to carry the shared dump method label
3. Refactor `src/backup_agent/providers/databases/postgresql.py` to support strategy selection and exec/local fallback
4. Refactor `src/backup_agent/providers/databases/mariadb.py` to support the same strategy model
5. Add tests for:
   - label-based method selection
   - default `auto` behavior
   - exec failure followed by local fallback
   - exec-only failure behavior
   - local-only behavior
   - cleanup of failed partial artifact files
   - gzip path behavior if implemented
   - coverage for both PostgreSQL and MariaDB
6. Run the full suite
7. Write `.pi/done/20-database-remote-exec-with-label-selected-strategy.md`

## Label behavior

Support a shared dump method label:

- `backup_agent.dump_method=auto|exec|local`

Expected semantics:

- missing label => `auto`
- `auto` => try remote exec, then local fallback if exec fails
- `exec` => remote exec only, no silent local fallback
- `local` => current local path only

## Implementation guidance

### Docker exec support

The current Docker API client only supports list/inspect/ping. Extend it minimally to support database exec use cases.

Needed capabilities:

- create exec command in a target container
- start the exec command
- capture stdout/stderr
- obtain exit status

### Provider changes

Keep the provider interfaces stable if possible.

A good shape is:

- resolve method from labels
- for each backup command, attempt exec/local based on method
- on exec failure in `auto`, record enough context and fall back to local
- if both fail, return a provider error that explains the sequence

Apply the same policy model to:

- PostgreSQL
- MariaDB

### Artifact handling

- stream stdout to the intended local artifact path
- remove incomplete files on exec failure before fallback or final failure
- keep manifest format metadata accurate

### Compression

Treat remote gzip as best-effort and optional.

Recommended approach:

- if the exec path uses a shell pipeline, first check whether that remains acceptably safe and testable
- if not, keep the initial implementation simple and document gzip follow-up behavior clearly
- do not make remote gzip mandatory for success

## Constraints

- Keep changes localized.
- Preserve secret masking and current error reporting discipline.
- Keep local backup behavior available for both engines.
- Avoid unrelated orchestrator or scheduler changes.

## Acceptance checklist

- [ ] PostgreSQL and MariaDB targets support `backup_agent.dump_method`
- [ ] Missing label defaults to `auto`
- [ ] `auto` tries exec first and falls back to local on failure
- [ ] `exec` does not silently fall back
- [ ] `local` preserves current local execution behavior
- [ ] Remote exec writes artifact output into local staging
- [ ] Failed exec attempts clean up incomplete files
- [ ] Tests cover selection and fallback behavior for both engines
- [ ] Full suite passes with `python -m unittest discover -s tests`

## Suggested verification

```bash
python -m unittest tests.test_database_backup_providers
python -m unittest tests.test_docker_discovery_and_metadata_resolution
python -m unittest discover -s tests
```

If possible, also validate against real PostgreSQL and MariaDB containers, confirming that `auto` succeeds via exec when remote tools are available.
