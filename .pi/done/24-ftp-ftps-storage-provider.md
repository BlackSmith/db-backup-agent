# Task 24 - FTP / FTPS Storage Provider and Retention Support: implementation record

## Implemented

- Added a new FTP / FTPS storage backend using the Python standard library `ftplib`.
- Supported both plain FTP and explicit FTPS via `ftplib.FTP_TLS`.
- Added configuration parsing for `FTP_*` environment variables:
  - `FTP_HOST`
  - `FTP_PORT`
  - `FTP_USER`
  - `FTP_PASSWORD`
  - `FTP_REMOTE_PATH`
  - `FTP_TLS`
  - `FTP_PASSIVE`
  - `FTP_TIMEOUT`
- Enforced fail-fast validation for incomplete FTP credential configuration.
- Added FTP / FTPS provider selection to storage backend factory composition.
- Preserved existing local mounted storage and rsync behavior.
- Implemented FTP / FTPS publish to `<FTP_REMOTE_PATH>/runs/<run-id>/` and remote `latest` marker maintenance.
- Implemented remote-state-driven FTP / FTPS retention cleanup that inventories remote runs, keeps ambiguous runs, deletes only expired remote run directories, and refreshes `latest`.
- Updated logging sanitization to treat `FTP_PASSWORD` as a secret field.
- Updated operator documentation for FTP / FTPS configuration, deployment, operations, and troubleshooting.
- Added focused tests for config parsing, storage selection, and the FTP / FTPS provider.

## Changed files

- `src/backup_agent/app/config.py`
- `src/backup_agent/infrastructure/logging.py`
- `src/backup_agent/providers/storage/ftp.py`
- `src/backup_agent/providers/storage/factory.py`
- `src/backup_agent/providers/storage/__init__.py`
- `tests/test_config_and_scheduler.py`
- `tests/test_storage_backend_selection.py`
- `tests/test_ftp_ftps_storage_provider.py`
- `tests/test_local_mounted_storage_provider.py`
- `docs/configuration.md`
- `docs/operations.md`
- `docs/README.md`
- `docs/deployment.md`
- `docs/troubleshooting.md`
- `.pi/done/24-ftp-ftps-storage-provider.md`

## Verification

- Ran focused tests successfully:
  - `python -m unittest tests.test_config_and_scheduler tests.test_storage_backend_selection tests.test_ftp_ftps_storage_provider tests.test_local_mounted_storage_provider`
- Ran the full test suite successfully:
  - `python -m unittest discover -s tests`

## Notes

- FTP / FTPS retention is intentionally conservative: unreadable or ambiguous remote runs are retained rather than deleted.
- The provider uses explicit FTPS rather than implicit FTPS.
- FTP / FTPS and rsync can be enabled together through the existing composite storage provider.
