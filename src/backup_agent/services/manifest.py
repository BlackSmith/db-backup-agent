"""Manifest writing boundary and JSON implementation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backup_agent.domain.manifest import RunManifest
from backup_agent.infrastructure.filesystem import ensure_directory, write_text_atomic


class ManifestWriter(ABC):
    """Abstract contract for writing run manifests."""

    @abstractmethod
    def write_run_manifest(self, run: RunManifest, output_dir: Path) -> Path:
        """Persist the manifest for a completed run."""
        raise NotImplementedError


class JsonManifestWriter(ManifestWriter):
    """Write the manifest as deterministic JSON."""

    def write_run_manifest(self, run: RunManifest, output_dir: Path) -> Path:
        ensure_directory(output_dir)
        manifest_path = output_dir / "manifest.json"
        payload = _manifest_payload(run)
        write_text_atomic(manifest_path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        return manifest_path


def _manifest_payload(run: RunManifest) -> dict[str, Any]:
    payload = asdict(run)
    payload["started_at"] = run.started_at.isoformat() if run.started_at else None
    payload["finished_at"] = run.finished_at.isoformat() if run.finished_at else None
    return payload
