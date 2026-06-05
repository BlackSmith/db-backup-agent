# Backup Agent Documentation

This directory contains the full user documentation for Backup Agent.

Backup Agent is intended primarily to run as a Docker image acting as a lightweight Docker operator for database backups. It watches the local Docker engine through the mounted Docker socket, discovers labeled PostgreSQL and MariaDB containers, creates local staging artifacts, publishes successful runs to one or more storage backends, and applies retention cleanup.

## Documentation map

- [Getting started](./getting-started.md)
- [Configuration reference](./configuration.md)
- [Container discovery and labels](./discovery-and-labels.md)
- [Operations and run lifecycle](./operations.md)
- [Deployment guide](./deployment.md)
- [Troubleshooting](./troubleshooting.md)

## Quick start

The primary deployment model is:

1. run Backup Agent as a container
2. mount `/var/run/docker.sock` into that container
3. attach it to the same Docker network as the target databases
4. label target database containers with `backup_agent.enabled=true`
5. provide storage backend configuration
6. run the agent in `--schedule` mode

Minimal example:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --schedule
```

For one immediate verification run, use:

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /.temporary_storage:/.temporary_storage \
  -e BACKUP_TIME=02:00 \
  -e BACKUP_RETENTION_DAYS=7 \
  -e RSYNC_REMOTE_HOST=nas.local \
  -e RSYNC_REMOTE_USER=backup \
  -e RSYNC_REMOTE_PASSWORD=change-me \
  backup-agent:local --run-once
```

The default local staging root is:

```text
/.temporary_storage
```

Successful runs produce artifacts under:

```text
/.temporary_storage/runs/<run-id>/
```

unless staging cleanup removes them after durable publication.

## Supported databases

- PostgreSQL
- MariaDB / MySQL-family metadata routed through the MariaDB backup path

## Supported storage backends

- rsync daemon-style remote storage
- mounted local directory publishing
- both backends together

## Canonical user docs

`docs/` is the canonical user documentation set for this project. When runtime behavior changes, these documents should be updated together with `README.md`.
