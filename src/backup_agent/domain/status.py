"""Standardized status values used across runs and operational results."""

from __future__ import annotations

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_SYNC_FAILED = "sync_failed"

RUN_TERMINAL_STATUSES = {
    STATUS_SUCCESS,
    STATUS_PARTIAL,
    STATUS_FAILED,
    STATUS_SYNC_FAILED,
}
