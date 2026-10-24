"""Versioned pattern identities without changing either historical legacy identity."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_search_pattern(request: Mapping[str, Any]) -> Any:
    if request.get("version") != 2:
        return request.get("cells")
    patterns = request.get("patterns")
    if not isinstance(patterns, list) or not 2 <= len(patterns) <= 4:
        raise ValueError("Invalid version 2 search pattern.")
    normalized = []
    for pattern in patterns:
        if not isinstance(pattern, dict) or not isinstance(pattern.get("cells"), list):
            raise ValueError("Invalid version 2 search cells.")
        cells = pattern["cells"]
        if not all(isinstance(cell, str) and ":" in cell for cell in cells):
            raise ValueError("Invalid version 2 search cell.")
        normalized.append({"cells": sorted(cells, key=lambda cell: int(cell.split(":", 1)[0]))})
    return {"version": 2, "patterns": normalized}


def search_pattern_key(request: Mapping[str, Any]) -> str:
    return json.dumps(canonical_search_pattern(request), ensure_ascii=False)


def search_pattern_fingerprint(request: Mapping[str, Any]) -> str:
    value = canonical_search_pattern(request)
    if request.get("version") != 2:
        value = sorted(value or [])
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
