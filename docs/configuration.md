# Configuration Reference

Backup Agent loads configuration from environment variables.

## Required variables

### `BACKUP_TIME`

Daily backup time in `HH:MM` 24-hour format.

Example:

```bash
export BACKUP_TIME=02:00
```

Notes:

- required
- invalid values fail fast
- example valid values: `00:30`, `02:00`, `23:59`

### `BACKUP_RETENTION_DAYS`

Number of days to retain completed backups.

Example:

```bash
export BACKUP_RETENTION_DAYS=7
```

Notes:

- required
- must be an integer
- must be `>= 1`

## Storage backend configuration

At least one storage backend must be configured.

### Mounted local storage

#### `BACKUP_LOCAL_STORAGE`

If set, successful runs are copied into the mounted directory.

Example:

```bash
export BACKUP_LOCAL_STORAGE=/mnt/backups
```

Resulting layout:

```text
/mnt/backups/
├── latest
└── runs/
    └── <run-id>/
```

Constraint:

- `BACKUP_LOCAL_STORAGE` must differ from `LOCAL_BACKUP_DIR`

### Rsync remote storage

#### `RSYNC_REMOTE_HOST`

Hostname or IP address of the rsync server.

#### `RSYNC_REMOTE_USER`

Rsync auth user.

#### `RSYNC_REMOTE_PASSWORD`

Rsync auth password.

#### `RSYNC_REMOTE_PATH`

Rsync daemon module name or remote module/path suffix used by the rsync provider.

Default:

```text
/backups
```

Notes:

- rsync configuration is considered incomplete unless host, user, and password are all present
- the provider uses `rsync://` destinations and strips any leading `/` from this value before building the remote URL
- the rsync destination is the configured `remote_root` with the run ID appended directly; completed run directories are not nested under an additional `runs/` prefix in the remote URL
- prefer a module name such as `backup` or `backups`, not a filesystem path like `/backup`
- the remote rsync module/path must already exist on the server

### FTP / FTPS storage

#### `FTP_HOST`

Hostname or IP address of the FTP or FTPS server.

#### `FTP_PORT`

FTP port number.

Default:

```text
21
```

#### `FTP_USER`

Login user name.

#### `FTP_PASSWORD`

Login password.

#### `FTP_REMOTE_PATH`

Remote root directory where runs are stored.

Default:

```text
/backups
```

#### `FTP_TLS`

Enable explicit FTPS using `ftplib.FTP_TLS`.

Default:

```text
false
```

Notes:

- explicit FTPS is used rather than implicit FTPS
- when enabled, the provider connects, logs in, and protects the data channel with `prot_p()`

#### `FTP_PASSIVE`

Enable passive mode for FTP data transfers.

Default:

```text
true
```

#### `FTP_TIMEOUT`

Connection timeout in seconds.

Default:

```text
30
```

Notes:

- `FTP_HOST`, `FTP_USER`, and `FTP_PASSWORD` must all be set together
- FTP configuration is treated as incomplete if only part of that credential set is provided
- FTP retention and publishing use the remote destination directly and maintain a `latest` marker under the configured remote root

## Optional variables

### `LOCAL_BACKUP_DIR`

Local staging root used while a run is in progress.

Default:

```text
/.temporary_storage
```

Notes:

- this directory is created if needed
- staged run directories are removed after a fully successful publish
- if the publish step fails, staged files remain available for inspection

### `TZ`

Timezone name used by the scheduler.

Default:

```text
UTC
```

Example:

```bash
export TZ=Europe/Prague
```

### `LOG_LEVEL`

Application log level.

Default:

```text
INFO
```

### `DOCKER_SOCKET_PATH`

Path to the Docker Unix socket.

Default:

```text
/var/run/docker.sock
```

## Effective storage modes

Depending on the configured variables, the application runs in one of these modes.

### rsync only

```bash
export RSYNC_REMOTE_HOST=nas.local
export RSYNC_REMOTE_USER=backup
export RSYNC_REMOTE_PASSWORD=secret
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
```

### FTP / FTPS only

```bash
export FTP_HOST=ftp.example
export FTP_USER=backup
export FTP_PASSWORD=secret
export FTP_TLS=true
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
```

### mounted local storage only

```bash
export BACKUP_LOCAL_STORAGE=/mnt/backups
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
```

### rsync + FTP / FTPS

```bash
export RSYNC_REMOTE_HOST=nas.local
export RSYNC_REMOTE_USER=backup
export RSYNC_REMOTE_PASSWORD=secret
export FTP_HOST=ftp.example
export FTP_USER=backup
export FTP_PASSWORD=secret
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
```

### local + FTP / FTPS

```bash
export BACKUP_LOCAL_STORAGE=/mnt/backups
export FTP_HOST=ftp.example
export FTP_USER=backup
export FTP_PASSWORD=secret
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
```

## Validation rules

Configuration validation fails when:

- `BACKUP_TIME` is missing or invalid
- `BACKUP_RETENTION_DAYS` is missing, not numeric, or less than `1`
- rsync host/user/password are only partially configured
- FTP host/user/password are only partially configured
- both `BACKUP_LOCAL_STORAGE` and `LOCAL_BACKUP_DIR` point to the same directory
- no storage backend is configured
- `LOCAL_BACKUP_DIR` or `BACKUP_LOCAL_STORAGE` is not writable
- `TZ` is not a valid timezone name

## Example complete configuration

```bash
export BACKUP_TIME=02:00
export BACKUP_RETENTION_DAYS=7
export LOCAL_BACKUP_DIR=/.temporary_storage
export BACKUP_LOCAL_STORAGE=/mnt/backups
export RSYNC_REMOTE_HOST=nas.local
export RSYNC_REMOTE_USER=backup
export RSYNC_REMOTE_PASSWORD=change-me
export RSYNC_REMOTE_PATH=/backups
export DOCKER_SOCKET_PATH=/var/run/docker.sock
export TZ=Europe/Prague
export LOG_LEVEL=INFO
```
