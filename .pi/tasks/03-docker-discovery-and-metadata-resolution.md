# Task 03: Docker Discovery and Metadata Resolution

## Goal
Implement discovery of eligible containers and resolve normalized backup targets from labels and environment variables.

## Scope
- Connect to Docker via mounted socket / Docker API
- List running containers
- Filter containers by `backup_agent.enabled=true`
- Resolve database metadata from labels first, then environment variables
- Normalize targets into a common domain model

## Required label support
### Common
- `backup_agent.enabled=true`
- optionally support `backup_agent.type`

### PostgreSQL
- `backup_agent.pguser`
- `backup_agent.pghost`
- `backup_agent.pgpassword`
- `backup_agent.pgport`
- `backup_agent.pgdatabase`

### MariaDB
- `backup_agent.mariadbuser`
- `backup_agent.mariadbpassword`
- `backup_agent.mariadbhost`
- `backup_agent.mariadbport`
- `backup_agent.mariadbdatabase`

## Required env fallback support
### PostgreSQL
- `POSTGRES_USER`
- `POSTGRES_HOST`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `POSTGRES_DB` or `POSTGRES_DATABASE`

### MariaDB
- `MARIADB_USER`
- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `MARIADB_HOST`
- `MARIADB_PORT`
- `MARIADB_DATABASE`

## Deliverables
- Docker discovery service
- Metadata resolver service
- `BackupTarget` domain model
- Parsing of comma-separated database lists
- Support for "all databases" when database list is empty or missing

## Constraints
- Never log secrets
- Discovery must happen fresh for each run
- Keep database-specific inference isolated from the orchestrator

## Acceptance criteria
- Only labeled containers are selected
- Label values override env values
- PostgreSQL and MariaDB targets are normalized into one shared model
- Missing database list is represented as `allDatabases=true`
- Resolution failures are explicit and traceable without exposing passwords

## Suggested notes for implementer
- If database type inference is ambiguous, fail clearly or require `backup_agent.type`
