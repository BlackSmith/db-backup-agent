"""Filesystem helper utilities."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def safe_name(value: str, default: str = "item") -> str:
    """Create a filesystem-safe, human-readable name."""

    cleaned = [char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip()]
    result = "".join(cleaned).strip("-")
    return result or default


def write_text_atomic(path: str | Path, content: str) -> Path:
    """Write text atomically by replacing a temporary file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=target.parent, encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    os.replace(temp_path, target)
    return target
