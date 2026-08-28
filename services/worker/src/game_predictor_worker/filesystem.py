"""Internal filesystem helpers shared by worker artifact writers."""

from __future__ import annotations

import os
from pathlib import Path


def long_path_aware(path: Path) -> Path:
    """Return an absolute path that bypasses legacy ``MAX_PATH`` on Windows."""

    resolved = path.resolve()
    if os.name != "nt":
        return resolved
    value = str(resolved)
    if value.startswith("\\\\?\\"):
        return resolved
    if value.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{value[2:]}")
    return Path(f"\\\\?\\{value}")


__all__ = ["long_path_aware"]
