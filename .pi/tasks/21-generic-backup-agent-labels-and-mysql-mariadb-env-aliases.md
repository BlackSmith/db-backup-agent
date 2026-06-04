# Task 21: Generic `backup_agent.*` Labels and MySQL/MariaDB Environment Alias Support

## Goal
Simplify metadata labeling so database-specific field names are removed from `backup_agent.*` labels, while database type is inferred primarily from target-container environment variables.

At the same time, extend MariaDB/MySQL metadata support so the application accepts both:

- `MARIADB_*`
- `MYSQL_*`

families of environment variables.

## User-requested behavior

- Rename database-specific `backup_agent.*` labels so they no longer encode the database engine in the key name.
- Example intent:
  - `backup_agent.pgpassword` -> `backup_agent.password`
  - `backup_agent.mariadbpassword` -> `backup_agent.password`
- Infer database type from the target container environment:
  - `POSTGRES_*` => PostgreSQL
  - `MARIADB_*` or `MYSQL_*` => MySQL-family target handled by the MariaDB provider path
- Update the application so it accepts both `MYSQL_*` and `MARIADB_*` environment variables.

## Motivation

The current metadata model uses engine-specific label keys such as:

- `backup_agent.pguser`
- `backup_agent.mariadbuser`

This makes the label surface larger and duplicates the same logical fields across database engines.

A generic label model:

- reduces label complexity
- makes deployment examples easier to read
- separates engine inference from shared credential/connection field names
- allows MySQL-compatible images using `MYSQL_*` envs to work without MariaDB-specific renaming

## Scope

- Introduce generic `backup_agent.*` labels for shared metadata fields.
- Update metadata resolution so engine inference can rely on env-variable families:
  - `POSTGRES_*`
  - `MARIADB_*`
  - `MYSQL_*`
- Update MariaDB/MySQL metadata resolution so both `MARIADB_*` and `MYSQL_*` env aliases are accepted.
- Update tests and documentation accordingly.

## Proposed generic label model

Recommended generic labels:

- `backup_agent.enabled`
- `backup_agent.type` (optional explicit override; still useful for ambiguity resolution)
- `backup_agent.user`
- `backup_agent.password`
- `backup_agent.host`
- `backup_agent.port`
- `backup_agent.database`
- `backup_agent.dump_method` (already planned in Task 20)

Notes:

- `backup_agent.type` may remain as an explicit override because it does not encode the engine in the key name and is still useful when inference is ambiguous.
- `backup_agent.database` may represent a comma-separated list, consistent with the current `parse_database_list(...)` behavior.

## Engine inference rules

Recommended precedence:

1. explicit `backup_agent.type` if present
2. infer from target-container env-variable family
3. fail with a metadata-resolution error if the container remains ambiguous

### PostgreSQL inference

If the target env contains PostgreSQL-shaped variables such as:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_DATABASE`

then resolve the target as PostgreSQL.

### MySQL/MariaDB inference

If the target env contains MySQL/MariaDB-shaped variables such as:

- `MARIADB_USER`
- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `MARIADB_HOST`
- `MARIADB_PORT`
- `MARIADB_DATABASE`

or:

- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DATABASE`

then resolve the target as MySQL-family and route it through the existing MariaDB provider path.

## Backward compatibility recommendation

To avoid breaking existing deployments abruptly, this task should preferably introduce a migration window:

- generic labels become the preferred and documented form
- legacy engine-specific labels remain accepted temporarily
- tests should prove precedence and compatibility rules clearly

Recommended precedence during migration:

1. new generic `backup_agent.*` labels
2. legacy engine-specific `backup_agent.pg*` / `backup_agent.mariadb*` labels
3. target container env variables
4. default port fallback where already implemented

If the coder session concludes that supporting both old and new labels materially complicates the change, it should document that trade-off before removing compatibility.

## MariaDB/MySQL env alias behavior

For the MariaDB provider path, support both families:

- `MARIADB_*`
- `MYSQL_*`

Recommended mapping examples:

- user:
  - `MARIADB_USER` or `MYSQL_USER`
- password:
  - `MARIADB_PASSWORD` or `MYSQL_PASSWORD`
- root password fallback:
  - `MARIADB_ROOT_PASSWORD` or `MYSQL_ROOT_PASSWORD`
- host:
  - `MARIADB_HOST` or `MYSQL_HOST`
- port:
  - `MARIADB_PORT` or `MYSQL_PORT`
- database:
  - `MARIADB_DATABASE` or `MYSQL_DATABASE`

## Constraints

- Keep the implementation localized primarily to metadata resolution and documentation.
- Do not redesign provider execution.
- Preserve default port fallback behavior from Task 17.
- Preserve explicit invalid-port validation.
- Preserve secret-safe logging and error handling.
- Keep discovery behavior unchanged.

## Acceptance criteria

- Generic labels such as `backup_agent.user`, `backup_agent.password`, `backup_agent.host`, `backup_agent.port`, and `backup_agent.database` are supported.
- Database type can be inferred from `POSTGRES_*` vs `MARIADB_*` / `MYSQL_*` env families.
- MariaDB/MySQL metadata resolution accepts both `MARIADB_*` and `MYSQL_*` env variables.
- Existing ambiguity handling still works.
- Default port fallback behavior still works.
- Tests cover generic labels, env-family inference, and MySQL alias support.
- Full suite passes:

```bash
python -m unittest discover -s tests
```

## Likely files to inspect

- `src/backup_agent/services/metadata_resolver.py`
- `src/backup_agent/domain/backup_target.py`
- `tests/test_docker_discovery_and_metadata_resolution.py`
- `README.md`
- `docker-compose.yml` comments/examples if they document old label names

## Suggested verification

- Focused metadata resolver tests first
- Then the full suite
- If possible, validate against one PostgreSQL-style container and one MySQL/MariaDB-style container using the new generic labels
