# Backup Agent

Backup Agent is a containerized backup service for PostgreSQL and MariaDB workloads. It discovers labeled database containers through the Docker API, creates local run directories, synchronizes completed backups to remote storage via rsync, and applies retention afterward.

## Current status

The project now contains:

- a Python application entrypoint
- validated environment-based configuration
- an internal daily scheduler
- Docker discovery and metadata resolution
- PostgreSQL and MariaDB backup providers
- local staging and manifest generation
- rsync sync and retention
- structured logging and health checks
- containerization and example deployment files

## Project structure

```text
src/
  backup_agent/
    app/
    domain/
    services/
    providers/
    infrastructure/
    interfaces/
```

## Local development

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install the package in editable mode

```bash
python -m pip install -e .
```

### 3. Run the application once

```bash
backup-agent --run-once
```

### 4. Run the scheduler loop

```bash
backup-agent --schedule
```

## Test execution

Run the test suite with:

```bash
python -m unittest discover -s tests
```

## Configuration

Configuration is loaded from environment variables.

Required variables:

- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`

Optional variables:

- `RSYNC_REMOTE_PATH`
- `LOCAL_BACKUP_DIR`
- `TZ`
- `LOG_LEVEL`
- `DOCKER_SOCKET_PATH`

See `.pi/project.md` and `.pi/architecture.md` for the full design context.

## Containerized deployment

### Runtime image

The provided `Dockerfile` builds a production-oriented image on top of `python:3.13-slim-bookworm` and installs the tools required by the backup providers:

- `pg_dump`
- `pg_dumpall`
- `mariadb-dump`
- `rsync`

Trade-off: the image runs as root so it can access the mounted Docker socket without extra host-specific UID/GID coordination.

### Required mounts and runtime access

The container needs:

- `/var/run/docker.sock:/var/run/docker.sock` for container discovery
- `/backup:/backup` as a writable local staging volume
- network access to the database containers on the same Docker network

### Required environment variables in containers

Agent runtime variables:

- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`
- `RSYNC_REMOTE_PATH` (optional)
- `LOCAL_BACKUP_DIR=/backup`
- `TZ` (optional)
- `LOG_LEVEL` (optional)
- `DOCKER_SOCKET_PATH=/var/run/docker.sock`

### Build the image

```bash
docker build -t backup-agent:local .
```

### Run the example deployment

The repository includes `docker-compose.yml` with:

- one `backup-agent` container
- one PostgreSQL example container
- one MariaDB example container
- shared Docker network access
- mounted Docker socket
- persistent backup volume

Start it with:

```bash
docker compose up -d --build
```

The compose file expects secrets and remote storage settings to come from your environment or a local `.env` file; it does not hardcode passwords.

### Example environment values

Set values like these before starting the compose stack:

```bash
export RSYNC_REMOTE_HOST=nas.local
export RSYNC_REMOTE_USER=backup
export RSYNC_REMOTE_PASSWORD=change-me
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
export POSTGRES_PASSWORD=change-me
export MARIADB_ROOT_PASSWORD=change-me
export MARIADB_PASSWORD=change-me
```

## Notes

- The backup agent discovers only containers labeled with `backup_agent.enabled=true`.
- PostgreSQL and MariaDB metadata is resolved from labels first, then environment variables.
- Local backups are written under `/backup/runs/<run-id>/`.
- The example deployment is intentionally minimal but reflects the architecture assumptions used by the application.
