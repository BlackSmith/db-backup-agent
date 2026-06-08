# Task 24 Config Notes: FTP / FTPS Environment Model

## Purpose
This note defines a concrete configuration model for adding FTP / FTPS storage support in a way that matches the repository’s current validation style.

## Recommended environment variables

### Required when FTP / FTPS backend is enabled
- `FTP_HOST`
- `FTP_USER`
- `FTP_PASSWORD`

### Optional with defaults
- `FTP_PORT`
- `FTP_REMOTE_PATH`
- `FTP_TLS`
- `FTP_PASSIVE`
- `FTP_TIMEOUT`

## Recommended `AppConfig` fields
Suggested additions to `AppConfig`:

```python
ftp_host: str = ""
ftp_port: int = 21
ftp_user: str = ""
ftp_password: str = ""
ftp_remote_path: str = "/backups"
ftp_tls: bool = False
ftp_passive: bool = True
ftp_timeout: float = 30.0
```

## Recommended derived properties
Suggested additional config property:

```python
@property
def has_ftp_storage(self) -> bool:
    return bool(self.ftp_host and self.ftp_user and self.ftp_password)
```

Recommended update to `enabled_storage_backends` order:
- local first
- rsync second
- ftp third

This preserves the current durable-local-first preference while keeping remote transports explicit.

Example result:
- local only -> `("local",)`
- ftp only -> `("ftp",)`
- local + ftp -> `("local", "ftp")`
- rsync + ftp -> `("rsync", "ftp")`

## Validation rules

### 1. Incomplete FTP config should fail fast
If any FTP credential field is present but the required set is incomplete, raise a config error.

Required-set rule:
- all or nothing for:
  - `FTP_HOST`
  - `FTP_USER`
  - `FTP_PASSWORD`

Recommended error shape:
- `FTP_* configuration is incomplete; missing: ...`

### 2. `FTP_PORT`
Recommended parsing:
- default: `21`
- must parse as integer
- must be in `1..65535`

Recommended invalid cases:
- non-integer
- `<= 0`
- `> 65535`

### 3. `FTP_REMOTE_PATH`
Recommended default:
- `/backups`

Recommended normalization:
- trim whitespace
- ensure non-empty after trimming
- keep it as a logical remote root string
- normalize duplicate trailing slashes in provider code, not necessarily in config

### 4. `FTP_TLS`
Recommended accepted values:
- `true`, `false`
- optionally also accept `1`, `0`, `yes`, `no`, `on`, `off` if that matches current config style decisions

Recommended default:
- `false`

### 5. `FTP_PASSIVE`
Recommended accepted values:
- same parser behavior as `FTP_TLS`

Recommended default:
- `true`

### 6. `FTP_TIMEOUT`
Recommended default:
- `30`

Recommended parsing:
- float or integer accepted
- must be `> 0`

If keeping parsing minimal is preferred, integer-only is acceptable, but document the choice.

## Storage backend selection rule
Update the global storage validation rule so that at least one of the following backend families is configured:
- `BACKUP_LOCAL_STORAGE`
- complete `RSYNC_*`
- complete `FTP_*`

Recommended updated error message:
- `At least one storage backend must be configured via BACKUP_LOCAL_STORAGE, complete RSYNC_* settings, or complete FTP_* settings`

## Logging / masking note
FTP passwords must be treated as secrets in the same way as rsync passwords.

Recommended masking fields:
- `ftp_password`
- `FTP_PASSWORD`

## Documentation recommendations
Update the operator docs with:
- FTP configuration reference
- FTPS explanation as explicit TLS
- default port behavior
- passive mode note
- retention behavior summary

## Suggested focused config tests
Add tests for:
- ftp-only valid config
- ftps enabled config
- incomplete FTP config rejection
- invalid `FTP_PORT`
- invalid `FTP_TIMEOUT`
- backend selection string containing `ftp`
- coexistence of local + ftp and rsync + ftp
