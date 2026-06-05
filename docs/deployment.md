# Deployment Guide

This guide documents the supported deployment shape for Backup Agent.

Backup Agent is primarily intended to be deployed as a Docker image acting as a Docker operator for database backups. In practice, that means one long-running container watches the local Docker engine through `/var/run/docker.sock`, selects only explicitly labeled database containers, and executes scheduled backup runs without requiring a separate sidecar inside each database container.

## Runtime assumptions

The primary supported runtime model is:

- Backup Agent runs as one containerized operator
- it has access to the Docker socket
- it shares network reachability with the target database containers
- it discovers targets dynamically from Docker metadata
- it publishes successful runs to local storage, rsync, or both

## Docker image

The provided image includes:

- Python runtime
- `pg_dump`
- `pg_dumpall`
- `mariadb-dump`
- `rsync`

The image uses the PostgreSQL APT repository so the PostgreSQL client remains compatible with newer PostgreSQL versions.

The image declares a writable staging volume at:

```text
/.temporary_storage
```

## Required mounts

Typical container mounts:

```text
/var/run/docker.sock:/var/run/docker.sock
/.temporary_storage:/.temporary_storage
```

Optional additional mount:

```text
/storage:/storage
```

when using mounted local storage publishing.

## Recommended deployment patterns

### Pattern 1: long-running Docker operator container

This is the main intended production usage.

```bash
docker run -d \
  --name backup-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -v /srv/backup-agent-storage:/storage \
  -e LOG_LEVEL=info \
  -e TZ=UTC \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e LOCAL_BACKUP_DIR=/.temporary_storage \
  -e BACKUP_LOCAL_STORAGE=/storage \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  backup-agent:local --schedule
```

### Pattern 2: Docker operator with rsync publishing

```bash
docker run -d \
  --name backup-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e TZ=UTC \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e LOCAL_BACKUP_DIR=/.temporary_storage \
  -e DOCKER_SOCKET_PATH=/var/run/docker.sock \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  -e RSYNC_REMOTE_PATH=/backups \
  backup-agent:local --schedule
```

### Pattern 3: Docker Compose operator

The repository currently contains a commented example in `docker-compose.yml`.

A representative service definition looks like this:

```yaml
backup-agent:
  build:
    context: .
    dockerfile: Dockerfile
  image: backup-agent:local
  command: ["--schedule"]
  restart: unless-stopped
  environment:
    LOG_LEVEL: ${LOG_LEVEL:-info}
    TZ: ${TZ:-UTC}
    BACKUP_TIME: ${BACKUP_TIME:-21:11}
    BACKUP_RETENTION_DAYS: ${BACKUP_RETENTION_DAYS:-7}
    LOCAL_BACKUP_DIR: /.temporary_storage
    BACKUP_LOCAL_STORAGE: /storage
    DOCKER_SOCKET_PATH: /var/run/docker.sock
    RSYNC_REMOTE_HOST: ${RSYNC_REMOTE_HOST}
    RSYNC_REMOTE_USER: ${RSYNC_REMOTE_USER}
    RSYNC_REMOTE_PASSWORD: ${RSYNC_REMOTE_PASSWORD}
    RSYNC_REMOTE_PATH: ${RSYNC_REMOTE_PATH:-/backups}
  volumes:
    - ./storage:/storage
    - backup-data:/.temporary_storage
    - /var/run/docker.sock:/var/run/docker.sock
```

## Why this behaves like a Docker operator

Backup Agent behaves operationally like a Docker operator because it:

- watches the local Docker engine instead of using static host lists
- targets only containers that declare backup intent through labels
- resolves connection metadata directly from the container definition
- can execute dump tools inside the target container through Docker exec when configured to do so
- runs independently from the database application lifecycle

## Database containers

Target containers must:

- be running
- be visible through the Docker socket
- have `backup_agent.enabled=true`
- expose sufficient metadata via labels or container environment variables

### PostgreSQL example

```yaml
postgres:
  image: postgres:16
  environment:
    POSTGRES_USER: app
    POSTGRES_PASSWORD: secret
    POSTGRES_DB: appdb
  labels:
    backup_agent.enabled: "true"
    backup_agent.type: "postgresql"
    backup_agent.pguser: app
    backup_agent.pghost: postgres
    backup_agent.pgpassword: secret
    backup_agent.pgport: "5432"
    backup_agent.pgdatabase: appdb
```

### MariaDB example

```yaml
mariadb:
  image: mariadb:11.4
  environment:
    MARIADB_USER: app
    MARIADB_PASSWORD: secret
    MARIADB_DATABASE: appdb
  labels:
    backup_agent.enabled: "true"
    backup_agent.type: "mariadb"
    backup_agent.mariadbuser: app
    backup_agent.mariadbpassword: secret
    backup_agent.mariadbhost: mariadb
    backup_agent.mariadbport: "3306"
    backup_agent.mariadbdatabase: appdb
```

## Rsync server example used in this repository

The repository includes an example rsync server service in `docker-compose.yml`:

- auth user from `RSYNC_USER`
- auth password from `RSYNC_PASSWORD`
- daemon module from `RSYNC_MODULE`
- filesystem path from `RSYNC_PATH`

Example values from the repository example:

```text
RSYNC_USER=backup
RSYNC_PASSWORD=super-secret-password
RSYNC_MODULE=backup
RSYNC_PATH=/srv/backup
```

## Deployment modes

### Rsync only

Use when the authoritative backup copy should live on a remote rsync server.

### Mounted local storage only

Use when a persistent host path or mounted storage location is the authoritative destination.

### Combined local + rsync

Use when you want a local published copy and an rsync copy in the same run.

## Permissions and runtime notes

- The image runs as root.
- This simplifies Docker socket access.
- It also allows the default staging directory `/.temporary_storage` to be created and used without extra UID/GID mapping.

## Recommended production checklist

- mount the Docker socket explicitly
- mount `/.temporary_storage` if you want persistent or inspectable staging
- set `BACKUP_TIME`
- set `BACKUP_RETENTION_DAYS`
- configure at least one storage backend
- verify labeled database containers are reachable
- validate rsync credentials before relying on scheduled runs
