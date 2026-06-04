# Coder Handoff for Task 21

## Objective
Implement support for generic `backup_agent.*` labels that no longer encode the database engine in the key name, and extend metadata resolution so the application accepts both `MARIADB_*` and `MYSQL_*` environment variables for MySQL-family targets.

## Primary target

Refactor metadata resolution and related tests/documentation with minimal impact outside that boundary.

## Recommended implementation order

1. Update `src/backup_agent/services/metadata_resolver.py`
2. Add or adjust any small domain support only if needed
3. Update resolver tests in `tests/test_docker_discovery_and_metadata_resolution.py`
4. Update docs/examples that still advertise the old engine-specific label names
5. Run focused resolver tests and then the full suite
6. Write `.pi/done/21-generic-backup-agent-labels-and-mysql-mariadb-env-aliases.md`

## Expected behavior

### New generic labels

Support generic labels such as:

- `backup_agent.user`
- `backup_agent.password`
- `backup_agent.host`
- `backup_agent.port`
- `backup_agent.database`

Keep supporting:

- `backup_agent.enabled`
- `backup_agent.type` as an optional explicit override

### Engine inference

Resolve engine type using this order:

1. `backup_agent.type` if present
2. env-family inference:
   - `POSTGRES_*` => PostgreSQL
   - `MARIADB_*` or `MYSQL_*` => MariaDB/MySQL path
3. fail if still ambiguous

### MySQL-family env aliases

For the MariaDB provider path, accept both:

- `MARIADB_*`
- `MYSQL_*`

Examples:

- user from `MARIADB_USER` or `MYSQL_USER`
- password from `MARIADB_PASSWORD` or `MYSQL_PASSWORD`
- root password fallback from `MARIADB_ROOT_PASSWORD` or `MYSQL_ROOT_PASSWORD`
- host from `MARIADB_HOST` or `MYSQL_HOST`
- port from `MARIADB_PORT` or `MYSQL_PORT`
- database from `MARIADB_DATABASE` or `MYSQL_DATABASE`

## Backward compatibility guidance

Prefer a migration-friendly implementation:

- new generic labels should be preferred
- legacy labels should still be accepted for now if possible

Recommended precedence:

1. generic labels
2. legacy engine-specific labels
3. env variables
4. default port fallback

If you find that backward compatibility adds disproportionate complexity, stop and document the trade-off before removing old-label support.

## Constraints

- Keep changes localized to metadata resolution, tests, and docs/examples.
- Do not redesign providers or orchestrator behavior.
- Preserve explicit invalid-port failures.
- Preserve Task 17 default-port behavior.
- Preserve secret-safe behavior.

## Acceptance checklist

- [ ] Generic `backup_agent.*` labels are supported
- [ ] `POSTGRES_*` envs infer PostgreSQL
- [ ] `MARIADB_*` envs infer MariaDB/MySQL-family
- [ ] `MYSQL_*` envs infer MariaDB/MySQL-family
- [ ] MariaDB/MySQL-family metadata resolution accepts both env families
- [ ] Ambiguity handling still works
- [ ] Default port fallback still works
- [ ] Focused tests and full suite pass

## Suggested verification

```bash
python -m unittest tests.test_docker_discovery_and_metadata_resolution
python -m unittest discover -s tests
```

## Design caveat

This task changes the metadata contract seen by deployments. Favor a migration path that keeps old labels working while switching docs/examples to the new generic form.
