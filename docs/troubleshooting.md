# Troubleshooting

This guide lists common failure modes and how to diagnose them.

## Configuration errors at startup

### Symptom

The process exits immediately with configuration validation errors.

### Common causes

- `BACKUP_TIME` missing
- `BACKUP_RETENTION_DAYS` missing or invalid
- no storage backend configured
- partial rsync configuration
- invalid `TZ`
- `LOCAL_BACKUP_DIR` or `BACKUP_LOCAL_STORAGE` not writable

### What to check

- all required environment variables are set
- rsync host/user/password are either all set or all omitted
- `LOCAL_BACKUP_DIR` and `BACKUP_LOCAL_STORAGE` are different paths
- the staging path is writable

## No containers discovered

### Symptom

The run finishes with no eligible targets.

### What to check

- the container is running
- `backup_agent.enabled=true` is present
- the Docker socket path is correct
- the process has permission to access the Docker socket

## Metadata resolution failures

### Symptom

A container is enabled but still not backed up.

### Common causes

- missing `backup_agent.type` and no inferrable database metadata
- conflicting PostgreSQL and MariaDB metadata in the same container
- missing user/host/password metadata
- invalid explicit port value

### What to check

- labels on the container
- container environment variables
- whether generic labels conflict with legacy labels

## PostgreSQL dump-format errors

### Symptom

PostgreSQL backup fails before artifact creation.

### Common causes

- invalid `backup_agent.dump_format`
- `all_databases=True` combined with `binary` or `both`

### What to check

- `backup_agent.dump_format`
- whether the target resolves to `all_databases=True`

## Remote exec failures

### Symptom

Provider logs show `remote ... failed`.

### What to check

- Docker socket is reachable
- the target container exists and is running
- the target container contains the necessary database client binary for exec mode
- `backup_agent.dump_method=exec` is only used when remote exec is expected to work

### Notes

- `auto` tries remote exec first and falls back to local execution
- `exec` does not fall back
- `local` never attempts remote exec

## Rsync publish failures

### Symptom

The run ends with `sync_failed` or a `run_error` from source `sync`.

### What to check

- `RSYNC_REMOTE_HOST`, `RSYNC_REMOTE_USER`, and `RSYNC_REMOTE_PASSWORD`
- network reachability to the rsync server
- `RSYNC_REMOTE_PATH`
- rsync daemon/module permissions on the remote side

### Notes

- the rsync provider uses a temporary password file
- sync commands use `--mkpath` to create missing destination path components
- if rsync publish fails, the staging run directory is intentionally preserved

## Local mounted storage publish failures

### Symptom

Local publish fails even though artifacts were created.

### What to check

- `BACKUP_LOCAL_STORAGE` exists and is writable
- `BACKUP_LOCAL_STORAGE` is not the same as `LOCAL_BACKUP_DIR`
- there is enough space on the mounted destination

## Docker API health failures

### Symptom

Readiness reports Docker API unavailable.

### What to check

- `/var/run/docker.sock` is mounted
- `DOCKER_SOCKET_PATH` matches the real socket path
- the process user can access the socket

## Staging cleanup expectations

### Symptom

You expected local staging files to remain after a run, but they disappeared.

### Explanation

That is expected after a fully successful publish.

Staging is removed only after:

- backup succeeded
- publish succeeded
- retention did not leave blocking errors

If publish fails, staging remains available for debugging.

## Useful verification commands

### Run one cycle

```bash
backup-agent --run-once
```

### Run tests

```bash
python -m unittest discover -s tests
```

### Inspect logs

Look for events such as:

- `config_validated`
- `run_start`
- `discovery_complete`
- `target_backup_finish`
- `sync_finish`
- `retention_finish`
- `run_summary`
- `run_error`
