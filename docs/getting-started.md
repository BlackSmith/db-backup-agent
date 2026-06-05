# Getting Started

This guide shows the minimum setup required to run Backup Agent.

The primary and recommended way to use Backup Agent is as a Docker image that acts like a small Docker operator for database backups. It is expected to run continuously as a container, inspect the local Docker engine through `/var/run/docker.sock`, and back up only containers that opt in through labels.

## What the agent does

For each run, Backup Agent:

1. reads configuration from environment variables
2. connects to the Docker socket
3. finds running containers labeled with `backup_agent.enabled=true`
4. resolves database connection metadata from labels or container environment variables
5. creates database dump artifacts in the local staging directory
6. writes `manifest.json` for the run
7. publishes the run to configured storage backends
8. applies retention cleanup
9. removes the temporary staging tree after a fully successful publish

## Minimum requirements

For the recommended Docker operator deployment, you need:

- a Docker host
- access to `/var/run/docker.sock`
- network reachability from the Backup Agent container to the database containers
- at least one configured storage backend
- labeled PostgreSQL and/or MariaDB containers

## Recommended usage: run as Docker image

### Build the image

```bash
docker build -t backup-agent:local .
```

### Run as a scheduled Docker operator

```bash
docker run -d \
  --name backup-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --schedule
```

### Run a single verification cycle

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --run-once
```

## Alternative usage: local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Minimum configuration

Set either local mounted storage or rsync storage.

### Option A: mounted local storage

```bash
export BACKUP_LOCAL_STORAGE=/mnt/backups
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
export DOCKER_SOCKET_PATH=/var/run/docker.sock
```

### Option B: rsync storage

```bash
export RSYNC_REMOTE_HOST=nas.local
export RSYNC_REMOTE_USER=backup
export RSYNC_REMOTE_PASSWORD=change-me
export RSYNC_REMOTE_PATH=/backups
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
export DOCKER_SOCKET_PATH=/var/run/docker.sock
```

### Optional staging override

If `LOCAL_BACKUP_DIR` is not set, the default staging root is:

```text
/.temporary_storage
```

To override it:

```bash
export LOCAL_BACKUP_DIR=/some/other/path
```

## First run

For the main Docker-based usage, run one backup cycle with:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --run-once
```

For local Python execution, the equivalent command is:

```bash
backup-agent --run-once
```

or:

```bash
python -m backup_agent --run-once
```

## Scheduler mode

Recommended production mode is the long-running containerized operator:

```bash
docker run -d \
  --name backup-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --schedule
```

For local non-container execution, scheduler mode is still available:

```bash
backup-agent --schedule
```

## Expected local staging layout

During a run, the local staging tree looks like this:

```text
/.temporary_storage/
├── latest
└── runs/
    └── <run-id>/
        ├── manifest.json
        ├── postgresql/
        └── mariadb/
```

## What a successful run means

A successful run means:

- at least one eligible target was discovered
- at least one artifact was created
- publish to the configured storage backend(s) succeeded
- retention completed without blocking errors

If the publish step succeeds completely, the temporary local run tree is removed from the staging directory.

## Exit codes

Current CLI behavior:

- `0` on successful CLI execution
- `2` on invalid configuration

Run failures are reported through structured logs and run summaries.
