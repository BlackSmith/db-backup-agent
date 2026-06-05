# Backup Agent

Backup Agent is a containerized backup service for PostgreSQL and MariaDB workloads. Its primary usage model is as a Docker image acting as a lightweight Docker operator: it discovers labeled database containers through the Docker API, creates local run directories, synchronizes completed backups to remote storage via rsync or mounted local storage, and applies retention afterward.

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
docs/
```

## User documentation

Full user documentation is available in `docs/`:

- Start here for the main Docker operator deployment model: `docs/deployment.md`


- `docs/README.md`
- `docs/getting-started.md`
- `docs/configuration.md`
- `docs/discovery-and-labels.md`
- `docs/operations.md`
- `docs/deployment.md`
- `docs/troubleshooting.md`

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

Required variables for any run:

- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`

Storage variables are optional individually and can be combined:

- `BACKUP_LOCAL_STORAGE`
- `RSYNC_REMOTE_HOST`
- `RSYNC_REMOTE_USER`
- `RSYNC_REMOTE_PASSWORD`
- `RSYNC_REMOTE_PATH`

Other optional variables:

- `LOCAL_BACKUP_DIR`
- `TZ`
- `LOG_LEVEL`
- `DOCKER_SOCKET_PATH`

See `.pi/project.md` and `.pi/architecture.md` for the full design context.

## Containerized deployment

### Runtime image

The provided `Dockerfile` builds a production-oriented image on top of `python:3.13-slim-bookworm` and installs the tools required by the backup providers.

For PostgreSQL, the image uses the PostgreSQL APT repository so it can install a newer packaged `postgresql-client` than Debian bookworm provides by default. That keeps `pg_dump` / `pg_dumpall` compatible with newer PostgreSQL servers such as PostgreSQL 17.

Installed tools include:

- `pg_dump`
- `pg_dumpall`
- `mariadb-dump`
- `rsync`

Trade-off: the image runs as root so it can access the mounted Docker socket without extra host-specific UID/GID coordination.

### Required mounts and runtime access

The container needs:

- `/var/run/docker.sock:/var/run/docker.sock` for container discovery
- `/.temporary_storage:/.temporary_storage` as a writable local staging volume
- network access to the database containers on the same Docker network

### Runtime environment variables in containers

Agent runtime variables:

- `BACKUP_LOCAL_STORAGE` (optional; mounted local storage backend)
- `RSYNC_REMOTE_HOST` (optional unless you want NAS upload)
- `RSYNC_REMOTE_USER` (optional unless you want NAS upload)
- `RSYNC_REMOTE_PASSWORD` (optional unless you want NAS upload)
- `BACKUP_TIME`
- `BACKUP_RETENTION_DAYS`
- `RSYNC_REMOTE_PATH` (optional)
- `LOCAL_BACKUP_DIR=/.temporary_storage`
- `TZ` (optional)
- `LOG_LEVEL` (optional)
- `DOCKER_SOCKET_PATH=/var/run/docker.sock`

You can configure mounted local storage, rsync upload, or both. If `BACKUP_LOCAL_STORAGE` is set, the rsync credentials are not required unless you also want NAS publishing.

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

Note: the runtime image now sources PostgreSQL client packages from the PostgreSQL APT repository to avoid the version skew caused by Debian bookworm's older default `postgresql-client` package.

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

### Optional mounted local storage mode

If you mount a persistent directory directly into the backup-agent container, you can store completed runs there without rsync:

```bash
export BACKUP_LOCAL_STORAGE=/mnt/backups
```

In that mode, the agent copies completed runs into the mounted path and keeps the same run-directory layout under `runs/`.

## GitHub Actions CI and release

The repository includes GitHub Actions workflows for continuous integration and releases.

### CI workflow

- Triggers on pull requests and pushes to `main` / `master`
- Runs `python -m unittest discover -s tests`
- Builds the Docker image
- On branch pushes, publishes a `nightly` image to GHCR

The nightly image is published as:

```text
ghcr.io/<owner>/<repo>:nightly
```

The workflow normalizes the GHCR repository name to lowercase before publishing, which avoids Docker tag errors when the GitHub repository contains uppercase letters.

### Release workflow

- Triggers on tag pushes matching `v*` such as `v0.1.0`
- Runs the test suite
- Builds and pushes the Docker image to GitHub Container Registry (GHCR)
- Creates a GitHub Release for the tag

### Published image name

The release workflow publishes the image to:

```text
ghcr.io/<owner>/<repo>:<tag>
```

For example, a `v0.1.0` tag produces an image such as:

```text
ghcr.io/<owner>/<repo>:v0.1.0
```

The workflow also publishes `latest` for version tags.

## Notes

- The backup agent discovers only containers labeled with `backup_agent.enabled=true`.
- PostgreSQL and MariaDB metadata is resolved from labels first, then environment variables.
- Local backups are written under `/.temporary_storage/runs/<run-id>/`.
- The example deployment is intentionally minimal but reflects the architecture assumptions used by the application.
