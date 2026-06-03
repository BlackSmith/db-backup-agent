"""Domain model describing one discovered backup target."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BackupTarget:
    container_id: str
    container_name: str
    db_type: str
    host: str
    port: int
    user: str | None = None
    password_ref: str | None = None
    databases: list[str] = field(default_factory=list)
    all_databases: bool = False
    labels: dict[str, str] = field(default_factory=dict)
