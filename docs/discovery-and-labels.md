# Container Discovery and Labels

Backup Agent only processes containers that explicitly opt in.

## Discovery model

The agent:

1. lists running containers through the Docker API
2. filters them to `backup_agent.enabled=true`
3. inspects each enabled container
4. resolves metadata from labels first, then from container environment variables

Only running containers are discovered.

## Opt-in label

Every backed-up container must include:

```text
backup_agent.enabled=true
```

Accepted truthy values for enablement are:

- `1`
- `true`
- `yes`
- `on`

## Database type selection

### Explicit type label

Recommended:

```text
backup_agent.type=postgresql
```

or

```text
backup_agent.type=mariadb
```

Accepted aliases:

- PostgreSQL: `postgresql`, `postgres`, `pg`
- MariaDB path: `mariadb`, `mysql`

If the explicit type is missing, the resolver tries to infer the database type from labels or environment variables.

If both PostgreSQL and MariaDB signals are present, resolution fails and the type must be set explicitly.

## Generic labels

Preferred generic labels:

- `backup_agent.user`
- `backup_agent.password`
- `backup_agent.host`
- `backup_agent.port`
- `backup_agent.database`

These generic labels override legacy engine-specific labels when both are present.

## PostgreSQL metadata

### Preferred labels

```text
backup_agent.enabled=true
backup_agent.type=postgresql
backup_agent.user=app
backup_agent.password=secret
backup_agent.host=postgres
backup_agent.port=5432
backup_agent.database=appdb
```

### Legacy PostgreSQL labels still accepted

- `backup_agent.pguser`
- `backup_agent.pgpassword`
- `backup_agent.pghost`
- `backup_agent.pgport`
- `backup_agent.pgdatabase`

### Environment fallback

If labels are not present, the resolver also reads:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_DATABASE`

### Multiple databases

Comma-separated lists are supported:

```text
backup_agent.database=db1,db2,db3
```

or via legacy PostgreSQL label:

```text
backup_agent.pgdatabase=db1,db2,db3
```

### All databases

If no database list is resolved, the target is treated as `all_databases=True`.

## MariaDB metadata

### Preferred labels

```text
backup_agent.enabled=true
backup_agent.type=mariadb
backup_agent.user=app
backup_agent.password=secret
backup_agent.host=mariadb
backup_agent.port=3306
backup_agent.database=appdb
```

### Legacy MariaDB labels still accepted

- `backup_agent.mariadbuser`
- `backup_agent.mariadbpassword`
- `backup_agent.mariadbhost`
- `backup_agent.mariadbport`
- `backup_agent.mariadbdatabase`

### Environment fallback

MariaDB-family environment variables supported:

- `MARIADB_USER`
- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `MARIADB_HOST`
- `MARIADB_PORT`
- `MARIADB_DATABASE`

MySQL-family aliases also supported:

- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DATABASE`

### Multiple databases

Comma-separated lists are supported through generic or legacy database labels.

### All databases

If no database list is resolved, the target is treated as `all_databases=True`.

## Port behavior

If the port is omitted:

- PostgreSQL defaults to `5432`
- MariaDB defaults to `3306`

Invalid explicit port values fail metadata resolution.

## Dump-method label

Both database providers support:

```text
backup_agent.dump_method=auto|exec|local
```

Behavior:

- `auto` = try Docker exec inside the target container first, then fall back to local execution
- `exec` = require Docker exec; no local fallback
- `local` = use local runtime tools only

If the label is missing or invalid, the effective behavior defaults to `auto`.

## PostgreSQL output-format label

PostgreSQL supports:

```text
backup_agent.dump_format=binary|sql_gzip|both
```

Behavior:

- missing label = `both`
- `binary` = custom-format dump (`.dump`)
- `sql_gzip` = gzip-compressed SQL (`.sql.gz`)
- `both` = both output variants

### PostgreSQL all-databases caveat

For PostgreSQL cluster-wide backups (`all_databases=True`):

- only `sql_gzip` is supported
- explicit `binary` or `both` returns an actionable provider error

This is because `pg_dumpall` does not produce a single PostgreSQL custom-format binary dump.

## Example labels

### PostgreSQL example

```yaml
labels:
  backup_agent.enabled: "true"
  backup_agent.type: "postgresql"
  backup_agent.user: "postgres"
  backup_agent.password: "${POSTGRES_PASSWORD}"
  backup_agent.host: "postgres"
  backup_agent.port: "5432"
  backup_agent.database: "appdb"
  backup_agent.dump_method: "auto"
  backup_agent.dump_format: "both"
```

### MariaDB example

```yaml
labels:
  backup_agent.enabled: "true"
  backup_agent.type: "mariadb"
  backup_agent.user: "app"
  backup_agent.password: "${MARIADB_PASSWORD}"
  backup_agent.host: "mariadb"
  backup_agent.port: "3306"
  backup_agent.database: "appdb"
  backup_agent.dump_method: "auto"
```
